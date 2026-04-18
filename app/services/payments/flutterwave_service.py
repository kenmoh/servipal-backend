import base64
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from Crypto.Cipher import DES3
import httpx
from fastapi import HTTPException, status

from app.config.config import settings


OAUTH_TOKEN_URL = (
    "https://idp.flutterwave.com/realms/flutterwave/protocol/openid-connect/token"
)


def _now_s() -> float:
    return time.time()


@dataclass
class _OAuthToken:
    access_token: str
    expires_at_s: float

    def is_about_to_expire(self, *, threshold_s: int = 60) -> bool:
        return (self.expires_at_s - _now_s()) < threshold_s


class FlutterwaveV4Auth:
    """
    OAuth2 token manager for Flutterwave v4 APIs.

    Docs: https://developer.flutterwave.com/docs/charging-a-card (Generate Access Token)
    """

    def __init__(
        self,
        *,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        timeout_s: float = 30.0,
    ) -> None:
        self._client_id = client_id or settings.FLW_TEST_CLIENT_ID
        self._client_secret = client_secret or settings.FLW_TEST_CLIENT_SECRET
        self._timeout = timeout_s
        self._token: Optional[_OAuthToken] = None

        if not self._client_id or not self._client_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Flutterwave v4 OAuth creds missing (FLW_TEST_CLIENT_ID/FLW_TEST_CLIENT_SECRET).",
            )

    async def get_access_token(self) -> str:
        if self._token and not self._token.is_about_to_expire(threshold_s=60):
            return self._token.access_token

        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
            "grant_type": "client_credentials",
        }

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(OAUTH_TOKEN_URL, headers=headers, data=data)
            body = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave OAuth token request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave OAuth: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Invalid OAuth response: {str(e)}",
            )

        if resp.status_code >= 400 or not body.get("access_token"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Failed to get Flutterwave access token",
                    "response": body,
                },
            )

        expires_in = int(body.get("expires_in") or 600)
        token = _OAuthToken(
            access_token=body["access_token"], expires_at_s=_now_s() + expires_in
        )
        self._token = token
        return token.access_token


