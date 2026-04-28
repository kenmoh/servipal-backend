from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterable

from app.schemas.fraud_schemas import RiskAction, RiskAssessment, RiskLevel
from app.services.fraud.rules import RuleHit


@dataclass(frozen=True)
class RiskPolicy:
    review_threshold: int = 40
    block_threshold: int = 70


def _clamp_score(score: int) -> int:
    return max(0, min(100, int(score)))


class RiskEngine:
    """
    Centralized rules-based scoring engine.

    Keep this deterministic and fast. Data-fetching lives in FraudService; the engine just aggregates rule hits.
    """

    def __init__(self, policy: RiskPolicy | None = None):
        self.policy = policy or RiskPolicy()

    def finalize(self, hits: Iterable[RuleHit], *, extra_signals: dict[str, Any] | None = None) -> RiskAssessment:
        total = 0
        reasons: list[str] = []
        signals: dict[str, Any] = {}

        for hit in hits:
            if not hit:
                continue
            total += int(hit.score)
            reasons.append(hit.reason)
            if hit.meta is not None:
                signals[hit.key] = hit.meta
            else:
                signals[hit.key] = True

        score = _clamp_score(total)

        if score >= self.policy.block_threshold:
            action = RiskAction.BLOCK
            level = RiskLevel.HIGH
        elif score >= self.policy.review_threshold:
            action = RiskAction.REVIEW
            level = RiskLevel.MEDIUM
        else:
            action = RiskAction.ALLOW
            level = RiskLevel.LOW

        merged_signals = {**signals, **(extra_signals or {})} if (signals or extra_signals) else None
        return RiskAssessment(
            risk_score=score,
            risk_level=level,
            action=action,
            reasons=reasons,
            signals=merged_signals,
        )


def default_high_amount_threshold(*, user_is_new: bool) -> Decimal:
    # Keep initial heuristics explicit and cheap; can be replaced by dynamic thresholds later.
    return Decimal("20000") if user_is_new else Decimal("50000")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)

