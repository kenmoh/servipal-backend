from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.openapi.docs import get_redoc_html
from fastapi.middleware.cors import CORSMiddleware
import json
import os

# Load environment variables from .env file before importing anything else
load_dotenv()
from app.routes import (
    user_routes,
    payment_route,
    delivery_route,
    review_router,
    food_router,
    laundry_route,
    auth_router,
    wallet_route,
    analytics_route,
    admin_router,
    product_route,
    dispute_route,
    escrow_route,
    order_create,
    audit_logs_routes,
    delivery_order_mgt_admin_routes,
    dispute_mgt_admin_routes,
    laundry_order_mgt_admin_routes,
    product_order_mgt_admin_routes,
    restaurant_order_mgt_admin_routes,
    charge_mgr_routes,
    admin_contacts_router,
    cache_admin,
    reservation
)
from app.config.logging import logger
from app.utils.payment import get_all_banks, resolve_account_details, verify_transaction_tx_ref
from app.schemas.bank_schema import AccountDetailResponse, AccountDetails, BankSchema
from app.config.config import settings
from app.middleware.rate_limiter import RateLimiterMiddleware
from app.middleware.cors import CORS_CONFIG
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.csrf import CSRFProtectionMiddleware
from app.middleware.input_size_limit import InputSizeLimitMiddleware
from app.utils.security import LogSanitizer
import warnings

# Suppress logfire warnings globally before importing
warnings.filterwarnings("ignore", category=UserWarning, module="logfire._internal.*")

try:
    import logfire
except Exception as e:
    logger.warning(f"Failed to import logfire: {e}")
    logfire = None

import sentry_sdk
# from prometheus_fastapi_instrumentator import Instrumentator

if settings.SENTRY_DSN:
    sentry_sdk.init(dsn=settings.SENTRY_DSN, send_default_pii=True, enable_logs=True)
else:
    logger.info("Sentry DSN not found, sentry disabled")


# def run_worker():
#     """Run the RQ worker"""
#     if not sync_redis_client:
#         logger.error("RQ worker cannot start: Redis client not initialized")
#         return
#     try:
#         logger.info("Starting RQ worker")
#         worker = Worker(["default"], connection=sync_redis_client)
#         worker.work()
#     except Exception as e:
#         logger.error("RQ worker failed to start", error=str(e))


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Handle application lifespan events"""
    # Startup
    logger.info("Servipal Application Started", version="1.0.0")

    # Start worker in a separate process
    # if os.getenv("ENABLE_WORKER", "true").lower() == "true":
    #     logger.info("Starting RQ worker process")
    #     try:
    #         worker_process = multiprocessing.Process(target=run_worker)
    #         worker_process.start()
    #     except Exception as e:
    #         logger.error("Failed to fork worker process", error=str(e))
    # else:
    #     logger.info("RQ worker is disabled")

    yield

    # Shutdown
    logger.info("Servipal Application Shutdown")

    # Stop worker
    # if worker_process.is_alive():
    #     logger.info("Stopping RQ worker")
    #     worker_process.terminate()
    #     worker_process.join(timeout=5)
    #     if worker_process.is_alive():
    #         worker_process.kill()
    #     logger.info("RQ worker stopped")


app = FastAPI(
    title="ServiPal API",
    description="Backend API for ServiPal - Food, Laundry, Delivery Services, and Product Marketplace",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.ENVIRONMENT == "development" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT == "development" else None,
    debug=settings.DEBUG,
    contact={
        "name": "ServiPal",
        "url": "https://servi-pal.com",
        "email": "servipal@servi-pal.com",
    },
)

if logfire and settings.LOGFIRE_TOKEN:
    try:
        logfire.configure(token=settings.LOGFIRE_TOKEN)
        logfire.instrument_fastapi(app)
        logger.info("Logfire configured successfully")
    except Exception as e:
        logger.debug(f"Failed to configure logfire: {e}")
else:
    if not settings.LOGFIRE_TOKEN:
        logger.debug("Logfire disabled (token not configured)")

# Instrumentator().instrument(app).expose(app)

FAVICON_URL = "https://mohdelivery.s3.us-east-1.amazonaws.com/favion/favicon.ico"

# Security headers middleware (applied first)
app.add_middleware(SecurityHeadersMiddleware)

# Input size limit middleware (prevent DoS via large payloads)
app.add_middleware(InputSizeLimitMiddleware)

# CSRF protection middleware
app.add_middleware(CSRFProtectionMiddleware)

# Rate limiter middleware
app.add_middleware(RateLimiterMiddleware)

# CORS middleware with security-conscious configuration
app.add_middleware(
    CORSMiddleware,
    **CORS_CONFIG
)


# Request logging middleware with sensitive data sanitization
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests with sanitized sensitive data"""
    import time

    start_time = time.time()

    # Sanitize user-agent and other headers
    user_agent = request.headers.get("user-agent")
    
    logger.info(
        "request_started",
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host if request.client else None,
        user_agent=user_agent,
        content_type=request.headers.get("content-type", "unknown"),
    )

    try:
        response = await call_next(request)
        process_time = time.time() - start_time

        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            process_time=round(process_time, 3),
        )

        return response
    except Exception as e:
        process_time = time.time() - start_time
        
        # Sanitize error message before logging
        error_msg = str(e)
        sanitized_error = LogSanitizer.sanitize_string(error_msg)
        
        logger.error(
            "request_failed",
            method=request.method,
            path=request.url.path,
            error=sanitized_error,
            process_time=round(process_time, 3),
            exc_info=True,
        )
        raise


