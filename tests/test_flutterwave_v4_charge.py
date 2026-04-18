import pytest


class _MockHTTPXResponse:
    def __init__(self, *, status_code: int, json_body: dict):
        self.status_code = status_code
        self._json_body = json_body

    def json(self):
        return self._json_body


class _MockAsyncClient:
    """
    Minimal stand-in for httpx.AsyncClient used in our services:
    - supports `async with`
    - supports `post(...)`
    """

    def __init__(self, *, timeout=None):
        self.timeout = timeout
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, *, headers=None, data=None, json=None):
        self.calls.append(
            {
                "method": "POST",
                "url": url,
                "headers": headers or {},
                "data": data,
                "json": json,
            }
        )

        if "openid-connect/token" in url:
            return _MockHTTPXResponse(
                status_code=200,
                json_body={"access_token": "TEST_TOKEN", "expires_in": 600},
            )

        if url.endswith("/charges"):
            return _MockHTTPXResponse(
                status_code=201,
                json_body={"status": "success", "data": {"id": "chg_test_123"}},
            )

        return _MockHTTPXResponse(status_code=404, json_body={"status": "error"})


@pytest.mark.asyncio
async def test_flutterwave_v4_create_charge_builds_headers_and_payload(monkeypatch):
    from app.services.payments import flutterwave_service as svc

    # Patch httpx.AsyncClient used inside the module.
    client = _MockAsyncClient()

    def _client_factory(*, timeout=None):
        # Each `async with httpx.AsyncClient(...)` creates a new instance in the code.
        # Return the same instance so we can assert on all calls in one place.
        client.timeout = timeout
        return client

    monkeypatch.setattr(svc.httpx, "AsyncClient", _client_factory)

    auth = svc.FlutterwaveV4Auth(
        client_id="test_client_id", client_secret="test_client_secret"
    )
    charges = svc.FlutterwaveV4ChargesClient(
        base_url="https://developersandbox-api.flutterwave.com", auth=auth
    )

    resp = await charges.create_charge(
        amount=10.5,
        currency="NGN",
        reference="ref_123456",
        customer_id="cus_abc",
        payment_method_id="pm_def",
        meta={"order_id": "o1"},
        recurring=False,
    )

    assert resp["status"] == "success"
    assert resp["data"]["id"] == "chg_test_123"

    # First call should fetch OAuth token.
    token_call = next(c for c in client.calls if "openid-connect/token" in c["url"])
    assert token_call["headers"]["Content-Type"] == "application/x-www-form-urlencoded"
    assert token_call["data"]["client_id"] == "test_client_id"
    assert token_call["data"]["client_secret"] == "test_client_secret"
    assert token_call["data"]["grant_type"] == "client_credentials"

    # Second call should create the charge.
    charge_call = next(c for c in client.calls if c["url"].endswith("/charges"))
    assert charge_call["headers"]["Authorization"] == "Bearer TEST_TOKEN"
    assert "X-Trace-Id" in charge_call["headers"]
    assert "X-Idempotency-Key" in charge_call["headers"]
    assert charge_call["json"]["amount"] == 10.5
    assert charge_call["json"]["currency"] == "NGN"
    assert charge_call["json"]["reference"] == "ref_123456"
    assert charge_call["json"]["customer_id"] == "cus_abc"
    assert charge_call["json"]["payment_method_id"] == "pm_def"
