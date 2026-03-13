from fastapi import HTTPException, status
import math
from uuid import UUID
from supabase import AsyncClient
from app.schemas.product_order_mgt_admin_schema import (
    ProductOrderDetail,
    ProductOrderSummary,
    ProductOrderListResponse,
    ProductOrderFilters,
    ProductOrderItem,
)
from app.schemas.restaurant_order_mgt_admin_schema import CustomerSnippet, VendorSnippet
from app.schemas.admin_schemas import PaginationMeta


async def list_product_orders(
    supabase: AsyncClient,
    filters: ProductOrderFilters,
    page: int = 1,
    page_size: int = 20,
) -> ProductOrderListResponse:
    result = await supabase.rpc(
        "admin_list_product_orders",
        {
            "p_order_status": filters.order_status,
            "p_payment_status": filters.payment_status,
            "p_escrow_status": filters.escrow_status,
            "p_vendor_id": str(filters.vendor_id) if filters.vendor_id else None,
            "p_customer_id": str(filters.customer_id) if filters.customer_id else None,
            "p_has_dispute": filters.has_dispute,
            "p_date_from": filters.date_from.isoformat() if filters.date_from else None,
            "p_date_to": filters.date_to.isoformat() if filters.date_to else None,
            "p_search": filters.search,
            "p_page": page,
            "p_page_size": page_size,
        },
    ).execute()

    rows = result.data or []
    total = rows[0]["total_count"] if rows else 0

    return ProductOrderListResponse(
        data=[ProductOrderSummary(**r) for r in rows],
        meta=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if total else 0,
        ),
    )


async def get_product_order(
    supabase: AsyncClient, order_id: UUID
) -> ProductOrderDetail:
    result = await supabase.rpc(
        "admin_get_product_order_detail",
        {"p_order_id": str(order_id)},
    ).execute()

    if not result.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product order {order_id} not found",
        )

    row = result.data[0]
    customer = CustomerSnippet(**row["customer"]) if row.get("customer") else None
    vendor = VendorSnippet(**row["vendor"]) if row.get("vendor") else None
    items = [ProductOrderItem(**i) for i in (row.get("items") or [])]

    return ProductOrderDetail(
        **{k: v for k, v in row.items() if k not in ("customer", "vendor", "items")},
        customer=customer,
        vendor=vendor,
        items=items,
    )
