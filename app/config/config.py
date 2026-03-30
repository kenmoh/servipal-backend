import os
from typing import Optional
from pydantic_settings import BaseSettings
from redis.asyncio import Redis as AsyncRedis
from redis import Redis as SyncRedis

from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Pydantic automatically loads these from env vars - no need for os.getenv()!
    """

    # Application settings
    APP_NAME: str = "ServiPal"
    DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "production")

    # Frontend URL (used for redirects after payment processing)
    API_URL: str = "https://servipal-backend.onrender.com/api/v1"

    # LOGFIRE
    LOGFIRE_TOKEN: Optional[str] = None

    # Internal API keys (for secure communication between services)
    INTERNAL_API_KEY: Optional[str] = os.getenv("INTERNAL_API_KEY")

    # FLUTTERWAVE
    FLW_PUBLIC_KEY: Optional[str] = os.getenv("FLW_PUBLIC_KEY")
    FLW_SECRET_KEY: Optional[str] = os.getenv("FLW_SECRET_KEY")
    FLW_SECRET_HASH: Optional[str] = os.getenv("FLW_SECRET_HASH")
    FLUTTERWAVE_PUBLIC_KEY: Optional[str] = os.getenv("FLUTTERWAVE_PUBLIC_KEY")
    FLUTTERWAVE_BASE_URL: str = os.getenv("FLUTTERWAVE_BASE_URL", "https://api.flutterwave.com/v3")
    FLW_PROD_SECRET_KEY: Optional[str] = os.getenv("FLW_PROD_SECRET_KEY")

    # SUPABASE
    SUPABASE_URL: str = os.getenv("SUPABASE_URL")
    SUPABASE_PUBLISHABLE_KEY: str = os.getenv("SUPABASE_PUBLISHABLE_KEY")
    SUPABASE_SECRET_KEY: str = os.getenv("SUPABASE_SECRET_KEY")
    SUPABASE_STORAGE_BUCKET_URL: str = os.getenv("SUPABASE_STORAGE_BUCKET_URL")

    # REDIS
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379")

    # SENTRY
    SENTRY_DSN: str = os.getenv("SENTRY_DSN")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


settings = Settings()

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
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            raise ValueError(f"Missing required env vars: {', '.join(missing_vars)}")
    except ValueError as e:
        import sys
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

# Redis initialization
# Clients are created on demand or initialized safely
redis_client = None
sync_redis_client = None

if settings.REDIS_URL:
    try:
        redis_client = AsyncRedis.from_url(settings.REDIS_URL, decode_responses=True)
        sync_redis_client = SyncRedis.from_url(
            settings.REDIS_URL, decode_responses=True
        )
    except Exception as e:
        print(f"Warning: Failed to initialize Redis clients: {e}")
