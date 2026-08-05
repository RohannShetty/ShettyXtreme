"""F3 — Fyers HSM data-socket wrapper tests.

The wrapper supervises the SDK's ``FyersDataSocket`` (not installed yet), so
the SDK class is swapped for a mock at the module seam
(``data_socket._FyersDataSocket``) and the supervisor's threading model is
exercised for real: the supervisor runs on an executor thread and the mock
fires SDK callbacks synchronously from ``connect()``, exactly like the real
SDK does from its internal socket thread.

Covered:
- ``connect()`` builds a supervised SDK socket with the raw-JWT access token.
- ``subscribe``/``unsubscribe`` forward to the SDK socket and update the
  re-subscription registry.
- Tick frames from ``on_message`` reach the registered handler.
- The supervisor restarts after a disconnect and re-applies subscriptions.
- SDK auth-error codes 11001 / -99 classify as :class:`FyersTokenExpired`.
- Missing SDK raises a clear :class:`FyersError`.
- ``disconnect()`` calls ``close_connection()`` on the SDK socket and stops
  the supervisor.
- ``_build_socket_kwargs`` stays within the installed SDK's constructor
  signature (contract lock).
"""
from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable
from unittest.mock import patch

import pytest

from shettyxtreme.integration.fyers.client import FyersError, FyersTokenExpired
from shettyxtreme.integration.fyers.data_socket import (
    FyersDataSocketWrapper,
    TOKEN_EXPIRY_CODES,
)

APP_ID = "APP123"
TOKEN = "TOK9"

_PATCH_TARGET = "shettyxtreme.integration.fyers.data_socket._FyersDataSocket"


async def _until(predicate: Callable[[], bool], timeout: float = 3.0, msg: str = "") -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError(f"timed out waiting for {msg or 'condition'}")
        await asyncio.sleep(0.01)


