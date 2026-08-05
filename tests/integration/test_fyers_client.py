"""F2 — Fyers REST transport tests.

Covers the token-bucket rate limiter, the ``Authorization`` header, and the
error taxonomy: HTTP 401 / codes -8..-17 -> FyersTokenExpired, 403/-373 ->
FyersDataEntitlementError, 429 honoring ``Retry-After``, everything else ->
FyersAPIError.

The transport is swapped for a mock ``httpx.AsyncClient`` (the same seam the
Dhan validator tests use) so no real network traffic is produced.
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from shettyxtreme.integration.fyers.client import (
    FyersAPIError,
    FyersDataEntitlementError,
    FyersHTTPClient,
    FyersRateLimitError,
    FyersTokenExpired,
)

APP_ID = "APP123"
TOKEN = "TOK9"


class _FakeResponse:
    """httpx.Response stand-in exposing the surface the client touches."""

    def __init__(
        self,
        status_code: int,
        payload: Any,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._payload = payload
        self.headers = headers or {}

    def json(self) -> Any:
        return self._payload


@pytest.fixture
def mock_transport():
    """Patch httpx.AsyncClient with a mock whose request() we control."""
    with patch("shettyxtreme.integration.fyers.client.httpx.AsyncClient") as cls:
        client = cls.return_value
        client.request = AsyncMock()
        client.aclose = AsyncMock()
        yield client


@pytest_asyncio.fixture
async def client(mock_transport: Any) -> FyersHTTPClient:
    c = FyersHTTPClient(app_id=APP_ID, access_token=TOKEN)
    yield c
    await c.aclose()


def _ok(payload: Any = None) -> _FakeResponse:
    return _FakeResponse(200, {"s": "ok", "data": payload})


def _err(status: int, code: int, message: str, headers=None) -> _FakeResponse:
    return _FakeResponse(
        status, {"s": "error", "code": code, "message": message}, headers
    )


class TestAuthHeader:
    @pytest.mark.asyncio
    async def test_authorization_header_injected(
        self, mock_transport: Any, client: FyersHTTPClient
    ) -> None:
        mock_transport.request.return_value = _ok()
        await client.get("/profile")
        call = mock_transport.request.await_args
        assert call.args[0] == "GET"
        assert call.args[1] == "https://api-t1.fyers.in/api/v3/profile"
        assert call.kwargs["headers"]["Authorization"] == f"{APP_ID}:{TOKEN}"

    @pytest.mark.asyncio
    async def test_post_includes_json_body(
        self, mock_transport: Any, client: FyersHTTPClient
    ) -> None:
        mock_transport.request.return_value = _ok()
        body = {"symbol": "NSE:SBIN-EQ", "qty": 1}
        await client.post("/orders", json=body)
        call = mock_transport.request.await_args
        assert call.args[0] == "POST"
        assert call.kwargs["json"] == body


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_10_rapid_requests_throttled_after_burst(
        self, mock_transport: Any, client: FyersHTTPClient
    ) -> None:
        """The 8-token burst passes instantly; the 9th and 10th wait for refill."""
        mock_transport.request.return_value = _ok()
        durations: list[float] = []
        for _ in range(10):
            start = time.monotonic()
            await client.get("/profile")
            durations.append(time.monotonic() - start)
        assert mock_transport.request.await_count == 10
        # First 8 acquire the initial burst tokens immediately...
        assert all(d < 0.05 for d in durations[:8])
        # ...the 9th and 10th each wait ~125ms for a token refill at 8/s.
        assert durations[8] >= 0.1
        assert durations[9] >= 0.1


class TestErrorClassification:
    @pytest.mark.asyncio
    async def test_http_401_raises_token_expired(
        self, mock_transport: Any, client: FyersHTTPClient
    ) -> None:
        mock_transport.request.return_value = _err(401, -8, "Token expired")
        with pytest.raises(FyersTokenExpired):
            await client.get("/profile")

    @pytest.mark.asyncio
    @pytest.mark.parametrize("code", [-8, -15, -16, -17])
    async def test_token_expired_codes_on_http_200(
        self, mock_transport: Any, client: FyersHTTPClient, code: int
    ) -> None:
        """Fyers can signal expiry on an HTTP 200 body with a -8/-15/-16/-17 code."""
        mock_transport.request.return_value = _err(200, code, "invalid token")
        with pytest.raises(FyersTokenExpired):
            await client.get("/profile")

    @pytest.mark.asyncio
    async def test_403_neg373_raises_entitlement(
        self, mock_transport: Any, client: FyersHTTPClient
    ) -> None:
        mock_transport.request.return_value = _err(403, -373, "Not entitled for Market Data")
        with pytest.raises(FyersDataEntitlementError):
            await client.get("/quotes")

    @pytest.mark.asyncio
    async def test_other_http_error_raises_fyers_api_error(
        self, mock_transport: Any, client: FyersHTTPClient
    ) -> None:
        mock_transport.request.return_value = _err(500, -99, "Internal server error")
        with pytest.raises(FyersAPIError) as excinfo:
            await client.get("/orders")
        assert excinfo.value.code == -99
        assert excinfo.value.status_code == 500

    @pytest.mark.asyncio
    async def test_returns_parsed_json_on_success(
        self, mock_transport: Any, client: FyersHTTPClient
    ) -> None:
        mock_transport.request.return_value = _ok({"name": "Rohan"})
        data = await client.get("/profile")
        assert data == {"s": "ok", "data": {"name": "Rohan"}}


class TestRetryAfter:
    @pytest.mark.asyncio
    async def test_429_honors_retry_after_before_retry(self, mock_transport: Any) -> None:
        mock_transport.request = AsyncMock(
            side_effect=[
                _err(429, -429, "rate limit", headers={"Retry-After": "2"}),
                _ok({"recovered": True}),
            ]
        )
        c = FyersHTTPClient(app_id=APP_ID, access_token=TOKEN)
        try:
            start = time.monotonic()
            data = await c.get("/profile")
            elapsed = time.monotonic() - start
        finally:
            await c.aclose()
        assert data == {"s": "ok", "data": {"recovered": True}}
        assert mock_transport.request.await_count == 2
        # Retry-After: 2 -> the client slept ~2s before retrying.
        assert elapsed >= 2.0

    @pytest.mark.asyncio
    async def test_429_exhausts_retries_raises(self, mock_transport: Any) -> None:
        mock_transport.request = AsyncMock(
            return_value=_err(429, -429, "rate limit", headers={"Retry-After": "0"})
        )
        c = FyersHTTPClient(app_id=APP_ID, access_token=TOKEN, max_retries=1)
        try:
            with pytest.raises(FyersRateLimitError) as excinfo:
                await c.get("/profile")
        finally:
            await c.aclose()
        # Header "0" is floored to the 1s minimum — never an immediate retry.
        assert excinfo.value.retry_after == 1.0
        assert mock_transport.request.await_count == 2  # initial + 1 retry

    @pytest.mark.asyncio
    async def test_429_missing_header_sleeps_at_least_1s(
        self, mock_transport: Any
    ) -> None:
        """A 429 without Retry-After must not sleep 0s (retry storm)."""
        mock_transport.request = AsyncMock(
            side_effect=[
                _err(429, -429, "rate limit"),  # no Retry-After header
                _ok({"recovered": True}),
            ]
        )
        c = FyersHTTPClient(app_id=APP_ID, access_token=TOKEN)
        sleeps: list[float] = []
        original_sleep = asyncio.sleep

        async def _fake_sleep(duration: float) -> None:
            sleeps.append(duration)
            await original_sleep(0)

        with patch(
            "shettyxtreme.integration.fyers.client.asyncio.sleep", _fake_sleep
        ):
            try:
                data = await c.get("/profile")
            finally:
                await c.aclose()
        assert data == {"s": "ok", "data": {"recovered": True}}
        assert mock_transport.request.await_count == 2
        assert len(sleeps) == 1
        assert sleeps[0] >= 1.0

    @pytest.mark.asyncio
    async def test_429_large_retry_after_capped_at_10s(
        self, mock_transport: Any
    ) -> None:
        """A 24h Retry-After must not hang the request — sleep is capped at 10s."""
        mock_transport.request = AsyncMock(
            side_effect=[
                _err(429, -429, "rate limit", headers={"Retry-After": "86400"}),
                _ok({"recovered": True}),
            ]
        )
        c = FyersHTTPClient(app_id=APP_ID, access_token=TOKEN)
        sleeps: list[float] = []
        original_sleep = asyncio.sleep

        async def _fake_sleep(duration: float) -> None:
            sleeps.append(duration)
            await original_sleep(0)

        with patch(
            "shettyxtreme.integration.fyers.client.asyncio.sleep", _fake_sleep
        ):
            try:
                data = await c.get("/profile")
            finally:
                await c.aclose()
        assert data == {"s": "ok", "data": {"recovered": True}}
        assert mock_transport.request.await_count == 2
        assert len(sleeps) == 1
        assert sleeps[0] <= 10.0

    @pytest.mark.asyncio
    async def test_429_http_date_retry_after_computes_seconds(
        self, mock_transport: Any
    ) -> None:
        """An HTTP-date Retry-After is converted to seconds until that instant."""
        future = format_datetime(
            datetime.now(timezone.utc) + timedelta(seconds=5), usegmt=True
        )
        mock_transport.request = AsyncMock(
            side_effect=[
                _err(429, -429, "rate limit", headers={"Retry-After": future}),
                _ok({"recovered": True}),
            ]
        )
        c = FyersHTTPClient(app_id=APP_ID, access_token=TOKEN)
        sleeps: list[float] = []
        original_sleep = asyncio.sleep

        async def _fake_sleep(duration: float) -> None:
            sleeps.append(duration)
            await original_sleep(0)

        with patch(
            "shettyxtreme.integration.fyers.client.asyncio.sleep", _fake_sleep
        ):
            try:
                data = await c.get("/profile")
            finally:
                await c.aclose()
        assert data == {"s": "ok", "data": {"recovered": True}}
        assert mock_transport.request.await_count == 2
        assert len(sleeps) == 1
        # ~5s until the date, inside the [1, 10] window and not floored/capped.
        assert 4.0 <= sleeps[0] <= 6.0


class TestVerbs:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "verb,path", [("get", "/profile"), ("post", "/orders"), ("patch", "/orders/1"),
                      ("delete", "/orders/1")]
    )
    async def test_verb_mapping(
        self, mock_transport: Any, client: FyersHTTPClient, verb: str, path: str
    ) -> None:
        mock_transport.request.return_value = _ok()
        await getattr(client, verb)(path)
        assert mock_transport.request.await_args.args[0] == verb.upper()


class TestContextManager:
    @pytest.mark.asyncio
    async def test_async_context_manager_closes_transport(self, mock_transport: Any) -> None:
        mock_transport.request.return_value = _ok()
        async with FyersHTTPClient(app_id=APP_ID, access_token=TOKEN) as c:
            await c.get("/profile")
        assert mock_transport.request.await_count == 1
        assert mock_transport.aclose.await_count == 1
