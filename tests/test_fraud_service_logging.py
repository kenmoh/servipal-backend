from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.schemas.fraud_schemas import FraudEvaluationEvent
from app.services.fraud import FraudService


@pytest.mark.asyncio
async def test_fraud_service_logs_decision(mock_supabase):
    # Seed profile rows so FraudService can compute "new account" etc.
    uid = str(uuid4())
    vid = str(uuid4())
    now = datetime.now(timezone.utc)

    mock_supabase._data["profiles"].append(
        {
            "id": uid,
            "created_at": (now - timedelta(hours=1)).isoformat(),
            "is_verified": False,
            "user_type": "CUSTOMER",
            "metadata": {},
        }
    )
    mock_supabase._data["profiles"].append(
        {
            "id": vid,
            "created_at": (now - timedelta(days=1)).isoformat(),
            "is_verified": False,
            "user_type": "RESTAURANT_VENDOR",
            "metadata": {},
        }
    )

    service = FraudService(mock_supabase)
    assessment = await service.evaluate(
        event=FraudEvaluationEvent.PAYMENT_INITIATION,
        user_id=uid,
        vendor_id=vid,
        amount=Decimal("60000"),
        tx_ref="FOOD-TEST",
        order_type="FOOD",
    )

    assert assessment.risk_score >= 40
    assert len(mock_supabase._data["fraud_logs"]) == 1
    row = mock_supabase._data["fraud_logs"][0]
    assert row["event"] == FraudEvaluationEvent.PAYMENT_INITIATION.value
    assert row["user_id"] == uid
    assert row["vendor_id"] == vid
