from fastapi import APIRouter, Depends, Request, status, HTTPException
from fastapi.responses import RedirectResponse
from uuid import UUID
from app.schemas.wallet_schema import (
    WalletBalanceResponse,
    TopUpRequest,
    WithdrawResponse,
    PaymentWithWalletData,
)
from app.services import wallet_service
from app.dependencies.auth import get_current_profile
import hmac
from app.routes.payment_route import PaymentWebhookResponse
from app.database.supabase import get_supabase_client, get_supabase_admin_client
from supabase import AsyncClient
from app.config.logging import logger
from app.config.config import settings
from postgrest.exceptions import APIError
from rq import Retry
from app.services.payment_service import (
    process_successful_delivery_payment,
    process_successful_food_payment,
    process_successful_topup_payment,
    process_successful_laundry_payment,
    process_successful_product_payment,
)
from app.worker import enqueue_job

router = APIRouter(prefix="/api/v1/wallet", tags=["Wallet"])


@router.get("/details")
async def get_my_wallet_details(
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
) -> WalletBalanceResponse:
    """
    Get current user's wallet details.

    Returns:
        WalletBalanceResponse: Balance and currency.
    """
    logger.debug("get_wallet_details_endpoint", user_id=current_profile["id"])
    return await wallet_service.get_wallet_details(current_profile["id"], supabase)


@router.post("/initiate-wallet-topup")
async def top_up_my_wallet(
    data: TopUpRequest,
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
):
    """
    Initiate wallet top-up.

    Args:
        data (TopUpRequest): Amount to add.

    Returns:
        WalletTopUpInitiationResponse: Payment initiation details.
    """
    logger.info(
        "topup_endpoint_called",
        user_id=current_profile["id"],
        amount=float(data.amount),
    )
    return await wallet_service.initiate_wallet_top_up(
        data=data,
        user_id=current_profile["id"],
        supabase=supabase,
        customer_info=current_profile,
    )


@router.post("/pay-with-wallet", status_code=status.HTTP_200_OK)
async def pay_with_wallet(
    data: PaymentWithWalletData,
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
) -> PaymentWebhookResponse:
    """
    ** Handle Flutterwave payment webhooks. **

    - Verifies signature, checks idempotency, and queues processing in the background.

    - Args:
        - data (PaymentWithWalletData): The payment data received from Flutterwave.

    - Returns:
        - PaymentWebhookResponse: Processing status.
        - :param verif_hash:
        - :param request:
        - :param supabase:
    """
    # 1. Verify wallet balance
    await wallet_service.verify_wallet_balance(
        customer_id=current_profile["id"],
        required_amount=data.amount,
        supabase=supabase,
    )

    # 3. Idempotency — check if wallet_payment row already exists
    existing = (
        await supabase.table("wallet_payment")
        .select("id, status")
        .eq("tx_ref", data.tx_ref)
        .execute()
    )

    if existing.data:
        return {
            "status": existing.data[0]["status"],
            "tx_ref": existing.data[0]["tx_ref"],
            "amount": existing.data[0]["amount"],
            "message": "Wallet payment already initiated",
        }

    # 4. Insert wallet_payment row with PENDING status

    try:
        wallet_payment = (
            await supabase.table("wallet_payment")
            .insert(
                {
                    "tx_ref": data.tx_ref,
                    "amount": f'{data.amount}',
                    "status": "success",
                    "user_id": current_profile["id"],
                 
                }
            )
            .execute()
        )
    except APIError as e:
        logger.error(
            "wallet_payment_db_insert_error",
            error=str(e),
            tx_ref=data.tx_ref,
            amount=f'{data.amount}',
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record wallet payment",
        )

    logger.info(
        event="wallet_payment",
        customer_id=current_profile["id"],
        tx_ref=data.tx_ref,
        amount=f'{data.amount}',
    )

    tx_ref = wallet_payment.data[0]["tx_ref"]
    paid_amount = wallet_payment.data[0]["amount"]

    if not tx_ref:
        logger.warning(
            event="wallet_payment_missing_tx_ref",
            level="warning",
            payload=data.model_dump(),
        )
        return PaymentWebhookResponse(status="error", message="Missing tx_ref")

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
            event="wallet_payment_unknown_transaction_type",
            level="warning",
            tx_ref=tx_ref,
        )
        return PaymentWebhookResponse(status="unknown_transaction_type")

    # 6. Queue the job with retry (5 attempts, exponential backoff)
    job_id = enqueue_job(
        handler,
        tx_ref=str(tx_ref),
        paid_amount=paid_amount,
        flw_ref=f"WALLET-{tx_ref}",
        payment_method="WALLET",
        retry=Retry(max=5, interval=[30, 60, 120, 300, 600]),
    )

    message = {
        'tx_ref': str(tx_ref),
        'paid_amount': paid_amount,
        'flw_ref': f"WALLET-{tx_ref}",
        'payment_method': "WALLET",
    }
    # Supabase Que
    await supabase.schema("pgmq_public").rpc(
        'send',
         {
            "queue_name": "payment_queue",
            "message": message,
            "sleep_seconds": 30,
        }

    ).execute()

    logger.info(
        event="wallet_payment_queued",
        level="info",
        wlt_ref=tx_ref,
        job_id=job_id,
        handler=handler.__name__,
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL}/payment/status?status=success&tx_ref={tx_ref}",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/withdraw-all", response_model=WithdrawResponse)
async def withdraw_all_balance(
    current_profile: dict = Depends(get_current_profile),
    supabase: AsyncClient = Depends(get_supabase_client),
    request: Request = None,
):
    """
    Withdraw ALL available balance to user's bank via Flutterwave Transfer.
    Funds deducted immediately, transfer attempted instantly.
    """
    return await wallet_service.withdraw_all_balance(
        current_profile=current_profile, supabase=supabase, request=request
    )
