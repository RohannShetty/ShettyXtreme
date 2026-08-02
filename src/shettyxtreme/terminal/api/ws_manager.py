"""WebSocket manager — handles connected WS clients and broadcasting."""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    """Manage connected WebSocket clients and broadcast data.

    Clients may declare topic subscriptions via subscribe()/unsubscribe().
    broadcast() delivers a topic only to clients subscribed to it; clients
    with no declared subscriptions receive everything — backward compatible
    with the original broadcast-to-all behavior.
    """

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._topics: dict[WebSocket, set[str]] = {}

    async def connect(self, websocket: WebSocket) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        self._connections.append(websocket)
        logger.info("WebSocket client connected (%d total)", len(self._connections))

    async def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket client."""
        self._connections.remove(websocket)
        self._topics.pop(websocket, None)
        logger.info("WebSocket client disconnected (%d remain)", len(self._connections))

    async def subscribe(
        self, websocket: WebSocket, topics: str | list[str]
    ) -> None:
        """Record a client's topic subscriptions, replacing the previous set.

        An empty list clears the client's subscriptions, returning it to
        unfiltered broadcast delivery.
        """
        wanted = {topics} if isinstance(topics, str) else set(topics)
        if wanted:
            self._topics[websocket] = wanted
        else:
            self._topics.pop(websocket, None)

    async def unsubscribe(
        self, websocket: WebSocket, topics: str | list[str]
    ) -> None:
        """Remove topics from a client's subscriptions.

        A client left with no subscriptions receives all broadcasts again.
        """
        removed = {topics} if isinstance(topics, str) else set(topics)
        if websocket not in self._topics:
            return
        self._topics[websocket] -= removed
        if not self._topics[websocket]:
            self._topics.pop(websocket, None)

    async def broadcast(self, topic: str, data: dict[str, Any]) -> None:
        """Broadcast data to interested clients.

        Clients with a declared subscription set receive only matching
        topics; clients without one receive everything. Dead connections
        are removed silently.
        """
        disconnected: list[WebSocket] = []
        for ws in self._connections:
            subscribed = self._topics.get(ws)
            if subscribed is not None and topic not in subscribed:
                continue
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
