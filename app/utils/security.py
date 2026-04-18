"""
Security utilities for logging sanitization and validation.
"""

import re
from typing import Any, Dict


class LogSanitizer:
    """Sanitize sensitive data from logs."""

    # Patterns to identify sensitive data
    PATTERNS = {
        # Email addresses
        "email": r"[\w\.-]+@[\w\.-]+\.\w+",
        # Credit card numbers (basic pattern)
        "credit_card": r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
        # JWT tokens (starts with eyJ)
        "jwt": r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
        # API keys and tokens (common patterns)
        "api_key": r"(?i)(api[_-]?key|secret|password|token|auth)['\"]?\s*[:=]\s*['\"]?[A-Za-z0-9_-]{20,}",
        # Phone numbers
        "phone": r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",
        # SSNs (simplified)
        "ssn": r"\b\d{3}-\d{2}-\d{4}\b",
    }

    REDACTED_VALUE = "***REDACTED***"

    @classmethod
    def sanitize_string(cls, value: str) -> str:
        """Sanitize sensitive data in a string."""
        if not isinstance(value, str):
            return str(value)

        sanitized = value
        for pattern_name, pattern in cls.PATTERNS.items():
            sanitized = re.sub(
                pattern,
                cls.REDACTED_VALUE,
                sanitized,
                flags=re.IGNORECASE,
            )

        return sanitized

    @classmethod
    def sanitize_dict(cls, data: Dict[str, Any], deep: bool = True) -> Dict[str, Any]:
        """
        Recursively sanitize sensitive data in a dictionary.

        Args:
            data: Dictionary to sanitize
            deep: Whether to recursively sanitize nested dicts

        Returns:
            Sanitized dictionary
        """
        if not isinstance(data, dict):
            return data

        sanitized = {}
        sensitive_keys = {
            "password",
            "token",
            "secret",
            "api_key",
            "auth",
            "credentials",
            "ssn",
            "credit_card",
            "card_number",
            "cvv",
            "pin",
            "private_key",
        }

        for key, value in data.items():
            # Check if key is sensitive
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = cls.REDACTED_VALUE
            # Recursively sanitize nested dicts
            elif isinstance(value, dict) and deep:
                sanitized[key] = cls.sanitize_dict(value, deep=deep)
            # Sanitize strings that may contain patterns
            elif isinstance(value, str):
                sanitized[key] = cls.sanitize_string(value)
            else:
                sanitized[key] = value

        return sanitized


def validate_required_env_vars(required_vars: list[str]) -> bool:
    """
    Validate that required environment variables are set.

    Args:
        required_vars: List of environment variable names to check

    Returns:
        True if all variables are set, False otherwise

    Raises:
        ValueError: If any required variable is missing
    """
    import os

    missing_vars = []
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)

    if missing_vars:
        raise ValueError(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )

    return True
