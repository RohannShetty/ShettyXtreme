"""Order-update bridge: Fyers order socket -> ORDER_UPDATED events.

Fyers has no postback webhooks — order status updates arrive as JSON frames
on the order WebSocket (F3). This module owns the parsing + EventBus bridge
for both the socket path (``consume_order_message``, wired in
``terminal_init``) and the legacy HTTP POST path (kept for compatibility so
the previously-registered webhook URL does not 404).

Order-socket frames are tolerated defensively — the Fyers trade socket
message layout is not frozen, so both ``{"T": "ORD", "data": {...}}`` and
``{"type": "orders", "data": {...}}`` shapes are accepted, along with a
bare order dict. Anything that does not carry an order id is ignored.
"""
from __future__ import annotations

import logging
import secrets
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.terminal.api.models import PostbackResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/postback", tags=["postback"])

_event_bus: EventBus | None = None
_store: CredentialStore | None = None


def set_event_bus(bus: EventBus | None) -> None:
    global _event_bus
    _event_bus = bus


def set_credential_store(store: CredentialStore | None) -> None:
    """Bind the credential store used to authenticate legacy postbacks.

    Wired in the app lifespan next to ``set_event_bus``; the store reference
    is live, so post-login token updates are seen without re-wiring.
    """
    global _store
    _store = store


def _order_id(value: Any) -> str:
    return str(value or "").strip()


def _extract_order_updates(message: Any) -> list[dict[str, Any]]:
    """Normalize an order-socket frame (or bare dict) into order-update dicts.

    Recognized shapes:
      - ``{"T": "ORD", "data": {...order fields...}}``
      - ``{"T": "ORD", "orders": [{...}, ...]}``
      - ``{"type": "orders", "data": {...order fields...}}``
      - a bare ``{...order fields...}`` dict

    Each returned dict carries at least ``order_id``; status/quantity/price
    fields are forwarded as-is when present.
    """
    if not isinstance(message, dict):
        return []

    # A bare order dict (has an id, no envelope keys).
    if _order_id(message.get("id") or message.get("order_id")):
        return [message]

    updates: list[dict[str, Any]] = []
    for key in ("orders", "data", "order"):
        value = message.get(key)
        if value is None:
            continue
        if isinstance(value, dict):
            if _order_id(value.get("id") or value.get("order_id")):
                updates.append(value)
        elif isinstance(value, list):
            for row in value:
                if isinstance(row, dict) and _order_id(row.get("id") or row.get("order_id")):
                    updates.append(row)
    return updates


def _normalize_update(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Fyers order fields onto the ORDER_UPDATED payload contract."""
    order_id = _order_id(raw.get("id") or raw.get("order_id"))
    return {
        "order_id": order_id,
        "status": raw.get("status", raw.get("orderStatus", "")),
        "filled_quantity": raw.get("filledQty", raw.get("filled_quantity", 0)),
        "average_price": raw.get("tradedPrice", raw.get("average_price", 0.0)),
    }


async def consume_order_message(message: Any) -> None:
    """Order-socket handler: publish one ORDER_UPDATED event per order update.

    Registered as the ``FyersOrderSocket.on_message`` callback by
    ``terminal_init``. Non-order frames (subscription confirmations, pings)
    are ignored.
    """
    try:
        updates = _extract_order_updates(message)
        if not updates or _event_bus is None:
            return
        for raw in updates:
            await _event_bus.publish(Event(
                topic=Topic.ORDER_UPDATED,
                data=_normalize_update(raw),
                source="fyers_order_socket",
            ))
    except Exception:
        logger.exception("Fyers order socket message handling failed")


def _require_auth(authorization: str | None = Header(default=None)) -> None:
    """Require the terminal's own Fyers access token (bearer) for the legacy POST.

    The legacy ``/api/postback/dhan`` endpoint mints ORDER_UPDATED events that
    the ledger recorder treats as real fills (F-TERM-007). Without a gate, any
    process that can reach this port could inject phantom fills into the paper
    ledger, P&L, and analytics. The caller must prove it holds the terminal's
    own stored access token — the same credential that gates trading.
    """
    if _store is None or not _store.access_token:
        raise HTTPException(status_code=401, detail="Postback auth not configured")
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.split(" ", 1)[1].strip()
    if not token or not secrets.compare_digest(token, _store.access_token):
        raise HTTPException(status_code=401, detail="Invalid bearer token")


@router.post("/dhan", response_model=PostbackResponse, dependencies=[Depends(_require_auth)])
async def handle_legacy_postback(request: Request) -> PostbackResponse:
    """Legacy webhook endpoint — accepts Dhan-era payloads, emits ORDER_UPDATED.

    Retained so a previously-registered Dhan postback URL continues to work
    during the migration window; Fyers itself never calls this.
    """
    try:
        payload: dict[str, Any] = await request.json()
    except Exception:
        logger.warning("Postback: invalid JSON body")
        return PostbackResponse(status="error")

    try:
        parsed: dict[str, Any] = {
            "order_id": payload.get("order_id"),
            "status": payload.get("status"),
            "filled_quantity": payload.get("filled_quantity"),
            "average_price": payload.get("average_price"),
        }
        if _event_bus is not None:
            await _event_bus.publish(
                Event(topic=Topic.ORDER_UPDATED, data=parsed, source="postback")
            )
    except Exception:
        logger.exception("Postback: failed to process payload")
        return PostbackResponse(status="error")

    return PostbackResponse(status="ok")
