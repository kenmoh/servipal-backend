"""
Idempotency middleware for ServiPal.
Prevents double-processing of POST/PUT requests using a client-provided X-Idempotency-Key.
Responses are cached in Redis for 24 hours.
"""

import json
from fastapi import Request, Response
from starlette.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.config.config import redis_client
from app.config.logging import logger

IDEMPOTENCY_HEADER = "x-idempotency-key"
CACHE_TTL = 86400  # 24 hours


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # 1. Only apply to mutating methods
        if request.method not in ("POST", "PUT", "PATCH"):
            return await call_next(request)

        # 2. Check for the header
        idempotency_key = request.headers.get(IDEMPOTENCY_HEADER)
        if not idempotency_key:
            return await call_next(request)

        # 3. Build a unique key per user + idempotency key
        client_ip = request.client.host if request.client else "unknown"
        redis_key = f"idempotency:{client_ip}:{idempotency_key}"

        if not redis_client:
            logger.warning("idempotency_redis_unavailable")
            return await call_next(request)

        try:
            # 4. Check if we have a cached response
            cached_data = await redis_client.get(redis_key)
            
            if cached_data:
                # Special case: request is still being processed
                if cached_data == "PROCESSING":
                    logger.info("idempotency_request_in_progress", key=idempotency_key)
                    return JSONResponse(
                        status_code=409,
                        content={
                            "error": "Conflict",
                            "message": "Request is already being processed. Please wait."
                        }
                    )
                
                # Return the cached response
                logger.info("idempotency_cache_hit", key=idempotency_key)
                data = json.loads(cached_data)
                return JSONResponse(
                    status_code=data["status_code"],
                    content=data["content"],
                    headers={"X-Idempotency-Cache": "HIT"}
                )

            # 5. Mark as processing to handle concurrent race conditions
            await redis_client.set(redis_key, "PROCESSING", ex=60) # Lock for 60 seconds

            # 6. Proceed with the request
            response = await call_next(request)

            # 7. Only cache successful or non-server-error responses (2xx, 4xx)
            # We avoid caching 5xx errors to allow retries on server failures
            if response.status_code < 500:
                response_body = b""
                async for chunk in response.body_iterator:
                    response_body += chunk
                
                try:
                    content = json.loads(response_body.decode())
                    cache_payload = {
                        "status_code": response.status_code,
                        "content": content
                    }
                    await redis_client.set(redis_key, json.dumps(cache_payload), ex=CACHE_TTL)
                except Exception:
                    # If not JSON or error during encoding, don't cache but return normally
                    pass

                # Reconstruct the response since we consumed the body iterator
                return Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type
                )
            else:
                # On server error, remove the "PROCESSING" lock so user can retry
                await redis_client.delete(redis_key)
                return response

        except Exception as e:
            logger.error("idempotency_middleware_error", error=str(e), exc_info=True)
            return await call_next(request)
