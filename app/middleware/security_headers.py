"""
Security headers middleware for FastAPI.
Adds essential security headers to prevent common web vulnerabilities.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from app.config.logging import logger


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.
    
    Headers added:
    - Strict-Transport-Security: Force HTTPS, prevent downgrade attacks
    - X-Content-Type-Options: Prevent MIME type sniffing
    - X-Frame-Options: Prevent clickjacking attacks
    - X-XSS-Protection: Enable browser XSS filters
    - Referrer-Policy: Control referrer information
    - Permissions-Policy: Control sensitive browser features
    - Content-Security-Policy: Restrict resource loading
    """

    async def dispatch(self, request: Request, call_next):
        """Add security headers to response."""
        response = await call_next(request)

        # Strict-Transport-Security: Force HTTPS for 1 year (31536000 seconds)
        # includeSubDomains: Apply to all subdomains
        # preload: Allow inclusion in HSTS preload lists
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains; preload"
        )

        # X-Content-Type-Options: Prevent MIME sniffing attacks
        # nosniff: Disables content type guessing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # X-Frame-Options: Clickjacking protection
        # DENY: No frames allowed (most restrictive)
        response.headers["X-Frame-Options"] = "DENY"

        # X-XSS-Protection: Enable browser XSS filtering
        # 1; mode=block: Enable filter and block if XSS detected
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Referrer-Policy: Control what referrer info is sent
        # strict-origin-when-cross-origin: Only send origin to cross-origin sites
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions-Policy: Disable risky APIs (formerly Feature-Policy)
        # Prevents malicious scripts from accessing sensitive browser features
        response.headers["Permissions-Policy"] = (
            "geolocation=(), microphone=(), camera=(), payment=(), usb=(), "
            "magnetometer=(), gyroscope=(), accelerometer=()"
        )

        # Content-Security-Policy: Restrict resource loading
        # Allow CDN resources for Swagger UI and ReDoc in development
        is_docs_path = request.url.path in ["/docs", "/redoc"]
        
        if is_docs_path:
            # For docs endpoints, allow CDN resources for Swagger UI and ReDoc
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.redoc.ly; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://cdn.redoc.ly; "
                "img-src 'self' data: https:; "
                "font-src 'self' https://cdn.jsdelivr.net https://cdn.redoc.ly; "
                "connect-src 'self' https://*.sentry.io https://cdn.jsdelivr.net https://cdn.redoc.ly; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )
        else:
            # Strict CSP for API endpoints
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self'; "
                "connect-src 'self' https://*.sentry.io; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )

        return response
