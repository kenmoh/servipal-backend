from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, Query
from supabase import Client
from app.database.supabase import get_supabase_client
from app.dependencies.auth import require_admin
from app.schemas.restaurant_order_mgt_admin_schema import (
    FoodOrderListResponse,
    FoodOrderDetail,
    FoodOrderFilters,
)
from app.services.restaurant_order_mgt_admin import list_food_orders, get_food_order

router = APIRouter(
    prefix="/api/v1/restaurant-orders", tags=["Restaurant Order Management"]
)


@router.get(
    "", response_model=FoodOrderListResponse, summary="List food orders with filters"
)
async def list_orders(
    order_status: str | None = Query(None),
    payment_status: str | None = Query(None),
    vendor_id: UUID | None = Query(None),
    customer_id: UUID | None = Query(None),
    has_dispute: bool | None = Query(None),
    require_delivery: bool | None = Query(None),
    date_from: datetime | None = Query(None),
    date_to: datetime | None = Query(None),
    search: str | None = Query(None, description="Order number or tx_ref"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    supabase: Client = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    filters = FoodOrderFilters(
        order_status=order_status,
        payment_status=payment_status,
        vendor_id=vendor_id,
        customer_id=customer_id,
        has_dispute=has_dispute,
        require_delivery=require_delivery,
        date_from=date_from,
        date_to=date_to,
        search=search,
    )
    return await list_food_orders(supabase, filters, page=page, page_size=page_size)


@router.get(
    "/{order_id}", response_model=FoodOrderDetail, summary="Get full food order detail"
)
async def get_order(
    order_id: UUID,
    supabase: Client = Depends(get_supabase_client),
    _actor: dict = Depends(require_admin),
):
    return await get_food_order(supabase, order_id)
