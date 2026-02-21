from fastapi import HTTPException, status
from uuid import UUID
from uuid import uuid4
import httpx
from decimal import Decimal
from datetime import datetime
import uuid
from typing import Optional
from app.services.notification_service import notify_user

from supabase import AsyncClient
from app.schemas.wallet_schema import (
    WalletBalanceResponse,
    WalletTransactionResponse,
    TopUpRequest,
    PayWithWalletRequest,
    PayWithWalletResponse,
    WithdrawalCreate,
    WithdrawalResponse,
    WithdrawalListResponse,
)
from app.config.config import settings
from app.utils.redis_utils import save_pending
from app.config.logging import logger
from fastapi import HTTPException, status
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from app.utils.audit import log_audit_event
from app.config.logging import logger
from supabase import AsyncClient
from app.schemas.wallet_schema import WithdrawResponse
from app.schemas.common import PaymentInitializationResponse, PaymentCustomerInfo, PaymentCustomization


# ───────────────────────────────────────────────
# Get Wallet Details (balance + escrow)
# ───────────────────────────────────────────────
async def get_wallet_details(
    user_id: UUID, supabase: AsyncClient
) -> WalletBalanceResponse:
    logger.debug("get_wallet_details_requested", user_id=str(user_id))
    wallet = (
        await supabase.table("wallets")
        .select("balance, escrow_balance")
        .eq("user_id", str(user_id))
        .single()
        .execute()
    )

    if not wallet.data:
        logger.warning("wallet_not_found", user_id=str(user_id))
        raise HTTPException(404, "Wallet not found")

    balance = (
        float(wallet.data["balance"]) if wallet.data["balance"] is not None else 0.0
    )
    escrow_balance = (
        float(wallet.data["escrow_balance"])
        if wallet.data["escrow_balance"] is not None
        else 0.0
    )

    # Round to 2 decimal places (money standard)
    balance = Decimal(round(balance, 2))
    escrow_balance = Decimal(round(escrow_balance, 2))

    # Fetch transactions (limit to recent 20 for performance)
    tx_resp = (
        await supabase.table("transactions")
        .select("*")
        .or_(f"from_user_id.eq.{user_id},to_user_id.eq.{user_id}")
        .order("created_at", desc=True)
        .limit(20)
        .execute()
    )

    transactions = []
    for tx in tx_resp.data:
        transactions.append(
            WalletTransactionResponse(
                tx_ref=tx["tx_ref"],
                amount=tx["amount"] if tx["amount"] else Decimal(0.0),
                transaction_type=tx["transaction_type"],
                status=tx["status"],
                payment_method=tx["payment_method"],
                created_at=tx["created_at"],
                from_user_id=tx["from_user_id"],
                to_user_id=tx["to_user_id"],
                order_id=tx["order_id"],
            )
        )

    return WalletBalanceResponse(
        balance=balance, escrow_balance=escrow_balance, transactions=transactions
    )


# ───────────────────────────────────────────────
# Top-up Wallet (via Flutterwave or other)
# ───────────────────────────────────────────────


async def initiate_wallet_top_up(
    data: TopUpRequest,
    user_id: str,
    supabase: AsyncClient,
    customer_info: dict,
) -> dict:
    """
    Initiate wallet top-up payment.
    Validates balance limit before proceeding.
    """
    MAX_BALANCE = Decimal("50000")  # ₦50,000

    # Get current balance
    wallet_resp = (
        await supabase.table("wallets")
        .select("balance")
        .eq("user_id", user_id)
        .single()
        .execute()
    )
    current_balance = (
        Decimal(str(wallet_resp.data["balance"])) if wallet_resp.data else Decimal("0")
    )

    # Check if current balance already at limit
    if current_balance >= MAX_BALANCE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Wallet balance limit reached (₦{current_balance:,.2f}). Maximum allowed is ₦{MAX_BALANCE:,.2f}. Please withdraw or spend before adding more funds.",
        )

    # Check if top-up would exceed limit
    new_balance = current_balance + data.amount
    if new_balance > MAX_BALANCE:
        max_topup_allowed = MAX_BALANCE - current_balance
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Top-up of ₦{data.amount:,.2f} would exceed wallet limit. Current balance: ₦{current_balance:,.2f}. Maximum top-up allowed: ₦{max_topup_allowed:,.2f}.",
        )

    # Generate tx_ref
    tx_ref = f"TOPUP-{uuid.uuid4().hex[:32].upper()}"

    # Save to Redis
    pending_data = {
        "user_id": str(user_id),
        "amount": str(data.amount),
        "tx_ref": tx_ref,
        "created_at": datetime.datetime.now().isoformat(),
    }
    await save_pending(f"pending_topup_{tx_ref}", pending_data, expire=1800)

    # Return for Flutterwave
    return PaymentInitializationResponse(
        tx_ref=tx_ref,
        amount=data.amount,
        public_key=settings.FLUTTERWAVE_PUBLIC_KEY,
        currency="NGN",
        customer=PaymentCustomerInfo(
            email=customer_info.get("email"),
            phone_number=customer_info.get("phone_number"),
            full_name=customer_info.get("full_name") or "N/A",
        ),
        customization=PaymentCustomization(
            title="Wallet Top-up",
            description=f"Add ₦{data.amount:,.2f} to your wallet",
            logo="https://mohdelivery.s3.us-east-1.amazonaws.com/favion/favicon.ico",
        ),
        message="Ready for payment",
    ).model_dump()


