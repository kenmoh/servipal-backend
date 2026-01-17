import pytest
from uuid import uuid4
from decimal import Decimal
from app.services.laundry_service import get_laundry_vendors, initiate_laundry_payment
from app.schemas.laundry_schemas import LaundryOrderCreate, LaundryItemOrder


@pytest.mark.asyncio
async def test_get_laundry_vendors(mock_supabase):
    # RPC mock
    result = await get_laundry_vendors(mock_supabase)
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_initiate_laundry_payment(mock_supabase):
    user_id = uuid4()
    vendor_id = uuid4()
    item_id = uuid4()

    # Mock Charges
    mock_supabase._data["charges_and_commissions"] = [
        {"base_delivery_fee": 500, "delivery_fee_per_km": 100}
    ]

    # Mock Service Item
    await (
        mock_supabase.table("laundry_services")
        .insert(
            {
                "id": str(item_id),
                "name": "Wash",
                "price": 2000,
                "vendor_id": str(vendor_id),
            }
        )
        .execute()
    )

    # Mock Vendor Profile
    await (
        mock_supabase.table("profiles")
        .insert(
            {"id": str(vendor_id), "full_name": "Laundry Shop", "user_type": "VENDOR"}
        )
        .execute()
    )

    data = LaundryOrderCreate(
        vendor_id=vendor_id,
        items=[LaundryItemOrder(item_id=item_id, quantity=1)],
        delivery_option="PICKUP",
        washing_instructions="Cold wash",
    )

    with pytest.MonkeyPatch.context() as m:

        async def mock_save(*args, **kwargs):
            return "pending_456"

        m.setattr("app.services.laundry_service.save_pending", mock_save)

        result = await initiate_laundry_payment(
            data,
            user_id,
            {"email": "test@example.com", "phone": "123456"},
            mock_supabase,
        )

        assert result.amount == Decimal("2000")
        assert result.tx_ref is not None
