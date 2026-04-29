import pytest

from app.services.payment_idempotency import check_payment_already_processed


@pytest.mark.asyncio
async def test_idempotency_detects_completed_intent(mock_supabase):
    await mock_supabase.table("transaction_intents").insert(
        {"tx_ref": "FOOD-123", "status": "COMPLETED"}
    ).execute()

    processed, source = await check_payment_already_processed(
        supabase=mock_supabase, tx_ref="FOOD-123"
    )

    assert processed is True
    assert source == "transaction_intents"


@pytest.mark.asyncio
async def test_idempotency_detects_transfer_or_transaction_records(mock_supabase):
    await mock_supabase.table("transaction_intents").insert(
        {"tx_ref": "TOPUP-123", "status": "PENDING"}
    ).execute()
    await mock_supabase.table("transfers").insert(
        {"tx_ref": "TOPUP-123", "id": "tr-1"}
    ).execute()

    processed, source = await check_payment_already_processed(
        supabase=mock_supabase, tx_ref="TOPUP-123"
    )

    assert processed is True
    assert source == "transfers"


@pytest.mark.asyncio
async def test_idempotency_returns_false_for_new_tx_ref(mock_supabase):
    processed, source = await check_payment_already_processed(
        supabase=mock_supabase, tx_ref="LAUNDRY-123"
    )

    assert processed is False
    assert source is None