class MockFyersDataSocket:
    """Stands in for ``fyers_apiv3...FyersDataSocket`` (SDK not installed)."""

    instances: list["MockFyersDataSocket"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.connect_called = 0
        self.subscribe_calls: list[tuple[list[str], str]] = []
        self.unsubscribe_calls: list[tuple[list[str], str]] = []
        self.closed = False
        MockFyersDataSocket.instances.append(self)

    def connect(self) -> None:
        self.connect_called += 1

    def subscribe(self, symbols: list[str], data_type: str = "SymbolUpdate") -> None:
        self.subscribe_calls.append((list(symbols), data_type))

    def unsubscribe(self, symbols: list[str], data_type: str = "SymbolUpdate") -> None:
        self.unsubscribe_calls.append((list(symbols), data_type))

    def close_connection(self) -> None:
        self.closed = True


class MockDroppingSocket(MockFyersDataSocket):
    """Socket that drops immediately — fires on_close from connect()."""

    def connect(self) -> None:
        super().connect()
        self.kwargs["on_close"]()


def _auth_error_socket(code: int) -> type[MockFyersDataSocket]:
    """Factory for a socket that fires an SDK auth error on connect()."""

    class _AuthErrorSocket(MockFyersDataSocket):
        def connect(self) -> None:
            super().connect()
            self.kwargs["on_error"]({"code": code, "message": "Invalid Token"})

    return _AuthErrorSocket


class MockTransientAuthSocket(MockFyersDataSocket):
    """First instance fires a token-expiry error on connect(); later ones
    are healthy — models a transient fatal error that the app recovers."""

    fired = False

    def connect(self) -> None:
        super().connect()
        if not MockTransientAuthSocket.fired:
            MockTransientAuthSocket.fired = True
            self.kwargs["on_error"]({"code": 11001, "message": "Invalid Token"})


@pytest.fixture(autouse=True)
def _reset_mock_instances() -> None:
    MockFyersDataSocket.instances.clear()
    yield


class TestConnect:
    @pytest.mark.asyncio
    @patch(_PATCH_TARGET, MockFyersDataSocket)
    async def test_connect_builds_supervised_socket(self) -> None:
        wrapper = FyersDataSocketWrapper(APP_ID, TOKEN)
        try:
            assert await wrapper.connect() is True
            await _until(lambda: wrapper._socket is not None, msg="socket created")
            instance = wrapper._socket
            assert isinstance(instance, MockFyersDataSocket)
            assert instance.connect_called == 1
            assert instance.kwargs["access_token"] == TOKEN
            for cb in ("on_connect", "on_close", "on_error", "on_message"):
                assert callable(instance.kwargs[cb]), cb
            assert wrapper.connected is True
        finally:
            await wrapper.disconnect()

    @pytest.mark.asyncio
    async def test_connect_raises_when_sdk_missing(self) -> None:
        with patch(_PATCH_TARGET, None):
            wrapper = FyersDataSocketWrapper(APP_ID, TOKEN)
            with pytest.raises(FyersError):
                await wrapper.connect()


class TestSdkContract:
    def test_build_socket_kwargs_locked_to_sdk_signature(self) -> None:
        """Lock ``_build_socket_kwargs`` to the installed SDK constructor.

        Guards the real contract: every kwarg must exist on
        ``FyersDataSocket.__init__``, the access token must be the raw JWT
        (``access_token_to_hsmtoken`` splits on ``.``), and the callback
        hooks must be the SDK's real ones (``on_message`` — there is no
        ``on_symbols`` / ``on_generic_message``).
        """
        data_ws = pytest.importorskip("fyers_apiv3.FyersWebsocket.data_ws")
        sig = inspect.signature(data_ws.FyersDataSocket.__init__)
        wrapper = FyersDataSocketWrapper(APP_ID, TOKEN)
        kwargs = wrapper._build_socket_kwargs()
        assert set(kwargs) <= set(sig.parameters)
        assert kwargs["access_token"] == TOKEN  # raw JWT, no "app_id:" prefix
        assert kwargs["on_message"] == wrapper._on_sdk_message
        assert not {"on_symbols", "on_generic_message"} & set(kwargs)


class TestSubscribe:
    @pytest.mark.asyncio
    @patch(_PATCH_TARGET, MockFyersDataSocket)
    async def test_subscribe_forwards_to_sdk_socket(self) -> None:
        wrapper = FyersDataSocketWrapper(APP_ID, TOKEN)
        try:
            await wrapper.connect()
            await _until(lambda: wrapper._socket is not None, msg="socket created")
            assert await wrapper.subscribe(["NSE:SBIN-EQ"]) is True
            assert wrapper._socket.subscribe_calls == [
                (["NSE:SBIN-EQ"], "SymbolUpdate")
            ]
            assert wrapper._subscriptions == {"SymbolUpdate": ["NSE:SBIN-EQ"]}
        finally:
            await wrapper.disconnect()

    @pytest.mark.asyncio
    @patch(_PATCH_TARGET, MockFyersDataSocket)
    async def test_subscribe_custom_data_type(self) -> None:
        wrapper = FyersDataSocketWrapper(APP_ID, TOKEN)
        try:
            await wrapper.connect()
            await _until(lambda: wrapper._socket is not None, msg="socket created")
            await wrapper.subscribe(["NSE:NIFTY50-INDEX"], data_type="DepthUpdate")
            assert wrapper._socket.subscribe_calls == [
                (["NSE:NIFTY50-INDEX"], "DepthUpdate")
            ]
        finally:
            await wrapper.disconnect()

    @pytest.mark.asyncio
    @patch(_PATCH_TARGET, MockFyersDataSocket)
    async def test_subscribe_before_connect_is_queued(self) -> None:
        wrapper = FyersDataSocketWrapper(APP_ID, TOKEN)
        try:
            assert await wrapper.subscribe(["NSE:SBIN-EQ"]) is True
            assert wrapper._subscriptions == {"SymbolUpdate": ["NSE:SBIN-EQ"]}
        finally:
            await wrapper.disconnect()

    @pytest.mark.asyncio
    @patch(_PATCH_TARGET, MockFyersDataSocket)
    async def test_unsubscribe_forwards_and_updates_registry(self) -> None:
        wrapper = FyersDataSocketWrapper(APP_ID, TOKEN)
        try:
            await wrapper.connect()
            await _until(lambda: wrapper._socket is not None, msg="socket created")
            await wrapper.subscribe(["NSE:SBIN-EQ", "NSE:NIFTY50-INDEX"])
            assert await wrapper.unsubscribe(["NSE:SBIN-EQ"]) is True
            assert wrapper._socket.unsubscribe_calls == [
                (["NSE:SBIN-EQ"], "SymbolUpdate")
            ]
            assert wrapper._subscriptions == {"SymbolUpdate": ["NSE:NIFTY50-INDEX"]}
        finally:
            await wrapper.disconnect()


class TestTickHandler:
    @pytest.mark.asyncio
    @patch(_PATCH_TARGET, MockFyersDataSocket)
    async def test_symbol_frame_reaches_tick_handler(self) -> None:
        wrapper = FyersDataSocketWrapper(APP_ID, TOKEN)
        received: list[Any] = []
        wrapper.on_tick(received.append)
        try:
            await wrapper.connect()
            await _until(lambda: wrapper._socket is not None, msg="socket created")
            # The SDK delivers one dict per frame via on_message; the wrapper
            # re-wraps it in a single-element batch for the tick callback.
            tick = {"type": "sf", "symbol": "NSE:SBIN-EQ", "ltp": 800.5}
            wrapper._socket.kwargs["on_message"](tick)
            assert received == [[tick]]
        finally:
            await wrapper.disconnect()


class TestSupervisor:
    @pytest.mark.asyncio
    @patch(_PATCH_TARGET, MockDroppingSocket)
    async def test_restarts_after_disconnect_and_resubscribes(self) -> None:
        wrapper = FyersDataSocketWrapper(
            APP_ID, TOKEN,
            restart_base_delay=0.01, restart_max_delay=0.05, jitter_max=0.0,
        )
        await wrapper.subscribe(["NSE:SBIN-EQ"])  # queued before connect
        try:
            await wrapper.connect()
            await _until(
                lambda: len(MockFyersDataSocket.instances) >= 3,
                timeout=3.0, msg="supervisor restarts",
            )
            instances = list(MockFyersDataSocket.instances)
            assert instances[0].connect_called == 1
            assert instances[1].connect_called == 1
            assert wrapper.restart_attempts >= 2
            # Outstanding subscription re-applied on the restarted socket.
            assert any(
                "NSE:SBIN-EQ" in syms for syms, _ in instances[1].subscribe_calls
            )
        finally:
            await wrapper.disconnect()


class TestRecovery:
    @pytest.mark.asyncio
    @patch(_PATCH_TARGET, MockTransientAuthSocket)
    async def test_reconnect_recovers_after_transient_fatal_error(self) -> None:
        """F-INT-003: a fatal error stops the supervisor and releases its
        ownership; reconnect() clears the error and brings the socket back."""
        MockTransientAuthSocket.fired = False
        wrapper = FyersDataSocketWrapper(
            APP_ID, TOKEN,
            restart_base_delay=0.01, restart_max_delay=0.02, jitter_max=0.0,
        )
        await wrapper.subscribe(["NSE:SBIN-EQ"])
        try:
            await wrapper.connect()
            await _until(
                lambda: wrapper.fatal_error is not None,
                timeout=3.0, msg="fatal error",
            )
            # The supervisor must have fully exited and released ownership,
            # otherwise reconnect() would no-op on a stale _running flag.
            await _until(
                lambda: not wrapper._running,
                timeout=3.0, msg="supervisor stopped",
            )
            assert isinstance(wrapper.fatal_error, FyersTokenExpired)
            assert wrapper._socket is None
            assert wrapper.connected is False

            await wrapper.reconnect()
            await _until(
                lambda: wrapper.connected, timeout=3.0, msg="reconnected",
            )
            assert wrapper.fatal_error is None
            assert wrapper._socket is not None
            # Outstanding subscriptions re-applied on the fresh socket.
            assert any(
                "NSE:SBIN-EQ" in syms for syms, _ in wrapper._socket.subscribe_calls
            )
        finally:
            await wrapper.disconnect()

    @pytest.mark.asyncio
    @patch(_PATCH_TARGET, MockTransientAuthSocket)
    async def test_connect_after_fatal_error_restarts_supervisor(self) -> None:
        """F-INT-003: a plain connect() after a fatal error also recovers —
        the supervisor releases _running on exit, so connect() restarts."""
        MockTransientAuthSocket.fired = False
        wrapper = FyersDataSocketWrapper(
            APP_ID, TOKEN,
            restart_base_delay=0.01, restart_max_delay=0.02, jitter_max=0.0,
        )
        try:
            await wrapper.connect()
            await _until(
                lambda: not wrapper._running,
                timeout=3.0, msg="stopped after fatal error",
            )
            assert wrapper.fatal_error is not None

            assert await wrapper.connect() is True
            await _until(
                lambda: wrapper.connected, timeout=3.0, msg="restarted",
            )
            assert wrapper.fatal_error is None
        finally:
            await wrapper.disconnect()


class TestBackoffReporting:
    @pytest.mark.asyncio
    @patch(_PATCH_TARGET, MockDroppingSocket)
    async def test_connected_false_during_restart_backoff(self) -> None:
        """F-INT-010: connected is False while the supervisor waits out its
        restart backoff, and stays False after a local disconnect."""
        wrapper = FyersDataSocketWrapper(
            APP_ID, TOKEN,
            restart_base_delay=1.0, restart_max_delay=1.0, jitter_max=0.0,
        )
        try:
            await wrapper.connect()
            await _until(
                lambda: wrapper._reconnecting, timeout=3.0, msg="backoff flag",
            )
            assert wrapper.connected is False
            assert wrapper.restart_attempts >= 1
            # The dead socket object is retained during backoff — but the
            # wrapper must not report itself as connected while reconnecting.
            assert wrapper._socket is not None

            await wrapper.disconnect()
            assert wrapper._reconnecting is False
            assert wrapper.connected is False
            assert wrapper._socket is None
        finally:
            await wrapper.disconnect()


class TestTokenExpiry:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("code", sorted(TOKEN_EXPIRY_CODES))
    async def test_sdk_auth_error_classified(self, code: int) -> None:
        with patch(_PATCH_TARGET, _auth_error_socket(code)):
            wrapper = FyersDataSocketWrapper(
                APP_ID, TOKEN,
                restart_base_delay=0.01, restart_max_delay=0.02, jitter_max=0.0,
            )
            errors: list[Any] = []
            wrapper.on_error(errors.append)
            try:
                await wrapper.connect()
                await _until(
                    lambda: wrapper.fatal_error is not None,
                    timeout=3.0, msg="token expiry",
                )
                assert isinstance(wrapper.fatal_error, FyersTokenExpired)
                assert wrapper.fatal_error.code == code
                # Raw SDK message is surfaced to the error handler.
                assert errors and errors[0] == {
                    "code": code, "message": "Invalid Token"
                }
                assert wrapper._socket is None  # supervisor stopped
            finally:
                await wrapper.disconnect()

    @pytest.mark.asyncio
    @patch(_PATCH_TARGET, MockFyersDataSocket)
    async def test_non_expiry_error_keeps_supervisor_alive(self) -> None:
        wrapper = FyersDataSocketWrapper(APP_ID, TOKEN)
        try:
            await wrapper.connect()
            await _until(lambda: wrapper._socket is not None, msg="socket created")
            wrapper._socket.kwargs["on_error"]({"code": -1000, "message": "whoops"})
            await asyncio.sleep(0.05)
            assert wrapper.fatal_error is None
            assert wrapper.connected is True
        finally:
            await wrapper.disconnect()


class TestDisconnect:
    @pytest.mark.asyncio
    @patch(_PATCH_TARGET, MockFyersDataSocket)
    async def test_disconnect_closes_socket_and_stops_supervisor(self) -> None:
        wrapper = FyersDataSocketWrapper(APP_ID, TOKEN)
        await wrapper.connect()
        await _until(lambda: wrapper._socket is not None, msg="socket created")
        instance = wrapper._socket
        await wrapper.disconnect()
        assert instance.closed is True
        assert wrapper._socket is None
        assert wrapper.connected is False
