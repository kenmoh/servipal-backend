from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from supabase import AsyncClient
from app.database.supabase import get_supabase_client
from app.dependencies.auth import require_admin, get_current_user
from app.schemas.delivery_order_mgt_admin_schema import (
    DeliveryOrderListResponse,
    DeliveryOrderDetail,
    DeliveryOrderFilters,
)
from app.services.delivery_order_mgt_admin import (
    list_delivery_orders,
    get_delivery_order,
)
from app.utils.cache_manager import cache_manager, create_filter_hash

router = APIRouter(prefix="/api/v1/delivery-orders", tags=["Delivery Order Management"])


@router.get(
    "",
    response_model=DeliveryOrderListResponse,
    summary="List delivery orders with filters",
)
async def list_orders(
    delivery_status: str | None = Query(None),
    payment_status: str | None = Query(None),
    escrow_status: str | None = Query(None),
    delivery_type: str | None = Query(None, description="STANDARD or SCHEDULED"),
    rider_id: UUID | None = Query(None),
    dispatch_id: UUID | None = Query(None),
    sender_id: UUID | None = Query(None),
    has_dispute: bool | None = Query(None),
    is_sender_cancelled: bool | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    search: str | None = Query(
        None, description="Order number, tx_ref or package name"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user=Depends(get_current_user),
    supabase: AsyncClient = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    filters_dict = {
        "delivery_status": delivery_status,
        "payment_status": payment_status,
        "escrow_status": escrow_status,
        "delivery_type": delivery_type,
        "rider_id": str(rider_id) if rider_id else None,
        "dispatch_id": str(dispatch_id) if dispatch_id else None,
        "sender_id": str(sender_id) if sender_id else None,
        "has_dispute": has_dispute,
        "is_sender_cancelled": is_sender_cancelled,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "search": search,
    }

    cache_key = cache_manager.get_delivery_orders_list_key(
        create_filter_hash(filters_dict), page
    )

    # Try to get from cache first
    cached = await cache_manager.get_cached(cache_key, DeliveryOrderListResponse)
    if cached:
        return cached

    # Build filters object and call service
    filters = DeliveryOrderFilters(
        delivery_status=delivery_status,
        payment_status=payment_status,
        escrow_status=escrow_status,
        delivery_type=delivery_type,
        rider_id=rider_id,
        dispatch_id=dispatch_id,
        sender_id=sender_id,
        has_dispute=has_dispute,
        is_sender_cancelled=is_sender_cancelled,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    result = await list_delivery_orders(
        supabase, filters, page=page, page_size=page_size
    )

    # Cache the result
    await cache_manager.set_cached(
        cache_key, result, ttl=cache_manager.DEFAULT_LIST_TTL
    )

    return result


@router.get(
    "/{order_id}",
    response_model=DeliveryOrderDetail,
    summary="Get full delivery order detail",
)
async def get_order(
    order_id: UUID,
    supabase: AsyncClient = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    cache_key = cache_manager.get_delivery_order_detail_key(str(order_id))

    # Try to get from cache first
    cached = await cache_manager.get_cached(cache_key, DeliveryOrderDetail)
    if cached:
        return cached

    # Call service
    result = await get_delivery_order(supabase, order_id)

    # Cache the result
    await cache_manager.set_cached(
        cache_key, result, ttl=cache_manager.DEFAULT_DETAIL_TTL
    )

    return result