# MAX_WALLET_LIMIT = Decimal("50000.00")


# async def initiate_wallet_top_up(
#     data: TopUpRequest,
#     user_id: UUID,
#     supabase: AsyncClient,
# ) -> WalletTopUpInitiationResponse:
#     logger.info(
#         "wallet_topup_initiated", user_id=str(user_id), amount=float(data.amount)
#     )
#     """
#     Initiate wallet top-up via Flutterwave RN SDK.
#     Enforces max wallet balance of ₦50,000.
#     """
#     try:
#         # Minimum amount validation
#         if data.amount < Decimal("1000"):
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Minimum top-up amount is ₦1000",
#             )

#         # Get current wallet balance
#         wallet = (
#             await supabase.table("wallets")
#             .select("balance")
#             .eq("user_id", str(user_id))
#             .single()
#             .execute()
#         )

#         if not wallet.data:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
#             )

#         current_balance = Decimal(str(wallet.data["balance"]))

#         # Check max limit
#         new_balance = current_balance + data.amount
#         if new_balance > MAX_WALLET_LIMIT:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Top-up would exceed the maximum wallet balance of ₦{MAX_WALLET_LIMIT:,.2f}. "
#                 f"Current balance: ₦{current_balance:,.2f}. "
#                 f"Maximum you can top up now: ₦{(MAX_WALLET_LIMIT - current_balance):,.2f}",
#             )

#         # Generate unique tx_ref
#         tx_ref = f"TOPUP-{uuid.uuid4().hex[:12].upper()}"

#         # Save pending state in Redis
#         pending_data = {
#             "user_id": str(user_id),
#             "amount": float(data.amount),
#             "tx_ref": tx_ref,
#             "payment_method": data.payment_method,
#             "created_at": datetime.now().isoformat(),
#         }
#         await save_pending(f"pending_topup_{tx_ref}", pending_data, expire=1800)

#         # Get real customer info
#         customer_info = await get_customer_contact_info()

#         # Return SDK-ready data
#         result = WalletTopUpInitiationResponse(
#             tx_ref=tx_ref,
#             amount=float(data.amount),
#             public_key=settings.FLUTTERWAVE_PUBLIC_KEY,
#             currency="NGN",
#             customer=CustomerInfo(
#                 email=customer_info["email"], name=customer_info["phone"]
#             ),
#             customization=Customization(
#                 title="Servipal Wallet Top-up",
#                 description=f"Top up ₦{data.amount:,.2f} to your wallet",
#             ),
#         )

#         logger.info(
#             "wallet_topup_initiation_success",
#             user_id=str(user_id),
#             tx_ref=tx_ref,
#             amount=float(data.amount),
#         )
#         return result

#     except HTTPException as he:
#         logger.error(
#             "wallet_topup_initiation_failed",
#             user_id=str(user_id),
#             error=str(he.detail),
#             exc_info=True,
#         )
#         raise he
#     except Exception as e:
#         logger.error(
#             "wallet_topup_initiation_error",
#             user_id=str(user_id),
#             error=str(e),
#             exc_info=True,
#         )
#         raise HTTPException(
#             status.HTTP_500_INTERNAL_SERVER_ERROR, f"Top-up initiation failed: {str(e)}"
#         )


