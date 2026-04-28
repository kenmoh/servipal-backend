from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class RiskAction(str, Enum):
    ALLOW = "allow"
    REVIEW = "review"
    BLOCK = "block"


class FraudEvaluationEvent(str, Enum):
    BOOKING_CREATE = "BOOKING_CREATE"
    PAYMENT_INITIATION = "PAYMENT_INITIATION"
    PAYMENT_CONFIRMATION = "PAYMENT_CONFIRMATION"
    SERVICE_COMPLETION = "SERVICE_COMPLETION"
    PAYOUT_REQUEST = "PAYOUT_REQUEST"


class RiskAssessment(BaseModel):
    risk_score: int = Field(..., ge=0, le=100)
    risk_level: RiskLevel
    action: RiskAction
    reasons: list[str] = Field(default_factory=list)

    # Optional structured debugging info (kept small)
    signals: dict[str, Any] | None = None


class FraudLogCreate(BaseModel):
    event: FraudEvaluationEvent
    user_id: UUID | None = None
    vendor_id: UUID | None = None
    transaction_id: UUID | None = None
    order_id: UUID | None = None
    order_type: str | None = None
    tx_ref: str | None = None
    amount: float | None = None

    risk_score: int = Field(..., ge=0, le=100)
    risk_level: Literal["low", "medium", "high"]
    action: Literal["allow", "review", "block"]
    reasons: list[str] = Field(default_factory=list)

    # request context
    ip_address: str | None = None
    user_agent: str | None = None

    # lifecycle for admin review/overrides
    status: Literal["OPEN", "APPROVED", "REJECTED", "AUTO_ALLOWED", "AUTO_BLOCKED"] = "OPEN"
    reviewed_by: UUID | None = None
    reviewed_at: datetime | None = None
    review_notes: str | None = None

    details: dict[str, Any] | None = None


class FraudLogEntry(FraudLogCreate):
    id: UUID
    created_at: datetime


class FraudLogListResponse(BaseModel):
    data: list[FraudLogEntry]
    total: int


class FraudReviewRequest(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    notes: str | None = Field(default=None, max_length=1000)

