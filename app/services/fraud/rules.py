from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class RuleHit:
    key: str
    score: int
    reason: str
    meta: dict[str, Any] | None = None


def _parse_dt(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc) if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        # Supabase returns ISO strings
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def rule_new_account(*, created_at: object, now: datetime, hours: int = 72, weight: int = 20) -> RuleHit | None:
    dt = _parse_dt(created_at)
    if not dt:
        return None
    if now - dt < timedelta(hours=hours):
        return RuleHit(
            key="user_new_account",
            score=weight,
            reason=f"New account (< {hours}h)",
            meta={"age_hours": round((now - dt).total_seconds() / 3600, 2)},
        )
    return None


def rule_unverified_user(*, is_verified: bool | None, weight: int = 15) -> RuleHit | None:
    if is_verified is False:
        return RuleHit(key="user_unverified", score=weight, reason="User is unverified")
    return None


def rule_new_vendor(*, created_at: object, now: datetime, days: int = 7, weight: int = 15) -> RuleHit | None:
    dt = _parse_dt(created_at)
    if not dt:
        return None
    if now - dt < timedelta(days=days):
        return RuleHit(
            key="vendor_new_account",
            score=weight,
            reason=f"New vendor (< {days}d)",
            meta={"age_days": round((now - dt).total_seconds() / 86400, 2)},
        )
    return None


def rule_unverified_vendor(*, is_verified: bool | None, weight: int = 15) -> RuleHit | None:
    if is_verified is False:
        return RuleHit(key="vendor_unverified", score=weight, reason="Vendor is unverified")
    return None


def rule_high_amount(
    *,
    amount: Decimal | float | int | str | None,
    threshold: Decimal,
    weight: int = 25,
) -> RuleHit | None:
    if amount is None:
        return None
    try:
        amt = Decimal(str(amount))
    except Exception:
        return None
    if amt > threshold:
        return RuleHit(
            key="tx_high_amount",
            score=weight,
            reason=f"High transaction amount (> {threshold})",
            meta={"amount": str(amt), "threshold": str(threshold)},
        )
    return None


def rule_velocity(
    *,
    recent_count: int,
    window_minutes: int,
    max_allowed: int,
    weight: int = 20,
) -> RuleHit | None:
    if recent_count > max_allowed:
        return RuleHit(
            key="velocity",
            score=weight,
            reason=f"High velocity activity ({recent_count} in {window_minutes}m)",
            meta={"recent_count": recent_count, "window_minutes": window_minutes, "max_allowed": max_allowed},
        )
    return None


def rule_completion_too_fast(
    *,
    started_at: object,
    completed_at: object,
    min_minutes: int = 10,
    weight: int = 25,
) -> RuleHit | None:
    start = _parse_dt(started_at)
    end = _parse_dt(completed_at)
    if not start or not end:
        return None
    minutes = (end - start).total_seconds() / 60
    if minutes < min_minutes:
        return RuleHit(
            key="completion_too_fast",
            score=weight,
            reason=f"Completed too quickly (< {min_minutes}m)",
            meta={"minutes": round(minutes, 2)},
        )
    return None

