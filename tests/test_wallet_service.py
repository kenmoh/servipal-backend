import pytest
from uuid import uuid4
from decimal import Decimal
from fastapi import HTTPException
from app.services.wallet_service import (
    get_wallet_details,
    initiate_wallet_top_up,
    pay_with_wallet,
)
from app.schemas.wallet_schema import TopUpRequest, PayWithWalletRequest


@pytest.mark.asyncio
async def test_get_wallet_details(mock_supabase):
    user_id = uuid4()

    # Setup wallet (MockDB uses lists, so we insert)
    await (
        mock_supabase.table("wallets")
        .insert(
            {"user_id": str(user_id), "balance": 5000.00, "escrow_balance": 1000.00}
        )
        .execute()
    )

    result = await get_wallet_details(user_id, mock_supabase)

    assert result.balance == Decimal("5000.00")
    assert result.escrow_balance == Decimal("1000.00")


@pytest.mark.asyncio
async def test_initiate_wallet_top_up(mock_supabase):
    user_id = uuid4()

    # Setup wallet
    await (
        mock_supabase.table("wallets")
        .insert({"user_id": str(user_id), "balance": 1000.00})
        .execute()
    )

    data = TopUpRequest(amount=Decimal("2000.00"), payment_method="FLUTTERWAVE")

    # We need to mock redis `save_pending`?
    # `initiate_wallet_top_up` calls `save_pending` from `app.utils.redis_utils`.
    # This will fail unless we mock `app.utils.redis_utils.save_pending`.
    # We can use unittest.mock.patch
    with pytest.MonkeyPatch.context() as m:
        m.setattr(
            "app.services.wallet_service.save_pending",
            lambda key, value, expire=None: None,
        )  # Mock sync/async?

        # Wait, save_pending is async. lambda returns None, which is not awaitable.
        async def mock_save(*args, **kwargs):
            return True

        m.setattr("app.services.wallet_service.save_pending", mock_save)

        # Also need to mock get_customer_contact_info dependency?
        # No, it's a dependency but usually passed by FastAPI.
        # BUT the service calls it?
        # Line 21: from app.dependencies.auth import get_customer_contact_info
        # Line 154: customer_info = await get_customer_contact_info()
        # This dependency likely depends on Request context which makes it hard to test pure service.
        # We should patch it.
        async def mock_get_contact():
            return {"email": "test@test.com", "phone": "123"}

        m.setattr(
            "app.services.wallet_service.get_customer_contact_info", mock_get_contact
        )

        # Mock settings.FLUTTERWAVE_PUBLIC_KEY
        m.setattr(
            "app.services.wallet_service.settings.FLUTTERWAVE_PUBLIC_KEY",
            "FLWPUBK-TEST",
        )
        m.setattr("app.config.config.settings.FLUTTERWAVE_PUBLIC_KEY", "FLWPUBK-TEST")

        result = await initiate_wallet_top_up(data, user_id, mock_supabase)

        assert result.amount == 2000.0
        assert result.currency == "NGN"
        assert result.tx_ref.startswith("TOPUP-")


@pytest.mark.asyncio
async def test_pay_with_wallet_success(mock_supabase):
    user_id = uuid4()

    # Setup wallet
    await (
        mock_supabase.table("wallets")
        .insert({"user_id": str(user_id), "balance": 5000.00})
        .execute()
    )

    data = PayWithWalletRequest(
        amount=Decimal("1000.00"),
        transaction_type="ORDER",
        to_user_id=uuid4(),
        order_id=uuid4(),
    )

    result = await pay_with_wallet(user_id, data, mock_supabase)

    assert result.success is True

    # Verify balance update (mock rpc handles update)
    wallets = mock_supabase._data["wallets"]
    assert wallets[0]["balance"] == 4000.00


@pytest.mark.asyncio
async def test_pay_with_wallet_insufficient_funds(mock_supabase):
    user_id = uuid4()

    await (
        mock_supabase.table("wallets")
        .insert({"user_id": str(user_id), "balance": 500.00})
        .execute()
    )

    data = PayWithWalletRequest(
        amount=Decimal("1000.00"), to_user_id=uuid4(), order_id=uuid4()
    )

    with pytest.raises(HTTPException) as exc:
        await pay_with_wallet(user_id, data, mock_supabase)

    assert exc.value.status_code == 400
