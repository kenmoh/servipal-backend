"""
API key authentication for internal service-to-service calls.
Provides secure key management, validation, and rate limiting.
"""

from fastapi import Header, HTTPException, status, Depends
from app.config.config import settings, sync_redis_client
from app.config.logging import logger
from typing import Optional
import hmac
import hashlib
import time


class APIKeyManager:
    """Manages API key authentication for internal service calls."""

    # API key patterns for different services
    VALID_SERVICES = {
        "worker": "Job queue processor",
        "internal_api": "Internal services",
        "webhook_handler": "Webhook processors",
        "batch_job": "Batch operations",
    }

    @staticmethod
    def _constant_time_compare(a: str, b: str) -> bool:
        """
        Compare two strings in constant time to prevent timing attacks.
        """
        if len(a) != len(b):
            return False

        result = 0
        for x, y in zip(a, b):
            result |= ord(x) ^ ord(y)

        return result == 0

    @staticmethod
    def validate_api_key(api_key: str) -> bool:
        """
        Validate API key using constant-time comparison.

        Args:
            api_key: API key from request header

        Returns:
            True if valid, False otherwise
        """
        if not api_key or not settings.INTERNAL_API_KEY:
            logger.warning("api_key_validation_missing_key")
            return False

        # Use constant-time comparison (prevents timing attacks)
        is_valid = APIKeyManager._constant_time_compare(
            api_key, settings.INTERNAL_API_KEY
        )

        if not is_valid:
            logger.warning(
                "api_key_validation_failed",
                key_length=len(api_key) if api_key else 0,
            )

        return is_valid

    @staticmethod
    async def check_internal_api_key(
        x_internal_key: Optional[str] = Header(None),
    ) -> str:
        """
        FastAPI dependency to validate internal API key.

        Usage:
            @router.post("/internal/endpoint")
            async def endpoint(api_key: str = Depends(check_internal_api_key)):
                # Request is authenticated

        Args:
            x_internal_key: API key from X-Internal-Key header

        Returns:
            API key (if valid)

        Raises:
            HTTPException: If invalid or missing
        """
        if not x_internal_key:
            logger.warning("api_key_missing")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="X-Internal-Key header required",
            )

        if not APIKeyManager.validate_api_key(x_internal_key):
            logger.warning("api_key_invalid")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid API key",
            )

        return x_internal_key

    @staticmethod
    async def check_internal_api_key_with_rate_limit(
        x_internal_key: Optional[str] = Header(None),
        service_name: str = "internal_service",
    ) -> str:
        """
        Validate API key AND enforce rate limit per service.

        Args:
            x_internal_key: API key from header
            service_name: Name of calling service (for rate limit tracking)

        Returns:
            API key (if valid and rate limit not exceeded)

        Raises:
            HTTPException: If invalid, missing, or rate limited
        """
        # First, validate the key
        api_key = await APIKeyManager.check_internal_api_key(x_internal_key)

        # Then, check rate limit for this service
        if sync_redis_client:
            try:
                # Rate limit: 1000 requests per minute per service
                rate_limit_key = f"internal_api_rate:{service_name}"
                current_count = await sync_redis_client.get(rate_limit_key)
                current_count = int(current_count) if current_count else 0

                if current_count >= 1000:
                    logger.warning(
                        "internal_api_rate_limit_exceeded",
                        service=service_name,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                        detail="Internal service rate limit exceeded",
                    )

                # Increment counter
                await sync_redis_client.incr(rate_limit_key)
                await sync_redis_client.expire(rate_limit_key, 60)

            except HTTPException:
                raise
            except Exception as e:
                logger.error(
                    "internal_api_rate_limit_error",
                    error=str(e),
                    service=service_name,
                )
                # Don't fail auth on rate limit check error
                pass

        return api_key

    @staticmethod
    def sign_request(
        method: str,
        path: str,
        body: str = "",
        timestamp: Optional[int] = None,
    ) -> str:
        """
        Generate HMAC signature for outgoing internal API requests.

        Example - Signing a request from worker to main API:
            signature = APIKeyManager.sign_request(
                method="POST",
                path="/api/v1/internal/process",
                body='{"order_id": 123}',
            )
            headers = {
                "X-Internal-Key": settings.INTERNAL_API_KEY,
                "X-Request-Signature": signature,
                "X-Request-Timestamp": str(int(time.time())),
            }

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Request path
            body: Request body
            timestamp: Unix timestamp (default: now)

        Returns:
            HMAC-SHA256 signature
        """
        if timestamp is None:
            timestamp = int(time.time())

        # Create request signature: METHOD|PATH|BODY|TIMESTAMP
        message = f"{method}|{path}|{body}|{timestamp}".encode()

        # Sign with INTERNAL_API_KEY
        signature = hmac.new(
            settings.INTERNAL_API_KEY.encode(),
            message,
            hashlib.sha256,
        ).hexdigest()

        return signature

    @staticmethod
    def verify_request_signature(
        method: str,
        path: str,
        signature: str,
        timestamp: str,
        body: str = "",
        max_age_seconds: int = 300,  # 5 minutes
    ) -> bool:
        """
        Verify HMAC signature on incoming internal API requests.

        Args:
            method: HTTP method
            path: Request path
            signature: Signature from X-Request-Signature header
            timestamp: Timestamp from X-Request-Timestamp header
            body: Request body
            max_age_seconds: Max age of request (prevents replay attacks)

        Returns:
            True if signature is valid and fresh
        """
        try:
            # Check timestamp freshness
            request_time = int(timestamp)
            current_time = int(time.time())

            if current_time - request_time > max_age_seconds:
                logger.warning(
                    "request_signature_stale",
                    age_seconds=current_time - request_time,
                )
                return False

            # Recompute signature
            expected_signature = APIKeyManager.sign_request(
                method=method,
                path=path,
                body=body,
                timestamp=request_time,
            )

            # Compare using constant-time
            return APIKeyManager._constant_time_compare(signature, expected_signature)

        except Exception as e:
            logger.error(
                "request_signature_verification_error",
                error=str(e),
            )
            return False
