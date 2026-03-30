"""
Security configuration for input size limits, timeouts, and constraints.
"""

# Request size limits
MAX_PAYLOAD_SIZE = 10 * 1024 * 1024  # 10 MB - prevents DoS via large payloads
MAX_UPLOAD_FILE_SIZE = 50 * 1024 * 1024  # 50 MB for file uploads
MAX_JSON_BODY_SIZE = 1 * 1024 * 1024  # 1 MB for JSON bodies (typical API payloads)

# Request timeout (seconds)
REQUEST_TIMEOUT = 30

# Database pool settings
DB_POOL_MIN_SIZE = 5
DB_POOL_MAX_SIZE = 20
DB_POOL_TIMEOUT = 10  # Connection timeout in seconds

# Rate limiting configuration
RATE_LIMIT_ENABLED = True
RATE_LIMIT_STORAGE_BACKEND = "redis"  # Redis is stateful

# Session & token settings
SESSION_TIMEOUT = 3600  # 1 hour
TOKEN_EXPIRY = 3600  # 1 hour
REFRESH_TOKEN_EXPIRY = 7 * 24 * 3600  # 7 days

# Security constraints
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128
MIN_USERNAME_LENGTH = 3
MAX_USERNAME_LENGTH = 50

# OWASP best practices
# Allow only common HTTP methods
ALLOWED_HTTP_METHODS = ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]

# Block known dangerous endpoints
BLOCKED_PATHS = [
    "/admin/shell",
    "/api/debug",
    "/private",
    "/internal",
]
