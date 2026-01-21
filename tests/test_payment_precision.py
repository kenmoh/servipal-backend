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
    paid_amount = Decimal('2818.19000000000005456968210637569427490234375')
    expected_fee = 2818.19
    
    with patch("app.services.payment_service.verify_transaction_tx_ref", new_callable=AsyncMock) as mock_verify, \
         patch("app.services.payment_service.get_pending", new_callable=AsyncMock) as mock_get_pending, \
         patch("app.services.payment_service.delete_pending", new_callable=AsyncMock) as mock_delete_pending, \
         patch("app.services.payment_service.get_commission_rate", new_callable=AsyncMock) as mock_comm:
        
        mock_verify.return_value = {"status": "success"}
        mock_get_pending.return_value = {
            "delivery_fee": expected_fee,
            "sender_id": "user-123",
            "delivery_data": {
                "receiver_phone": "123456",
                "pickup_location": "A",
                "destination": "B",
                "pickup_coordinates": [0, 0],
                "dropoff_coordinates": [1, 1],
                "delivery_type": "BIKE"
            }
        }
        mock_comm.return_value = 0.2
        
        # We don't need to mock the entire supabase interaction if we just want to see if it passes the comparison
        # But to avoid actual DB calls, we mock the table insert
        mock_supabase.table.return_value.insert.return_value.execute = AsyncMock(return_value=AsyncMock(data=[{"id": "order-123"}]))
        mock_supabase.rpc.return_value.execute = AsyncMock()

        await process_successful_delivery_payment(
            tx_ref=tx_ref,
            paid_amount=paid_amount,
            flw_ref="flw-123",
            supabase=mock_supabase
        )
        
        # If it reached here without returning early at line 47 (mismatch), it's a success
        # The delete_pending should be called at the end of successful processing
        mock_delete_pending.assert_called()
        
        # Verify that mismatch warning was NOT triggered (or rather, verify logic continued)
        # We can also check if table("delivery_orders") was called
        mock_supabase.table.assert_any_call("delivery_orders")

@pytest.mark.asyncio
async def test_delivery_payment_actual_mismatch(mock_supabase):
    """Test that actual mismatches still trigger the warning."""
    tx_ref = "DELIVERY-MISMATCH-TEST"
    paid_amount = Decimal('2818.20')
    expected_fee = 2818.19
    
    with patch("app.services.payment_service.verify_transaction_tx_ref", new_callable=AsyncMock) as mock_verify, \
         patch("app.services.payment_service.get_pending", new_callable=AsyncMock) as mock_get_pending, \
         patch("app.services.payment_service.delete_pending", new_callable=AsyncMock) as mock_delete_pending:
        
        mock_verify.return_value = {"status": "success"}
        mock_get_pending.return_value = {
            "delivery_fee": expected_fee,
            "sender_id": "user-123",
            "delivery_data": {}
        }
        
        await process_successful_delivery_payment(
            tx_ref=tx_ref,
            paid_amount=paid_amount,
            flw_ref="flw-123",
            supabase=mock_supabase
        )
        
        # Should have returned early and deleted pending
        mock_delete_pending.assert_called_once()
        # Should NOT have tried to insert into delivery_orders
        try:
            mock_supabase.table.assert_any_call("delivery_orders")
            pytest.fail("Should not have called delivery_orders table")
        except AssertionError:
            pass