class FlutterwaveV4ChargesClient:
    """
    Flutterwave v4 Charges API client.

    Reference: https://developersandbox-api.flutterwave.com/orchestration/direct-charges
    """

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        auth: Optional[FlutterwaveV4Auth] = None,
        timeout_s: float = 30.0,
    ) -> None:
        # v4 charges base is developersandbox-api.flutterwave.com in sandbox.
        self._base_url = (base_url or settings.FLW_ORCHESTRATOR_BASE_URL).rstrip("/")
        self._auth = auth or FlutterwaveV4Auth()
        self._timeout = timeout_s

        if not self._base_url:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Flutterwave v4 base URL not configured (FLW_ORCHESTRATOR_BASE_URL).",
            )

    async def _headers(
        self,
        *,
        trace_id: str,
        idempotency_key: str,
        scenario_key: Optional[str] = None,
    ) -> dict[str, str]:
        token = await self._auth.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "accept": "application/json",
            "X-Trace-Id": trace_id,
            "X-Idempotency-Key": idempotency_key,
        }
        if scenario_key:
            headers["X-Scenario-Key"] = scenario_key
        return headers

    async def create_charge(
        self,
        *,
        amount: float,
        currency: str,
        reference: str,
        customer_id: str,
        payment_method_id: str,
        redirect_url: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
        authorization: Optional[dict[str, Any]] = None,
        recurring: bool = False,
        order_id: Optional[str] = None,
        merchant_vat_amount: Optional[float] = None,
        trace_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        scenario_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Create a charge (v4): POST {base_url}/charges

        Headers:
        - X-Trace-Id (recommended)
        - X-Idempotency-Key (recommended)
        - X-Scenario-Key (optional; sandbox testing)
        """
        trace_id = trace_id or uuid.uuid4().hex
        idempotency_key = idempotency_key or uuid.uuid4().hex

        payload: dict[str, Any] = {
            "amount": amount,
            "currency": currency,
            "reference": reference,
            "customer_id": customer_id,
            "payment_method_id": payment_method_id,
            "recurring": recurring,
        }
        if redirect_url:
            payload["redirect_url"] = redirect_url
        if meta is not None:
            payload["meta"] = meta
        if authorization is not None:
            payload["authorization"] = authorization
        if order_id:
            payload["order_id"] = order_id
        if merchant_vat_amount is not None:
            payload["merchant_vat_amount"] = merchant_vat_amount

        url = f"{self._base_url}/charges"

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url,
                    headers=await self._headers(
                        trace_id=trace_id,
                        idempotency_key=idempotency_key,
                        scenario_key=scenario_key,
                    ),
                    json=payload,
                )
            body = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave v4 charge request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave v4 charges API: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Invalid Flutterwave charge response: {str(e)}",
            )

        # Reference lists 201 on success; still accept other 2xx if returned.
        if resp.status_code >= 400 or body.get("status") not in (None, "success"):
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Flutterwave v4 charge creation failed",
                    "response": body,
                },
            )

        return body


class FlutterwaveEncryptor:
    """
    3DES (DES-EDE3) ECB encryption with PKCS#5 padding, base64 output.

    Note: ECB is typically dictated by upstream payment gateway specs.
    """

    def __init__(self, key):
        # Accept either str or bytes-like; DES3 requires bytes.
        if isinstance(key, str):
            key_bytes = key.encode("utf-8")
        else:
            key_bytes = bytes(key)

        # PyCryptodome may require correct key parity; adjust defensively.
        self._key = DES3.adjust_key_parity(key_bytes)

    @staticmethod
    def _pkcs5_pad(data: bytes, block_size: int = 8) -> bytes:
        pad_len = block_size - (len(data) % block_size)
        return data + bytes([pad_len]) * pad_len

    def encrypt_data(self, plain_text) -> bytes:
        if isinstance(plain_text, str):
            pt = plain_text.encode("utf-8")
        else:
            pt = bytes(plain_text)

        cipher = DES3.new(self._key, DES3.MODE_ECB)
        padded = self._pkcs5_pad(pt, block_size=8)
        encrypted = cipher.encrypt(padded)
        return base64.b64encode(encrypted)

    # Alias to match the original function name.
    def encryp_data(self, plain_text) -> bytes:
        return self.encrypt_data(plain_text)


def encryp_data(key, plain_text):
    # Backward-compatible wrapper; prefer FlutterwaveEncryptor(key).encrypt_data(...)
    return FlutterwaveEncryptor(key).encrypt_data(plain_text)


class FlutterwavePaymentsClient:
    """
    Minimal Flutterwave v3 client for (pre)authorized card charges.

    Preauth flow (docs):
    - Initiate: POST /v3/charges?type=card with encrypted payload and `preauthorize: true`
    - Capture:  POST /v3/charges/:flw_ref/capture
    - Void:     POST /v3/charges/:flw_ref/void
    - Refund:   POST /v3/charges/:flw_ref/refund
    """

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        secret_key: Optional[str] = None,
        encryption_key: Optional[str] = None,
        timeout_s: float = 30.0,
    ) -> None:
        self._base_url = (base_url or settings.FLUTTERWAVE_BASE_URL).rstrip("/")
        # v3 payments API uses the Flutterwave API secret key + 3DES encryption key.
        self._secret_key = secret_key or settings.FLW_SECRET_KEY
        self._encryption_key = encryption_key or settings.FLW_ENCRYPTION_KEY
        self._timeout = timeout_s

        if not self._secret_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Flutterwave secret key not configured (FLW_SECRET_KEY).",
            )
        if not self._encryption_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Flutterwave encryption key not configured (FLW_ENCRYPTION_KEY).",
            )

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._secret_key}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }

    def _encrypt_payload(self, payload: dict[str, Any]) -> str:
        try:
            text = json.dumps(payload)
            encrypted_b64 = FlutterwaveEncryptor(self._encryption_key).encrypt_data(
                text
            )
            return encrypted_b64.decode("utf-8")
        except ValueError as e:
            # Typically bad 3DES key length/parity.
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to encrypt payload: {str(e)}",
            )

    async def initiate_preauthorized_card_charge(
        self, payload: dict[str, Any]
    ) -> dict[str, Any]:
        # Ensure preauth flag is set.
        payload = {**payload, "preauthorize": True}
        client_b64 = self._encrypt_payload(payload)

        url = f"{self._base_url}/charges?type=card"
        body = {"client": client_b64}

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, headers=self._headers(), json=body)
            data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Unexpected Flutterwave response: {str(e)}",
            )

        if resp.status_code != 200 or data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Flutterwave preauth initiation failed",
                    "response": data,
                },
            )

        return data

    async def capture_preauthorized_charge(
        self, flw_ref: str, amount: Any
    ) -> dict[str, Any]:
        url = f"{self._base_url}/charges/{flw_ref}/capture"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url, headers=self._headers(), json={"amount": amount}
                )
            data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave: {str(e)}",
            )

        if resp.status_code != 200 or data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Flutterwave preauth capture failed",
                    "response": data,
                },
            )
        return data

    async def void_preauthorized_charge(self, flw_ref: str) -> dict[str, Any]:
        url = f"{self._base_url}/charges/{flw_ref}/void"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, headers=self._headers())
            data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave: {str(e)}",
            )

        if resp.status_code != 200 or data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"message": "Flutterwave preauth void failed", "response": data},
            )
        return data

    async def refund_preauthorized_charge(
        self, flw_ref: str, amount: Any
    ) -> dict[str, Any]:
        url = f"{self._base_url}/charges/{flw_ref}/refund"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    url, headers=self._headers(), json={"amount": amount}
                )
            data = resp.json()
        except httpx.TimeoutException:
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Flutterwave request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave: {str(e)}",
            )

        if resp.status_code != 200 or data.get("status") != "success":
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Flutterwave preauth refund failed",
                    "response": data,
                },
            )
        return data

    async def check_health(self) -> bool:
        """
        Check if Flutterwave API is reachable and responding.
        Hits a lightweight public endpoint (fetching NG banks).
        Useful for implementing fallbacks if the gateway is down.
        """
        url = f"{self._base_url}/banks/NG"
        try:
            # We use a short timeout because health checks shouldn't block
            async with httpx.AsyncClient(timeout=4.0) as client:
                resp = await client.get(url, headers=self._headers())
            
            # 200 OK means the API is up and running
            return resp.status_code == 200
        except Exception:
            return False
