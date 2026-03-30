"""
User-based rate limiting by UserType from Supabase.
Allows different rate limits for different user roles/types.
"""

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from app.config.config import redis_client
from app.config.logging import logger
from app.schemas.user_schemas import UserType
import time
import json
import base64


class UserRateLimitConfig:
    """Configuration for rate limits by UserType."""

    # Rate limits per minute by user type
    LIMITS = {
        UserType.SUPER_ADMIN: -1,  # Unlimited
        UserType.ADMIN: -1,  # Unlimited
        UserType.MODERATOR: 5000,  # Moderators can handle high volume
        UserType.RESTAURANT_VENDOR: 5000,  # Vendors need high limits
        UserType.LAUNDRY_VENDOR: 5000,  # Vendors need high limits
        UserType.RIDER: 3000,  # Dispatch/riders handle many requests
        UserType.DISPATCH: 3000,  # Dispatch workers
        UserType.CUSTOMER: 300,  # Regular customers
        "anonymous": 60,  # Non-authenticated requests
    }

    # Time window in seconds
    WINDOW = 60


def extract_user_type(request: Request) -> str:
    """
    Extract user type from JWT token (Supabase user_metadata).
    Falls back to 'anonymous' if no valid token.
    
    Supabase JWT structure:
    {
        "sub": "user-id",
        "user_metadata": {
            "user_type": "CUSTOMER" or "ADMIN" etc.
        }
    }
    
    Returns:
        User type string (one of UserType enum values) or 'anonymous'
    """
    try:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return "anonymous"

        token = auth_header[7:]

        # Parse JWT without verification (Supabase validates this server-side)
        # JWT format: header.payload.signature
        parts = token.split(".")
        if len(parts) != 3:
            return "anonymous"

        # Decode payload (add padding if needed)
        payload = parts[1]
        padding = 4 - len(payload) % 4
        if padding != 4:
            payload += "=" * padding

        try:
            decoded = json.loads(base64.urlsafe_b64decode(payload))
            
            # Extract user_type from user_metadata
            user_metadata = decoded.get("user_metadata", {})
            user_type = user_metadata.get("user_type", "CUSTOMER")
            
            # Validate it's a valid UserType
            valid_types = [member.value for member in UserType]
            if user_type in valid_types:
                return user_type
            
            # Default to CUSTOMER if unknown type
            return UserType.CUSTOMER

        except Exception as e:
            logger.debug(f"jwt_decode_error: {e}")
            return "anonymous"

    except Exception as e:
        logger.debug(f"extract_user_type_error: {e}")
        return "anonymous"


class UserRateLimiterMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware that considers user subscription tier."""

    async def dispatch(self, request: Request, call_next):
        """Process request with user-aware rate limiting."""
        
        if not redis_client:
            logger.warning("user_rate_limiter_redis_unavailable")
            return await call_next(request)

        try:
            # Get user type
            user_type = extract_user_type(request)
            
            # Get rate limit for this user type
            limit = UserRateLimitConfig.LIMITS.get(user_type, 60)

            # No limit (admin, super_admin)
            if limit == -1:
                return await call_next(request)

            # Extract client ID
            forwarded_for = request.headers.get("x-forwarded-for")
            if forwarded_for:
                client_ip = forwarded_for.split(",")[0].strip()
            elif request.client:
                client_ip = request.client.host
            else:
                client_ip = "unknown"

            # Create rate limit key per user type and IP
            rate_limit_key = f"user_rate_limit:{user_type}:{client_ip}"

            # Check current count
            current_count = await redis_client.get(rate_limit_key)
            current_count = int(current_count) if current_count else 0

            # Get TTL
            ttl = await redis_client.ttl(rate_limit_key)
            if ttl == -1 or ttl == -2:
                ttl = UserRateLimitConfig.WINDOW

            # Increment counter
            await redis_client.incr(rate_limit_key)
            await redis_client.expire(rate_limit_key, UserRateLimitConfig.WINDOW)

            remaining = max(0, limit - current_count - 1)

            # Add rate limit headers
            headers = {
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": str(remaining),
                "X-RateLimit-Reset": str(int(time.time()) + ttl),
                "X-RateLimit-UserType": user_type,
            }

            # Check if limit exceeded
            if current_count >= limit:
                logger.warning(
                    "user_rate_limit_exceeded",
                    user_type=user_type,
                    client_ip=client_ip,
                    limit=limit,
                )

                return HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Rate limit exceeded. Max {limit} requests per minute.",
                    headers=headers,
                )

            response = await call_next(request)

            # Add headers to response
            for key, value in headers.items():
                response.headers[key] = value

            return response

        except HTTPException:
            raise
        except Exception as e:
            logger.error("user_rate_limit_error", error=str(e), exc_info=True)
            # On error, allow request
            return await call_next(request)
