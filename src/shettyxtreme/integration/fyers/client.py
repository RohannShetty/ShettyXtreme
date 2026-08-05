"""Fyers REST transport client.

Owned by the F2 transport lane. Provides the ``FyersHTTPClient`` consumed by
the F5 auth layer (validator ``/profile`` probe, health-monitor pre-market
probe) and by the F4 adapters.

Contract (F2, tested in ``tests/integration/test_fyers_client.py``):

- Verbs ``get/post/patch/delete`` resolve relative paths against
  ``DEFAULT_BASE_URL`` and inject the ``Authorization: <app_id>:<access_token>``
  header. Success responses are returned as parsed JSON.
- Token-bucket throttle (~8/s, burst 8) acquired before every request.
- Error taxonomy:
    HTTP 401 or body codes -8/-15/-16/-17 -> :class:`FyersTokenExpired`
    HTTP 403 or body code -373          -> :class:`FyersDataEntitlementError`
    HTTP 429                            -> retry honoring ``Retry-After``,
                                           then :class:`FyersRateLimitError`
    everything else non-2xx             -> :class:`FyersAPIError`
- Async context manager closes the underlying transport.
"""
from __future__ import annotations

import asyncio
import datetime
import email.utils
import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api-t1.fyers.in/api/v3"

# Fyers expiry error codes signalled inside an HTTP 200 body with s="error".
EXPIRY_ERROR_CODES: frozenset[int] = frozenset({-8, -15, -16, -17})

# Entitlement error code (data-API entitlement missing — the Fyers twin of
# Dhan's 806).
ENTITLEMENT_ERROR_CODE = -373

_TOKEN_BUCKET_RATE = 8.0      # tokens per second
_TOKEN_BUCKET_CAPACITY = 8    # burst

# Retry-After bounds for HTTP 429 handling. A 429 must never trigger a
# zero-second retry storm (Fyers bans for a full day on rate-limit abuse), so
# the sleep is floored at 1s; and a far-future Retry-After (e.g. a daily ban)
# must not hang a request for hours, so it is capped at 10s.
_MIN_RETRY_AFTER = 1.0
_MAX_RETRY_AFTER = 10.0


