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
from app.database.supabase import get_supabase_client, get_supabase_admin_client
# from app.worker import enqueue_job
# from rq import Retry

# import hmac  # COMMENTED OUT - Using WebhookValidator instead for secure signature validation
from app.common import order
from app.services.payment_service import PaymentService
from app.services.payment_service import process_pay_on_delivery
from app.webhooks.flutterwave_webhook import PaymentWebhookResponse, handle_flutterwave_webhook


router = APIRouter(tags=["payments-webhook"], prefix="/api/v1/payment")


# Backwards-compatible endpoint. Canonical endpoint is `/api/v1/payments/webhook`.
@router.post("/webhook", status_code=status.HTTP_200_OK, include_in_schema=False)
@router.post("/webhook/", status_code=status.HTTP_200_OK, include_in_schema=False)
async def flutterwave_webhook(
    request: Request,
    supabase: AsyncClient = Depends(get_supabase_admin_client),
) -> PaymentWebhookResponse:
    return await handle_flutterwave_webhook(request=request, supabase=supabase)


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
