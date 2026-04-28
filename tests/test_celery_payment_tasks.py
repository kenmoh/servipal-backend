import pytest

from app.celery_queue.tasks import normalize_payment_payload


def test_normalize_payment_payload_success():
    payload = {
        "tx_ref": "FOOD-0001",
        "paid_amount": "1500.129",
        "flw_ref": "FLW-123",
        "payment_method": "card",
    }

    result = normalize_payment_payload(payload)

    assert result.tx_ref == "FOOD-0001"
    assert result.flw_ref == "FLW-123"
    assert result.payment_method == "CARD"
    assert result.paid_amount == 1500.13


@pytest.mark.parametrize(
    "payload",
    [
        {"paid_amount": "1000", "flw_ref": "x", "payment_method": "CARD"},
        {"tx_ref": "FOOD-2", "flw_ref": "x", "payment_method": "CARD"},
        {
            "tx_ref": "FOOD-2",
            "paid_amount": "0",
            "flw_ref": "x",
            "payment_method": "CARD",
        },
        {
            "tx_ref": "FOOD-2",
            "paid_amount": "abc",
            "flw_ref": "x",
            "payment_method": "CARD",
        },
    ],
)
def test_normalize_payment_payload_validation_errors(payload):
    with pytest.raises(ValueError):
        normalize_payment_payload(payload)
