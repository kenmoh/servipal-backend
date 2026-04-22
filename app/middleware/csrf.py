"""
CSRF (Cross-Site Request Forgery) protection middleware for FastAPI.
Requires valid CSRF tokens for state-changing operations (POST, PUT, DELETE, PATCH).
"""

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from app.config.config import sync_redis_client
from app.config.logging import logger
import hashlib
import secrets


class CSRFProtectionMiddleware(BaseHTTPMiddleware):
    """
    CSRF protection middleware using synchronous Redis.
    Requires CSRF tokens for state-changing HTTP methods.

    Token flow:
    1. GET request -> generate token, store in Redis
    2. Client receives token and must include in X-CSRF-Token header
    3. POST/PUT/DELETE/PATCH -> validate token from header against stored value
    """

    # Methods that require CSRF protection (state-changing operations)
    PROTECTED_METHODS = {"POST", "PUT", "DELETE", "PATCH"}

    # Paths exempt from CSRF protection (e.g., webhooks, public endpoints)
    EXEMPT_PATHS = {
        "/api/v1/payments/webhook",  # Canonical Flutterwave webhook endpoint
        "/api/v1/payment/webhook",   # Backwards-compatible alias
        "/api/v1/health",
        "/",
    }

    # Token configuration
    TOKEN_LENGTH = 32  # bytes
    TOKEN_EXPIRY = 3600  # 1 hour

    @staticmethod
    def _generate_token() -> str:
        """Generate a cryptographically secure random token."""
        return secrets.token_urlsafe(CSRFProtectionMiddleware.TOKEN_LENGTH)

    @staticmethod
    def _get_session_id(request: Request) -> str:
        """
        Extract session identifier from request.
        Uses Authorization header (user ID from JWT) or IP address.
        """
        # Try to get user ID from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
            return hashlib.sha256(token.encode()).hexdigest()

        # Fallback to IP address for unauthenticated requests
        if request.client:
            return hashlib.sha256(request.client.host.encode()).hexdigest()

        return hashlib.sha256(b"unknown").hexdigest()

    def _should_protect(self, request: Request) -> bool:
        """Check if this request should be protected."""
        # Don't protect safe methods
        if request.method not in self.PROTECTED_METHODS:
            return False

        # Check exempt paths
        path = request.url.path
        for exempt_path in self.EXEMPT_PATHS:
            if path.startswith(exempt_path):
                return False

        return True

    async def dispatch(self, request: Request, call_next):
        """Process request with CSRF protection."""
        if not sync_redis_client:
            logger.warning("csrf_redis_unavailable")
            return await call_next(request)

        # For protected methods, validate CSRF token
        if self._should_protect(request):
            try:
                session_id = self._get_session_id(request)
                csrf_token_header = request.headers.get("X-CSRF-Token")

                if not csrf_token_header:
                    logger.warning(
                        "csrf_token_missing",
                        method=request.method,
                        path=request.url.path,
                        session_id=session_id,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="CSRF token missing",
                    )

                # Retrieve stored token from Redis
                redis_key = f"csrf_token:{session_id}"
                stored_token = sync_redis_client.get(redis_key)

                if not stored_token or not self._constant_time_compare(
                    stored_token, csrf_token_header
                ):
                    logger.warning(
                        "csrf_token_invalid",
                        method=request.method,
                        path=request.url.path,
                        session_id=session_id,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Invalid CSRF token",
                    )

                # Token is valid, consume it (prevent reuse)
                sync_redis_client.delete(redis_key)

            except HTTPException:
                raise
            except Exception as e:
                logger.error("csrf_protection_error", error=str(e), exc_info=True)
                # On error, reject the request (fail secure)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="CSRF validation failed",
                )

        response = await call_next(request)

        # For safe methods (GET, HEAD, OPTIONS), generate and store a new token
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            try:
                session_id = self._get_session_id(request)
                new_token = self._generate_token()
                redis_key = f"csrf_token:{session_id}"

                # Store token with expiry
                sync_redis_client.setex(redis_key, self.TOKEN_EXPIRY, new_token)

                # Add token to response header
                response.headers["X-CSRF-Token"] = new_token

            except Exception as e:
                logger.error("csrf_token_generation_error", error=str(e), exc_info=True)
                # Don't fail the request if token generation fails

        return response

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
