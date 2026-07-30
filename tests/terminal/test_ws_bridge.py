import pytest
from unittest.mock import AsyncMock, MagicMock

from shettyxtreme.terminal.api import ws_bridge


@pytest.fixture(autouse=True)
def _reset_bridge():
    yield
    ws_bridge._manager = None


@pytest.mark.asyncio
async def test_broadcast_sends_to_manager():
    manager = MagicMock()
    manager.connection_count = 1
    manager.broadcast = AsyncMock()
    ws_bridge.configure(manager)

    await ws_bridge.broadcast("tick", {"symbol": "NIFTY"})

    manager.broadcast.assert_awaited_once_with("tick", {"symbol": "NIFTY"})


@pytest.mark.asyncio
async def test_broadcast_no_manager_no_crash():
    await ws_bridge.broadcast("tick", {"symbol": "NIFTY"})


@pytest.mark.asyncio
async def test_broadcast_empty_connections_no_crash():
    manager = MagicMock()
    manager.connection_count = 0
    manager.broadcast = AsyncMock()
    ws_bridge.configure(manager)

    await ws_bridge.broadcast("tick", {"symbol": "NIFTY"})

    manager.broadcast.assert_not_awaited()
