from __future__ import annotations
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from supabase import Client
from app.database.supabase import get_supabase_client
from app.dependencies.auth import require_admin
from app.schemas.product_order_mgt_admin_schema import (
    ProductOrderListResponse,
    ProductOrderDetail,
    ProductOrderFilters,
)
from app.services.product_order_mgt_admin import list_product_orders, get_product_order

router = APIRouter(prefix="/api/v1/product-orders", tags=["Product Order Management"])


@router.get(
    "",
    response_model=ProductOrderListResponse,
    summary="List product orders with filters",
)
async def list_orders(
    order_status: str | None = Query(None),
    payment_status: str | None = Query(None),
    escrow_status: str | None = Query(None),
    vendor_id: UUID | None = Query(None),
    customer_id: UUID | None = Query(None),
    has_dispute: bool | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    search: str | None = Query(None, description="Order number or tx_ref"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Client = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    filters = ProductOrderFilters(
        order_status=order_status,
        payment_status=payment_status,
        escrow_status=escrow_status,
        vendor_id=vendor_id,
        customer_id=customer_id,
        has_dispute=has_dispute,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    return await list_product_orders(db, filters, page=page, page_size=page_size)


@router.get(
    "/{order_id}",
    response_model=ProductOrderDetail,
    summary="Get full product order detail",
)
async def get_order(
    order_id: UUID,
    db: Client = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    return await get_product_order(db, order_id)
