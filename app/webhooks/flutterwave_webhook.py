from fastapi import Depends, HTTPException, Request, status
from pydantic import BaseModel
from supabase import AsyncClient

from app.config.config import settings
from app.config.logging import logger
from app.database.supabase import get_supabase_admin_client
from app.utils.webhook_validation import WebhookValidator


class PaymentWebhookResponse(BaseModel):
    status: str
    message: str | None = None
    tx_ref: str | None = None


async def handle_flutterwave_webhook(
    request: Request,
    supabase: AsyncClient = Depends(get_supabase_admin_client),
) -> PaymentWebhookResponse:
    """
    Handle Flutterwave payment webhooks.

    - Verifies signature using the dashboard secret hash (verif-hash).
    - Checks idempotency and queues processing in the background (pgmq).
    """
    secret_hash = settings.FLW_SECRET_HASH
    signature = request.headers.get("verif-hash") or request.headers.get("x-flutterwave-signature")

    is_valid = WebhookValidator.validate_flutterwave_signature(
        signature_header=signature or "",
        secret_hash=secret_hash or "",
    )

    if not is_valid:
        logger.warning(
            event="webhook_signature_invalid",
            level="warning",
            client_ip=request.client.host if request.client else None,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature"
        )

    try:
        payload = await request.json()
    except Exception as e:
        logger.error(
            event="flutterwave_webhook_parse_error",
            error=str(e),
            client_ip=request.client.host if request.client else None,
        )
        return PaymentWebhookResponse(status="error", message="Invalid JSON payload")

    webhook_event = payload.get("event") or payload.get("event.type") or payload.get(
        "type"
    )
    data = payload.get("data") if payload.get("data") else payload

    flw_ref = data.get("flw_ref")
    payment_type = data.get("payment_type")
    payment_status = data.get("status")
    paid_amount = data.get("amount")
    tx_ref = data.get("tx_ref")
    tx_id = data.get("id")

    logger.info(
        event="flutterwave_webhook_received",
        webhook_event=webhook_event,
        payment_status=payment_status,
        tx_ref=tx_ref,
        amount=paid_amount,
        flw_ref=flw_ref,
        tx_id=tx_id,
        payment_type=payment_type,
    )

    # Flutterwave status for successful is usually 'successful'
    if payment_status != "successful":
        logger.debug(
            event="flutterwave_webhook_event_ignored",
            level="debug",
            status=payment_status,
        )
        return PaymentWebhookResponse(
            status="ignored",
            tx_ref=tx_ref,
            message=f"Payment status is {payment_status}, not successful",
        )

    if not tx_ref:
        logger.warning(
            event="flutterwave_webhook_missing_tx_ref",
            level="warning",
            payload=payload,
        )
        return PaymentWebhookResponse(status="error", message="Missing tx_ref")

    # Idempotency check (prevent double-processing)
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
            tx_ref=tx_ref,
        )

    result = (
        await supabase.schema("pgmq_public")
        .rpc(
            "send",
            {
                "queue_name": "payment_queue",
                "message": {
                    "tx_ref": tx_ref,
                    "paid_amount": str(paid_amount),
                    "flw_ref": str(flw_ref),
                    "payment_method": f"{(payment_type or '').upper()}",
                    "tx_id": tx_id,
                },
            },
        )
        .execute()
    )

    msg_id = result.data

    logger.info(
        event=webhook_event,
        level="info",
        tx_ref=tx_ref,
        msg_id=msg_id,
    )

    return PaymentWebhookResponse(
        status="queued_with_retry",
        tx_ref=tx_ref,
        message="Payment processing queued",
    )

