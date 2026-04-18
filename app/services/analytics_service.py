from app.schemas.analytics_schemas import (
    DashboardOverviewResponse,
    OrderTrendPoint,
    UserGrowthPoint,
    StatusBreakdownResponse,
    TopRider,
    TopVendor,
    ReviewAnalyticsResponse,
    TransactionAnalyticsResponse,
    TxByType,
    TxByOrderType,
    TxTrendPoint,
    StatusBucket,
)

from supabase import AsyncClient


async def get_dashboard_overview(supabase: AsyncClient) -> DashboardOverviewResponse:
    result = await supabase.rpc("admin_dashboard_overview").execute()
    return DashboardOverviewResponse(**result.data)


async def get_order_trends(
    supabase: AsyncClient,
    days: int = 30,
    interval: str = "day",  # 'day' | 'week' | 'month'
) -> list[OrderTrendPoint]:
    result = await supabase.rpc(
        "admin_get_order_trends",
        {"p_days": days, "p_interval": interval},
    ).execute()
    return [OrderTrendPoint(**row) for row in (result.data or [])]


async def get_user_growth(
    supabase: AsyncClient,
    days: int = 30,
    interval: str = "day",
) -> list[UserGrowthPoint]:
    result = await supabase.rpc(
        "admin_get_user_growth",
        {"p_days": days, "p_interval": interval},
    ).execute()
    return [UserGrowthPoint(**row) for row in (result.data or [])]


async def get_status_breakdown(
    supabase: AsyncClient,
    days: int = 30,
) -> StatusBreakdownResponse:
    result = await supabase.rpc(
        "admin_get_status_breakdown",
        {"p_days": days},
    ).execute()
    data = result.data
    return StatusBreakdownResponse(
        delivery=[StatusBucket(**b) for b in (data.get("delivery") or [])],
        delivery_payment=[
            StatusBucket(**b) for b in (data.get("delivery_payment") or [])
        ],
        food=[StatusBucket(**b) for b in (data.get("food") or [])],
        laundry=[StatusBucket(**b) for b in (data.get("laundry") or [])],
        product=[StatusBucket(**b) for b in (data.get("product") or [])],
    )


async def get_top_riders(
    supabase: AsyncClient,
    limit: int = 10,
    days: int = 30,
) -> list[TopRider]:
    result = await supabase.rpc(
        "admin_get_top_riders",
        {"p_limit": limit, "p_days": days},
    ).execute()
    return [TopRider(**row) for row in (result.data or [])]


async def get_top_vendors(
    supabase: AsyncClient,
    order_type: str = "FOOD",  # 'FOOD' | 'LAUNDRY' | 'PRODUCT'
    limit: int = 10,
    days: int = 30,
) -> list[TopVendor]:
    result = await supabase.rpc(
        "admin_get_top_vendors",
        {"p_order_type": order_type, "p_limit": limit, "p_days": days},
    ).execute()
    return [TopVendor(**row) for row in (result.data or [])]


async def get_review_analytics(
    supabase: AsyncClient,
    days: int = 30,
) -> ReviewAnalyticsResponse:
    result = await supabase.rpc(
        "admin_get_review_analytics",
        {"p_days": days},
    ).execute()
    data = result.data
    return ReviewAnalyticsResponse(
        overall=ReviewOverallStats.from_dict(data["overall"]),
        by_order_type=[
            ReviewByOrderType(**r) for r in (data.get("by_order_type") or [])
        ],
        top_rated=[TopRatedProfile(**r) for r in (data.get("top_rated") or [])],
    )


async def get_transaction_analytics(
    supabase: AsyncClient,
    days: int = 30,
    interval: str = "day",
) -> TransactionAnalyticsResponse:
    result = await supabase.rpc(
        "admin_get_transaction_analytics",
        {"p_days": days, "p_interval": interval},
    ).execute()
    data = result.data
    return TransactionAnalyticsResponse(
        by_type=[TxByType(**r) for r in (data.get("by_type") or [])],
        by_order_type=[TxByOrderType(**r) for r in (data.get("by_order_type") or [])],
        trend=[TxTrendPoint(**r) for r in (data.get("trend") or [])],
    )
