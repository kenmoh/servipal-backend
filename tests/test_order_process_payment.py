import pytest
from fastapi import HTTPException
from postgrest.exceptions import APIError

from app.common.order import ProcessPaymentRequest, process_payment
from app.common import order as order_module


class _DuplicateAPIError(APIError):
    def __init__(self, message: str):
        self.message = message

    def __str__(self):
        return self.message


@pytest.mark.asyncio
async def test_process_payment_returns_already_processed_when_handler_reports_it(monkeypatch):
    async def _handler(**_kwargs):
        return {"status": "already_processed"}

    monkeypatch.setattr(order_module, "HANDLER_MAP", {"FOOD-": _handler})

    result = await process_payment(
        data=ProcessPaymentRequest(
            tx_ref="FOOD-abc",
            paid_amount=1000.0,
            flw_ref="flw-1",
            payment_method="CARD",
        ),
        supabase=None,
    )

    assert result["status"] == "already_processed"


@pytest.mark.asyncio
async def test_process_payment_returns_already_processed_for_duplicate_constraint(monkeypatch):
    async def _handler(**_kwargs):
        raise _DuplicateAPIError("duplicate key value violates unique constraint")

    monkeypatch.setattr(order_module, "HANDLER_MAP", {"FOOD-": _handler})

    result = await process_payment(
        data=ProcessPaymentRequest(
            tx_ref="FOOD-xyz",
            paid_amount=2000.0,
            flw_ref="flw-2",
            payment_method="BANK_TRANSFER",
        ),
        supabase=None,
    )

    assert result["status"] == "already_processed"


@pytest.mark.asyncio
async def test_process_payment_rejects_unknown_prefix(monkeypatch):
    monkeypatch.setattr(order_module, "HANDLER_MAP", {"FOOD-": lambda **_kwargs: None})

    with pytest.raises(HTTPException) as exc:
        await process_payment(
            data=ProcessPaymentRequest(
                tx_ref="UNKNOWN-1",
                paid_amount=500.0,
                flw_ref="flw-3",
                payment_method="CARD",
            ),
            supabase=None,
        )

    assert exc.value.status_code == 400
