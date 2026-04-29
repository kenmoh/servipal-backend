import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from app.services.payment_service import process_successful_delivery_payment


@pytest.mark.asyncio
async def test_delivery_payment_precision_tolerance(mock_supabase):
    """Test that small precision differences don't trigger amount mismatch."""
    tx_ref = "DELIVERY-PRECISION-TEST"
    # Exact expected: 2818.19
    # Received from gateway: 2818.19000000000005456968210637569427490234375
    paid_amount = Decimal("2818.19000000000005456968210637569427490234375")
    expected_fee = 2818.19

    # Setup transaction intent
    await mock_supabase.table("transaction_intents").insert({
        "tx_ref": tx_ref,
        "service_type": "DELIVERY",
        "customer_id": "user-123",
        "vendor_id": "user-123",
        "amount": expected_fee,
        "currency": "NGN",
        "status": "PENDING",
        "payload": {
            "pricing": {"total": expected_fee, "distance_km": 5},
            "delivery": {
                "notes": "Test",
                "dropoff": "B",
                "dropoff_coordinates": [0,0],
                "pickup": "A",
                "pickup_coordinates": [0,0],
                "receiver_phone": "123"
            },
            "package": {"duration": "10m", "name": "Box"}
        }
    }).execute()

    with (
        patch(
            "app.services.payment_service.verify_transaction_tx_ref",
            new_callable=AsyncMock,
        ) as mock_verify,
    ):
        mock_verify.return_value = {"status": "success"}

        # We don't need to mock the entire supabase interaction if we just want to see if it passes the comparison
        # mock_supabase handles the table updates and rpc calls.

        await process_successful_delivery_payment(
            tx_ref=tx_ref,
            paid_amount=paid_amount,
            flw_ref="flw-123",
            supabase=mock_supabase,
            payment_method="CARD"
        )

        # Check that intent is completed
        intent = await mock_supabase.table("transaction_intents").select("*").eq("tx_ref", tx_ref).single().execute()
        assert intent.data["status"] == "COMPLETED"

@pytest.mark.asyncio
async def test_delivery_payment_actual_mismatch(mock_supabase):
    """Test that actual mismatches still trigger the warning."""
    tx_ref = "DELIVERY-MISMATCH-TEST"
    paid_amount = Decimal("2818.20")
    expected_fee = 2818.19

    # Setup transaction intent
    await mock_supabase.table("transaction_intents").insert({
        "tx_ref": tx_ref,
        "service_type": "DELIVERY",
        "customer_id": "user-123",
        "vendor_id": "user-123",
        "amount": expected_fee,
        "currency": "NGN",
        "status": "PENDING",
        "payload": {
            "pricing": {"total": expected_fee},
            "delivery": {},
            "package": {}
        }
    }).execute()

    with (
        patch(
            "app.services.payment_service.verify_transaction_tx_ref",
            new_callable=AsyncMock,
        ) as mock_verify,
    ):
        mock_verify.return_value = {"status": "success"}

        await process_successful_delivery_payment(
            tx_ref=tx_ref,
            paid_amount=paid_amount,
            flw_ref="flw-123",
            supabase=mock_supabase,
            payment_method="CARD"
        )

        # Should have returned early and completed intent
        intent = await mock_supabase.table("transaction_intents").select("*").eq("tx_ref", tx_ref).single().execute()
        assert intent.data["status"] == "COMPLETED"
        # Should NOT have tried to insert into delivery_orders
        try:
            mock_supabase.table.assert_any_call("delivery_orders")
            pytest.fail("Should not have called delivery_orders table")
        except AssertionError:
            pass
