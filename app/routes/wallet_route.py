from fastapi import APIRouter, Depends, Request, status, HTTPException
from decimal import Decimal
from uuid import UUID
from app.schemas.wallet_schema import (
    WalletBalanceResponse,
    TopUpRequest,
    WithdrawResponse,
    PaymentWithWalletData,
)
from app.services import wallet_service
from app.dependencies.auth import get_current_profile
from app.routes.payment_route import PaymentWebhookResponse
from app.database.supabase import get_supabase_client, get_supabase_admin_client
from supabase import AsyncClient
from app.config.logging import logger
from postgrest.exceptions import APIError

from app.utils.redis_utils import get_pending

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
    supabase: AsyncClient = Depends(get_supabase_admin_client),
) -> PaymentWebhookResponse:
    """
    ** Handle Flutterwave payments webhooks. **

    - Verifies signature, checks idempotency, and queues processing in the background.

    - Args:
        - data (PaymentWithWalletData): The payments data received from Flutterwave.

    - Returns:
        - PaymentWebhookResponse: Processing status.
        - :param verif_hash:
        - :param request:
        - :param supabase:
    """
    service = data.tx_ref.split("-")[0].lower() if data.tx_ref else "UNKNOWN"
    pending_key = f"pending_{service}_{data.tx_ref}"
    pending = await get_pending(pending_key)

    if not pending:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Order data not found or expired. Please try again.",
        )
    # 1. Verify wallet balance
    await wallet_service.verify_wallet_balance(
        customer_id=current_profile["id"],
        required_amount=data.amount,
        supabase=supabase,
    )

    # 3. Idempotency — check if wallet_payment row already exists
    if not data.tx_ref:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="tx_ref is required in the request body",
        )

    existing = (
        await supabase.table("wallet_payment")
        .select("id, status, tx_ref, amount")
        .eq("tx_ref", data.tx_ref)
        .execute()
    )

    if existing.data:
        return {
            "status": existing.data[0]["status"],
            "tx_ref": existing.data[0]["tx_ref"],
            "amount": existing.data[0]["amount"],
            "message": "Wallet payments already initiated",
        }

    # 4. Insert wallet_payment row with PENDING status

    try:
        wallet_payment = (
            await supabase.table("wallet_payment")
            .insert(
                {
                    "tx_ref": data.tx_ref,
                    "amount": f"{Decimal(data.amount)}",
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
            amount=f"{data.amount}",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record wallet payments",
        )

    logger.info(
        event="wallet_payment",
        customer_id=current_profile["id"],
        tx_ref=data.tx_ref,
        amount=f"{data.amount}",
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

    # Supabase Que
    result = (
        await supabase.schema("pgmq_public")
        .rpc(
            "send",
            {
                "queue_name": "payment_queue",
                "message": {
                    "tx_ref": tx_ref,
                    "paid_amount": str(paid_amount),
                    "flw_ref": str(data.tx_ref),
                    "payment_method": "WALLET",
                    "pending_data": pending,
                },
            },
        )
        .execute()
    )

    msg_id = result.data

    logger.info(
        event="wallet_payment_queued",
        level="info",
        wlt_ref=tx_ref,
        msg_id=msg_id,
    )
    return PaymentWebhookResponse(
        status="success",
        tx_ref=tx_ref,
        amount=paid_amount,
        message="Wallet payments processed and queued",
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
