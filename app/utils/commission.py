from supabase import AsyncClient
from app.config.logging import logger


async def get_commission_rate(order_type: str, supabase: AsyncClient) -> float:
    """
    Fetch commission rate for a specific service type
    Returns the vendor/dispatch share (e.g., 0.85)
    """
    column_map = {
        "DELIVERY": "delivery_commission_percentage",
        "FOOD": "food_commission_percentage",
        "LAUNDRY": "laundry_commission_percentage",
        "PRODUCT": "product_commission_percentage",
    }

    if order_type not in column_map:
        raise ValueError(f"Unknown order type: {order_type}")

    column = column_map[order_type]

    resp = (
        await supabase.table("charges_and_commissions")
        .select(column)
        .maybe_single()
        .execute()
    )
    
    print('*'*50)
    print(resp.data)
    print('*'*50)

    if not resp.data:
        logger.warning(
            event="commission_config_not_found",
            order_type=order_type,
            notes="Using fallback commission rate of 0.8",
        )
        return 0.8

    return float(resp.data[column])
