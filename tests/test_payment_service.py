import pytest
from uuid import uuid4
from decimal import Decimal
from app.services.payment_service import process_successful_topup_payment


@pytest.mark.asyncio
async def test_process_successful_topup_payment(mock_supabase):
    user_id = uuid4()

    # Needs a pending key in Redis
    # We patch redis_utils.get_pending and delete_pending
    with pytest.MonkeyPatch.context() as m:

        async def mock_get(*args, **kwargs):
            return {
                "user_id": str(user_id),
                "amount": 2000.0,
                "currency": "NGN",
                "payment_method": "FLUTTERWAVE",
            }

        async def mock_delete(*args, **kwargs):
            return True

        m.setattr("app.services.payment_service.get_pending", mock_get)
        m.setattr("app.services.payment_service.delete_pending", mock_delete)
        m.setattr(
            "app.services.payment_service.log_audit_event", lambda *args, **kwargs: None
        )

        # Mock Wallet RPC for topup
        # `wallet_service.credit_wallet` calls `update_wallet_balance` RPC
        # My conftest handles `update_wallet_balance`.

        # Need wallet
        await (
            mock_supabase.table("wallets")
            .insert({"user_id": str(user_id), "balance": 1000.0})
            .execute()
        )

        await process_successful_topup_payment(
            "TOPUP-123", 2000.0, "abc", mock_supabase
        )

        # Verify Wallet Balance (1000 + 2000 = 3000)
        wallets = mock_supabase._data["wallets"]
        assert wallets[0]["balance"] == 3000.0
