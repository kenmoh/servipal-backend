from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from pydantic import BaseModel
from app.schemas.admin_schemas import PaginationMeta


class SenderSnippet(BaseModel):
    id: UUID
    full_name: str | None = None
    email: str | None = None
    phone_number: str | None = None
    profile_image_url: str | None = None


class RiderSnippet(BaseModel):
    id: UUID
    full_name: str | None = None
    phone_number: str | None = None
    bike_number: str | None = None
    profile_image_url: str | None = None


class DispatchSnippet(BaseModel):
    id: UUID
    business_name: str | None = None
    phone_number: str | None = None
    profile_image_url: str | None = None


class DeliveryOrderSummary(BaseModel):
    id: UUID
    order_number: int
    tx_ref: str | None = None
    sender_id: UUID
    rider_id: UUID | None = None
    dispatch_id: UUID | None = None
    package_name: str
    delivery_type: str
    delivery_status: str
    payment_status: str | None = None
    escrow_status: str | None = None
    delivery_fee: Decimal = Decimal("0.00")
    total_price: Decimal = Decimal("0.00")
    amount_due_dispatch: Decimal = Decimal("0.00")
    has_dispute: bool = False
    has_review: bool = False
    is_sender_cancelled: bool = False
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class DeliveryOrderDetail(DeliveryOrderSummary):
    receiver_phone: str
    sender_phone_number: str | None = None
    rider_phone_number: str | None = None
    pickup_location: str
    destination: str
    distance: Decimal = Decimal("0.00")
    duration: str | None = None
    description: str | None = None
    additional_info: str | None = None
    package_image_url: str | None = None
    image_url: str | None = None
    pickup_coordinates: dict[str, Any] | None = None
    dropoff_coordinates: dict[str, Any] | None = None
    last_known_rider_coordinates: dict[str, Any] | None = None
    order_type: Any | None = None
    flw_ref: str | None = None
    cancel_reason: str | None = None
    cancelled_by: str | None = None
    cancelled_at: datetime | None = None
    dispute_id: UUID | None = None
    is_deleted: bool = False
    sender: SenderSnippet | None = None
    rider: RiderSnippet | None = None
    dispatch: DispatchSnippet | None = None


class DeliveryOrderListResponse(BaseModel):
    data: list[DeliveryOrderSummary]
    meta: PaginationMeta


class DeliveryOrderFilters(BaseModel):
    delivery_status: str | None = None
    payment_status: str | None = None
    escrow_status: str | None = None
    delivery_type: str | None = None
    rider_id: UUID | None = None
    dispatch_id: UUID | None = None
    sender_id: UUID | None = None
    has_dispute: bool | None = None
    is_sender_cancelled: bool | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    search: str | None = None  # order_number, tx_ref, package_name
