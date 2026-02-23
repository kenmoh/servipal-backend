# routers/internal.py

from fastapi import APIRouter, Header, HTTPException, status, Depends
from typing import Optional, Any
from pydantic import BaseModel, Field
from supabase import AsyncClient
from app.database.supabase import get_supabase_client

from app.config.config import settings
from app.services.payment_service import (
    process_successful_delivery_payment,
    process_successful_food_payment,
    process_successful_topup_payment,
    process_successful_laundry_payment,
    process_successful_product_payment,
)
from app.config.logging import logger

router = APIRouter(prefix="/api/v1/internal", tags=["Internal"])

class PaymentMessage(BaseModel):
    tx_ref: str
    paid_amount: float
    flw_ref: str
    payment_method: str


class QueueRecord(BaseModel):
    msg_id: int
    read_ct: int
    enqueued_at: str
    vt: str
    message: PaymentMessage


class InsertPayload(BaseModel):
    type: str
    table: str
    schema: str = Field(None, alias="schema") 
    record: QueueRecord
    old_record: Optional[Any] = None

    model_config = {"populate_by_name": True}



HANDLER_MAP = {
    "FOOD-": process_successful_food_payment,
    "PRODUCT-": process_successful_product_payment,
    "LAUNDRY-": process_successful_laundry_payment,
    "DELIVERY-": process_successful_delivery_payment,
    "TOPUP-": process_successful_topup_payment,
}


@router.post("/process-payment", status_code=status.HTTP_200_OK)
async def process_payment(
    payload: InsertPayload,
    x_internal_key: str = Header(...),
    supabase: AsyncClient = Depends(get_supabase_client),
):

    logger.info('*'*100)
    logger.info(payload)
    logger.info('*'*100)
    # 1. Verify internal key
    if x_internal_key != settings.INTERNAL_API_KEY:
        logger.warning("internal_endpoint_unauthorized")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    # 2. Only process INSERT events
    if payload.type != "INSERT":
        return {"status": "ignored", "reason": f"Event type {payload.type} not handled"}

    # 3. Extract message directly from record
    data = payload.record.message
    tx_ref = data.tx_ref
    paid_amount = data.paid_amount
    flw_ref = data.flw_ref
    payment_method = data.payment_method

    logger.info(
        "process_payment_received",
        tx_ref=tx_ref,
        payment_method=payment_method,
        paid_amount=paid_amount,
        msg_id=payload.record.msg_id,
    )

    # 4. Find handler
    handler = next(
        (h for prefix, h in HANDLER_MAP.items() if tx_ref.startswith(prefix)),
        None,
    )

    if not handler:
        logger.warning("process_payment_unknown_prefix", tx_ref=tx_ref)
        # Return 200 — bad prefix won't fix itself, no point retrying
        return {"status": "ignored", "reason": f"Unknown tx_ref prefix: {tx_ref}"}

    # 5. Run handler
    try:
        await handler(
            tx_ref=tx_ref,
            paid_amount=paid_amount,
            flw_ref=flw_ref,
            payment_method=payment_method,
            supabase=supabase,
        )

        logger.info(
            "process_payment_success",
            tx_ref=tx_ref,
            handler=handler.__name__,
            payment_method=payment_method,
            msg_id=payload.record.msg_id,
        )

        return {"status": "success", "tx_ref": tx_ref}

    except Exception as e:
        logger.error(
            "process_payment_failed",
            tx_ref=tx_ref,
            handler=handler.__name__,
            error=str(e),
            exc_info=True,
        )
        # Return 500 — webhook will retry
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
    

@router.post("/retry-payments", status_code=status.HTTP_200_OK)
async def retry_payments(
    x_internal_key: str = Header(...),
    supabase: AsyncClient = Depends(get_supabase_client),
):
    if x_internal_key != settings.INTERNAL_API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    # Read messages with read_ct > 0 (previously attempted but failed)
    result = await supabase.schema("pgmq_public").rpc(
        "read",
        {
            "queue_name": "payment_queue",
            "vt": 60,
            "qty": 10,
        }
    ).execute()

    messages = result.data or []

    if not messages:
        return {"status": "empty"}

    for msg in messages:
        data = msg["message"]
        tx_ref = data["tx_ref"]

        # Dead letter — exceeded max retries
        if msg["read_ct"] > 5:
            logger.error(
                "payment_dead_letter",
                tx_ref=tx_ref,
                attempts=msg["read_ct"],
            )
            await supabase.schema("pgmq_public").rpc(
                "archive",
                {"queue_name": "payment_queue", "msg_id": msg["msg_id"]}
            ).execute()
            continue

        handler = next(
            (h for prefix, h in HANDLER_MAP.items() if tx_ref.startswith(prefix)),
            None,
        )

        if not handler:
            await supabase.schema("pgmq_public").rpc(
                "archive",
                {"queue_name": "payment_queue", "msg_id": msg["msg_id"]}
            ).execute()
            continue

        try:
            await handler(
                tx_ref=tx_ref,
                paid_amount=float(data["paid_amount"]),
                flw_ref=data["flw_ref"],
                payment_method=data["payment_method"],
                supabase=supabase,
            )
            await supabase.schema("pgmq_public").rpc(
                "archive",
                {"queue_name": "payment_queue", "msg_id": msg["msg_id"]}
            ).execute()
            logger.info("payment_retry_success", tx_ref=tx_ref)

        except Exception as e:
            logger.error("payment_retry_failed", tx_ref=tx_ref, error=str(e))

    return {"status": "done", "processed": len(messages)}
