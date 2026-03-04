
from datetime import datetime
from typing import Any
from uuid import UUID
from pydantic import BaseModel, field_validator
from app.schemas.admin_schemas import PaginationMeta


DISPUTE_STATUSES = {"OPEN", "UNDER_REVIEW", "ESCALATED", "RESOLVED", "CLOSED"}


class DisputePartySnippet(BaseModel):
    id: UUID
    full_name: str | None = None
    business_name: str | None = None
    store_name: str | None = None
    profile_image_url: str | None = None
    user_type: str | None = None

    @property
    def display_name(self) -> str:
        return self.full_name or self.business_name or self.store_name or "Unknown"


class DisputeMessageItem(BaseModel):
    id: UUID
    dispute_id: UUID
    sender_id: UUID
    message_text: str
    attachments: list[str] | None = None
    is_read: bool = False     
    created_at: datetime
    sender: DisputePartySnippet | None = None


class DisputeSummary(BaseModel):
    id: UUID
    order_id: UUID
    order_type: str | None = None
    initiator_id: UUID
    respondent_id: UUID
    reason: str
    status: str
    last_message_text: str | None = None
    last_message_at: datetime | None = None
    unread_count: int = 0          #  per-caller, from tracking table
    resolved_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DisputeDetail(DisputeSummary):
    resolution_notes: str | None = None
    resolved_by_id: UUID | None = None
    initiator: DisputePartySnippet | None = None
    respondent: DisputePartySnippet | None = None
    resolved_by: DisputePartySnippet | None = None
    messages: list[DisputeMessageItem] = []


class DisputeListResponse(BaseModel):
    data: list[DisputeSummary]
    meta: PaginationMeta


class DisputeFilters(BaseModel):
    status: str | None = None
    order_type: str | None = None
    initiator_id: UUID | None = None
    respondent_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    search: str | None = None  


# ── Write operations ──────────────────────────────────────────────────────────

class AddDisputeMessageRequest(BaseModel):
    message_text: str
    attachments: list[str] | None = None



class UpdateDisputeStatusRequest(BaseModel):
    status: str
    resolution_notes: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        if v not in DISPUTE_STATUSES:
            raise ValueError(f"status must be one of {DISPUTE_STATUSES}")
        return v


class DisputeMessageResponse(BaseModel):
    id: UUID
    dispute_id: UUID
    sender_id: UUID
    message_text: str
    attachments: list[str] | None = None
    is_read: bool = False
    created_at: datetime