"""Real-time WS projections (P4): proposal + order topics.

The ExecutionEngine publishes ``PROPOSAL_CHANGED`` on every proposal
lifecycle transition; the paper engine (and broker adapters) publish
``ORDER_PLACED/FILLED/REJECTED/CANCELLED``. These projections serialize the
payloads into the same response shapes the REST endpoints return and push
them on the ``proposal`` and ``order`` WS topics.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.terminal.api import ws_bridge

logger = logging.getLogger(__name__)


# ── Proposal Projection (P4: real-time proposal WS topic) ──────────────────

class ProposalProjection:
    """Subscribes to PROPOSAL_CHANGED, pushes proposal updates to WS clients.

    The ExecutionEngine publishes ``{action, approval}`` on every lifecycle
    transition (created / approved / rejected / expired); this projection
    serializes the approval into the same ProposalResponse shape the REST
    queue returns and broadcasts it on the ``proposal`` WS topic as
    ``{action: str, proposal: ProposalResponse}``.
    """

    async def on_proposal_changed(self, event: Event) -> None:
        d = event.data
        if not isinstance(d, dict):
            return
        action = d.get("action", "")
        approval = d.get("approval")
        if not action or approval is None:
            return
        try:
            from shettyxtreme.terminal.api.execution_router import _proposal_response
            proposal = _proposal_response(approval).model_dump(mode="json")
        except Exception:
            logger.exception("proposal WS serialization failed")
            return
        await ws_bridge.broadcast("proposal", {
            "action": action,
            "proposal": proposal,
        })

    def subscribe(self, bus: EventBus) -> None:
        bus.subscribe(Topic.PROPOSAL_CHANGED, self.on_proposal_changed)


# ── Order Projection (P4: real-time order WS topic) ────────────────────────

#: dataclass fields of the Order record — used to rebuild an Order from the
#: enriched ORDER_* bus payloads without importing the models at module load.
_ORDER_FIELDS = {
    "order_id", "symbol", "exchange", "side", "order_type", "quantity",
    "price", "status", "filled_quantity", "average_price", "trigger_price",
    "tag", "created_at", "strike", "expiry", "option_type", "lot_size",
    "stop_loss", "target", "rationale", "confidence", "signal_id",
}


class OrderWSProjection:
    """Subscribes to ORDER_* events, pushes order updates to WS clients.

    Broadcasts ``{action: "placed"|"filled"|"rejected"|"cancelled",
    order: OrderResponse}`` on the ``order`` WS topic. The paper engine
    (and broker adapters that emit the same bus events) publish the full
    order record on the wire so the projection can serialize a complete
    OrderResponse without a broker round-trip.
    """

    _ACTIONS = {
        Topic.ORDER_PLACED: "placed",
        Topic.ORDER_FILLED: "filled",
        Topic.ORDER_REJECTED: "rejected",
        Topic.ORDER_CANCELLED: "cancelled",
    }

    @staticmethod
    def _to_order(data: dict[str, Any]) -> Any | None:
        """Rebuild an Order record from an ORDER_* bus payload."""
        from shettyxtreme.core.data_models.orders import Order
        kwargs: dict[str, Any] = {}
        for key in _ORDER_FIELDS:
            if key in data and data[key] is not None:
                kwargs[key] = data[key]
        if "created_at" in kwargs and isinstance(kwargs["created_at"], str):
            try:
                kwargs["created_at"] = datetime.fromisoformat(kwargs["created_at"])
            except ValueError:
                kwargs.pop("created_at", None)
        try:
            return Order(**kwargs)
        except (TypeError, ValueError):
            logger.exception("order WS payload did not reconstruct an Order")
            return None

    async def on_order_event(self, event: Event) -> None:
        d = event.data
        if not isinstance(d, dict):
            return
        action = self._ACTIONS.get(event.topic)
        if action is None:
            return
        order = self._to_order(d)
        if order is None:
            return
        try:
            from shettyxtreme.terminal.api.execution_router import _order_response
            payload = _order_response(order).model_dump(mode="json")
        except Exception:
            logger.exception("order WS serialization failed")
            return
        await ws_bridge.broadcast("order", {
            "action": action,
            "order": payload,
        })

    def subscribe(self, bus: EventBus) -> None:
        for topic in self._ACTIONS:
            bus.subscribe(topic, self.on_order_event)
