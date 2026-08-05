"""Fyers HSM market-data socket wrapper (supervised SDK thread).

Owned by the F3 lane. The market-data socket
(``wss://socket.fyers.in/hsm/v1-5/prod``) speaks the HSM binary protocol —
reimplementing that raw is not worth the risk, so per the hybrid decision
(mission §9 Q2) this wraps the SDK's ``fyers_apiv3.FyersWebsocket.data_ws.
FyersDataSocket`` inside a supervisor thread, mirroring Dhan's
``_feed_supervisor`` pattern.

The SDK is a sync/threading model, so the import is guarded and the class
surfaces a clear error if the SDK is missing. :class:`FyersDataSocketWrapper`
takes ownership of the supervisor lifecycle:

- ``connect()`` starts the supervisor in an executor thread.
- The supervisor (re)builds the SDK socket on every cycle, re-applies the
  outstanding subscription set, and restarts with exponential backoff on
  drops.
- Token expiry (SDK error codes ``11001`` / ``-99``) is classified as
  :class:`FyersTokenExpired` and surfaced through :attr:`fatal_error` plus
  the error callback; there is no mid-stream renewal — a fresh token and a
  reconnect are required.
- ``disconnect()`` stops the supervisor and closes the SDK socket.
"""
from __future__ import annotations

import asyncio
import logging
import random
import threading
from typing import Any, Callable

from shettyxtreme.integration.fyers.client import FyersError, FyersTokenExpired

logger = logging.getLogger(__name__)

DATA_SOCKET_URL = "wss://socket.fyers.in/hsm/v1-5/prod"
DEFAULT_DATA_TYPE = "SymbolUpdate"
MAX_RESTART_ATTEMPTS = 50
RESTART_BASE_DELAY_SEC = 1.0
RESTART_MAX_DELAY_SEC = 8.0
RESTART_JITTER_MAX_SEC = 0.5

# SDK data-socket auth-error codes: 11001 (invalid/expired token) and -99.
TOKEN_EXPIRY_CODES: frozenset[int] = frozenset({11001, -99})

try:  # pragma: no cover - exercised only when the SDK is present
    from fyers_apiv3.FyersWebsocket.data_ws import (
        FyersDataSocket as _FyersDataSocket,
    )
except ImportError:  # pragma: no cover - SDK not installed yet (F4/F6 pin it)
    _FyersDataSocket = None  # type: ignore[assignment]

TickCallback = Callable[[list[Any]], Any]
ErrorCallback = Callable[[Any], Any]
CloseCallback = Callable[[], Any]


