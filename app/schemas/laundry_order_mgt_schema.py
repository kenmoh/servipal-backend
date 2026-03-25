from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from pydantic import BaseModel
from app.schemas.admin_schemas import PaginationMeta
from app.schemas.restaurant_order_mgt_admin_schema import (
    CustomerSnippet,
    VendorSnippet,
)  # reuse


class LaundryOrderItem(BaseModel):
    order_id: UUID
    item_id: UUID
    quantity: int = 1
    images: list[Any] | None = None
    created_at: datetime


class LaundryOrderSummary(BaseModel):
    id: UUID
    order_number: int | None = None
    tx_ref: str | None = None
    customer_id: UUID | None = None
    vendor_id: UUID | None = None
    total_price: Decimal = Decimal("0.00")
    subtotal: Decimal = Decimal("0.00")
    grand_total: Decimal = Decimal("0.00")
    amount_due_vendor: Decimal = Decimal("0.00")
    order_status: str | None = None
    payment_status: str | None = None
    laundry_type: str | None = None
    require_delivery: bool = False
    has_dispute: bool = False
    has_review: bool = False
    delivery_fee: Decimal = Decimal("0.00")
    delivery_option: str | None = None
    order_type: str | None = None
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class LaundryOrderDetail(LaundryOrderSummary):
    pickup_location: str | None = None
    destination: str | None = None
    distance: str | None = None
    vendor_pickup_dropoff_charge: Decimal = Decimal("0.00")
    cancel_reason: str | None = None
    additional_info: str | None = None
    dispute_id: UUID | None = None
    is_deleted: bool = False
    customer: CustomerSnippet | None = None
    vendor: VendorSnippet | None = None
    items: list[LaundryOrderItem] = []


class LaundryOrderListResponse(BaseModel):
    data: list[LaundryOrderSummary]
    meta: PaginationMeta


class LaundryOrderFilters(BaseModel):
    order_status: str | None = None
    payment_status: str | None = None
    laundry_type: str | None = None
    vendor_id: UUID | None = None
    customer_id: UUID | None = None
    has_dispute: bool | None = None
    require_delivery: bool | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    search: str | None = None  # order_number or tx_ref