# ───────────────────────────────────────────────
# Pay with Wallet (deduct from balance)
# ───────────────────────────────────────────────
async def pay_with_wallet(
    user_id: UUID, data: PayWithWalletRequest, supabase: AsyncClient
) -> PayWithWalletResponse:
    """
    Deduct amount from user's wallet balance.
    - Checks sufficient balance
    - Atomic via RPC
    - Records trans action
    """
    logger.info(
        "wallet_payment_attempt",
        user_id=str(user_id),
        amount=float(data.amount),
        order_id=str(data.order_id) if data.order_id else None,
    )
    try:
        # Get current balance
        wallet = (
            await supabase.table("wallets")
            .select("balance")
            .eq("user_id", str(user_id))
            .single()
            .execute()
        )

        if not wallet.data:
            logger.warning("wallet_not_found_for_payment", user_id=str(user_id))
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Wallet not found"
            )

        old_balance = Decimal(str(wallet.data["balance"]))
        current_balance = old_balance

        if current_balance < data.amount:
            logger.warning(
                "insufficient_wallet_balance",
                user_id=str(user_id),
                balance=float(current_balance),
                requested=float(data.amount),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient wallet balance",
            )

        # Deduct from balance (atomic RPC)
        await supabase.rpc(
            "update_wallet_balance",
            {"p_user_id": str(user_id), "p_delta": -data.amount, "p_field": "balance"},
        ).execute()

        # Get new balance after deduction
        wallet_after = (
            await supabase.table("wallets")
            .select("balance")
            .eq("user_id", str(user_id))
            .single()
            .execute()
        )

        new_balance = Decimal(str(wallet_after.data["balance"]))

        # Record transaction
        tx_ref = f"PAY-{uuid.uuid4().hex[:22].upper()}"
        await (
            supabase.table("transactions")
            .insert(
                {
                    "tx_ref": tx_ref,
                    "amount": float(data.amount),
                    "from_user_id": str(user_id),
                    "to_user_id": data.to_user_id,
                    "order_id": data.order_id,
                    "transaction_type": data.transaction_type or "ORDER_PAYMENT",
                    "status": "COMPLETED",
                    "payment_method": "WALLET",
                    "details": data.details or {},
                }
            )
            .execute()
        )

        logger.info(
            "wallet_payment_success",
            user_id=str(user_id),
            tx_ref=tx_ref,
            amount=float(data.amount),
            new_balance=float(new_balance),
        )
        return PayWithWalletResponse(
            success=True,
            message="Payment successful from wallet",
            new_balance=new_balance,
            tx_ref=tx_ref,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "wallet_payment_error", user_id=str(user_id), error=str(e), exc_info=True
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Wallet payment failed: {str(e)}"
        )


async def request_withdrawal(
    data: WithdrawalCreate,
    user_id: UUID,
    supabase: AsyncClient,
    request=None,
) -> WithdrawalResponse:
    try:
        # 1. Get user wallet
        wallet = (
            await supabase.table("wallets")
            .select("balance")
            .eq("user_id", str(user_id))
            .single()
            .execute()
        ).data

        if not wallet:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Wallet not found")

        current_balance = Decimal(str(wallet["balance"]))

        # 2. Check minimum and balance
        min_amount = Decimal("1000")
        if data.amount < min_amount:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, f"Minimum withdrawal is ₦{min_amount}"
            )

        if current_balance < data.amount:
            raise HTTPException(400, "Insufficient balance")

        # 3. Calculate fee (example: ₦100 flat)
        fee = Decimal("100")
        net_amount = data.amount - fee

        # 4. Deduct from balance immediately
        await supabase.rpc(
            "update_wallet_balance",
            {"p_user_id": str(user_id), "p_delta": -data.amount, "p_field": "balance"},
        ).execute()

        # 5. Create withdrawal record
        withdrawal = (
            await supabase.table("withdrawals")
            .insert(
                {
                    "user_id": str(user_id),
                    "amount": float(data.amount),
                    "fee": float(fee),
                    "bank_name": data.bank_name,
                    "account_number": data.account_number,
                    "account_name": data.account_name,
                    "status": "PENDING",
                    "created_at": datetime.utcnow().isoformat(),
                }
            )
            .execute()
        ).data[0]

        withdrawal_id = withdrawal["id"]

        # 6. Audit log
        await log_audit_event(
            entity_type="WITHDRAWAL",
            entity_id=str(withdrawal_id),
            action="REQUESTED",
            change_amount=-data.amount,
            actor_id=str(user_id),
            actor_type="USER",
            notes=f"Withdrawal of ₦{data.amount} requested (fee ₦{fee})",
            request=request,
        )

        return WithdrawalResponse(**withdrawal)

    except Exception as e:
        # Rollback balance deduction on error (optional - add try/except rollback)
        logger.error(
            "Withdrawal request failed",
            user_id=str(user_id),
            error=str(e),
            exc_info=True,
        )
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Withdrawal request failed: {str(e)}",
        )