class FyersDataSocketWrapper:
    """Supervised wrapper around the SDK ``FyersDataSocket``.

    Args:
        app_id: Fyers application ID.
        access_token: Current access token.
        data_type: Default SDK data type for ``subscribe`` (SymbolUpdate,
            DepthUpdate, CommentryUpdate).
        max_restart_attempts: Consecutive restart attempts before the
            supervisor records a fatal error and stops.
        restart_base_delay / restart_max_delay / jitter_max: Backoff tuning.
    """

    def __init__(
        self,
        app_id: str,
        access_token: str,
        *,
        data_type: str = DEFAULT_DATA_TYPE,
        max_restart_attempts: int = MAX_RESTART_ATTEMPTS,
        restart_base_delay: float = RESTART_BASE_DELAY_SEC,
        restart_max_delay: float = RESTART_MAX_DELAY_SEC,
        jitter_max: float = RESTART_JITTER_MAX_SEC,
    ) -> None:
        self._app_id = app_id
        self._access_token = access_token
        self._default_data_type = data_type
        self._max_restart_attempts = max_restart_attempts
        self._restart_base_delay = restart_base_delay
        self._restart_max_delay = restart_max_delay
        self._jitter_max = jitter_max

        self._socket: Any = None
        self._supervisor_future: asyncio.Future | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_event = threading.Event()
        self._disconnected = threading.Event()
        self._running = False
        self._restart_attempt = 0
        self._last_error: Any = None
        self._fatal_error: Exception | None = None
        self._subscriptions: dict[str, list[str]] = {}

        self._tick_cb: TickCallback | None = None
        self._error_cb: ErrorCallback | None = None
        self._close_cb: CloseCallback | None = None

    # ---- callback registration ----

    def on_tick(self, callback: TickCallback) -> "FyersDataSocketWrapper":
        """Register the handler for symbol-update tick batches."""
        self._tick_cb = callback
        return self

    def on_error(self, callback: ErrorCallback) -> "FyersDataSocketWrapper":
        """Register the handler for SDK error messages."""
        self._error_cb = callback
        return self

    def on_close(self, callback: CloseCallback) -> "FyersDataSocketWrapper":
        """Register the handler invoked when a socket lifecycle ends."""
        self._close_cb = callback
        return self

    # ---- lifecycle ----

    @property
    def connected(self) -> bool:
        """True while the supervisor owns a live SDK socket."""
        return self._socket is not None

    async def is_connected(self) -> bool:
        """Async protocol view of :attr:`connected` (used by the F4 adapter)."""
        return self.connected

    @property
    def restart_attempts(self) -> int:
        """Number of consecutive restart attempts (reset on a live link)."""
        return self._restart_attempt

    @property
    def fatal_error(self) -> Exception | None:
        """The error that stopped the supervisor (token expiry / retries)."""
        return self._fatal_error

    @property
    def last_error(self) -> Any:
        """The most recent SDK error message (raw dict when available)."""
        return self._last_error

    async def connect(self) -> bool:
        """Start the supervisor thread. Returns True when it is running.

        Raises :class:`FyersError` when the ``fyers_apiv3`` SDK is not
        installed (the HSM binary protocol is delegated to the SDK).
        """
        if self._running:
            return True
        if _FyersDataSocket is None:
            raise FyersError(
                "fyers_apiv3 SDK not installed — cannot open the HSM data "
                "socket (pin fyers-apiv3 per the F3/F6 plan)"
            )
        self._running = True
        self._restart_attempt = 0
        self._stop_event.clear()
        self._loop = asyncio.get_running_loop()
        self._supervisor_future = self._loop.run_in_executor(
            None, self._supervisor
        )
        return True

    async def disconnect(self) -> None:
        """Stop the supervisor and close the SDK socket (local close)."""
        self._running = False
        self._stop_event.set()
        socket = self._socket
        if socket is not None:
            try:
                socket.close_connection()
            except Exception:
                pass
        if self._supervisor_future is not None:
            try:
                await asyncio.wait_for(self._supervisor_future, timeout=2.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass
        self._socket = None

    # ---- subscription ----

    async def subscribe(
        self, symbols: list[str], data_type: str | None = None
    ) -> bool:
        """Register symbols and push them to the live SDK socket (if any)."""
        dt = data_type or self._default_data_type
        known = self._subscriptions.setdefault(dt, [])
        for sym in symbols:
            if sym not in known:
                known.append(sym)
        socket = self._socket
        if socket is not None:
            try:
                socket.subscribe(symbols, data_type=dt)
            except Exception as exc:
                self._last_error = exc
                return False
        return True

    async def unsubscribe(
        self, symbols: list[str], data_type: str | None = None
    ) -> bool:
        """Drop symbols from the registry and the live SDK socket (if any)."""
        dt = data_type or self._default_data_type
        known = self._subscriptions.get(dt, [])
        for sym in symbols:
            if sym in known:
                known.remove(sym)
        socket = self._socket
        if socket is not None:
            try:
                socket.unsubscribe(symbols, data_type=dt)
            except Exception as exc:
                self._last_error = exc
                return False
        return True

    # ---- supervisor (runs on the executor thread) ----

    def _supervisor(self) -> None:
        while not self._stop_event.is_set():
            pending = {
                dt: list(syms) for dt, syms in self._subscriptions.items() if syms
            }
            socket = self._build_socket()
            self._socket = socket
            self._disconnected.clear()
            try:
                socket.connect()
            except Exception as exc:
                self._last_error = exc
                self._notify_error(exc)
            else:
                self._apply_subscriptions(socket, pending)
                while not self._stop_event.is_set():
                    if self._disconnected.wait(timeout=0.5):
                        break
            if self._stop_event.is_set():
                break
            if self._fatal_error is not None:
                break
            self._restart_attempt += 1
            if self._restart_attempt > self._max_restart_attempts:
                self._fatal_error = FyersError(
                    "Fyers data socket restart attempts exhausted "
                    f"({self._max_restart_attempts})"
                )
                self._notify_error(self._fatal_error)
                break
            delay = self._restart_delay(self._restart_attempt)
            logger.warning(
                "Fyers data socket dropped — restart %d/%d in %.2fs",
                self._restart_attempt, self._max_restart_attempts, delay,
            )
            if self._stop_event.wait(delay):
                break
        self._socket = None

    def _build_socket_kwargs(self) -> dict[str, Any]:
        """Constructor kwargs for the SDK ``FyersDataSocket``.

        Locked against ``inspect.signature(FyersDataSocket.__init__)`` in the
        tests. Two SDK facts drive this shape:

        - ``access_token_to_hsmtoken`` decodes the raw JWT (splits on ``.``
          and reads the ``hsm_key`` claim), so the access token is passed
          *without* the ``app_id:`` prefix that the REST/order-WS auth uses.
        - The SDK delivers exactly one dict per frame through ``on_message``
          (there is no ``on_symbols`` / ``on_generic_message`` hook).
        """
        return {
            "access_token": self._access_token,
            "write_to_file": False,
            "log_path": "",
            "on_connect": self._on_sdk_connect,
            "on_close": self._on_sdk_close,
            "on_error": self._on_sdk_error,
            "on_message": self._on_sdk_message,
        }

    def _build_socket(self) -> Any:
        if _FyersDataSocket is None:
            raise FyersError(
                "fyers_apiv3 SDK not installed — cannot open the HSM data socket"
            )
        return _FyersDataSocket(**self._build_socket_kwargs())

    def _apply_subscriptions(self, socket: Any, pending: dict[str, list[str]]) -> None:
        for data_type, symbols in pending.items():
            if not symbols:
                continue
            try:
                socket.subscribe(symbols, data_type=data_type)
            except Exception as exc:
                self._last_error = exc
                logger.warning(
                    "Fyers data socket resubscribe failed (%s): %s", data_type, exc
                )

    # ---- SDK callbacks (fired from the SDK socket thread) ----

    def _on_sdk_connect(self) -> None:
        self._restart_attempt = 0
        logger.info("Fyers data socket connected")

    def _on_sdk_close(self) -> None:
        self._disconnected.set()

    def _on_sdk_error(self, message: Any) -> None:
        code = None
        if isinstance(message, dict):
            code = message.get("code")
        self._last_error = message
        logger.error("Fyers data socket error: %s", message)
        if code in TOKEN_EXPIRY_CODES:
            self._fatal_error = FyersTokenExpired(
                "Fyers data socket token expired", code=code
            )
            self._disconnected.set()
        self._notify_error(message)

    def _on_sdk_message(self, message: Any) -> None:
        """SDK ``on_message``: one frame (dict) per symbol update.

        The frame is wrapped in a single-element list so the registered tick
        callback keeps its batch contract. Control/ack frames (auth, sub,
        unsub — no ``symbol`` key) flow through and are filtered by the
        adapter's parser.
        """
        self._dispatch_cb(self._tick_cb, [message])

    # ---- dispatch ----

    def _dispatch_cb(self, cb: Callable | None, *args: Any) -> None:
        if cb is None:
            return
        result = cb(*args)
        if asyncio.iscoroutine(result):
            loop = self._loop
            if loop is not None and loop.is_running():
                asyncio.run_coroutine_threadsafe(result, loop)

    def _notify_error(self, message: Any) -> None:
        self._dispatch_cb(self._error_cb, message)

    def _restart_delay(self, attempt: int) -> float:
        base = min(
            self._restart_base_delay * (2 ** max(attempt - 1, 0)),
            self._restart_max_delay,
        )
        return base + random.uniform(0.0, self._jitter_max)
