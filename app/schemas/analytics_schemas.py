from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel
from typing import Literal


VendorOrderType = Literal['FOOD', 'LAUNDRY', 'PRODUCT']
AnalyticsInterval = Literal['day', 'week', 'month']

# ──────────────────────────────────────────────────────────────
# 1. Dashboard Overview
# ──────────────────────────────────────────────────────────────
class UserOverview(BaseModel):
    total: int
    customers: int
    riders: int
    dispatchers: int
    restaurant_vendors: int
    laundry_vendors: int
    blocked: int
    active: int
    new_7d: int
    new_30d: int


class OrderTypeStats(BaseModel):
    total: int
    completed: int
    cancelled: int
    disputed: int
    orders_7d: int
    orders_30d: int
    completion_rate: Decimal


class DeliveryOrderStats(OrderTypeStats):
    pending: int
    active: int


class OrderTotals(BaseModel):
    all_orders: int
    all_completed: int
    all_cancelled: int
    all_disputed: int
    orders_7d: int
    orders_30d: int


class OrderOverview(BaseModel):
    delivery: DeliveryOrderStats
    food: OrderTypeStats
    laundry: OrderTypeStats
    product: OrderTypeStats
    totals: OrderTotals


class RevenueOverview(BaseModel):
    total: Decimal
    delivery: Decimal
    food: Decimal
    laundry: Decimal
    product: Decimal
    revenue_7d: Decimal
    revenue_30d: Decimal


class WalletOverview(BaseModel):
    total_balance: Decimal
    total_escrow: Decimal
    total_wallets: int


class TransactionOverview(BaseModel):
    total_volume: Decimal
    volume_7d: Decimal
    volume_30d: Decimal
    total_count: int
    count_30d: int


class ReviewOverview(BaseModel):
    total: int
    avg_rating: Decimal
    five_star: int
    four_plus_star: int
    five_star_pct: Decimal


class DashboardOverviewResponse(BaseModel):
    users: UserOverview
    orders: OrderOverview
    revenue: RevenueOverview
    wallets: WalletOverview
    transactions: TransactionOverview
    reviews: ReviewOverview


# ──────────────────────────────────────────────────────────────
# 2. Order Trends
# ──────────────────────────────────────────────────────────────
class OrderTrendPoint(BaseModel):
    period: str
    delivery_orders: int
    delivery_revenue: Decimal
    food_orders: int
    food_revenue: Decimal
    laundry_orders: int
    laundry_revenue: Decimal
    product_orders: int
    product_revenue: Decimal
    total_orders: int
    total_revenue: Decimal


# ──────────────────────────────────────────────────────────────
# 3. User Growth
# ──────────────────────────────────────────────────────────────
class UserGrowthPoint(BaseModel):
    period: str
    customers: int
    riders: int
    dispatchers: int
    restaurant_vendors: int
    laundry_vendors: int
    total: int


# ──────────────────────────────────────────────────────────────
# 4. Status Breakdown
# ──────────────────────────────────────────────────────────────
class StatusBucket(BaseModel):
    status: str
    count: int
    percentage: Decimal


class StatusBreakdownResponse(BaseModel):
    delivery: list[StatusBucket]
    delivery_payment: list[StatusBucket]
    food: list[StatusBucket]
    laundry: list[StatusBucket]
    product: list[StatusBucket]


# ──────────────────────────────────────────────────────────────
# 5. Top Riders
# ──────────────────────────────────────────────────────────────
class TopRider(BaseModel):
    id: UUID
    full_name: str | None = None
    phone_number: str | None = None
    profile_image_url: str | None = None
    bike_number: str | None = None
    average_rating: Decimal = Decimal("0.00")
    review_count: int = 0
    is_blocked: bool = False
    is_online: bool = False
    total_distance: Decimal = Decimal("0.00")
    dispatcher_id: UUID | None = None
    dispatcher_business_name: str | None = None
    completed_deliveries: int
    cancelled_deliveries: int
    revenue_generated: Decimal
    earnings: Decimal
    cancel_rate: Decimal


# ──────────────────────────────────────────────────────────────
# 6. Top Vendors
# ──────────────────────────────────────────────────────────────
class TopVendor(BaseModel):
    id: UUID
    name: str | None = None
    phone_number: str | None = None
    profile_image_url: str | None = None
    average_rating: Decimal = Decimal("0.00")
    review_count: int = 0
    is_blocked: bool = False
    completed_orders: int
    cancelled_orders: int
    total_orders: int
    revenue: Decimal


# ──────────────────────────────────────────────────────────────
# 7. Review Analytics
# ──────────────────────────────────────────────────────────────
class RatingDistribution(BaseModel):
    field_5: int = 0
    field_4: int = 0
    field_3: int = 0
    field_2: int = 0
    field_1: int = 0

    model_config = {"populate_by_name": True}

    @classmethod
    def from_dict(cls, d: dict) -> "RatingDistribution":
        return cls(
            field_5=d.get("5", 0),
            field_4=d.get("4", 0),
            field_3=d.get("3", 0),
            field_2=d.get("2", 0),
            field_1=d.get("1", 0),
        )


class ReviewOverallStats(BaseModel):
    total: int
    avg_rating: Decimal
    distribution: RatingDistribution
    five_star_pct: Decimal

    @classmethod
    def from_dict(cls, d: dict) -> "ReviewOverallStats":
        return cls(
            total=d["total"],
            avg_rating=d["avg_rating"],
            distribution=RatingDistribution.from_dict(d.get("distribution", {})),
            five_star_pct=d["five_star_pct"],
        )


class ReviewByOrderType(BaseModel):
    order_type: str
    count: int
    avg_rating: Decimal


class TopRatedProfile(BaseModel):
    id: UUID
    name: str | None = None
    profile_image_url: str | None = None
    user_type: str
    average_rating: Decimal
    review_count: int


class ReviewAnalyticsResponse(BaseModel):
    overall: ReviewOverallStats
    by_order_type: list[ReviewByOrderType]
    top_rated: list[TopRatedProfile]


# ──────────────────────────────────────────────────────────────
# 8. Transaction Analytics
# ──────────────────────────────────────────────────────────────
class TxByType(BaseModel):
    type: str
    count: int
    volume: Decimal


class TxByOrderType(BaseModel):
    order_type: str
    count: int
    volume: Decimal


class TxTrendPoint(BaseModel):
    period: str
    count: int
    volume: Decimal


class TransactionAnalyticsResponse(BaseModel):
    by_type: list[TxByType]
    by_order_type: list[TxByOrderType]
    trend: list[TxTrendPoint]