@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint to verify API status.

    Returns:
        dict: A welcome message, link to docs, and status.
    """
    logger.debug("root_endpoint_accessed")
    return {"message": "Welcome to ServiPal API", "docs": "/docs" if settings.ENVIRONMENT == "development" else None, "status": "active"}


@app.get("/api/v1/health", tags=["Root"])
async def health_check():
    """
    Health check endpoint.

    Returns:
        dict: The health status of the application.
    """
    logger.debug("health_check_accessed")
    return {"status": "healthy"}


# Override default ReDoc with custom favicon (optional)
@app.get("/redoc", include_in_schema=False)
def custom_redoc_html():
    return get_redoc_html(
        openapi_url=app.openapi_url,
        title=app.title,
        redoc_favicon_url=FAVICON_URL,
        redoc_js_url="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js",
    )


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return RedirectResponse(url=FAVICON_URL)


@app.get("/api/v1/banks", response_model=list[BankSchema], tags=["Banks"])
async def get_banks():
    """Get list of all supported bank(Nigeria)"""

    return await get_all_banks()

@app.post("/api/v1/banks/resolve", tags=["Banks"])
async def resolve_bank(data: AccountDetails,)-> AccountDetailResponse:
    """Get list of all supported bank(Nigeria)"""

    return await resolve_account_details(data)


# Include Routers
app.include_router(auth_router.router, include_in_schema=True)
app.include_router(user_routes.router)
app.include_router(wallet_route.router, include_in_schema=False)
app.include_router(payment_route.router)
app.include_router(delivery_route.router)
app.include_router(review_router.router)
app.include_router(food_router.router)
app.include_router(laundry_route.router)
app.include_router(product_route.router)
# app.include_router(dispute_route.router)
app.include_router(analytics_route.router)
app.include_router(reservation.router)
app.include_router(charge_mgr_routes.router, include_in_schema=False)
app.include_router(admin_router.router, include_in_schema=False)
app.include_router(order_create.router, include_in_schema=False)
app.include_router(audit_logs_routes.router, include_in_schema=False)
app.include_router(dispute_mgt_admin_routes.router, include_in_schema=False)
app.include_router(delivery_order_mgt_admin_routes.router, include_in_schema=False)
app.include_router(dispute_mgt_admin_routes.router, include_in_schema=False)
app.include_router(laundry_order_mgt_admin_routes.router, include_in_schema=False)
app.include_router(product_order_mgt_admin_routes.router, include_in_schema=False)
app.include_router(restaurant_order_mgt_admin_routes.router, include_in_schema=False)
app.include_router(admin_contacts_router.router, include_in_schema=False)
app.include_router(cache_admin.router, include_in_schema=False)

