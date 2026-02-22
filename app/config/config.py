import os
from typing import Optional
from pydantic_settings import BaseSettings
from redis.asyncio import Redis as AsyncRedis
from redis import Redis as SyncRedis


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    Pydantic automatically loads these from env vars - no need for os.getenv()!
    """

    # Application settings
    APP_NAME: str = "ServiPal"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Frontend URL (used for redirects after payment processing)
    FRONTEND_URL: str = "https://servipal-backend.onrender.com/api/v1"

    # LOGFIRE
    LOGFIRE_TOKEN: Optional[str] = None

    # FLUTTERWAVE
    FLW_PUBLIC_KEY: Optional[str] = None
    FLW_SECRET_KEY: Optional[str] = None
    FLW_SECRET_HASH: Optional[str] = None
    FLUTTERWAVE_PUBLIC_KEY: Optional[str] = "Kenneth-TEST-1234567"

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

# Redis initialization
# redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

redis_client = AsyncRedis.from_url(settings.REDIS_URL)
sync_redis_client = SyncRedis.from_url(settings.REDIS_URL)
# const redis = new Redis(process.env.REDIS_URL)
