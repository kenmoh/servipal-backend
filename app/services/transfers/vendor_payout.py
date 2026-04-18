from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

import httpx
from fastapi import HTTPException, status

from app.config.config import settings
from app.config.logging import logger


OAUTH_TOKEN_URL = (
    "https://idp.flutterwave.com/realms/flutterwave/protocol/openid-connect/token"
)


def _now_s() -> float:
    return time.time()


def _as_int_amount(value: int | float | Decimal | str) -> int:
    # Flutterwave examples use integer amounts for transfers (e.g., 50000 NGN).
    try:
        return int(Decimal(str(value)))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid amount",
        )


@dataclass
class OAuthToken:
    access_token: str
    expires_at_s: float  # epoch seconds

    def is_about_to_expire(self, *, threshold_s: int = 60) -> bool:
        return (self.expires_at_s - _now_s()) < threshold_s


class FlutterwaveOrchestratorAuth:
    """
    OAuth2 token manager for Flutterwave Orchestrator APIs (v4).

    Tokens are valid for ~10 minutes; we refresh when <60s remains.
    """

    def __init__(
        self,
        *,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        timeout_s: float = 30.0,
    ) -> None:
        self._client_id = client_id or settings.FLW_CLIENT_ID
        self._client_secret = client_secret or settings.FLW_CLIENT_SECRET
        self._timeout = timeout_s
        self._token: Optional[OAuthToken] = None

        if not self._client_id or not self._client_secret:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Flutterwave orchestrator OAuth creds missing (FLW_CLIENT_ID/FLW_CLIENT_SECRET).",
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
            logger.error(
                "flutterwave_oauth_failed", status_code=resp.status_code, response=body
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={
                    "message": "Failed to get Flutterwave access token",
                    "response": body,
                },
            )

        expires_in = int(body.get("expires_in") or 600)
        token = OAuthToken(
            access_token=body["access_token"],
            expires_at_s=_now_s() + expires_in,
        )
        self._token = token
        return token.access_token


class TransferOrchestratorClient:
    """
    Flutterwave Transfer Orchestrator (Direct Transfer Flow).

    Docs:
    - POST {base_url}/direct-transfers to create a direct transfer
    - Verify via webhooks/callback/retrieve transfer endpoint
    """

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        auth: Optional[FlutterwaveOrchestratorAuth] = None,
        timeout_s: float = 30.0,
    ) -> None:
        self._base_url = (base_url or settings.FLW_ORCHESTRATOR_BASE_URL).rstrip("/")
        self._auth = auth or FlutterwaveOrchestratorAuth()
        self._timeout = timeout_s

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

    async def create_direct_transfer(
        self,
        *,
        action: str,
        transfer_type: str,
        reference: str,
        payment_instruction: dict[str, Any],
        disburse_option: Optional[dict[str, Any]] = None,
        callback_url: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
        trace_id: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        scenario_key: Optional[str] = None,
    ) -> dict[str, Any]:
        trace_id = trace_id or uuid.uuid4().hex
        idempotency_key = idempotency_key or uuid.uuid4().hex

        payload: dict[str, Any] = {
            "action": action,
            "type": transfer_type,
            "reference": reference,
            "payment_instruction": payment_instruction,
        }
        if disburse_option:
            payload["disburse_option"] = disburse_option
        if callback_url:
            payload["callback_url"] = callback_url
        if meta is not None:
            payload["meta"] = meta

        url = f"{self._base_url}/direct-transfers"

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
                detail="Flutterwave transfer request timed out.",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Could not reach Flutterwave transfers API: {str(e)}",
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Invalid transfer response: {str(e)}",
            )

        if resp.status_code >= 400 or body.get("status") != "success":
            logger.error(
                "flutterwave_direct_transfer_failed",
                status_code=resp.status_code,
                response=body,
                reference=reference,
                trace_id=trace_id,
            )
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"message": "Direct transfer failed", "response": body},
            )

        return body

    async def retrieve_transfer(
        self, *, transfer_id: str, trace_id: Optional[str] = None
    ) -> dict[str, Any]:
        """
        Best-effort retrieve:
        - Prefer /transfers/{id} (general retrieve endpoint)
        - Fallback to /direct-transfers/{id} if needed
        """
        trace_id = trace_id or uuid.uuid4().hex
        idempotency_key = uuid.uuid4().hex

        for path in (f"/transfers/{transfer_id}", f"/direct-transfers/{transfer_id}"):
            url = f"{self._base_url}{path}"
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.get(
                        url,
                        headers=await self._headers(
                            trace_id=trace_id,
                            idempotency_key=idempotency_key,
                        ),
                    )
                body = resp.json()
            except Exception:
                continue

            if resp.status_code < 400 and body:
                return body

        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to retrieve transfer status from Flutterwave.",
        )


async def create_vendor_bank_payout(
    *,
    amount: int | float | Decimal | str,
    account_number: str,
    bank_code: str,
    reference: str,
    source_currency: str = "NGN",
    destination_currency: str = "NGN",
    action: str = "instant",
    callback_url: Optional[str] = None,
    meta: Optional[dict[str, Any]] = None,
    trace_id: Optional[str] = None,
    idempotency_key: Optional[str] = None,
    scenario_key: Optional[str] = None,
    client: Optional[TransferOrchestratorClient] = None,
) -> dict[str, Any]:
    """
    Initiate a vendor bank payout using Transfer Orchestrator direct transfer flow.
    """
    client = client or TransferOrchestratorClient()

    payment_instruction = {
        "source_currency": source_currency,
        "amount": {
            "applies_to": "destination_currency",
            "value": _as_int_amount(amount),
        },
        "recipient": {
            "bank": {
                "account_number": account_number,
                "code": bank_code,
            }
        },
        "destination_currency": destination_currency,
    }

    return await client.create_direct_transfer(
        action=action,
        transfer_type="bank",
        reference=reference,
        payment_instruction=payment_instruction,
        callback_url=callback_url,
        meta=meta,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
        scenario_key=scenario_key,
    )
