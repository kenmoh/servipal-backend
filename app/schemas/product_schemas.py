from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from uuid import UUID
from decimal import Decimal
from datetime import datetime
from enum import Enum


# ───────────────────────────────────────────────
# Product Item (what sellers list)
# ───────────────────────────────────────────────


class ProductType(str, Enum):
    DIGITAL = "DIGITAL"
    PHYSICAL = "PHYSICAL"


class ProductItemCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    price: Decimal = Field(..., gt=0)
    product_type: ProductType = Field(
        description="DIGITAL or PHYSICAL", default=ProductType.PHYSICAL
    )
    stock: int = Field(..., ge=0, description="Initial stock quantity")
    sizes: Optional[List[str]] = Field(
        None, description="Available sizes e.g. ['S', 'M', 'L', 42]"
    )
    colors: Optional[List[str]] = Field(
        None, description="Available colors e.g. ['Red', 'Blue', '#000000']"
    )
    category_id: Optional[UUID] = None
    warranty: int = Field(default=0)
    shipping_cost: Decimal | None = None
    return_days: int = Field(default=0)
    images: List[str] = Field(default_factory=list, description="URLs after upload")


class ProductItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    stock: Optional[int] = None
    sizes: Optional[List[str]] = None
    colors: Optional[List[str]] = None
    category_id: Optional[UUID] = None


class ProductItemResponse(ProductItemCreate):
    id: UUID
    seller_id: UUID
    created_at: datetime
    updated_at: datetime


# ───────────────────────────────────────────────
# Product Order Creation (customer checkout)
# ───────────────────────────────────────────────
class ProductOrderItem(BaseModel):
    vendor_id: str
    item_id: UUID
    quantity: int = Field(..., ge=1)
    sizes: List[str] = None
    colors: List[str] = None
    images: List[str] = None


class ProductOrderCreate(BaseModel):
    item: ProductOrderItem = Field(..., description="Single product + quantity")
    delivery_option: Literal["PICKUP", "VENDOR_DELIVERY"]
    delivery_address: Optional[str] = Field(
        None, description="Full delivery address if VENDOR_DELIVERY"
    )
    additional_info: Optional[str] = Field(None, description="Extra notes/instructions")


class ProductOrderResponse(BaseModel):
    order_id: UUID
    tx_ref: str
    amount: float
    public_key: str
    currency: str = "NGN"
    customer: dict
    customization: dict
    message: str


# ───────────────────────────────────────────────
# Vendor Order Action
# ───────────────────────────────────────────────
class ProductVendorOrderAction(BaseModel):
    action: Literal["accept", "reject"]
    reason: Optional[str] = None


class ProductVendorOrderActionResponse(BaseModel):
    order_id: UUID
    order_status: str
    message: str


# ───────────────────────────────────────────────
# Vendor Mark Ready & Customer Confirm
# ───────────────────────────────────────────────
class ProductVendorMarkReadyResponse(BaseModel):
    order_id: UUID
    message: str


class ProductCustomerConfirmResponse(BaseModel):
    order_id: UUID
    amount_released: Decimal
    message: str
