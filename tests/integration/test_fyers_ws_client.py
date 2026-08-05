"""F3 — Fyers order WebSocket client tests.

The order socket is exercised against a real in-process ``websockets`` server
on loopback (no external network). This is the closest thing Fyers has to a
sandbox for the WS layer and gives real handshake/header/frame coverage.

Covered:
- ``connect()`` sends the ``authorization: <app_id>:<access_token>`` header.
- ``subscribe``/``unsubscribe`` emit the ``SUB_ORD`` frame (SUB_T 1 / -1).
- Message handler receives decoded JSON order updates.
- ``"ping"`` heartbeat cadence.
- Reconnect uses exponential backoff (1 -> 2 -> 4 -> 8 -> 8…).
- A 403 handshake on first connect raises :class:`FyersTokenExpired`;
  a 403 on reconnect is classified and surfaced via ``fatal_error``.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any, Callable
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from websockets.asyncio.server import serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Response

from shettyxtreme.integration.fyers.client import FyersTokenExpired
from shettyxtreme.integration.fyers.ws_client import (
    FyersOrderSocket,
    ORDER_SOCKET_URL,
)

APP_ID = "APP123"
TOKEN = "TOK9"


async def _until(predicate: Callable[[], bool], timeout: float = 3.0, msg: str = "") -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not predicate():
        if loop.time() > deadline:
            raise AssertionError(f"timed out waiting for {msg or 'condition'}")
        await asyncio.sleep(0.01)


@pytest_asyncio.fixture
async def make_server():
    """Factory fixture starting real loopback websockets servers."""
    servers: list[Any] = []

    async def _make(handler: Callable, process_request: Callable | None = None) -> str:
        server = await serve(handler, "127.0.0.1", 0, process_request=process_request)
        port = server.sockets[0].getsockname()[1]
        servers.append(server)
        return f"ws://127.0.0.1:{port}/"

    try:
        yield _make
    finally:
        for server in servers:
            server.close()
        for server in servers:
            try:
                await server.wait_closed()
            except Exception:
                pass


def _recording_handler(received: list[Any]) -> Callable:
    async def handler(conn: Any) -> None:
        try:
            async for message in conn:
                received.append(message)
        except ConnectionClosed:
            pass
    return handler


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_sends_auth_header(self, make_server) -> None:
        seen: list[str | None] = []

        async def handler(conn: Any) -> None:
            seen.append(conn.request.headers.get("authorization"))

        url = await make_server(handler)
        client = FyersOrderSocket(APP_ID, TOKEN, url=url)
        try:
            assert await client.connect() is True
            assert client.connected is True
            await _until(lambda: bool(seen), msg="auth header")
            assert seen == [f"{APP_ID}:{TOKEN}"]
        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_connect_url_defaults_to_order_socket(self) -> None:
        client = FyersOrderSocket(APP_ID, TOKEN)
        assert client._url == ORDER_SOCKET_URL


class TestSubscribe:
    @pytest.mark.asyncio
    async def test_subscribe_sends_sub_ord_frame(self, make_server) -> None:
        received: list[Any] = []
        url = await make_server(_recording_handler(received))
        client = FyersOrderSocket(APP_ID, TOKEN, url=url)
        try:
            await client.connect()
            assert await client.subscribe(["orders", "trades"]) is True
            await _until(lambda: len(received) == 1, msg="SUB_ORD frame")
            assert json.loads(received[0]) == {
                "T": "SUB_ORD", "SLIST": ["orders", "trades"], "SUB_T": 1,
            }
        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_unsubscribe_sends_sub_t_neg1(self, make_server) -> None:
        received: list[Any] = []
        url = await make_server(_recording_handler(received))
        client = FyersOrderSocket(APP_ID, TOKEN, url=url)
        try:
            await client.connect()
            assert await client.unsubscribe(["positions"]) is True
            await _until(lambda: len(received) == 1, msg="SUB_ORD frame")
            assert json.loads(received[0]) == {
                "T": "SUB_ORD", "SLIST": ["positions"], "SUB_T": -1,
            }
        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_subscribe_before_connect_returns_false(self) -> None:
        client = FyersOrderSocket(APP_ID, TOKEN)
        assert await client.subscribe(["orders"]) is False


class TestMessageHandler:
    @pytest.mark.asyncio
    async def test_order_update_dispatched_to_callback(self, make_server) -> None:
        order_update = {"type": "orders", "data": {"id": "O1", "status": "complete"}}

        async def handler(conn: Any) -> None:
            await conn.send(json.dumps(order_update))

        url = await make_server(handler)
        received: list[Any] = []
        client = FyersOrderSocket(APP_ID, TOKEN, url=url)
        client.on_message(received.append)
        try:
            await client.connect()
            await _until(lambda: len(received) == 1, msg="order update")
            assert received[0] == order_update
        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_subscription_confirmation_dispatched(self, make_server) -> None:
        confirmation = {"code": 1605, "message": "Successfully subscribed", "s": "ok"}

        async def handler(conn: Any) -> None:
            await conn.send(json.dumps(confirmation))

        url = await make_server(handler)
        received: list[Any] = []
        client = FyersOrderSocket(APP_ID, TOKEN, url=url)
        client.on_message(received.append)
        try:
            await client.connect()
            await _until(lambda: len(received) == 1, msg="confirmation")
            assert received[0] == confirmation
        finally:
            await client.disconnect()


class TestPing:
    @pytest.mark.asyncio
    async def test_ping_sent_on_interval(self, make_server) -> None:
        received: list[Any] = []
        url = await make_server(_recording_handler(received))
        client = FyersOrderSocket(APP_ID, TOKEN, url=url, ping_interval=0.05)
        try:
            await client.connect()
            await _until(lambda: received.count("ping") >= 2, timeout=3.0, msg="ping")
            assert received.count("ping") >= 2
        finally:
            await client.disconnect()


class TestReconnect:
    @pytest.mark.asyncio
    async def test_exponential_backoff_on_disconnect(self, make_server) -> None:
        async def drop(conn: Any) -> None:
            await conn.close()

        url = await make_server(drop)
        recorded: list[float] = []
        client = FyersOrderSocket(
            APP_ID, TOKEN, url=url, jitter_max=0.0, max_reconnect_attempts=10,
        )
        client._backoff_sleep = AsyncMock(side_effect=lambda d: recorded.append(d))  # type: ignore[method-assign]
        try:
            await client.connect()
            await _until(lambda: len(recorded) >= 5, msg="backoff delays")
            assert recorded[:5] == [1.0, 2.0, 4.0, 8.0, 8.0]
        finally:
            await client.disconnect()

    @pytest.mark.asyncio
    async def test_reconnect_attempts_capped(self, make_server) -> None:
        async def drop(conn: Any) -> None:
            await conn.close()

        url = await make_server(drop)
        client = FyersOrderSocket(
            APP_ID, TOKEN, url=url, jitter_max=0.0,
            max_reconnect_attempts=2, reconnect_base_delay=0.01,
            reconnect_max_delay=0.02,
        )
        try:
            await client.connect()
            await _until(
                lambda: client.fatal_error is not None, timeout=3.0, msg="fatal error"
            )
            assert "exhausted" in str(client.fatal_error)
            assert client.reconnect_attempts == 2
        finally:
            await client.disconnect()


class TestTokenExpiry:
    @pytest.mark.asyncio
    async def test_403_handshake_raises_on_connect(self, make_server) -> None:
        async def process_request(conn: Any, request: Any) -> Response:
            return Response(403, "Forbidden", Headers())

        async def handler(conn: Any) -> None:
            pass

        url = await make_server(handler, process_request=process_request)
        errors: list[Any] = []
        client = FyersOrderSocket(APP_ID, TOKEN, url=url)
        client.on_error(errors.append)
        with pytest.raises(FyersTokenExpired):
            await client.connect()
        assert isinstance(client.fatal_error, FyersTokenExpired)
        assert client.fatal_error.code == 403
        assert len(errors) == 1 and isinstance(errors[0], FyersTokenExpired)

    @pytest.mark.asyncio
    async def test_403_on_reconnect_surfaces_token_expired(self, make_server) -> None:
        attempts = {"n": 0}

        async def process_request(conn: Any, request: Any) -> Response | None:
            attempts["n"] += 1
            if attempts["n"] > 1:
                return Response(403, "Forbidden", Headers())
            return None

        async def drop(conn: Any) -> None:
            await conn.close()

        url = await make_server(drop, process_request=process_request)
        errors: list[Any] = []
        client = FyersOrderSocket(APP_ID, TOKEN, url=url, jitter_max=0.0)
        client.on_error(errors.append)
        try:
            await client.connect()
            await _until(
                lambda: client.fatal_error is not None, timeout=5.0, msg="token expiry"
            )
            assert isinstance(client.fatal_error, FyersTokenExpired)
            assert any(isinstance(e, FyersTokenExpired) for e in errors)
        finally:
            await client.disconnect()


class TestContextManager:
    @pytest.mark.asyncio
    async def test_async_context_manager(self, make_server) -> None:
        async def handler(conn: Any) -> None:
            pass

        url = await make_server(handler)
        async with FyersOrderSocket(APP_ID, TOKEN, url=url) as client:
            assert client.connected is True
        assert client.connected is False
        assert client._local_close is True
