from fastapi import APIRouter, Request, HTTPException, Depends, status
from supabase import AsyncClient
from app.dependencies.auth import get_current_user
from app.schemas.payments_schema import (
    CreateRefundRequest,
    MarkPaymentSuccessRequest,
)
from app.utils.api_key_auth import APIKeyManager

# from app.services.payment_service import (
#     process_successful_delivery_payment,
#     process_successful_food_payment,
#     process_successful_topup_payment,
#     process_successful_laundry_payment,
#     process_successful_product_payment,
# )
from app.config.config import settings
from app.config.logging import logger
from app.database.supabase import get_supabase_client, get_supabase_admin_client
from app.utils.webhook_validation import WebhookValidator

# from app.worker import enqueue_job
# from rq import Retry
from pydantic import BaseModel

# import hmac  # COMMENTED OUT - Using WebhookValidator instead for secure signature validation
from app.common import order
from app.services.payment_service import PaymentService
from app.services.payment_service import process_pay_on_delivery


class PaymentWebhookResponse(BaseModel):
    status: str
    message: str | None = None
    tx_ref: str | None = None


router = APIRouter(tags=["payments-webhook"], prefix="/api/v1/payment")


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def flutterwave_webhook(
    request: Request,
    supabase: AsyncClient = Depends(get_supabase_admin_client),
) -> PaymentWebhookResponse:
    """
    ** Handle Flutterwave payments webhooks. **

    - Verifies signature using WebhookValidator, checks idempotency, and queues processing in the background.

    - Args:
        - request (Request): The raw request.

    - Returns:
        - PaymentWebhookResponse: Processing status.
    """
    # 1. Get raw body for signature verification
    # 1. Verify webhook signature (Flutterwave sends verif-hash header)

    # secret_hash = settings.FLW_SECRET_HASH
    # signature = request.headers.get("verif-hash")
    # if not hmac.compare_digest(signature, secret_hash):
    #     logger.warning(
    #         event="webhook_signature_invalid",
    #         level="warning",
    #         client_ip=request.client.host if request.client else None,
    #     )
    #     raise HTTPException(
    #         status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature"
    #     )

    # 2. Verify webhook signature using WebhookValidator (secure HMAC validation)
    secret_hash = settings.FLW_SECRET_HASH
    signature = request.headers.get("verif-hash")

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

    # 3. Parse payload
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
        id=id,
        payment_type=payment_type,
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
            tx_ref=tx_ref,
            message=f"Payment status is {payment_status}, not successful",
        )

    if not tx_ref:
        logger.warning(
            event="flutterwave_webhook_missing_tx_ref", level="warning", payload=payload
        )
        return PaymentWebhookResponse(status="error", message="Missing tx_ref")

    # 4. Idempotency check (prevent double-processing)
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

    # 5. Determine which handler is based on the tx_ref prefix
    # handler = None
    # if tx_ref.startswith("DELIVERY-"):
    #     handler = process_successful_delivery_payment
    # elif tx_ref.startswith("FOOD-"):
    #     handler = process_successful_food_payment
    # elif tx_ref.startswith("TOPUP-"):
    #     handler = process_successful_topup_payment
    # elif tx_ref.startswith("LAUNDRY-"):
    #     handler = process_successful_laundry_payment
    # elif tx_ref.startswith("PRODUCT-"):
    #     handler = process_successful_product_payment

    # if not handler:
    #     logger.warning(
    #         event="flutterwave_webhook_unknown_transaction_type",
    #         level="warning",
    #         tx_ref=tx_ref,
    #     )
    #     return PaymentWebhookResponse(status="unknown_transaction_type")

    # 6. Queue the job with retry (5 attempts, exponential backoff)
    # job_id = enqueue_job(
    #     handler,
    #     tx_ref=str(tx_ref),
    #     payment_method="CARD",
    #     paid_amount=paid_amount,
    #     flw_ref=str(flw_ref),
    #     retry=Retry(max=5, interval=[30, 60, 120, 300, 600]),
    # )
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
                    "payment_method": f"{payment_type.upper()}",
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
        status="queued_with_retry", tx_ref=tx_ref, message="Payment processing queued"
    )


@router.post("/process-successful-order", status_code=status.HTTP_200_OK)
async def process_successful_order_payment(
    data: order.ProcessPaymentRequest,
    api_key: str = Depends(APIKeyManager.check_internal_api_key),
    supabase: AsyncClient = Depends(get_supabase_client),
):
    # API key already validated by dependency
    return await order.process_payment(data, supabase)


# Payout/Refund processing


@router.post("/success")
async def mark_payment_success(
    payload: MarkPaymentSuccessRequest,
    supabase: AsyncClient = Depends(get_supabase_client),
):

    return await supabase.mark_payment_success(
        str(payload.order_id),
        payload.flutterwave_tx_id,
        payload.scheduled_payout_at.isoformat(),
    )


@router.get("/due")
async def get_due_payouts(supabase: AsyncClient = Depends(get_supabase_client)):
    return await supabase.get_due_payouts()


@router.post("/process")
async def process_payout(
    order_payment_id: str,
    flutterwave_transfer_id: str,
    flutterwave_reference: str,
    supabase: AsyncClient = Depends(get_supabase_client),
):
    payout_service = PaymentService(supabase)
    return await payout_service.process_payout(
        order_payment_id,
        flutterwave_transfer_id,
        flutterwave_reference,
    )


@router.post("/")
async def create_refund(
    payload: CreateRefundRequest, supabase: AsyncClient = Depends(get_supabase_client)
):
    refund_service = PaymentService(supabase)
    return await refund_service.create_refund(
        str(payload.order_payment_id),
        payload.amount,
        payload.reason,
    )


@router.get("/pending")
async def get_pending_refunds(supabase: AsyncClient = Depends(get_supabase_client)):
    refund_service = PaymentService(supabase)
    return await refund_service.get_pending_refunds()


@router.post("/pay-on-delivery/{tx_ref}/confirm", status_code=status.HTTP_200_OK)
async def confirm_pay_on_delivery(
    tx_ref: str,
    request: Request,
    current_user: dict = Depends(get_current_user),
    supabase: AsyncClient = Depends(get_supabase_admin_client),
):
    # Customer confirms they have paid on delivery; backend finalizes order using pending Redis payload.
    return await process_pay_on_delivery(
        tx_ref=tx_ref,
        actor_id=str(current_user.get("id")),
        supabase=supabase,
        request=request,
    )
