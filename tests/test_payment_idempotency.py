import pytest

from app.services.payment_idempotency import check_payment_already_processed


class _FakeResult:
    def __init__(self, data):
        self.data = data


class _FakeTableQuery:
    def __init__(self, table_name, dataset):
        self.table_name = table_name
        self.dataset = dataset
        self.tx_ref = None

    def select(self, _column):
        return self

    def eq(self, _column, value):
        self.tx_ref = value
        return self

    def limit(self, _count):
        return self

    async def execute(self):
        table_rows = self.dataset.get(self.table_name, {})
        row = table_rows.get(self.tx_ref)
        return _FakeResult([row] if row else [])


class _FakeSupabase:
    def __init__(self, dataset):
        self.dataset = dataset

    def table(self, table_name):
        return _FakeTableQuery(table_name, self.dataset)


@pytest.mark.asyncio
async def test_idempotency_detects_completed_intent():
    supabase = _FakeSupabase(
        {
            "transaction_intents": {"FOOD-123": {"status": "COMPLETED"}},
            "transactions": {},
            "transfers": {},
        }
    )

    processed, source = await check_payment_already_processed(
        supabase=supabase, tx_ref="FOOD-123"
    )

    assert processed is True
    assert source == "transaction_intents"


@pytest.mark.asyncio
async def test_idempotency_detects_transfer_or_transaction_records():
    supabase = _FakeSupabase(
        {
            "transaction_intents": {"TOPUP-123": {"status": "PENDING"}},
            "transactions": {},
            "transfers": {"TOPUP-123": {"id": "tr-1"}},
        }
    )

    processed, source = await check_payment_already_processed(
        supabase=supabase, tx_ref="TOPUP-123"
    )

    assert processed is True
    assert source == "transfers"


@pytest.mark.asyncio
async def test_idempotency_returns_false_for_new_tx_ref():
    supabase = _FakeSupabase(
        {
            "transaction_intents": {},
            "transactions": {},
            "transfers": {},
        }
    )

    processed, source = await check_payment_already_processed(
        supabase=supabase, tx_ref="LAUNDRY-123"
    )

    assert processed is False
    assert source is None
