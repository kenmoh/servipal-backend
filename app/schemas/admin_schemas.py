from enum import Enum
from datetime import datetime, date
from typing import Literal
from decimal import Decimal
from typing import Any
from uuid import UUID
from pydantic import BaseModel, EmailStr, Field, field_validator
from app.schemas.user_schemas import UserType


class AccountStatus(str, Enum):
    PENDING = "PENDING"
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    DELETED = "DELETED"


MANAGEMENT_USER_TYPES = {UserType.ADMIN, UserType.MODERATOR, UserType.SUPER_ADMIN}


# ── Base ────────────────────────────────────────────────────────────────────
class ProfileBase(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone_number: str
    user_type: UserType = UserType.CUSTOMER
    account_status: AccountStatus = AccountStatus.PENDING
    is_blocked: bool = False
    is_verified: bool = False
    state: str | None = None
    profile_image_url: str | None = None


# ── Admin / Management user creation (SUPER_ADMIN only) ─────────────────────
class ManagementUserCreate(BaseModel):
    email: str
    phone_number: str
    full_name: str
    user_type: Literal["ADMIN", "MODERATOR"] = Field(
        ..., description="Must be ADMIN or MODERATOR"
    )
    password: str = Field(..., min_length=8)

    @field_validator("user_type")
    @classmethod
    def validate_management_type(cls, v: UserType) -> UserType:
        allowed = {UserType.ADMIN, UserType.MODERATOR}
        if v not in allowed:
            raise ValueError("user type must be ADMIN or MODERATOR")
        return v


# ── Filters & Pagination ────────────────────────────────────────────────────
class UserFilterParams(BaseModel):
    """Filters for listing users."""
    user_type: UserType | None = None
    account_status: AccountStatus | None = None
    is_blocked: bool | None = None
    search: str | None = None


class PaginationParams(BaseModel):
    """Pagination parameters."""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=25, ge=1, le=100)


# ── Block / Unblock ──────────────────────────────────────────────────────────
class BlockUserRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


# ── Response shapes ──────────────────────────────────────────────────────────
class ProfileSummary(BaseModel):
    """Lightweight profile for list views."""

    id: UUID
    full_name: str | None
    email: str | None
    phone_number: str
    user_type: UserType
    account_status: AccountStatus
    is_blocked: bool
    is_verified: bool
    is_online: bool
    average_rating: Decimal
    review_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class ProfileDetail(ProfileSummary):
    """Full profile for detail view."""

    business_name: str | None = None
    store_name: str | None = None
    business_address: str | None = None
    state: str | None = None
    bank_name: str | None = None
    bank_account_number: str | None = None
    account_holder_name: str | None = None
    bike_number: str | None = None
    dispatcher_id: UUID | None = None
    has_delivery: bool = False
    total_delivery_count: Decimal | None = None
    daily_delivery_count: int = 0
    total_distance_travelled: Decimal = Decimal("0.0")
    order_cancel_count: int = 0
    delivery_order_cancel_count: int = 0
    suspension_end_date: datetime | None = None
    last_seen_at: datetime | None = None
    last_delivery_date: date | None = None
    profile_image_url: str | None = None
    backdrop_image_url: str | None = None
    opening_hour: str | None = None
    closing_hour: str | None = None
    metadata: dict[str, Any] | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


# ── List / pagination wrappers ───────────────────────────────────────────────
class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int


class ProfileListResponse(BaseModel):
    data: list[ProfileSummary]
    meta: PaginationMeta


# ── Auth ─────────────────────────────────────────────────────────────────────
class AdminLoginRequest(BaseModel):
    email: str
    password: str


class AuditLogFilters(BaseModel):
    entity_type: str | None = None
    entity_id: UUID | None = None
    action: str | None = None
    actor_id: UUID | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None


class AuditLogCreate(BaseModel):
    entity_type: str
    entity_id: UUID
    action: str
    old_value: dict | None = None
    new_value: dict | None = None
    change_amount: Decimal | None = None
    actor_id: UUID | None = None
    actor_type: str = "SYSTEM"
    notes: str | None = None


class AuditLogEntry(AuditLogCreate):
    id: UUID
    ip_address: str | None = None
    user_agent: str | None = None
    created_at: datetime


class AuditLogListResponse(BaseModel):
    data: list[AuditLogEntry]
    meta: PaginationMeta


class TransactionItem(BaseModel):
    id: UUID
    tx_ref: str | None = None
    wallet_id: UUID | None = None
    amount: Decimal = Decimal("0.00")
    transaction_type: str
    payment_status: str | None = None
    payment_method: str | None = None
    from_user_id: UUID | None = None
    to_user_id: UUID | None = None
    order_id: UUID | None = None
    order_type: str | None = None
    details: dict[str, Any] = {}
    released_at: datetime | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class WalletSummary(BaseModel):
    id: UUID
    user_id: UUID
    balance: Decimal
    escrow_balance: Decimal
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class WalletWithTransactions(WalletSummary):
    transactions: list[TransactionItem] = []


class WalletListResponse(BaseModel):
    data: list[WalletWithTransactions]
    meta: PaginationMeta


# ── Contacts ─────────────────────────────────────────────────────────────────
class Contact(BaseModel):
    id: UUID
    full_name: str
    email: str
    category: str
    subject: str
    message: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ContactListResponse(BaseModel):
    data: list[Contact]
    meta: PaginationMeta
