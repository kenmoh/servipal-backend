from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.schemas.fraud_schemas import RiskAction, RiskLevel
from app.services.fraud.risk_engine import RiskEngine
from app.services.fraud.rules import (
    rule_completion_too_fast,
    rule_high_amount,
    rule_new_account,
    rule_new_vendor,
    rule_unverified_user,
    rule_unverified_vendor,
    rule_velocity,
)


def _utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def test_risk_engine_finalize_thresholds():
    engine = RiskEngine()
    now = datetime.now(timezone.utc)

    hits = [
        rule_new_account(created_at=now - timedelta(hours=1), now=now, hours=72, weight=20),
        rule_high_amount(amount=Decimal("60000"), threshold=Decimal("50000"), weight=25),
    ]
    assessment = engine.finalize([h for h in hits if h is not None])
    assert assessment.risk_score == 45
    assert assessment.risk_level == RiskLevel.MEDIUM
    assert assessment.action == RiskAction.REVIEW
    assert "New account" in " ".join(assessment.reasons)


def test_rules_new_account_and_unverified():
    now = datetime.now(timezone.utc)
    hit = rule_new_account(created_at=now - timedelta(hours=2), now=now, hours=72, weight=20)
    assert hit is not None
    assert hit.key == "user_new_account"

    v = rule_unverified_user(is_verified=False, weight=15)
    assert v is not None
    assert v.key == "user_unverified"


def test_rules_vendor_new_and_unverified():
    now = datetime.now(timezone.utc)
    hit = rule_new_vendor(created_at=now - timedelta(days=1), now=now, days=7, weight=15)
    assert hit is not None
    assert hit.key == "vendor_new_account"

    v = rule_unverified_vendor(is_verified=False, weight=15)
    assert v is not None
    assert v.key == "vendor_unverified"


def test_rule_velocity():
    hit = rule_velocity(recent_count=5, window_minutes=10, max_allowed=3, weight=20)
    assert hit is not None
    assert hit.key == "velocity"


def test_rule_completion_too_fast_parses_iso_strings():
    start = _utc(datetime.now(timezone.utc) - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    end = _utc(datetime.now(timezone.utc)).isoformat().replace("+00:00", "Z")
    hit = rule_completion_too_fast(started_at=start, completed_at=end, min_minutes=10, weight=25)
    assert hit is not None
    assert hit.key == "completion_too_fast"