# Admin approve withdrawal (manual or auto)
async def approve_withdrawal(
    withdrawal_id: UUID,
    admin_id: UUID,
    supabase: AsyncClient,
    notes: Optional[str] = None,
):
    try:
        withdrawal = (
            await supabase.table("withdrawals")
            .select(
                "user_id, amount, fee, status, bank_name, account_number, account_name"
            )
            .eq("id", str(withdrawal_id))
            .single()
            .execute()
        ).data

        if not withdrawal:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Withdrawal not found")

        if withdrawal["status"] != "PENDING":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"Withdrawal already {withdrawal['status']}",
            )

        # Here: Call Flutterwave Transfer API (or manual bank transfer)
        # For now, simulate success
        flutterwave_ref = f"TRF-{uuid.uuid4().hex[:12].upper()}"

        # Update status
        await (
            supabase.table("withdrawals")
            .update(
                {
                    "status": "PROCESSING",
                    "approved_at": datetime.utcnow().isoformat(),
                    "flutterwave_ref": flutterwave_ref,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            )
            .eq("id", str(withdrawal_id))
            .execute()
        )

        # Audit
        await log_audit_event(
            entity_type="WITHDRAWAL",
            entity_id=str(withdrawal_id),
            action="APPROVED",
            actor_id=str(admin_id),
            actor_type="ADMIN",
            notes=f"Approved withdrawal of ₦{withdrawal['amount']} to {withdrawal['account_name']}",
        )

        return {
            "success": True,
            "message": "Withdrawal approved and processing",
            "withdrawal_id": withdrawal_id,
        }

    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Approval failed: {str(e)}"
        )


