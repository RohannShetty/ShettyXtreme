"""Tests for WebSocket manager."""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from shettyxtreme.terminal.api.ws_manager import WebSocketManager


class TestWebSocketManager:
    @pytest.mark.asyncio
    async def test_connect_disconnect(self) -> None:
        mgr = WebSocketManager()
        ws = AsyncMock()
        ws.send_text = AsyncMock()

        await mgr.connect(ws)
        assert mgr.connection_count == 1

        await mgr.disconnect(ws)
        assert mgr.connection_count == 0

    @pytest.mark.asyncio
    async def test_broadcast_sends_to_all(self) -> None:
        mgr = WebSocketManager()
        ws1 = AsyncMock()
        ws2 = AsyncMock()
        ws1.send_text = AsyncMock()
        ws2.send_text = AsyncMock()

        await mgr.connect(ws1)
        await mgr.connect(ws2)

        await mgr.broadcast("test", {"key": "value"})
        assert ws1.send_text.called
        assert ws2.send_text.called

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self) -> None:
        mgr = WebSocketManager()
        ws = AsyncMock()
        ws.send_text = AsyncMock(side_effect=Exception("dead"))

        await mgr.connect(ws)
        assert mgr.connection_count == 1

        await mgr.broadcast("test", {})
        assert mgr.connection_count == 0

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe(self) -> None:
        mgr = WebSocketManager()
        ws = AsyncMock()
        await mgr.connect(ws)
        await mgr.subscribe(ws, "ticks")
        await mgr.unsubscribe(ws, "ticks")
        # Should not raise
        assert True

    @pytest.mark.asyncio
    async def test_subscribe_filters_broadcast_by_topic(self) -> None:
        mgr = WebSocketManager()
        subscribed = AsyncMock()
        unsubscribed = AsyncMock()
        subscribed.send_text = AsyncMock()
        unsubscribed.send_text = AsyncMock()

        await mgr.connect(subscribed)
        await mgr.connect(unsubscribed)
        await mgr.subscribe(subscribed, ["tick"])

        await mgr.broadcast("alert", {})
        assert not subscribed.send_text.called
        assert unsubscribed.send_text.called

    @pytest.mark.asyncio
    async def test_broadcast_delivers_subscribed_topic(self) -> None:
        mgr = WebSocketManager()
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        await mgr.connect(ws)
        await mgr.subscribe(ws, ["tick"])

        await mgr.broadcast("tick", {"ltp": 100})
        assert ws.send_text.called
        sent = ws.send_text.await_args.args[0]
        assert '"topic": "tick"' in sent
        assert '"ltp": 100' in sent

    @pytest.mark.asyncio
    async def test_subscribe_replaces_previous_topics(self) -> None:
        mgr = WebSocketManager()
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        await mgr.connect(ws)
        await mgr.subscribe(ws, ["tick", "alert"])
        await mgr.subscribe(ws, ["tick"])

        await mgr.broadcast("alert", {})
        assert not ws.send_text.called
        await mgr.broadcast("tick", {})
        assert ws.send_text.called

    @pytest.mark.asyncio
    async def test_unsubscribe_returns_client_to_unfiltered(self) -> None:
        mgr = WebSocketManager()
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        await mgr.connect(ws)
        await mgr.subscribe(ws, ["tick"])
        await mgr.unsubscribe(ws, ["tick"])

        await mgr.broadcast("alert", {})
        assert ws.send_text.called

    @pytest.mark.asyncio
    async def test_subscribe_empty_list_means_unfiltered(self) -> None:
        mgr = WebSocketManager()
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        await mgr.connect(ws)
        await mgr.subscribe(ws, [])

        await mgr.broadcast("alert", {})
        assert ws.send_text.called

    @pytest.mark.asyncio
    async def test_subscribe_string_signature(self) -> None:
        mgr = WebSocketManager()
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        await mgr.connect(ws)
        await mgr.subscribe(ws, "tick")

        await mgr.broadcast("alert", {})
        assert not ws.send_text.called
        await mgr.broadcast("tick", {})
        assert ws.send_text.called

    @pytest.mark.asyncio
    async def test_disconnect_clears_subscriptions(self) -> None:
        mgr = WebSocketManager()
        ws = AsyncMock()
        ws.send_text = AsyncMock()
        await mgr.connect(ws)
        await mgr.subscribe(ws, ["tick"])
        await mgr.disconnect(ws)
        assert mgr.connection_count == 0
        assert mgr._topics == {}
