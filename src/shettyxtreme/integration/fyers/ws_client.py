"""Fyers order WebSocket client (JSON protocol, raw ``websockets``).

Owned by the F3 lane. The order socket (``wss://socket.fyers.in/trade/v3``)
carries order/trade/position/EDIS updates as JSON text frames and replaces
the Dhan postback webhooks — fill fidelity improves.

Wire facts (primary-source verified 2026-08-04):

- Auth: handshake header ``authorization: <app_id>:<access_token>``.
- Subscribe frame: ``{"T": "SUB_ORD", "SLIST": [channels...], "SUB_T": 1}``
  (``SUB_T: -1`` unsubscribes; ``SLIST`` accepts orders/trades/positions/
  edis/pricealerts/login).
- Heartbeat: send the string ``"ping"`` every ~10s.
- Token expiry: the handshake is rejected with HTTP 403 (there is no
  mid-stream renewal). ``connect()`` raises :class:`FyersTokenExpired` when
  the *first* handshake is rejected; a 403 on a *reconnect* is classified the
  same way and surfaced through :attr:`fatal_error` plus the error callback.

The client is async-native. ``connect()`` blocks until the first handshake
settles (connected or fatally rejected); from then on a single supervised
task owns connect / read / ping / reconnect with exponential backoff
(1s -> 8s + jitter, capped attempts, local-close aware).
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any, Callable

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus

from shettyxtreme.integration.fyers.client import (
    FyersAPIError,
    FyersError,
    FyersTokenExpired,
)

logger = logging.getLogger(__name__)

ORDER_SOCKET_URL = "wss://socket.fyers.in/trade/v3"
PING_INTERVAL_SEC = 10.0
MAX_RECONNECT_ATTEMPTS = 50
RECONNECT_BASE_DELAY_SEC = 1.0
RECONNECT_MAX_DELAY_SEC = 8.0
RECONNECT_JITTER_MAX_SEC = 0.5
# A connection alive at least this long is "healthy" — its drop resets the
# backoff counter. Flapping connections (drop immediately) keep growing the
# exponential backoff instead of restarting at 1s every cycle.
RECONNECT_RESET_UPTIME_SEC = 5.0

# Channels the order socket accepts in ``SLIST``.
VALID_CHANNELS: tuple[str, ...] = (
    "orders", "trades", "positions", "edis", "pricealerts", "login",
)

MessageCallback = Callable[[Any], Any]
ErrorCallback = Callable[[Exception], Any]
CloseCallback = Callable[[], Any]


class FyersOrderSocket:
    """Async order-socket client for the Fyers trade WebSocket.

    Args:
        app_id: Fyers application ID.
        access_token: Current access token.
        url: Override the socket URL (used by tests / mirror endpoints).
        ping_interval: Heartbeat cadence in seconds.
        max_reconnect_attempts: Consecutive reconnect attempts before the
            client gives up and records a fatal :class:`FyersError`.
        reconnect_base_delay / reconnect_max_delay / jitter_max: Backoff
            tuning (1s doubling to 8s + uniform jitter by default).
    """

    def __init__(
        self,
        app_id: str,
        access_token: str,
        *,
        url: str = ORDER_SOCKET_URL,
        ping_interval: float = PING_INTERVAL_SEC,
        max_reconnect_attempts: int = MAX_RECONNECT_ATTEMPTS,
        reconnect_base_delay: float = RECONNECT_BASE_DELAY_SEC,
        reconnect_max_delay: float = RECONNECT_MAX_DELAY_SEC,
        jitter_max: float = RECONNECT_JITTER_MAX_SEC,
    ) -> None:
        self._app_id = app_id
        self._access_token = access_token
        self._url = url
        self._ping_interval = ping_interval
        self._max_reconnect_attempts = max_reconnect_attempts
        self._reconnect_base_delay = reconnect_base_delay
        self._reconnect_max_delay = reconnect_max_delay
        self._jitter_max = jitter_max

        self._ws: Any = None
        self._run_task: asyncio.Task | None = None
        self._local_close = False
        self._connected = False
        self._connected_event = asyncio.Event()
        self._reconnect_attempt = 0
        self._connected_at: float | None = None
        self._fatal_error: Exception | None = None

        self._on_message_cb: MessageCallback | None = None
        self._on_error_cb: ErrorCallback | None = None
        self._on_close_cb: CloseCallback | None = None

    # ---- callback registration ----

    def on_message(self, callback: MessageCallback) -> "FyersOrderSocket":
        """Register the handler for order/trade/position updates."""
        self._on_message_cb = callback
        return self

    def on_error(self, callback: ErrorCallback) -> "FyersOrderSocket":
        """Register the handler for connection/transport errors."""
        self._on_error_cb = callback
        return self

    def on_close(self, callback: CloseCallback) -> "FyersOrderSocket":
        """Register the handler invoked when a socket lifecycle ends."""
        self._on_close_cb = callback
        return self

    # ---- lifecycle ----

    @property
    def connected(self) -> bool:
        """True while a socket is open."""
        return self._connected

    @property
    def reconnect_attempts(self) -> int:
        """Number of consecutive reconnect attempts (reset on a live link)."""
        return self._reconnect_attempt

    @property
    def fatal_error(self) -> Exception | None:
        """The error that stopped the client (token expiry / exhausted retries)."""
        return self._fatal_error

    async def connect(self) -> bool:
        """Open the order socket and start the supervised background loop.

        Blocks until the first handshake settles. Raises
        :class:`FyersTokenExpired` when the handshake is rejected with 403.
        """
        if self._run_task is not None and not self._run_task.done():
            return True
        self._local_close = False
        self._reconnect_attempt = 0
        self._fatal_error = None
        self._connected_event.clear()
        self._run_task = asyncio.create_task(self._run())
        waiter = asyncio.create_task(self._connected_event.wait())
        done, _ = await asyncio.wait(
            {self._run_task, waiter}, return_when=asyncio.FIRST_COMPLETED
        )
        # Never cancel the run task — only the wait helper when the run task
        # settled first (e.g. a 403 handshake). Cancel the helper, not _run.
        if waiter not in done:
            waiter.cancel()
        if self._fatal_error is not None:
            raise self._fatal_error
        return True

    async def disconnect(self) -> None:
        """Local close: stop the supervisor and release the socket."""
        self._local_close = True
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._run_task is not None and not self._run_task.done():
            try:
                await asyncio.wait_for(self._run_task, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._run_task.cancel()

    async def __aenter__(self) -> "FyersOrderSocket":
        await self.connect()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.disconnect()

    # ---- subscription ----

    async def subscribe(self, channels: list[str]) -> bool:
        """Send a ``SUB_ORD`` frame subscribing to ``channels``."""
        if self._ws is None:
            return False
        frame = {"T": "SUB_ORD", "SLIST": list(channels), "SUB_T": 1}
        await self._ws.send(json.dumps(frame))
        return True

    async def unsubscribe(self, channels: list[str]) -> bool:
        """Send a ``SUB_ORD`` frame unsubscribing from ``channels``."""
        if self._ws is None:
            return False
        frame = {"T": "SUB_ORD", "SLIST": list(channels), "SUB_T": -1}
        await self._ws.send(json.dumps(frame))
        return True

    # ---- supervisor ----

    async def _run(self) -> None:
        """Supervised loop: connect, read, reconnect with backoff."""
        while not self._local_close:
            try:
                await self._connect_once()
                await self._read_loop()
            except FyersTokenExpired as exc:
                self._fatal_error = exc
                await self._notify_error(exc)
                break
            except Exception as exc:
                if not self._local_close:
                    await self._notify_error(exc)
            finally:
                self._ws = None
            # A connection that survived the healthy-uptime threshold counts
            # as stable: its drop starts a fresh backoff. Flapping links keep
            # growing the exponential backoff instead of resetting each cycle.
            if self._connected_at is not None:
                uptime = asyncio.get_running_loop().time() - self._connected_at
                self._connected_at = None
                if uptime >= RECONNECT_RESET_UPTIME_SEC:
                    self._reconnect_attempt = 0
            if self._local_close or self._fatal_error is not None:
                break
            self._reconnect_attempt += 1
            if self._reconnect_attempt >= self._max_reconnect_attempts:
                self._fatal_error = FyersError(
                    "Fyers order socket reconnect attempts exhausted "
                    f"({self._max_reconnect_attempts})"
                )
                await self._notify_error(self._fatal_error)
                break
            delay = self._reconnect_delay(self._reconnect_attempt)
            logger.warning(
                "Fyers order socket dropped — reconnect %d/%d in %.2fs",
                self._reconnect_attempt, self._max_reconnect_attempts, delay,
            )
            await self._backoff_sleep(delay)

    async def _connect_once(self) -> None:
        headers = {"authorization": f"{self._app_id}:{self._access_token}"}
        try:
            ws = await connect(self._url, additional_headers=headers)
        except InvalidStatus as exc:
            if exc.response.status_code == 403:
                raise FyersTokenExpired(
                    "Fyers order socket auth rejected (403)",
                    code=403,
                    status_code=exc.response.status_code,
                ) from exc
            raise FyersAPIError(
                "Fyers order socket handshake rejected",
                status_code=exc.response.status_code,
            ) from exc
        self._ws = ws
        self._connected = True
        self._connected_at = asyncio.get_running_loop().time()
        self._connected_event.set()
        logger.info("Fyers order socket connected")

    async def _read_loop(self) -> None:
        ws = self._ws
        assert ws is not None
        ping_task = asyncio.create_task(self._ping_loop(ws))
        try:
            async for message in ws:
                await self._dispatch_message(self._decode_message(message))
        except ConnectionClosed:
            pass
        finally:
            ping_task.cancel()
            try:
                await ping_task
            except asyncio.CancelledError:
                pass
            self._connected = False
            await self._notify_close()

    async def _ping_loop(self, ws: Any) -> None:
        while True:
            await asyncio.sleep(self._ping_interval)
            try:
                await ws.send("ping")
            except Exception:
                return

    # ---- dispatch helpers ----

    def _decode_message(self, message: str | bytes) -> Any:
        """Decode a JSON text frame to a dict/list; pass non-JSON through."""
        if isinstance(message, bytes):
            try:
                message = message.decode("utf-8")
            except UnicodeDecodeError:
                return message
        if isinstance(message, str):
            try:
                return json.loads(message)
            except (ValueError, TypeError):
                return message
        return message

    async def _dispatch_message(self, message: Any) -> None:
        cb = self._on_message_cb
        if cb is None:
            return
        result = cb(message)
        if asyncio.iscoroutine(result):
            await result

    async def _notify_close(self) -> None:
        cb = self._on_close_cb
        if cb is None:
            return
        result = cb()
        if asyncio.iscoroutine(result):
            await result

    async def _notify_error(self, exc: Exception) -> None:
        cb = self._on_error_cb
        if cb is None:
            return
        result = cb(exc)
        if asyncio.iscoroutine(result):
            await result

    async def _backoff_sleep(self, delay: float) -> None:
        await asyncio.sleep(delay)

    def _reconnect_delay(self, attempt: int) -> float:
        base = min(
            self._reconnect_base_delay * (2 ** max(attempt - 1, 0)),
            self._reconnect_max_delay,
        )
        return base + random.uniform(0.0, self._jitter_max)
