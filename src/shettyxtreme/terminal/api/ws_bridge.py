"""WebSocket broadcast bridge for projections.

Thin helper that projections call after updating state.
Avoids circular imports (projections don't import ws_manager directly).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from shettyxtreme.terminal.api.ws_manager import WebSocketManager

logger = logging.getLogger(__name__)

_manager: WebSocketManager | None = None


def configure(manager: WebSocketManager) -> None:
    """Set the WebSocketManager instance for broadcasting."""
    global _manager
    _manager = manager
    logger.info("ws_bridge configured (connections: %d)", manager.connection_count)


async def broadcast(topic: str, data: dict) -> None:
    """Broadcast data to all connected WebSocket clients.

    Safe to call even if no manager is configured — logs a warning and no-ops.
    """
    if _manager is None:
        logger.debug("ws_bridge: no manager configured, skipping broadcast for %s", topic)
        return
    if _manager.connection_count == 0:
        return
    try:
        await _manager.broadcast(topic, data)
    except Exception:
        logger.exception("ws_bridge: broadcast failed for topic %s", topic)
