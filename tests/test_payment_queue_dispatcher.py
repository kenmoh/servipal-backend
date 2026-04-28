import pytest

from app.services import payment_queue_dispatcher


class _FakeRPCExecutor:
    def __init__(self, data):
        self._data = data

    async def execute(self):
        class _Result:
            def __init__(self, data):
                self.data = data

        return _Result(self._data)


class _FakeSchemaClient:
    def __init__(self, data):
        self._data = data
        self.rpc_name = None
        self.rpc_payload = None

    def rpc(self, rpc_name, payload):
        self.rpc_name = rpc_name
        self.rpc_payload = payload
        return _FakeRPCExecutor(self._data)


class _FakeSupabase:
    def __init__(self, queue_msg_id):
        self.queue_msg_id = queue_msg_id
        self.schema_name = None
        self.schema_client = _FakeSchemaClient(queue_msg_id)

    def schema(self, name):
        self.schema_name = name
        return self.schema_client


@pytest.mark.asyncio
async def test_enqueue_successful_payment_dual_mode(monkeypatch):
    supabase = _FakeSupabase(queue_msg_id=42)

    monkeypatch.setattr(
        payment_queue_dispatcher.settings, "PAYMENT_QUEUE_BACKEND", "dual"
    )
    monkeypatch.setattr(
        payment_queue_dispatcher,
        "enqueue_payment_order_creation_task",
        lambda message: "task-abc",
    )

    result = await payment_queue_dispatcher.enqueue_successful_payment_for_processing(
        supabase=supabase,
        tx_ref="FOOD-123",
        paid_amount="5000",
        flw_ref="FLW-REF",
        payment_type="card",
        tx_id=99,
    )

    assert result["backend"] == "dual"
    assert result["supabase_msg_id"] == 42
    assert result["celery_task_id"] == "task-abc"
    assert supabase.schema_name == "pgmq_public"
    assert supabase.schema_client.rpc_name == "send"
    assert supabase.schema_client.rpc_payload["queue_name"] == "payment_queue"


@pytest.mark.asyncio
async def test_enqueue_successful_payment_dual_mode_partial_failure(monkeypatch):
    supabase = _FakeSupabase(queue_msg_id=77)

    monkeypatch.setattr(
        payment_queue_dispatcher.settings, "PAYMENT_QUEUE_BACKEND", "dual"
    )

    def _raise_celery_error(_message):
        raise RuntimeError("celery down")

    monkeypatch.setattr(
        payment_queue_dispatcher,
        "enqueue_payment_order_creation_task",
        _raise_celery_error,
    )

    result = await payment_queue_dispatcher.enqueue_successful_payment_for_processing(
        supabase=supabase,
        tx_ref="PRODUCT-123",
        paid_amount="12000",
        flw_ref="FLW-REF-2",
        payment_type="bank_transfer",
        tx_id=100,
    )

    assert result["backend"] == "dual"
    assert result["supabase_msg_id"] == 77
    assert result["celery_task_id"] is None


@pytest.mark.asyncio
async def test_enqueue_successful_payment_celery_only_failure_raises(monkeypatch):
    supabase = _FakeSupabase(queue_msg_id=5)

    monkeypatch.setattr(
        payment_queue_dispatcher.settings, "PAYMENT_QUEUE_BACKEND", "celery"
    )

    def _raise_celery_error(_message):
        raise RuntimeError("celery down")

    monkeypatch.setattr(
        payment_queue_dispatcher,
        "enqueue_payment_order_creation_task",
        _raise_celery_error,
    )

    with pytest.raises(RuntimeError):
        await payment_queue_dispatcher.enqueue_successful_payment_for_processing(
            supabase=supabase,
            tx_ref="LAUNDRY-123",
            paid_amount="3500",
            flw_ref="FLW-REF-3",
            payment_type="bank",
            tx_id=200,
        )
