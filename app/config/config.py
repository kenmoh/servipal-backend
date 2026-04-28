import sys
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis as AsyncRedis
from redis import Redis as SyncRedis
from dotenv import load_dotenv

# Use load_dotenv if we want to ensure os.environ is populated as well,
# though Pydantic SettingsConfigDict handles file loading natively.
load_dotenv()


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    """

    model_config = SettingsConfigDict(
        env_file=("/secrets/.env", ".env", ".env.local"),
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # Application settings
    APP_NAME: str = "ServiPal"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"

    # Frontend URL (used for redirects after payments processing)
    API_URL: str = "https://api.servi-pal.com/api/v1"

    # LOGFIRE
    LOGFIRE_TOKEN: Optional[str] = None

    # Internal API keys (for secure communication between services)
    INTERNAL_API_KEY: Optional[str] = None

    # FLUTTERWAVE
    FLW_PUBLIC_KEY: Optional[str] = None
    FLW_SECRET_KEY: Optional[str] = None
    FLW_SECRET_HASH: Optional[str] = None
    # From Flutterwave Dashboard -> Settings -> API. Used for direct card charge payload encryption.
    FLW_ENCRYPTION_KEY: Optional[str] = None
    # Flutterwave v4 (Orchestrator) OAuth2 credentials for payouts/collections orchestrator APIs.
    FLW_TEST_CLIENT_ID: Optional[str] = None
    FLW_TEST_CLIENT_SECRET: Optional[str] = None
    FLW_TEST_ENCRYPTION_KEY: Optional[str] = None
    TEST_SECRET_HASH: Optional[str] = None
    # Transfer Orchestrator base URL. Defaults based on ENVIRONMENT if not provided.
    FLW_ORCHESTRATOR_BASE_URL: Optional[str] = None
    FLUTTERWAVE_PUBLIC_KEY: Optional[str] = None
    FLUTTERWAVE_BASE_URL: str = "https://api.flutterwave.com/v3"
    FLW_PROD_SECRET_KEY: Optional[str] = None

    # SUPABASE
    SUPABASE_URL: Optional[str] = None
    SUPABASE_PUBLISHABLE_KEY: Optional[str] = None
    SUPABASE_SECRET_KEY: Optional[str] = None
    SUPABASE_STORAGE_BUCKET_URL: Optional[str] = None

    # REDIS
    UPSTASH_REDIS_REST_URL: str = "redis://localhost:6379"
    UPSTASH_REDIS_REST_TOKEN: Optional[str] = None
    # Queue backend migration strategy: supabase | dual | celery
    PAYMENT_QUEUE_BACKEND: str = "celery"

    # CELERY (new queue pipeline; can run in parallel with Supabase queue)
    CELERY_ENABLED: bool = True
    CELERY_BROKER_URL: Optional[str] = (
        "amqp://servipal:change_me@rabbitmq:5672/servipal"
    )
    CELERY_RESULT_BACKEND: Optional[str] = "rpc://"
    CELERY_TASK_QUEUE: str = "payment_order_creation"
    CELERY_RABBITMQ_QUEUE_TYPE: str = "quorum"
    CELERY_TASK_DEFAULT_DELIVERY_MODE: str = "persistent"
    CELERY_TASK_MAX_RETRIES: int = 5
    CELERY_TASK_RETRY_BACKOFF_MAX_SECONDS: int = 300
    CELERY_TASK_EXPIRES_SECONDS: int = 3600
    CELERY_TASK_IGNORE_RESULT: bool = True
    CELERY_TASK_SOFT_TIME_LIMIT_SECONDS: int = 120
    CELERY_TASK_TIME_LIMIT_SECONDS: int = 180
    CELERY_BROKER_HEARTBEAT: int = 30
    CELERY_BROKER_CONNECTION_TIMEOUT_SECONDS: int = 30
    CELERY_BROKER_POOL_LIMIT: int = 10
    CELERY_PUBLISH_RETRY_MAX_RETRIES: int = 5
    CELERY_WORKER_PREFETCH_MULTIPLIER: int = 1
    CELERY_WORKER_MAX_TASKS_PER_CHILD: int = 500
    CELERY_WORKER_MAX_MEMORY_PER_CHILD_KB: int = 262144
    CELERY_BROKER_VISIBILITY_TIMEOUT_SECONDS: int = 3600
    CELERY_REDIS_USE_SSL: bool = False
    CELERY_REDIS_SSL_CERT_REQS: str = "required"

    # SENTRY
    SENTRY_DSN: Optional[str] = None


settings = Settings()

settings.PAYMENT_QUEUE_BACKEND = settings.PAYMENT_QUEUE_BACKEND.strip().lower()
if settings.PAYMENT_QUEUE_BACKEND not in {"supabase", "dual", "celery"}:
    print(
        (
            "ERROR: PAYMENT_QUEUE_BACKEND must be one of "
            "'supabase', 'dual', or 'celery'."
        ),
        file=sys.stderr,
    )
    sys.exit(1)

if settings.PAYMENT_QUEUE_BACKEND in {"dual", "celery"} and not settings.CELERY_ENABLED:
    print(
        (
            "ERROR: CELERY_ENABLED must be true when "
            "PAYMENT_QUEUE_BACKEND is 'dual' or 'celery'."
        ),
        file=sys.stderr,
    )
    sys.exit(1)

if (
    settings.PAYMENT_QUEUE_BACKEND in {"dual", "celery"}
    and not settings.CELERY_BROKER_URL
):
    print(
        (
            "ERROR: CELERY_BROKER_URL is required when "
            "PAYMENT_QUEUE_BACKEND is 'dual' or 'celery'."
        ),
        file=sys.stderr,
    )
    sys.exit(1)

# Derived defaults (keep these near settings init so other modules can rely on them).
if not settings.FLW_ORCHESTRATOR_BASE_URL:
    # v4 Orchestrator uses a different hostname than v3.
    # Sandbox examples use developersandbox-api.flutterwave.com.
    settings.FLW_ORCHESTRATOR_BASE_URL = (
        "https://f4bexperience.flutterwave.com"
        if settings.ENVIRONMENT == "production"
        else "https://developersandbox-api.flutterwave.com"
    )

# Validate required environment variables in production
if settings.ENVIRONMENT == "production":
    try:
        required_vars = [
            "SUPABASE_URL",
            "SUPABASE_PUBLISHABLE_KEY",
            "SUPABASE_SECRET_KEY",
            "FLW_SECRET_HASH",
            "INTERNAL_API_KEY",
        ]
        missing_vars = [var for var in required_vars if not getattr(settings, var)]
        if missing_vars:
            raise ValueError(f"Missing required env vars: {', '.join(missing_vars)}")
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

# Redis initialization
# Clients are created on demand or initialized safely
redis_client = None
sync_redis_client = None

if settings.UPSTASH_REDIS_REST_URL:
    try:
        url = f"rediss://default:{settings.UPSTASH_REDIS_REST_TOKEN}@{settings.UPSTASH_REDIS_REST_URL.lstrip('https://')}"
        redis_client = AsyncRedis.from_url(url, decode_responses=True)
        sync_redis_client = SyncRedis.from_url(url, decode_responses=True)
    except Exception as e:
        print(f"Warning: Failed to initialize Redis clients: {e}")
