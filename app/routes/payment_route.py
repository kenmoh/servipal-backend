from fastapi import APIRouter, Request, HTTPException, Depends, status
from supabase import AsyncClient
from app.services.payment_service import (
    process_successful_delivery_payment,
    process_successful_food_payment,
    process_successful_topup_payment,
    process_successful_laundry_payment,
    process_successful_product_payment,
)
from app.config.config import settings
from app.config.logging import logger
from app.database.supabase import get_supabase_client
from app.worker import enqueue_job
from rq import Retry
from pydantic import BaseModel
import hmac


class PaymentWebhookResponse(BaseModel):
    status: str
    message: str | None = None
    trx_ref: str | None = None


router = APIRouter(tags=["payment-webhook"], prefix="/api/v1/payment")


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def flutterwave_webhook(
    request: Request,
    supabase: AsyncClient = Depends(get_supabase_client),
) -> PaymentWebhookResponse:
    """
    ** Handle Flutterwave payment webhooks. **

    - Verifies signature, checks idempotency, and queues processing in the background.

    - Args:
        - request (Request): The raw request.
        - verif_hash (str): The verification hash header.

    - Returns:
        - PaymentWebhookResponse: Processing status.
        - :param verif_hash:
        - :param request:
        - :param supabase:
    """
    # 1. Verify webhook signature (Flutterwave sends verif-hash header)

    secret_hash = settings.FLW_SECRET_HASH
    signature = request.headers.get("verif-hash")
    if not hmac.compare_digest(signature, secret_hash):
        logger.warning(
            event="webhook_signature_invalid",
            level="warning",
            client_ip=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature"
        )

    # 2. Parse payload
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(
            event="flutterwave_webhook_parse_error",
            error=str(e),
            client_ip=request.client.host if request.client else None,
        )
        return PaymentWebhookResponse(status="error", message="Invalid JSON payload")

    webhook_event = (
        payload.get("event") or payload.get("event.type") or payload.get("type")
    )

    data = payload.get("data") if payload.get("data") else payload

    flw_ref = data.get("flw_ref") or payload.get("flw_ref")
    logger.info(
        event="flutterwave_webhook_received",
        webhook_event=webhook_event,
        payment_status=data.get("status"),
        tx_ref=data.get("tx_ref"),
        amount=data.get("amount"),
        flw_ref=flw_ref,
    )

    # 3. Only process successful charge events
    # Flutterwave status for successful is usually 'successful'
    if data.get("status") != "successful":
        logger.debug(
            event="flutterwave_webhook_event_ignored",
            level="debug",
            status=data.get("status"),
        )
        return PaymentWebhookResponse(
            status="ignored",
            message=f"Payment status is {data.get('status')}, not successful",
        )

    tx_ref = data.get("tx_ref")
    paid_amount = data.get("amount")

    if not tx_ref:
        logger.warning(
            event="flutterwave_webhook_missing_tx_ref", level="warning", payload=payload
        )
        return PaymentWebhookResponse(status="error", message="Missing tx_ref")

    # 4. Idempotency check (prevent double-processing)
    # We use the raw supabase client here as it's available in the route
    existing = (
        await supabase.table("transactions").select("id").eq("tx_ref", tx_ref).execute()
    )

    if existing.data:
        logger.info(
            event="flutterwave_webhook_already_processed", level="info", tx_ref=tx_ref
        )
        return PaymentWebhookResponse(
            status="already_processed",
            message="Transaction already processed",
            trx_ref=tx_ref,
        )

    # 5. Determine which handler is based on the tx_ref prefix
    handler = None
    if tx_ref.startswith("DELIVERY-"):
        handler = process_successful_delivery_payment
    elif tx_ref.startswith("FOOD-"):
        handler = process_successful_food_payment
    elif tx_ref.startswith("TOPUP-"):
        handler = process_successful_topup_payment
    elif tx_ref.startswith("LAUNDRY-"):
        handler = process_successful_laundry_payment
    elif tx_ref.startswith("PRODUCT-"):
        handler = process_successful_product_payment

    if not handler:
        logger.warning(
            event="flutterwave_webhook_unknown_transaction_type",
            level="warning",
            tx_ref=tx_ref,
        )
        return PaymentWebhookResponse(status="unknown_transaction_type")

    # 6. Queue the job with retry (5 attempts, exponential backoff)
    job_id = enqueue_job(
        handler,
        tx_ref=str(tx_ref),
        payment_method='CARD',
        paid_amount=paid_amount,
        flw_ref=str(flw_ref),
        retry=Retry(max=5, interval=[30, 60, 120, 300, 600]),
    )

    logger.info(
        event=webhook_event,
        level="info",
        tx_ref=tx_ref,
        job_id=job_id,
        handler=handler.__name__,
    )
    return PaymentWebhookResponse(
        status="queued_with_retry", trx_ref=tx_ref, message="Payment processing queued"
    )
