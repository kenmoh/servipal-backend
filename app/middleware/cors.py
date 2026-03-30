"""
CORS (Cross-Origin Resource Sharing) configuration for FastAPI.
Implements secure CORS policy with environment-based allowlists.
Prevents unauthorized cross-origin requests while allowing legitimate frontend clients.
"""

from typing import List, Optional
from pydantic_settings import BaseSettings
import os


class CORSSettings(BaseSettings):
    """
    CORS configuration loaded from environment variables.
    
    Environment Variables:
        ALLOWED_ORIGINS: Comma-separated list of allowed origins (e.g., "https://app.servipal.com,https://admin.servipal.com")
        CORS_ALLOW_CREDENTIALS: Whether to allow credentials in CORS requests (default: True)
    """
    
    # Allowed origins for CORS requests
    ALLOWED_ORIGINS: str = os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:8000,http://localhost:5173"  # Dev defaults
    )
    
    # Allow credentials (cookies, authorization headers)
    CORS_ALLOW_CREDENTIALS: bool = os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


cors_settings = CORSSettings()


def get_allowed_origins() -> List[str]:
    """
    Parse and return allowed origins from configuration.
    
    Returns:
        List of allowed origin URLs
    """
    origins = [origin.strip() for origin in cors_settings.ALLOWED_ORIGINS.split(",") if origin.strip()]
    return origins


# CORS configuration for CORSMiddleware
CORS_CONFIG = {
    "allow_origins": get_allowed_origins(),
    "allow_credentials": cors_settings.CORS_ALLOW_CREDENTIALS,
    "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
    "allow_headers": [
        "Content-Type",
        "Authorization",
        "X-Requested-With",
        "X-API-Key",
        "Accept",
        "Accept-Language",
        "Content-Language",
    ],
    "expose_headers": [
        "Content-Length",
        "Content-Type",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
    ],
    "max_age": 600,  # 10 minutes - browser caches preflight responses
}
