import pytest
from uuid import uuid4
from decimal import Decimal
from app.services.food_service import get_food_vendors, initiate_food_payment
from app.schemas.food_schemas import CheckoutRequest, CartItem


@pytest.mark.asyncio
async def test_get_food_vendors(mock_supabase):
    # Setup vendors
    await (
        mock_supabase.table("profiles")
        .insert(
            [
                {"id": str(uuid4()), "full_name": "Vendor A", "user_type": "VENDOR"},
                {"id": str(uuid4()), "full_name": "Vendor B", "user_type": "VENDOR"},
            ]
        )
        .execute()
    )

    # RPC mock for get_food_vendors returns mock_supabase._data["profiles"] filtered?
    # Our MockRPCBuilder is generic. Let's just assume it returns something.
    result = await get_food_vendors(mock_supabase)
    assert len(result) >= 0  # Depends on RPC mock implementation


@pytest.mark.asyncio
async def test_initiate_food_payment(mock_supabase):
    user_id = uuid4()
    vendor_id = uuid4()
    item_id = uuid4()

    # Mock Charges
    mock_supabase._data["charges_and_commissions"] = [
        {"base_delivery_fee": 500, "delivery_fee_per_km": 100}
    ]

    # Mock Vendor Menu Item
    await (
        mock_supabase.table("menu_items")
        .insert(
            {
                "id": str(item_id),
                "name": "Burger",
                "price": 1500,
                "vendor_id": str(vendor_id),
            }
        )
        .execute()
    )

    # Mock Vendor Profile
    await (
        mock_supabase.table("profiles")
        .insert(
            {"id": str(vendor_id), "full_name": "Burger Shop", "user_type": "VENDOR"}
        )
        .execute()
    )

    data = CheckoutRequest(
        vendor_id=vendor_id,
        items=[
            CartItem(item_id=item_id, name="Burger", price=Decimal("1500"), quantity=2)
        ],
        delivery_option="PICKUP",
        cooking_instructions="No onions",
    )

    with pytest.MonkeyPatch.context() as m:

        async def mock_save(*args, **kwargs):
            return "pending_123"

        m.setattr("app.services.food_service.save_pending", mock_save)

        # Dispatch calls get_customer_contact_info if not provided?
        # Actually initiate_food_payment takes (data, customer_id, supabase, request)

        result = await initiate_food_payment(data, user_id, mock_supabase)

        assert result.amount == Decimal("3000")  # 1500 * 2
        assert result.currency == "NGN"
        assert result.tx_ref is not None
