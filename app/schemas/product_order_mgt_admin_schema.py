from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID
from pydantic import BaseModel, HttpUrl
from app.schemas.admin_schemas import PaginationMeta
from app.schemas.restaurant_order_mgt_admin_schema import CustomerSnippet, VendorSnippet


class ProductOrderItem(BaseModel):
    id: UUID
    order_id: UUID
    product_id: UUID
    name: str
    price: Decimal = Decimal("0.00")
    quantity: int = 1
    selected_size: list[Any] | None = None
    selected_color: list[Any] | None = None
    images: list[HttpUrl] | None = None
    created_at: datetime


class ProductOrderSummary(BaseModel):
    id: UUID
    order_number: int | None = None
    tx_ref: str | None = None
    customer_id: UUID | None = None
    vendor_id: UUID | None = None
    grand_total: Decimal = Decimal("0.00")
    amount_due_vendor: Decimal = Decimal("0.00")
    order_status: str | None = None
    payment_status: str | None = None
    escrow_status: str | None = None
    delivery_option: str | None = None
    shipping_cost: Decimal = Decimal("0.00")
    order_type: str | None = None
    has_dispute: bool = False
    has_review: bool = False
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class ProductOrderDetail(ProductOrderSummary):
    delivery_address: str | None = None
    additional_info: str | None = None
    cancel_reason: str | None = None
    dispute_id: UUID | None = None
    is_deleted: bool = False
    customer: CustomerSnippet | None = None
    vendor: VendorSnippet | None = None
    items: list[ProductOrderItem]


class ProductOrderListResponse(BaseModel):
    data: list[ProductOrderSummary]
    meta: PaginationMeta


class ProductOrderFilters(BaseModel):
    order_status: str | None = None
    payment_status: str | None = None
    escrow_status: str | None = None
    vendor_id: UUID | None = None
    customer_id: UUID | None = None
    has_dispute: bool | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    search: str | None = None
