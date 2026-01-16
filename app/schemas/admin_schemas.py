from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Literal, Dict, Any
from datetime import datetime
from uuid import UUID
from decimal import Decimal
from app.schemas.user_schemas import UserType

# ========================
# USER MANAGEMENT SCHEMAS
# ========================


class AdminUserUpdate(BaseModel):
    """Update user profile - admin only"""

    full_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone_number: Optional[str] = None
    user_type: Optional[UserType] = None
    is_verified: Optional[bool] = None
    is_blocked: Optional[bool] = None
    account_status: Optional[str] = None
    store_name: Optional[str] = None
    business_name: Optional[str] = None
    business_address: Optional[str] = None


class AdminUserResponse(BaseModel):
    """Extended user response for admin dashboard"""

    id: UUID
    email: Optional[str]
    phone_number: str
    full_name: Optional[str]
    user_type: UserType
    store_name: Optional[str]
    business_name: Optional[str]
    profile_image_url: Optional[str]
    is_online: bool
    is_verified: bool
    is_blocked: bool
    account_status: str
    created_at: datetime
    last_seen_at: Optional[datetime]
    total_orders: Optional[int] = 0
    total_spent: Optional[Decimal] = 0
    total_earned: Optional[Decimal] = 0

    class Config:
        from_attributes = True


class UserFilterParams(BaseModel):
    """Filters for user listing"""

    user_type: Optional[UserType] = None
    is_verified: Optional[bool] = None
    is_blocked: Optional[bool] = None
    account_status: Optional[str] = None
    search: Optional[str] = None  # Search in name, email, phone
    created_from: Optional[datetime] = None
    created_to: Optional[datetime] = None


class UsersListResponse(BaseModel):
    """Paginated users list"""

    users: List[AdminUserResponse]
    total: int
    page: int
    page_size: int


# ========================
# ORDER MANAGEMENT SCHEMAS
# ========================


class OrderFilterParams(BaseModel):
    """Filters for order listing"""

    order_type: Optional[Literal["food", "delivery", "laundry"]] = None
    status: Optional[str] = None
    payment_status: Optional[str] = None
    customer_id: Optional[UUID] = None
    vendor_id: Optional[UUID] = None
    rider_id: Optional[UUID] = None
    created_from: Optional[datetime] = None
    created_to: Optional[datetime] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None


class AdminOrderResponse(BaseModel):
    """Order details for admin"""

    id: UUID
    order_type: str
    customer_id: UUID
    customer_name: Optional[str]
    vendor_id: Optional[UUID]
    vendor_name: Optional[str]
    rider_id: Optional[UUID]
    rider_name: Optional[str]
    status: str
    payment_status: str
    total_amount: Decimal
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class OrdersListResponse(BaseModel):
    """Paginated orders list"""

    orders: List[AdminOrderResponse]
    total: int
    page: int
    page_size: int


class OrderStatusUpdate(BaseModel):
    """Update order status"""

    status: str
    notes: Optional[str] = None


# ========================
# TRANSACTION MANAGEMENT SCHEMAS
# ========================


class TransactionFilterParams(BaseModel):
    """Filters for transaction listing"""

    transaction_type: Optional[str] = None
    status: Optional[str] = None
    from_user_id: Optional[UUID] = None
    to_user_id: Optional[UUID] = None
    created_from: Optional[datetime] = None
    created_to: Optional[datetime] = None
    min_amount: Optional[Decimal] = None
    max_amount: Optional[Decimal] = None


class AdminTransactionResponse(BaseModel):
    """Transaction details for admin"""

    id: UUID
    tx_ref: str
    amount: Decimal
    transaction_type: str
    status: str
    payment_method: Optional[str]
    from_user_id: Optional[UUID]
    from_user_name: Optional[str]
    to_user_id: Optional[UUID]
    to_user_name: Optional[str]
    created_at: datetime
    details: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True


class TransactionsListResponse(BaseModel):
    """Paginated transactions list"""

    transactions: List[AdminTransactionResponse]
    total: int
    page: int
    page_size: int


# ========================
# WALLET MANAGEMENT SCHEMAS
# ========================


class AdminWalletResponse(BaseModel):
    """Wallet details for admin"""

    id: UUID
    user_id: UUID
    user_name: Optional[str]
    user_type: UserType
    balance: Decimal
    escrow_balance: Decimal
    total_deposited: Decimal
    total_withdrawn: Decimal
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class WalletAdjustmentRequest(BaseModel):
    """Adjust wallet balance (admin only)"""

    user_id: UUID
    amount: Decimal
    adjustment_type: Literal["credit", "debit"]
    reason: str
    notes: Optional[str] = None


class WalletsListResponse(BaseModel):
    """Paginated wallets list"""

    wallets: List[AdminWalletResponse]
    total: int
    page: int
    page_size: int


# ========================
# ANALYTICS & DASHBOARD SCHEMAS
# ========================


class DashboardStatsResponse(BaseModel):
    """Overall dashboard statistics"""

    total_users: int
    active_users: int
    blocked_users: int
    total_orders: int
    pending_orders: int
    completed_orders: int
    total_revenue: Decimal
    total_transactions: int
    pending_withdrawals: Decimal
    users_by_type: Dict[str, int]
    orders_by_type: Dict[str, int]
    revenue_today: Decimal
    revenue_this_week: Decimal
    revenue_this_month: Decimal


class RevenueReportParams(BaseModel):
    """Parameters for revenue report"""

    start_date: datetime
    end_date: datetime
    group_by: Optional[Literal["day", "week", "month"]] = "day"


class RevenueReportResponse(BaseModel):
    """Revenue report data"""

    period: str
    total_revenue: Decimal
    transaction_count: int
    breakdown: List[Dict[str, Any]]


# ========================
# AUDIT LOG SCHEMAS
# ========================


class AuditLogFilterParams(BaseModel):
    """Filters for audit log"""

    entity_type: Optional[str] = None
    action: Optional[str] = None
    actor_id: Optional[UUID] = None
    actor_type: Optional[str] = None
    created_from: Optional[datetime] = None
    created_to: Optional[datetime] = None


class AuditLogResponse(BaseModel):
    """Audit log entry"""

    id: UUID
    entity_type: str
    entity_id: UUID
    action: str
    old_value: Optional[Dict[str, Any]]
    new_value: Optional[Dict[str, Any]]
    change_amount: Optional[Decimal]
    actor_id: Optional[UUID]
    actor_type: str
    notes: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AuditLogsListResponse(BaseModel):
    """Paginated audit logs"""

    logs: List[AuditLogResponse]
    total: int
    page: int
    page_size: int


# ========================
# VENDOR/RIDER VERIFICATION SCHEMAS
# ========================


class VerificationRequest(BaseModel):
    """Verify or reject vendor/rider"""

    user_id: UUID
    verified: bool
    reason: Optional[str] = None


# ========================
# SYSTEM SETTINGS SCHEMAS
# ========================


class SystemSettingUpdate(BaseModel):
    """Update system setting"""

    key: str
    value: Any
    description: Optional[str] = None


class SystemSettingResponse(BaseModel):
    """System setting"""

    key: str
    value: Any
    description: Optional[str]
    updated_at: datetime
    updated_by: Optional[UUID]


# ========================
# PAGINATION SCHEMAS
# ========================


class PaginationParams(BaseModel):
    """Standard pagination parameters"""

    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=100)
