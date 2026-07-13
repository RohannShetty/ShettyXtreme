"""Postback router for Dhan order status updates.

Register this URL in Dhan Developer Portal -> Your API App -> Postback URL:
http://localhost:8000/api/postback/dhan
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.terminal.api.models import PostbackResponse

router = APIRouter(prefix="/api/postback", tags=["postback"])

_event_bus: EventBus | None = None


def set_event_bus(bus: EventBus | None) -> None:
    global _event_bus
    _event_bus = bus


@router.post("/dhan", response_model=PostbackResponse)
async def handle_dhan_postback(request: Request) -> PostbackResponse:
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        payload = {}

    try:
        order_id = payload.get("order_id")
        status = payload.get("status")
        filled_quantity = payload.get("filled_quantity")
        average_price = payload.get("average_price")

        parsed: dict[str, Any] = {
            "order_id": order_id,
            "status": status,
            "filled_quantity": filled_quantity,
            "average_price": average_price,
        }

        if _event_bus is not None:
            await _event_bus.publish(
                Event(topic=Topic.ORDER_UPDATED, data=parsed, source="postback")
            )
    except Exception:
        pass

    return PostbackResponse(status="ok")
