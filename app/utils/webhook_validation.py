"""
Webhook signature verification utilities.
Validates webhook authenticity from payments providers and other third-party services.
"""

import hmac
import hashlib
from typing import Optional
from fastapi import HTTPException, status
from app.config.logging import logger


class WebhookValidator:
    """Validates webhook signatures from different providers."""

    @staticmethod
    def validate_flutterwave_signature(
        signature_header: str,
        secret_hash: str,
    ) -> bool:
        """
        Validate Flutterwave webhook signature.

        Flutterwave sends:
        - Signature in 'h' header
        - Secret hash from dashboard

        Args:
            signature_header: Value of 'verif-hash' header from Flutterwave
            secret_hash: FLW_SECRET_HASH from config

        Returns:
            True if signature is valid, False otherwise
        """
        if not signature_header or not secret_hash:
            logger.warning("flutterwave_webhook_validation_missing_params")
            return False

        try:
            # Constant-time comparison to prevent timing attacks
            return hmac.compare_digest(signature_header, secret_hash)

        except Exception as e:
            logger.error(
                "flutterwave_signature_validation_error",
                error=str(e),
                exc_info=True,
            )
            return False

    @staticmethod
    def validate_generic_hmac_signature(
        signature_header: str,
        payload_body: bytes,
        secret: str,
        algorithm: str = "sha256",
        prefix: str = "",
    ) -> bool:
        """
        Generic HMAC signature validation for any provider.

        Args:
            signature_header: Signature from webhook header
            payload_body: Raw request body
            secret: Secret key from provider
            algorithm: Hash algorithm (sha256, sha512, etc.)
            prefix: Optional prefix (some providers include algorithm name)

        Returns:
            True if signature is valid
        """
        try:
            if not signature_header or not secret:
                return False

            # Strip prefix if present (e.g., "sha256=...")
            if prefix:
                if signature_header.startswith(prefix):
                    signature_header = signature_header[len(prefix) :]

            # Compute expected signature
            expected_signature = hmac.new(
                secret.encode(),
                payload_body,
                getattr(hashlib, algorithm),
            ).hexdigest()

            # Constant-time comparison
            return hmac.compare_digest(signature_header, expected_signature)

        except Exception as e:
            logger.error(
                "hmac_signature_validation_error",
                error=str(e),
                exc_info=True,
            )
            return False

    @staticmethod
    def validate_webhook_ip(
        client_ip: str,
        allowed_ips: list[str],
    ) -> bool:
        """
        Validate webhook source IP address.

        Args:
            client_ip: Client IP from request
            allowed_ips: List of allowed IP addresses or CIDR ranges

        Returns:
            True if IP is allowed
        """
        if not allowed_ips or client_ip not in allowed_ips:
            logger.warning(
                "webhook_unauthorized_ip",
                client_ip=client_ip,
            )
            return False

        return True


def require_webhook_signature(
    signature_header: Optional[str],
    payload_body: bytes,
    secret: str,
    provider: str = "generic",
) -> None:
    """
    Dependency function to validate webhook signatures.

    Args:
        signature_header: Signature from webhook header
        payload_body: Raw request body
        secret: Secret key from provider
        provider: Provider name ('flutterwave', 'generic', etc.)

    Raises:
        HTTPException: If signature is invalid
    """
    if provider == "flutterwave":
        is_valid = WebhookValidator.validate_flutterwave_signature(
            signature_header or "",
            secret,
        )
    else:
        is_valid = WebhookValidator.validate_generic_hmac_signature(
            signature_header or "",
            payload_body,
            secret,
        )

    if not is_valid:
        logger.warning(
            "webhook_signature_validation_failed",
            provider=provider,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )


# Known IP ranges from major payments providers
PROVIDER_IPS = {
    "flutterwave": [
        "52.174.74.0/24",
        "52.183.85.0/24",
    ],
    "stripe": [
        "54.187.174.169/32",
        "54.187.205.235/32",
        "54.187.216.72/32",
    ],
    "paypal": [
        "173.0.80.0/24",
        "173.0.81.0/24",
    ],
}