class FyersError(Exception):
    """Base class for Fyers transport errors."""

    def __init__(
        self,
        message: str,
        code: int | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code


class FyersTokenExpired(FyersError):
    """Token rejected as expired (HTTP 401 or an expiry error code)."""


class FyersAuthExpiredError(FyersTokenExpired):
    """Backward-compatible alias — same meaning as :class:`FyersTokenExpired`."""


class FyersDataEntitlementError(FyersError):
    """App lacks the data entitlement (HTTP 403 / -373)."""


class FyersRateLimitError(FyersError):
    """Minute/rate-limit breached and retries exhausted."""

    def __init__(
        self,
        message: str,
        code: int | None = None,
        status_code: int | None = None,
        retry_after: float = 0.0,
    ) -> None:
        super().__init__(message, code, status_code)
        self.retry_after = retry_after


class FyersAPIError(FyersError):
    """Any other non-2xx Fyers API error."""


class _TokenBucket:
    """Async token bucket (8 tokens burst, refills at ~8/s)."""

    def __init__(self, rate: float, capacity: int) -> None:
        self._rate = rate
        self._capacity = float(capacity)
        self._tokens = float(capacity)
        self._updated = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            self._tokens = min(
                self._capacity,
                self._tokens + (now - self._updated) * self._rate,
            )
            if self._tokens >= 1.0:
                self._tokens -= 1.0
                self._updated = now
                return
            wait = (1.0 - self._tokens) / self._rate
            self._tokens = 0.0
        # Sleep outside the lock. The sleep does NOT refill the bucket for
        # the next acquire — a burst that exhausts capacity settles into a
        # steady ~8 req/s.
        await asyncio.sleep(wait)
        self._updated = time.monotonic()


class FyersHTTPClient:
    """Async REST client for the Fyers API v3."""

    def __init__(
        self,
        app_id: str = "",
        access_token: str | None = None,
        timeout: float = 15.0,
        max_retries: int = 3,
        base_url: str = DEFAULT_BASE_URL,
    ) -> None:
        self._app_id = app_id
        self._access_token = access_token
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._bucket = _TokenBucket(_TOKEN_BUCKET_RATE, _TOKEN_BUCKET_CAPACITY)
        self._transport: httpx.AsyncClient = httpx.AsyncClient(timeout=timeout)

    def set_credentials(self, app_id: str, access_token: str) -> None:
        self._app_id = app_id
        self._access_token = access_token

    async def aclose(self) -> None:
        await self._transport.aclose()

    async def __aenter__(self) -> "FyersHTTPClient":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    def _resolve(self, url: str) -> str:
        if url.startswith("http://") or url.startswith("https://"):
            return url
        return f"{self._base_url}/{url.lstrip('/')}"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"{self._app_id}:{self._access_token}"}

    async def request(self, method: str, url: str, **kwargs: Any) -> Any:
        """Perform a request, apply the token bucket, and classify errors."""
        if not self._app_id or not self._access_token:
            raise FyersTokenExpired("No Fyers credentials configured")

        full_url = self._resolve(url)
        headers = self._headers()
        merged = {**kwargs}
        if "headers" in merged:
            merged["headers"] = {**merged["headers"], **headers}
        else:
            merged["headers"] = headers

        for attempt in range(self._max_retries + 1):
            await self._bucket.acquire()
            resp = await self._transport.request(method, full_url, **merged)
            if resp.status_code == 429:
                retry_after = _parse_retry_after(resp)
                if attempt < self._max_retries:
                    await asyncio.sleep(retry_after)
                    continue
                raise FyersRateLimitError(
                    "Fyers rate limit exceeded",
                    code=-429,
                    status_code=429,
                    retry_after=retry_after,
                )
            return self._classify(resp)

        # Unreachable: the loop always returns or raises.
        raise FyersAPIError("Fyers request failed", status_code=0)

    async def get(self, url: str) -> Any:
        return await self.request("GET", url)

    async def post(self, url: str, **kwargs: Any) -> Any:
        return await self.request("POST", url, **kwargs)

    async def patch(self, url: str, **kwargs: Any) -> Any:
        return await self.request("PATCH", url, **kwargs)

    async def delete(self, url: str, **kwargs: Any) -> Any:
        return await self.request("DELETE", url, **kwargs)

    async def get_profile(self) -> Any:
        """Liveness probe: GET /profile (returns parsed JSON on success)."""
        return await self.get("/profile")

    @staticmethod
    def _classify(resp: Any) -> Any:
        try:
            data = resp.json()
        except Exception:
            data = {}
        code = data.get("code") if isinstance(data, dict) else None

        if resp.status_code == 401 or code in EXPIRY_ERROR_CODES:
            raise FyersTokenExpired(
                "Fyers token expired", code=code, status_code=resp.status_code
            )
        if resp.status_code == 403 or code == ENTITLEMENT_ERROR_CODE:
            raise FyersDataEntitlementError(
                "App lacks the Fyers data entitlement (403/-373)",
                code=code,
                status_code=resp.status_code,
            )
        if 200 <= resp.status_code < 300:
            return data
        raise FyersAPIError(
            "Fyers API error",
            code=code,
            status_code=resp.status_code,
        )


def _parse_retry_after(resp: Any) -> float:
    """Seconds to sleep before a 429 retry, clamped to ``[_MIN_RETRY_AFTER,
    _MAX_RETRY_AFTER]``.

    Accepts both RFC 7231 forms of ``Retry-After``:

    - delta-seconds: ``Retry-After: 2`` (float seconds)
    - HTTP-date: ``Retry-After: Wed, 05 Aug 2026 12:00:00 GMT`` (the delay is
      seconds until that instant)

    A missing or unparseable header falls back to the 1s floor — a 429 must
    never resolve to a zero-second sleep. The 10s cap keeps a far-future date
    (e.g. a full-day ban) from hanging a request for hours.
    """
    raw = resp.headers.get("Retry-After")
    if raw is None:
        return _MIN_RETRY_AFTER

    # Delta-seconds form: "2" or "2.5".
    try:
        delta = float(raw)
    except (TypeError, ValueError):
        # HTTP-date form: "Wed, 05 Aug 2026 12:00:00 GMT".
        try:
            when = email.utils.parsedate_to_datetime(raw)
            if when.tzinfo is None:
                # RFC 7231 HTTP-dates are always GMT; treat naive dates as UTC
                # so ``timestamp()`` is not interpreted as local time.
                when = when.replace(tzinfo=datetime.timezone.utc)
            delta = when.timestamp() - time.time()
        except (TypeError, ValueError, OverflowError):
            return _MIN_RETRY_AFTER

    return min(max(delta, _MIN_RETRY_AFTER), _MAX_RETRY_AFTER)
