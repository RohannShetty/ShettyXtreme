"""WebSocket manager — handles connected WS clients and broadcasting."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manage connected WebSocket clients and broadcast data."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._topics: dict[str, list[WebSocket]] = {}

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self._connections.append(websocket)
        logger.info("WebSocket client connected (%d total)", len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket client."""
        self._connections.remove(websocket)
        # Clean up topic subscriptions
        for topic_clients in self._topics.values():
            if websocket in topic_clients:
                topic_clients.remove(websocket)
        logger.info("WebSocket client disconnected (%d remain)", len(self._connections))

    async def subscribe(self, websocket: WebSocket, topic: str) -> None:
        """Subscribe a client to a topic."""
        if topic not in self._topics:
            self._topics[topic] = []
        if websocket not in self._topics[topic]:
            self._topics[topic].append(websocket)

    async def unsubscribe(self, websocket: WebSocket, topic: str) -> None:
        """Unsubscribe a client from a topic."""
        if topic in self._topics and websocket in self._topics[topic]:
            self._topics[topic].remove(websocket)

    async def broadcast(self, topic: str, data: dict[str, Any]) -> None:
        """Broadcast data to all connected clients.

        Tries to send to each client; removes dead connections silently.
        """
        disconnected: list[WebSocket] = []
        for ws in self._connections:
            try:
                payload = json.dumps({"topic": topic, "data": data}, default=str)
                await ws.send_text(payload)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            try:
                await self.disconnect(ws)
            except Exception:
                pass

    @property
    def connection_count(self) -> int:
        return len(self._connections)
