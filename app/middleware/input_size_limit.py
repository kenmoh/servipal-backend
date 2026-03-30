"""
Input size limiting middleware to prevent DoS attacks.
Enforces maximum payload sizes for different content types.
"""

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from app.config.logging import logger
from app.config.security_config import (
    MAX_JSON_BODY_SIZE,
    MAX_PAYLOAD_SIZE,
)


class InputSizeLimitMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce request size limits and prevent payload-based DoS attacks."""

    async def dispatch(self, request: Request, call_next):
        """Process request with size limit validation."""
        
        # Get content length from headers
        content_length = request.headers.get("content-length")
        
        if content_length:
            try:
                content_length = int(content_length)
                
                # Check against global payload limit
                if content_length > MAX_PAYLOAD_SIZE:
                    logger.warning(
                        "request_payload_too_large",
                        content_length=content_length,
                        max_allowed=MAX_PAYLOAD_SIZE,
                        client_ip=request.client.host if request.client else None,
                        path=request.url.path,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Payload too large. Max {MAX_PAYLOAD_SIZE} bytes allowed.",
                    )
                
                # Check JSON-specific limit if content-type is JSON
                content_type = request.headers.get("content-type", "").lower()
                if "application/json" in content_type:
                    if content_length > MAX_JSON_BODY_SIZE:
                        logger.warning(
                            "json_payload_too_large",
                            content_length=content_length,
                            max_allowed=MAX_JSON_BODY_SIZE,
                            client_ip=request.client.host if request.client else None,
                            path=request.url.path,
                        )
                        raise HTTPException(
                            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail=f"JSON body too large. Max {MAX_JSON_BODY_SIZE} bytes allowed.",
                        )
                
            except ValueError:
                logger.warning(
                    "invalid_content_length_header",
                    content_length=content_length,
                )
                # Invalid content-length, let it pass through
                pass
        
        return await call_next(request)
