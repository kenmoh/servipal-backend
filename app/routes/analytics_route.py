from fastapi import APIRouter, Depends, Query
from supabase import AsyncClient

from app.database.supabase import get_supabase_client
from app.services.analytics_service import (
    get_dashboard_overview,
    get_order_trends,
    get_user_growth,
    get_status_breakdown,
    get_top_riders,
    get_top_vendors,
    get_review_analytics,
    get_transaction_analytics,
)
from app.schemas.analytics_schemas import (
    DashboardOverviewResponse,
    OrderTrendPoint,
    UserGrowthPoint,
    StatusBreakdownResponse,
    TopRider,
    TopVendor,
    ReviewAnalyticsResponse,
    TransactionAnalyticsResponse,
    VendorOrderType,
    AnalyticsInterval,
)
from app.dependencies.auth import (
    require_admin,
    require_super_admin,
    require_admin_or_super,
)

router = APIRouter(prefix="/api/v1/analytics", tags=["Analytics"])


@router.get("/overview", response_model=DashboardOverviewResponse)
async def dashboard_overview(
    supabase: AsyncClient = Depends(get_supabase_client),
    _admin: dict = Depends(require_admin),
):
    """
    Master KPI cards — total users, orders, revenue, wallets,
    transactions and review stats across all service types.
    """
    return await get_dashboard_overview(supabase)


@router.get("/order-trends", response_model=list[OrderTrendPoint])
async def order_trends(
    days: int = Query(default=30, ge=0, description="0 = all time"),
    interval: AnalyticsInterval = Query(default="day"),
    supabase: AsyncClient = Depends(get_supabase_client),
    _admin: dict = Depends(require_admin_or_super)
):
    """
    Time-series order counts and revenue across all service types.
    Use for line/area charts. interval: day | week | month.
    """
    return await get_order_trends(supabase, days=days, interval=interval)


@router.get("/user-growth", response_model=list[UserGrowthPoint])
async def user_growth(
    days: int = Query(default=30, ge=0, description="0 = all time"),
    interval: AnalyticsInterval = Query(default="day"),
    supabase: AsyncClient = Depends(get_supabase_client),
    _admin: dict = Depends(require_admin_or_super),
    
):
    """
    User registration trends broken down by user type.
    Use for stacked area/bar charts.
    """
    return await get_user_growth(supabase, days=days, interval=interval)


@router.get("/status-breakdown", response_model=StatusBreakdownResponse)
async def status_breakdown(
    days: int = Query(default=30, ge=0, description="0 = all time"),
    supabase: AsyncClient = Depends(get_supabase_client),
    _admin: dict = Depends(require_admin_or_super),
):
    """
    Order status distributions for all service types + delivery payment status.
    Use for donut/pie charts.
    """
    return await get_status_breakdown(supabase, days=days)


@router.get("/top-riders", response_model=list[TopRider])
async def top_riders(
    limit: int = Query(default=10, ge=1, le=100),
    days: int  = Query(default=30, ge=0, description="0 = all time"),
    supabase: AsyncClient = Depends(get_supabase_client),
    _admin: dict = Depends(require_admin_or_super),
):
    """
    Rider leaderboard sorted by completed deliveries.
    Includes cancel rate, earnings, distance and dispatcher info.
    """
    return await get_top_riders(supabase, limit=limit, days=days)


@router.get("/top-vendors", response_model=list[TopVendor])
async def top_vendors(
    order_type: VendorOrderType = Query(default="FOOD"),
    limit: int = Query(default=10, ge=1, le=100),
    days: int  = Query(default=30, ge=0, description="0 = all time"),
    supabase: AsyncClient = Depends(get_supabase_client),
    _admin: dict = Depends(require_admin_or_super),
):
    """
    Vendor leaderboard sorted by completed orders.
    order_type: FOOD | LAUNDRY | PRODUCT
    """
    return await get_top_vendors(supabase, order_type=order_type, limit=limit, days=days)


@router.get("/reviews", response_model=ReviewAnalyticsResponse)
async def review_analytics(
    days: int = Query(default=30, ge=0, description="0 = all time"),
    supabase: AsyncClient = Depends(get_supabase_client),
    _admin: dict = Depends(require_admin_or_super),
):
    """
    Rating distributions, per-service breakdown and top-rated profiles.
    Use for bar charts and leaderboard tables.
    """
    return await get_review_analytics(supabase, days=days)


@router.get("/transactions", response_model=TransactionAnalyticsResponse)
async def transaction_analytics(
    days: int = Query(default=30, ge=0, description="0 = all time"),
    interval: AnalyticsInterval = Query(default="day"),
    supabase: AsyncClient = Depends(get_supabase_client),
    _admin: dict = Depends(require_admin_or_super),
):
    """
    Transaction volume by type, by order type and time-series trend.
    Use for bar + line combo charts.
    """
    return await get_transaction_analytics(supabase, days=days, interval=interval)