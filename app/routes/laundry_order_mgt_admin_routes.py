from __future__ import annotations
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from supabase import Client
from app.database.supabase import get_supabase_client
from app.dependencies.auth import require_admin
from app.schemas.laundry_order_mgt_schema import (
    LaundryOrderListResponse,
    LaundryOrderDetail,
    LaundryOrderFilters,
)
from app.services.laundry_order_mgt_admin import list_laundry_orders, get_laundry_order
from app.utils.cache_manager import cache_manager, create_filter_hash

router = APIRouter(prefix="/api/v1/laundry-orders", tags=["Laundry Order Management"])


@router.get(
    "",
    response_model=LaundryOrderListResponse,
    summary="List laundry orders with filters",
)
async def list_orders(
    order_status: str | None = Query(None),
    payment_status: str | None = Query(None),
    laundry_type: str | None = Query(None),
    vendor_id: UUID | None = Query(None),
    customer_id: UUID | None = Query(None),
    has_dispute: bool | None = Query(None),
    require_delivery: bool | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    search: str | None = Query(None, description="Order number or tx_ref"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Client = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    filters_dict = {
        "order_status": order_status,
        "payment_status": payment_status,
        "laundry_type": laundry_type,
        "vendor_id": str(vendor_id) if vendor_id else None,
        "customer_id": str(customer_id) if customer_id else None,
        "has_dispute": has_dispute,
        "require_delivery": require_delivery,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "search": search,
    }

    cache_key = cache_manager.get_laundry_orders_list_key(
        create_filter_hash(filters_dict), page
    )

    # Try to get from cache first
    cached = await cache_manager.get_cached(cache_key, LaundryOrderListResponse)
    if cached:
        return cached

    filters = LaundryOrderFilters(
        order_status=order_status,
        payment_status=payment_status,
        laundry_type=laundry_type,
        vendor_id=vendor_id,
        customer_id=customer_id,
        has_dispute=has_dispute,
        require_delivery=require_delivery,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    result = await list_laundry_orders(db, filters, page=page, page_size=page_size)

    # Cache the result
    await cache_manager.set_cached(
        cache_key, result, ttl=cache_manager.DEFAULT_LIST_TTL
    )

    return result


@router.get(
    "/{order_id}",
    response_model=LaundryOrderDetail,
    summary="Get full laundry order detail",
)
async def get_order(
    order_id: UUID,
    db: Client = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    cache_key = cache_manager.get_laundry_order_detail_key(str(order_id))

    # Try to get from cache first
    cached = await cache_manager.get_cached(cache_key, LaundryOrderDetail)
    if cached:
        return cached

    result = await get_laundry_order(db, order_id)

    # Cache the result
    await cache_manager.set_cached(
        cache_key, result, ttl=cache_manager.DEFAULT_DETAIL_TTL
    )

    return result
