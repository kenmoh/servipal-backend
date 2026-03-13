import math
from uuid import UUID
from supabase import AsyncClient
from fastapi import HTTPException, status
from app.schemas.delivery_order_mgt_admin_schema import (
    DeliveryOrderDetail,
    DeliveryOrderSummary,
    DeliveryOrderListResponse,
    DeliveryOrderFilters,
    SenderSnippet,
    RiderSnippet,
    DispatchSnippet,
)
from app.schemas.admin_schemas import PaginationMeta


async def list_delivery_orders(
    supabase: AsyncClient,
    filters: DeliveryOrderFilters,
    page: int = 1,
    page_size: int = 20,
) -> DeliveryOrderListResponse:
    result = await supabase.rpc(
        "admin_list_delivery_orders",
        {
            "p_delivery_status": filters.delivery_status,
            "p_payment_status": filters.payment_status,
            "p_escrow_status": filters.escrow_status,
            "p_delivery_type": filters.delivery_type,
            "p_rider_id": str(filters.rider_id) if filters.rider_id else None,
            "p_dispatch_id": str(filters.dispatch_id) if filters.dispatch_id else None,
            "p_sender_id": str(filters.sender_id) if filters.sender_id else None,
            "p_has_dispute": filters.has_dispute,
            "p_is_sender_cancelled": filters.is_sender_cancelled,
            "p_date_from": filters.date_from.isoformat() if filters.date_from else None,
            "p_date_to": filters.date_to.isoformat() if filters.date_to else None,
            "p_search": filters.search,
            "p_page": page,
            "p_page_size": page_size,
        },
    ).execute()

    rows = result.data or []
    total = rows[0]["total_count"] if rows else 0

    return DeliveryOrderListResponse(
        data=[DeliveryOrderSummary(**r) for r in rows],
        meta=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        ),
    )


async def get_delivery_order(
    supabase: AsyncClient, order_id: UUID
) -> DeliveryOrderDetail:
    result = await supabase.rpc(
        "admin_get_delivery_order_detail",
        {"p_order_id": str(order_id)},
    ).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Delivery order {order_id} not found",
        )

    row = result.data[0]
    sender = SenderSnippet(**row["sender"]) if row.get("sender") else None
    rider = RiderSnippet(**row["rider"]) if row.get("rider") else None
    dispatch = DispatchSnippet(**row["dispatch"]) if row.get("dispatch") else None

    return DeliveryOrderDetail(
        **{k: v for k, v in row.items() if k not in ("sender", "rider", "dispatch")},
        sender=sender,
        rider=rider,
        dispatch=dispatch,
    )