async def withdraw_all_balance(
    current_profile: dict, supabase: AsyncClient, request=None
) -> WithdrawResponse:
    """
    Withdraw ALL available balance to user's bank via Flutterwave Transfer API.
    - Deducts full amount from balance immediately (atomic)
    - Creates PENDING transaction
    - Sends money via Flutterwave
    - Updates transaction on success/failure
    """
    user_id = current_profile["id"]
    balance = None  # Track for refund
    tx_id = None

    try:
        # 1. Withdrawal fee (flat ₦100)
        fee = Decimal("100.00")

        # 2. Generate reference
        reference = f"WITHDRAW-{uuid4().hex[:20].upper()}"

        # 3. Process withdrawal atomically (deduct balance + create transaction)
        logger.info("initiating_withdrawal", user_id=user_id, reference=reference)

        withdrawal_result = await supabase.rpc(
            "process_withdrawal",
            {
                "p_user_id": user_id,
                "p_tx_ref": reference,
                "p_withdrawal_fee": float(fee),
                "p_bank_details": {
                    "bank_name": current_profile.get("bank_name"),
                    "account_number": current_profile.get("account_number"),
                    "account_name": current_profile.get("account_holder_name"),
                },
            },
        ).execute()

        if not withdrawal_result.data:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Withdrawal initialization failed"
            )

        result = withdrawal_result.data
        balance = Decimal(str(result["balance_withdrawn"]))
        net_amount = Decimal(str(result["net_amount"]))
        tx_id = result["transaction_id"]

        logger.info(
            "withdrawal_initialized",
            user_id=user_id,
            tx_id=tx_id,
            balance=str(balance),
            net_amount=str(net_amount),
        )

        # 4. Call Flutterwave Transfer API
        logger.info("calling_flutterwave_transfer", reference=reference)

        async with httpx.AsyncClient(timeout=30.0) as client:
            payload = {
                "account_bank": current_profile.get("bank_code"),
                "account_number": current_profile.get("account_number"),
                "amount": int(net_amount),
                "narration": "Servipal Wallet Withdrawal",
                "currency": "NGN",
                "reference": reference,
                "callback_url": f"{settings.API_BASE_URL}/webhooks/flutterwave/transfer",
                "debit_currency": "NGN",
            }

            headers = {
                "Authorization": f"Bearer {settings.FLUTTERWAVE_SECRET_KEY}",
                "Content-Type": "application/json",
            }

            resp = await client.post(
                "https://api.flutterwave.com/v3/transfers",
                json=payload,
                headers=headers,
            )

            fw_response = resp.json()

            logger.info(
                "flutterwave_response",
                status_code=resp.status_code,
                response=fw_response,
            )

            # 5. Handle Flutterwave response
            if resp.status_code != 200 or fw_response.get("status") != "success":
                # Transfer failed → refund balance
                error_msg = fw_response.get("message", "Unknown error")

                logger.error(
                    "flutterwave_transfer_failed",
                    user_id=user_id,
                    error=error_msg,
                    response=fw_response,
                )

                await supabase.rpc(
                    "refund_failed_withdrawal",
                    {
                        "p_user_id": user_id,
                        "p_tx_id": tx_id,
                        "p_amount": float(balance),
                        "p_error_details": {
                            "flutterwave_error": fw_response,
                            "error_message": error_msg,
                            "failed_at": datetime.now().isoformat(),
                        },
                    },
                ).execute()

                logger.info("withdrawal_refunded", user_id=user_id, amount=str(balance))

                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Transfer failed: {error_msg}. Your balance has been refunded.",
                )

            # 6. Success - Update transaction
            flw_data = fw_response.get("data", {})

            await supabase.rpc(
                "update_withdrawal_status",
                {
                    "p_tx_id": tx_id,
                    "p_status": "SUCCESS",
                    "p_details": {
                        "flutterwave_ref": flw_data.get("reference"),
                        "flutterwave_id": flw_data.get("id"),
                        "transfer_status": flw_data.get("status"),
                        "completed_at": datetime.utcnow().isoformat(),
                    },
                },
            ).execute()

            logger.info(
                "withdrawal_completed",
                user_id=user_id,
                tx_id=tx_id,
                flw_ref=flw_data.get("reference"),
            )

            # 7. Log audit event
            await log_audit_event(
                entity_type="WITHDRAWAL",
                entity_id=str(tx_id),
                action="COMPLETED",
                change_amount=-balance,
                actor_id=user_id,
                actor_type=current_profile.get("user_type"),
                notes=f"Withdrawal of ₦{balance} (net ₦{net_amount}) completed to {current_profile.get('account_holder_name')}",
                request=request,
            )

            # 8. Notify user
            await notify_user(
                user_id=user_id,
                title="💰 Withdrawal Successful",
                message=f"₦{net_amount} has been sent to your {current_profile.get('bank_name')} account",
                notification_type="WITHDRAWAL",
                request=request,
            )

            return WithdrawResponse(
                success=True,
                message="Withdrawal successful! Funds sent to your bank.",
                amount_withdrawn=balance,
                fee=fee,
                net_amount=net_amount,
                transaction_id=str(tx_id),
                flutterwave_ref=flw_data.get("reference"),
                status="COMPLETED",
            )

    except HTTPException:
        raise

    except Exception as e:
        logger.critical(
            "withdrawal_critical_error",
            user_id=user_id,
            tx_id=tx_id,
            error=str(e),
            exc_info=True,
        )

        # Emergency refund if we have balance and tx_id
        if balance and tx_id:
            try:
                await supabase.rpc(
                    "refund_failed_withdrawal",
                    {
                        "p_user_id": user_id,
                        "p_tx_id": tx_id,
                        "p_amount": float(balance),
                        "p_error_details": {
                            "error": str(e),
                            "error_type": "SYSTEM_ERROR",
                            "failed_at": datetime.utcnow().isoformat(),
                        },
                    },
                ).execute()

                logger.info("emergency_refund_completed", user_id=user_id)

                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    f"Withdrawal failed (funds refunded): {str(e)}",
                )
            except Exception as refund_error:
                logger.critical(
                    "refund_failed",
                    user_id=user_id,
                    error=str(refund_error),
                    exc_info=True,
                )
                raise HTTPException(
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    "Critical error - please contact support immediately",
                )

        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            f"Withdrawal failed: {str(e)}",
        )
