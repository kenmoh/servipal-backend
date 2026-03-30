"""
Cache management system for admin routes with Pydantic serialization support.
Handles caching of complex nested data structures with proper TTL and invalidation.
"""

import json
from typing import Any, Optional, Type, TypeVar
from abc import ABC, abstractmethod
from pydantic import BaseModel
from app.config.config import redis_client, settings
from app.config.logging import logger

T = TypeVar("T", bound=BaseModel)


class CacheBackend(ABC):
    """Abstract base for cache implementations."""

    @abstractmethod
    async def get(self, key: str) -> Optional[str]:
        """Get value from cache."""
        pass

    @abstractmethod
    async def set(self, key: str, value: str, ttl: int) -> bool:
        """Set value in cache with TTL."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        pass

    @abstractmethod
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern. Returns count deleted."""
        pass


class RedisCacheBackend(CacheBackend):
    """Redis-based cache implementation."""

    def __init__(self):
        self.client = redis_client

    async def get(self, key: str) -> Optional[str]:
        """Get value from Redis."""
        if not self.client:
            return None
        try:
            return await self.client.get(key)
        except Exception as e:
            logger.error("cache_get_error", key=key, error=str(e))
            return None

    async def set(self, key: str, value: str, ttl: int) -> bool:
        """Set value in Redis with TTL."""
        if not self.client:
            return False
        try:
            await self.client.setex(key, ttl, value)
            return True
        except Exception as e:
            logger.error("cache_set_error", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        if not self.client:
            return False
        try:
            result = await self.client.delete(key)
            return result > 0
        except Exception as e:
            logger.error("cache_delete_error", key=key, error=str(e))
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis."""
        if not self.client:
            return False
        try:
            return await self.client.exists(key) > 0
        except Exception as e:
            logger.error("cache_exists_error", key=key, error=str(e))
            return False

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern in Redis."""
        if not self.client:
            return 0
        try:
            keys = await self.client.keys(pattern)
            if not keys:
                return 0
            return await self.client.delete(*keys)
        except Exception as e:
            logger.error("cache_delete_pattern_error", pattern=pattern, error=str(e))
            return 0


class CacheManager:
    """
    Manages caching for admin routes with Pydantic model support.
    Handles serialization, deserialization, and cache key generation.
    """

    # Default TTL values (in seconds)
    DEFAULT_LIST_TTL = 300  # 5 minutes for list endpoints
    DEFAULT_DETAIL_TTL = 600  # 10 minutes for detail endpoints
    DEFAULT_admin_ttl = 300

    # Cache key prefixes
    PREFIX_DELIVERY_ORDERS = "cache:admin:delivery_orders:"
    PREFIX_FOOD_ORDERS = "cache:admin:food_orders:"
    PREFIX_PRODUCT_ORDERS = "cache:admin:product_orders:"
    PREFIX_LAUNDRY_ORDERS = "cache:admin:laundry_orders:"
    PREFIX_DISPUTES = "cache:admin:disputes:"
    PREFIX_CHARGES = "cache:admin:charges:"
    PREFIX_USERS = "cache:admin:users:"
    PREFIX_WALLETS = "cache:admin:wallets:"
    PREFIX_ANALYTICS = "cache:analytics:"

    def __init__(self, backend: Optional[CacheBackend] = None):
        """Initialize with cache backend (defaults to Redis)."""
        self.backend = backend or RedisCacheBackend()

    async def get_cached(
        self, key: str, model: Type[T]
    ) -> Optional[T]:
        """
        Retrieve and deserialize cached Pydantic model.
        
        Args:
            key: Cache key
            model: Pydantic model class to deserialize to
            
        Returns:
            Deserialized model instance or None if not cached
        """
        try:
            cached_json = await self.backend.get(key)
            if not cached_json:
                return None

            logger.debug("cache_hit", key=key, model=model.__name__)
            return model.model_validate_json(cached_json)
        except Exception as e:
            logger.error("cache_get_deserialize_error", key=key, error=str(e))
            # If deserialization fails, invalidate the cache entry
            await self.backend.delete(key)
            return None

    async def set_cached(
        self, key: str, model: BaseModel, ttl: Optional[int] = None
    ) -> bool:
        """
        Serialize and cache Pydantic model.
        
        Args:
            key: Cache key
            model: Pydantic model instance to cache
            ttl: Time-to-live in seconds (uses default if None)
            
        Returns:
            True if successfully cached, False otherwise
        """
        try:
            ttl = ttl or self.DEFAULT_LIST_TTL
            
            # Use model_dump_json() for efficient JSON serialization
            json_str = model.model_dump_json()
            
            result = await self.backend.set(key, json_str, ttl)
            if result:
                logger.debug(
                    "cache_set",
                    key=key,
                    model=model.__class__.__name__,
                    ttl=ttl,
                )
            return result
        except Exception as e:
            logger.error("cache_set_serialize_error", key=key, error=str(e))
            return False

    async def invalidate(self, key: str) -> bool:
        """Delete specific cache key."""
        result = await self.backend.delete(key)
        if result:
            logger.info("cache_invalidated", key=key)
        return result

    async def invalidate_pattern(self, pattern: str) -> int:
        """Delete all cache keys matching pattern."""
        count = await self.backend.delete_pattern(pattern)
        if count > 0:
            logger.info("cache_invalidated_pattern", pattern=pattern, count=count)
        return count

    # Cache key generators
    @staticmethod
    def get_delivery_orders_list_key(filters_hash: str, page: int) -> str:
        """Generate cache key for delivery orders list."""
        return f"{CacheManager.PREFIX_DELIVERY_ORDERS}list:{filters_hash}:p{page}"

    @staticmethod
    def get_delivery_order_detail_key(order_id: str) -> str:
        """Generate cache key for delivery order detail."""
        return f"{CacheManager.PREFIX_DELIVERY_ORDERS}detail:{order_id}"

    @staticmethod
    def get_food_orders_list_key(filters_hash: str, page: int) -> str:
        """Generate cache key for food orders list."""
        return f"{CacheManager.PREFIX_FOOD_ORDERS}list:{filters_hash}:p{page}"

    @staticmethod
    def get_food_order_detail_key(order_id: str) -> str:
        """Generate cache key for food order detail."""
        return f"{CacheManager.PREFIX_FOOD_ORDERS}detail:{order_id}"

    @staticmethod
    def get_product_orders_list_key(filters_hash: str, page: int) -> str:
        """Generate cache key for product orders list."""
        return f"{CacheManager.PREFIX_PRODUCT_ORDERS}list:{filters_hash}:p{page}"

    @staticmethod
    def get_product_order_detail_key(order_id: str) -> str:
        """Generate cache key for product order detail."""
        return f"{CacheManager.PREFIX_PRODUCT_ORDERS}detail:{order_id}"

    @staticmethod
    def get_laundry_orders_list_key(filters_hash: str, page: int) -> str:
        """Generate cache key for laundry orders list."""
        return f"{CacheManager.PREFIX_LAUNDRY_ORDERS}list:{filters_hash}:p{page}"

    @staticmethod
    def get_laundry_order_detail_key(order_id: str) -> str:
        """Generate cache key for laundry order detail."""
        return f"{CacheManager.PREFIX_LAUNDRY_ORDERS}detail:{order_id}"

    @staticmethod
    def get_disputes_list_key(filters_hash: str, page: int) -> str:
        """Generate cache key for disputes list."""
        return f"{CacheManager.PREFIX_DISPUTES}list:{filters_hash}:p{page}"

    @staticmethod
    def get_dispute_detail_key(dispute_id: str) -> str:
        """Generate cache key for dispute detail."""
        return f"{CacheManager.PREFIX_DISPUTES}detail:{dispute_id}"

    @staticmethod
    def get_charges_list_key(filters_hash: str, page: int) -> str:
        """Generate cache key for charges list."""
        return f"{CacheManager.PREFIX_CHARGES}list:{filters_hash}:p{page}"

    @staticmethod
    def get_users_list_key(filters_hash: str, page: int) -> str:
        """Generate cache key for users list."""
        return f"{CacheManager.PREFIX_USERS}list:{filters_hash}:p{page}"

    @staticmethod
    def get_user_detail_key(user_id: str) -> str:
        """Generate cache key for user detail."""
        return f"{CacheManager.PREFIX_USERS}detail:{user_id}"

    @staticmethod
    def get_wallets_list_key(page: int) -> str:
        """Generate cache key for wallets list."""
        return f"{CacheManager.PREFIX_WALLETS}list:p{page}"

    @staticmethod
    def get_wallet_detail_key(user_id: str) -> str:
        """Generate cache key for wallet detail."""
        return f"{CacheManager.PREFIX_WALLETS}detail:{user_id}"

    @staticmethod
    def get_analytics_overview_key() -> str:
        """Generate cache key for analytics dashboard overview."""
        return f"{CacheManager.PREFIX_ANALYTICS}overview"

    @staticmethod
    def get_analytics_order_trends_key(days: int, interval: str) -> str:
        """Generate cache key for order trends analytics."""
        return f"{CacheManager.PREFIX_ANALYTICS}order_trends:d{days}:{interval}"

    @staticmethod
    def get_analytics_user_growth_key(days: int, interval: str) -> str:
        """Generate cache key for user growth analytics."""
        return f"{CacheManager.PREFIX_ANALYTICS}user_growth:d{days}:{interval}"

    @staticmethod
    def get_analytics_status_breakdown_key(days: int) -> str:
        """Generate cache key for status breakdown analytics."""
        return f"{CacheManager.PREFIX_ANALYTICS}status_breakdown:d{days}"

    @staticmethod
    def get_analytics_top_riders_key(limit: int, days: int) -> str:
        """Generate cache key for top riders analytics."""
        return f"{CacheManager.PREFIX_ANALYTICS}top_riders:l{limit}:d{days}"

    @staticmethod
    def get_analytics_top_vendors_key(order_type: str, limit: int, days: int) -> str:
        """Generate cache key for top vendors analytics."""
        return f"{CacheManager.PREFIX_ANALYTICS}top_vendors:{order_type}:l{limit}:d{days}"

    @staticmethod
    def get_analytics_reviews_key(days: int) -> str:
        """Generate cache key for review analytics."""
        return f"{CacheManager.PREFIX_ANALYTICS}reviews:d{days}"

    @staticmethod
    def get_analytics_transactions_key(days: int, interval: str) -> str:
        """Generate cache key for transaction analytics."""
        return f"{CacheManager.PREFIX_ANALYTICS}transactions:d{days}:{interval}"

    @staticmethod
    def invalidate_all_admin_caches() -> tuple[str, int]:
        """Get pattern to invalidate all admin caches."""
        return "cache:admin:*"


# Global cache manager instance
cache_manager = CacheManager()


def create_filter_hash(filters: dict) -> str:
    """
    Create a deterministic hash from filter dictionary.
    Used to generate consistent cache keys for list endpoints with filters.
    """
    try:
        # Sort keys for consistency, exclude None values
        sorted_filters = sorted(
            (k, v) for k, v in filters.items() if v is not None
        )
        filter_str = json.dumps(sorted_filters, default=str, sort_keys=True)
        
        # Use simple hash for readability in Redis
        hash_value = abs(hash(filter_str)) % 10000000
        return f"f{hash_value}"
    except Exception as e:
        logger.error("filter_hash_error", filters=str(filters), error=str(e))
        return "f0"
