"""
Cache invalidation endpoints for admin panel.
These endpoints allow manual cache clearing when data changes.
Typically called by Supabase realtime listeners when tables change.
"""

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from app.utils.cache_manager import cache_manager
from app.dependencies.auth import require_admin
from app.config.logging import logger

router = APIRouter(
    prefix="/api/v1/admin/cache",
    tags=["Admin Cache Management"],
    dependencies=[Depends(require_admin)]
)


class CacheInvalidationRequest(BaseModel):
    """Request model for cache invalidation."""
    
    target: Literal[
        "all",
        "delivery_orders",
        "food_orders",
        "product_orders",
        "laundry_orders",
        "disputes",
        "charges"
    ] = "all"
    order_id: str | None = None


class CacheInvalidationResponse(BaseModel):
    """Response model for cache invalidation."""
    
    status: str
    message: str
    count_invalidated: int


@router.post(
    "/invalidate",
    response_model=CacheInvalidationResponse,
    summary="Invalidate admin caches",
    description="""
    Manually invalidate admin cache entries.
    
    Can invalidate:
    - All admin caches
    - Specific order type caches (delivery, food, product, laundry)
    - Specific order cache (provide order_id)
    
    Protected endpoint - requires admin authentication.
    """
)
async def invalidate_admin_caches(
    request: CacheInvalidationRequest,
    _admin: dict = Depends(require_admin),
) -> CacheInvalidationResponse:
    """
    Invalidate admin cache entries.
    Typically called by Supabase realtime listeners.
    """
    
    try:
        count = 0
        
        if request.target == "all":
            # Invalidate all admin caches
            pattern = "cache:admin:*"
            count = await cache_manager.invalidate_pattern(pattern)
            message = "All admin caches invalidated"
            
        elif request.target == "delivery_orders":
            pattern = f"{cache_manager.PREFIX_DELIVERY_ORDERS}*"
            if request.order_id:
                # Invalidate specific delivery order (both list and detail)
                count += await cache_manager.invalidate(
                    cache_manager.get_delivery_order_detail_key(request.order_id)
                )
                # Invalidate related lists (any page, any filter)
                pattern = f"{cache_manager.PREFIX_DELIVERY_ORDERS}list:*"
                count += await cache_manager.invalidate_pattern(pattern)
            else:
                count = await cache_manager.invalidate_pattern(pattern)
            message = f"Delivery orders cache invalidated ({request.order_id or 'all'})"
            
        elif request.target == "food_orders":
            pattern = f"{cache_manager.PREFIX_FOOD_ORDERS}*"
            if request.order_id:
                count += await cache_manager.invalidate(
                    cache_manager.get_food_order_detail_key(request.order_id)
                )
                pattern = f"{cache_manager.PREFIX_FOOD_ORDERS}list:*"
                count += await cache_manager.invalidate_pattern(pattern)
            else:
                count = await cache_manager.invalidate_pattern(pattern)
            message = f"Food orders cache invalidated ({request.order_id or 'all'})"
            
        elif request.target == "product_orders":
            pattern = f"{cache_manager.PREFIX_PRODUCT_ORDERS}*"
            if request.order_id:
                count += await cache_manager.invalidate(
                    cache_manager.get_product_order_detail_key(request.order_id)
                )
                pattern = f"{cache_manager.PREFIX_PRODUCT_ORDERS}list:*"
                count += await cache_manager.invalidate_pattern(pattern)
            else:
                count = await cache_manager.invalidate_pattern(pattern)
            message = f"Product orders cache invalidated ({request.order_id or 'all'})"
            
        elif request.target == "laundry_orders":
            pattern = f"{cache_manager.PREFIX_LAUNDRY_ORDERS}*"
            if request.order_id:
                count += await cache_manager.invalidate(
                    cache_manager.get_laundry_order_detail_key(request.order_id)
                )
                pattern = f"{cache_manager.PREFIX_LAUNDRY_ORDERS}list:*"
                count += await cache_manager.invalidate_pattern(pattern)
            else:
                count = await cache_manager.invalidate_pattern(pattern)
            message = f"Laundry orders cache invalidated ({request.order_id or 'all'})"
            
        elif request.target == "disputes":
            pattern = f"{cache_manager.PREFIX_DISPUTES}*"
            if request.order_id:
                count += await cache_manager.invalidate(
                    cache_manager.get_dispute_detail_key(request.order_id)
                )
                pattern = f"{cache_manager.PREFIX_DISPUTES}list:*"
                count += await cache_manager.invalidate_pattern(pattern)
            else:
                count = await cache_manager.invalidate_pattern(pattern)
            message = f"Disputes cache invalidated ({request.order_id or 'all'})"
            
        elif request.target == "charges":
            pattern = f"{cache_manager.PREFIX_CHARGES}*"
            count = await cache_manager.invalidate_pattern(pattern)
            message = f"Charges cache invalidated"
        
        logger.info(
            "admin_cache_invalidated",
            target=request.target,
            order_id=request.order_id,
            count=count,
            actor=_admin.get("id")
        )
        
        return CacheInvalidationResponse(
            status="success",
            message=message,
            count_invalidated=count
        )
        
    except Exception as e:
        logger.error(
            "cache_invalidation_error",
            target=request.target,
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to invalidate cache"
        )


@router.get(
    "/status",
    summary="Get cache status",
    description="Check if caching is enabled and backend is available"
)
async def get_cache_status(
    _admin: dict = Depends(require_admin),
) -> dict:
    """Check if cache backend is available."""
    
    try:
        # Try a simple cache operation
        test_key = "cache:health:check"
        test_value = '{"status": "ok"}'
        
        # Try to set and get
        set_result = await cache_manager.backend.set(test_key, test_value, 5)
        exists_result = await cache_manager.backend.exists(test_key)
        
        # Cleanup
        await cache_manager.backend.delete(test_key)
        
        return {
            "enabled": True,
            "backend": "redis",
            "healthy": set_result and exists_result,
            "message": "Cache backend is operational"
        }
    except Exception as e:
        logger.error("cache_status_error", error=str(e))
        return {
            "enabled": False,
            "backend": "redis",
            "healthy": False,
            "message": f"Cache backend unavailable: {str(e)}"
        }
