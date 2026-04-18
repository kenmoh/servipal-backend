"""
Rate limiting middleware for FastAPI.
Uses Redis to track request counts and enforce rate limits.
Payment routes are exempted to prevent blocking legitimate transfers.
"""

from fastapi import Request
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.config.config import redis_client
from app.config.logging import logger
import time


class RateLimitConfig:
    """Configuration for different rate limit tiers."""

    # Route patterns to rate limits (requests per minute)
    LIMITS = {
        # Strictest: Auth endpoints (prevent brute force attacks)
        "/api/v1/auth/token": 5,
        "/api/v1/auth/login": 5,
        "/api/v1/auth/register": 5,
        "/api/v1/auth/forgot-password": 3,
        "/api/v1/auth/reset-password": 3,
        # Strict: Admin endpoints (prevent abuse)
        "/api/v1/admin": 30,
        "/api/v1/admin-contacts": 30,
        "/api/v1/delivery-order-management": 30,
        "/api/v1/dispute-management": 30,
        "/api/v1/laundry-order-management": 30,
        "/api/v1/product-order-management": 30,
        "/api/v1/restaurant-order-management": 30,
        "/api/v1/charge-manager": 30,
        # Moderate: General endpoints
        "default": 100,
    }

    # Routes to exempt from rate limiting (e.g., payments processing)
    EXEMPT_PATHS = {
        "/api/v1/payments",  # All payments routes
        "/api/v1/health",  # Health checks
        "/",  # Root endpoint
    }

    # Time window in seconds (1 minute)
    WINDOW = 60


def get_client_id(request: Request) -> str:
    """
    Extract client identifier from request.
    Uses X-Forwarded-For header if available (for proxied requests),
    otherwise uses direct client IP.
    """
    # Check for X-Forwarded-For header (set by reverse proxies like Nginx, Cloudflare)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        client_ip = forwarded_for.split(",")[0].strip()
    elif request.client:
        client_ip = request.client.host
    else:
        client_ip = "unknown"

    return client_ip


def should_rate_limit(request: Request) -> bool:
    """Check if this request should be rate limited."""
    path = request.url.path

    # Exempt certain paths
    for exempt_path in RateLimitConfig.EXEMPT_PATHS:
        if path.startswith(exempt_path):
            return False

    return True


def get_rate_limit(path: str) -> int:
    """Get the rate limit for a given path."""
    # Check for exact or prefix match
    for route_pattern, limit in RateLimitConfig.LIMITS.items():
        if path.startswith(route_pattern) or route_pattern in path:
            return limit

    return RateLimitConfig.LIMITS.get("default", 100)


async def check_rate_limit(client_id: str, path: str) -> tuple[bool, dict]:
    """
    Check if client has exceeded rate limit.

    Returns:
        tuple: (is_allowed, metadata)
        - is_allowed: bool - whether request should proceed
        - metadata: dict with remaining requests and reset time
    """
    if not redis_client:
        # If Redis is unavailable, allow all requests
        logger.warning("rate_limiter_redis_unavailable")
        return True, {"message": "Rate limiter unavailable"}

    try:
        # Create unique key per client and path
        rate_limit_key = f"rate_limit:{client_id}:{path}"
        reset_key = f"rate_limit_reset:{client_id}:{path}"

        # Get current count
        current_count = await redis_client.get(rate_limit_key)
        current_count = int(current_count) if current_count else 0

        # Get limit for this path
        limit = get_rate_limit(path)

        # Get remaining time in window
        ttl = await redis_client.ttl(rate_limit_key)
        if ttl == -1:  # Key exists but has no TTL (shouldn't happen)
            ttl = RateLimitConfig.WINDOW
        elif ttl == -2:  # Key doesn't exist
            ttl = RateLimitConfig.WINDOW

        # Increment counter
        await redis_client.incr(rate_limit_key)
        await redis_client.expire(rate_limit_key, RateLimitConfig.WINDOW)

        remaining = max(0, limit - current_count - 1)

        metadata = {
            "limit": limit,
            "remaining": remaining,
            "reset_in_seconds": ttl,
        }

        # Check if limit exceeded
        if current_count >= limit:
            return False, metadata

        return True, metadata

    except Exception as e:
        logger.error("rate_limit_check_error", error=str(e), exc_info=True)
        # On error, allow request to proceed
        return True, {"error": "Rate limit check failed"}


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce rate limiting using Redis."""

    async def dispatch(self, request: Request, call_next):
        """Process request with rate limiting."""
        # Check if this path should be rate limited
        if not should_rate_limit(request):
            return await call_next(request)

        # Get client identifier
        client_id = get_client_id(request)

        # Check rate limit
        is_allowed, metadata = await check_rate_limit(client_id, request.url.path)

        # Create response headers for rate limit info
        headers = {
            "X-RateLimit-Limit": str(metadata.get("limit", 0)),
            "X-RateLimit-Remaining": str(metadata.get("remaining", 0)),
            "X-RateLimit-Reset": str(
                int(time.time()) + metadata.get("reset_in_seconds", 0)
            ),
        }

        if not is_allowed:
            logger.warning(
                "rate_limit_exceeded",
                client_id=client_id,
                path=request.url.path,
                limit=metadata.get("limit"),
            )

            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too Many Requests",
                    "message": f"Rate limit exceeded. Max {metadata.get('limit')} requests per minute.",
                    "reset_in_seconds": metadata.get("reset_in_seconds"),
                },
                headers=headers,
            )

        # Request is allowed, continue
        response = await call_next(request)

        # Add rate limit headers to response
        for key, value in headers.items():
            response.headers[key] = value

        return response
