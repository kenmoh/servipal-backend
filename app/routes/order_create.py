# routers/internal.py

from fastapi import APIRouter, Header, HTTPException, status, Depends
from pydantic import BaseModel
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

router = APIRouter(prefix="/internal", tags=["Internal"])


class ProcessPaymentRequest(BaseModel):
    tx_ref: str
    paid_amount: float
    flw_ref: str
    payment_method: str  # 'CARD' or 'WALLET'


HANDLER_MAP = {
    "FOOD-": process_successful_food_payment,
    "PRODUCT-": process_successful_product_payment,
    "LAUNDRY-": process_successful_laundry_payment,
    "DELIVERY-": process_successful_delivery_payment,
    "TOPUP-": process_successful_topup_payment,
}


@router.post("/process-payment", status_code=status.HTTP_200_OK)
async def process_payment(
    data: ProcessPaymentRequest,
    x_internal_key: str = Header(...),
    supabase: AsyncClient = Depends(get_supabase_client),
):
    # 1. Verify internal key — only Edge Function can call this
    if x_internal_key != settings.INTERNAL_API_KEY:
        logger.warning(
            "internal_endpoint_unauthorized",
            tx_ref=data.tx_ref,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )

    logger.info(
        "process_payment_received",
        tx_ref=data.tx_ref,
        payment_method=data.payment_method,
        paid_amount=data.paid_amount,
    )

    # 2. Find handler from tx_ref prefix
    handler = next(
        (h for prefix, h in HANDLER_MAP.items() if data.tx_ref.startswith(prefix)),
        None,
    )

    if not handler:
        logger.warning(
            "process_payment_unknown_prefix",
            tx_ref=data.tx_ref,
        )
        # Return 400 — Edge Function will dead letter this message
        # since retrying won't help (prefix will always be unknown)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown tx_ref prefix: {data.tx_ref}",
        )

    # 3. Run the handler
    try:
        await handler(
            tx_ref=data.tx_ref,
            paid_amount=data.paid_amount,
            flw_ref=data.flw_ref,
            payment_method=data.payment_method,
            supabase=supabase,
        )

        logger.info(
            "process_payment_success",
            tx_ref=data.tx_ref,
            handler=handler.__name__,
            payment_method=data.payment_method,
        )

        return {"status": "success", "tx_ref": data.tx_ref}

    except Exception as e:
        logger.error(
            "process_payment_failed",
            tx_ref=data.tx_ref,
            handler=handler.__name__,
            error=str(e),
            exc_info=True,
        )
        # Return 500 — Edge Function leaves message in queue for retry
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Something went wrong while processing the payment",
        )
