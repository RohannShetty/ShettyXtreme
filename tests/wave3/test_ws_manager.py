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
