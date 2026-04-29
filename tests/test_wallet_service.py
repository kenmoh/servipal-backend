import pytest
from uuid import uuid4
from decimal import Decimal
from fastapi import HTTPException
from app.services.wallet_service import (
    get_wallet_details,
    initiate_wallet_top_up,
    pay_with_wallet,
)
from app.schemas.wallet_schema import TopUpRequest, PayWithWalletRequest, WalletPaymentRequest, OrderType


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

    with pytest.MonkeyPatch.context() as m:
        async def mock_save(*args, **kwargs):
            return True

        m.setattr("app.services.wallet_service.save_pending", mock_save)

        # Mock settings.FLUTTERWAVE_PUBLIC_KEY
        m.setattr("app.config.config.settings.FLUTTERWAVE_PUBLIC_KEY", "FLWPUBK-TEST")

        customer_info = {
            "email": "test@test.com",
            "phone_number": "+2348000000000",
            "full_name": "Test User",
        }

        result = await initiate_wallet_top_up(data, user_id, mock_supabase, customer_info)

        assert result["amount"] == Decimal("2000.00")
        assert result["currency"] == "NGN"
        assert result["tx_ref"].startswith("TOPUP-")


@pytest.mark.asyncio
async def test_pay_with_wallet_success(mock_supabase):
    user_id = uuid4()

    # Setup wallet
    await (
        mock_supabase.table("wallets")
        .insert({"user_id": str(user_id), "balance": 5000.00})
        .execute()
    )

    data = WalletPaymentRequest(
        order_type=OrderType.PRODUCT,
        grand_total=Decimal("1000.00"),
        product_id=uuid4(),
        vendor_id=uuid4(),
        distance=5.0,
        quantity=1,
        product_name="T-Shirt",
        unit_price=Decimal("1000.00"),
        subtotal=Decimal("1000.00"),
    )

    current_profile = {"id": str(user_id), "full_name": "Test User"}
    result = await pay_with_wallet(data, current_profile, mock_supabase)

    assert result["success"] is True

    # Verify balance update
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

    data = WalletPaymentRequest(
        order_type=OrderType.FOOD,
        grand_total=Decimal("1000.00"),
        vendor_id=uuid4(),
        distance=5.0,
        total_price=Decimal("1000.00"),
        delivery_option="PICKUP",
        order_data=[{"item_id": str(uuid4()), "quantity": 1}],
    )

    current_profile = {"id": str(user_id)}

    with pytest.raises(HTTPException) as exc:
        await pay_with_wallet(data, current_profile, mock_supabase)

    assert exc.value.status_code == 400
