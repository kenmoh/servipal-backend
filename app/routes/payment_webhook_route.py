from fastapi import APIRouter, Depends, Request, status
from supabase import AsyncClient

from app.database.supabase import get_supabase_admin_client
from app.webhooks.flutterwave_webhook import PaymentWebhookResponse, handle_flutterwave_webhook

# Canonical Flutterwave webhook endpoint:
# Flutterwave dashboard should point here.
router = APIRouter(tags=["payments-webhook"], prefix="/api/v1/payments")


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def flutterwave_webhook(
    request: Request,
    supabase: AsyncClient = Depends(get_supabase_admin_client),
) -> PaymentWebhookResponse:
    return await handle_flutterwave_webhook(request=request, supabase=supabase)

