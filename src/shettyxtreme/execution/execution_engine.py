"""Semi-automatic execution engine with operator approval flow.

WAVE 5 (Execution + Position Management).

The ExecutionEngine implements a semi-auto approval flow:
  submit_signal -> PENDING approval (operator must approve)
  approve       -> pre-execution risk check -> validate -> place order
  reject        -> no order placed
  expire_stale  -> timeout stale PENDING approvals

Position management (always allowed, never blocked by loss limit) lives in
position_manager.py.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any
from uuid import uuid4

from shettyxtreme.core.data_models import OrderRequest, OrderSide, OrderType, ProductType
from shettyxtreme.core.interfaces.order_executor import OrderExecutor
from shettyxtreme.integration.order_validator import OrderValidator
from shettyxtreme.intelligence.risk.risk_engine import (
    Portfolio,
    ProposalRiskContext,
    RiskDecision,
    RiskEngine,
)
from shettyxtreme.intelligence.signals.signal_engine import (
    Signal,
    SignalDirection,
    Vote,
)

logger = logging.getLogger(__name__)


class ApprovalStatus(str, Enum):
    """Lifecycle status of a pending approval."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


@dataclass
class PendingApproval:
    """An order awaiting operator approval."""
    id: str
    signal: Signal
    strategy_hint: dict[str, Any]
    timestamp: datetime
    status: str
    expires_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    order: OrderRequest | None = None
    signal_id: str = ""
    failure_reason: str | None = None


# ---------------------------------------------------------------------------
# Persistence serialization (F-KNOW-002: full payload round-trips the DB)
# ---------------------------------------------------------------------------
def _json_default(obj: Any) -> Any:
    """JSON fallback encoder: enum members and datetimes as plain values."""
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"not JSON serializable: {type(obj).__name__}")


def _parse_dt(value: Any, fallback: datetime) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return fallback


def _signal_to_dict(signal: Signal) -> dict[str, Any]:
    """JSON-safe serialization of a Signal."""
    return {
        "direction": signal.direction.value,
        "conviction": signal.conviction,
        "voters": [
            {
                "direction": voter.direction,
                "confidence": voter.confidence,
                "weight": voter.weight,
                "name": voter.name,
            }
            for voter in signal.voters
        ],
        "timestamp": signal.timestamp.isoformat(),
        "D": signal.D,
        "P": signal.P,
        "G": signal.G,
    }


def _signal_from_dict(data: dict[str, Any]) -> Signal:
    """Rebuild a Signal from _signal_to_dict output (best-effort defaults)."""
    try:
        direction = SignalDirection(data.get("direction", "neutral"))
    except ValueError:
        direction = SignalDirection.NEUTRAL
    return Signal(
        direction=direction,
        conviction=float(data.get("conviction", 0.0)),
        voters=[
            Vote(
                direction=float(voter.get("direction", 0.0)),
                confidence=float(voter.get("confidence", 0.0)),
                weight=float(voter.get("weight", 0.0)),
                name=str(voter.get("name", "")),
            )
            for voter in data.get("voters", [])
        ],
        timestamp=_parse_dt(data.get("timestamp"), datetime.now(UTC)),
        D=float(data.get("D", 0.0)),
        P=float(data.get("P", 1.0)),
        G=str(data.get("G", "contested")),
    )


#: strategy_hint fields that hold enum members and must be restored as such.
_ENUM_HINT_FIELDS: dict[str, type[Enum]] = {
    "order_type": OrderType,
    "product": ProductType,
}


def _coerce_hint(hint: dict[str, Any]) -> dict[str, Any]:
    """Restore persisted enum members (order_type/product) in a strategy hint."""
    restored = dict(hint)
    for key, enum_cls in _ENUM_HINT_FIELDS.items():
        value = restored.get(key)
        if isinstance(value, str):
            try:
                restored[key] = enum_cls(value)
            except ValueError:
                pass
    return restored


def _approval_payload(approval: PendingApproval) -> dict[str, Any]:
    """JSON-safe payload carrying the full proposal (signal + strategy_hint)."""
    return {
        "signal": _signal_to_dict(approval.signal),
        "strategy_hint": approval.strategy_hint,
        "timestamp": approval.timestamp.isoformat(),
        "expires_at": approval.expires_at.isoformat(),
        "signal_id": approval.signal_id,
        "failure_reason": approval.failure_reason,
    }


def _row_to_approval(row: tuple[Any, ...]) -> PendingApproval | None:
    """Rebuild a PendingApproval from a stored row; None when unparseable."""
    approval_id, status, created_at, payload = row
    if not payload:
        return None
    try:
        data = json.loads(payload)
    except (TypeError, ValueError):
        return None
    timestamp = _parse_dt(data.get("timestamp"), datetime.now(UTC))
    return PendingApproval(
        id=approval_id,
        signal=_signal_from_dict(data.get("signal") or {}),
        strategy_hint=_coerce_hint(data.get("strategy_hint") or {}),
        timestamp=timestamp,
        status=status,
        expires_at=_parse_dt(data.get("expires_at"), timestamp),
        signal_id=str(data.get("signal_id", "")),
        failure_reason=data.get("failure_reason"),
    )


class ExecutionEngine:
    """Semi-auto execution flow with operator approval gate."""

    def __init__(
        self,
        executor: OrderExecutor,
        risk_engine: RiskEngine,
        validator: OrderValidator | None = None,
        approval_timeout_seconds: int = 300,
        db_path: str | None = None,
        portfolio_provider: Callable[[], Portfolio] | None = None,
        event_bus: Any | None = None,
    ) -> None:
        self._executor = executor
        self._risk_engine = risk_engine
        self._validator = validator or OrderValidator()
        self._approval_timeout = approval_timeout_seconds
        self._db_path = db_path
        self._approvals: dict[str, PendingApproval] = {}
        self._portfolio_provider = portfolio_provider
        self._event_bus = event_bus
        if db_path is not None:
            self._init_db()
            self._load_approvals()

    # ------------------------------------------------------------------
    # DB (optional, F-KNOW-002: persistence is best-effort, never fatal)
    # ------------------------------------------------------------------
    def _init_db(self) -> None:
        assert self._db_path is not None
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        try:
            with sqlite3.connect(self._db_path, timeout=5.0) as conn:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS pending_approvals (
                        id TEXT PRIMARY KEY,
                        status TEXT,
                        created_at TEXT,
                        payload TEXT
                    )"""
                )
                self._ensure_payload_column(conn)
                conn.commit()
        except sqlite3.Error:
            logger.exception("failed to open proposals db at %s", self._db_path)

    def _ensure_payload_column(self, conn: sqlite3.Connection) -> None:
        """Migrate the pre-payload schema (id, status, created_at) in place."""
        columns = {row[1] for row in conn.execute("PRAGMA table_info(pending_approvals)")}
        if "payload" not in columns:
            conn.execute("ALTER TABLE pending_approvals ADD COLUMN payload TEXT")

    def _db_upsert(self, approval: PendingApproval) -> None:
        if self._db_path is None:
            return
        try:
            payload = json.dumps(_approval_payload(approval), default=_json_default)
            with sqlite3.connect(self._db_path, timeout=5.0) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO pending_approvals (id, status, created_at, payload) "
                    "VALUES (?, ?, ?, ?)",
                    (approval.id, approval.status, approval.timestamp.isoformat(), payload),
                )
                conn.commit()
        except Exception:
            logger.exception(
                "failed to persist proposal %s; continuing in-memory only",
                approval.id,
            )

    def _load_approvals(self) -> None:
        """Restore ALL proposals (PENDING/APPROVED/REJECTED/EXPIRED) from the DB.

        Phase 4: the proposal queue doubles as durable proposal history, so
        every lifecycle status is restored on restart — rejected/expired
        proposals must survive a restart to keep the audit trail intact.
        Restored PENDING proposals that are past their timeout are marked
        EXPIRED by ``expire_stale()`` on the next listing.
        """
        if self._db_path is None:
            return
        try:
            with sqlite3.connect(self._db_path, timeout=5.0) as conn:
                rows = conn.execute(
                    "SELECT id, status, created_at, payload FROM pending_approvals"
                ).fetchall()
        except sqlite3.Error:
            logger.exception("failed to load persisted proposals from %s", self._db_path)
            return
        for row in rows:
            approval = _row_to_approval(row)
            if approval is None:
                continue
            self._approvals[approval.id] = approval
        if self._approvals:
            logger.info(
                "restored %d persisted proposals from %s",
                len(self._approvals),
                self._db_path,
            )

    # ------------------------------------------------------------------
    # Submit / approve / reject
    # ------------------------------------------------------------------
    async def _get_portfolio(self) -> Portfolio:
        if self._portfolio_provider is not None:
            return self._portfolio_provider()
        return Portfolio(
            positions=[],
            daily_pnl=0.0,
            total_margin_used=0.0,
            available_margin=0.0,
        )

    def submit_signal(
        self,
        signal: Signal,
        strategy_hint: dict[str, Any],
        signal_id: str = "",
    ) -> str:
        """Create a PENDING approval and return its id."""
        now = datetime.now(UTC)
        approval_id = uuid4().hex
        expires_at = now + timedelta(seconds=self._approval_timeout)
        approval = PendingApproval(
            id=approval_id,
            signal=signal,
            strategy_hint=strategy_hint,
            timestamp=now,
            status=ApprovalStatus.PENDING.value,
            expires_at=expires_at,
            signal_id=signal_id,
        )
        self._approvals[approval_id] = approval
        self._db_upsert(approval)
        self._publish_proposal_event("created", approval)
        return approval_id

    async def approve(self, approval_id: str) -> OrderRequest:
        """Operator approves an approval: risk check -> validate -> place order."""
        approval = self._approvals.get(approval_id)
        if approval is None:
            raise KeyError(f"unknown approval_id: {approval_id}")
        if approval.status != ApprovalStatus.PENDING.value:
            raise RuntimeError(f"approval {approval_id} is not pending (status={approval.status})")

        order = self._build_order(approval.signal, approval.strategy_hint)
        # P3-4.3: link the order back to its originating signal so the fill
        # event and position projection can trace the trade back to the plan.
        order.signal_id = approval.signal_id

        # Build proposal risk context from strategy_hint + built order
        hint = approval.strategy_hint
        proposal = ProposalRiskContext(
            symbol=order.symbol,
            side=order.side.value,
            quantity=order.quantity,
            entry_price=order.price or hint.get("entry_premium"),
            stop_loss=hint.get("stop_loss"),
            target=hint.get("target"),
            product=order.product.value if hasattr(order.product, "value") else str(order.product),
            lot_size=order.lot_size or hint.get("lot_size"),
            underlying=hint.get("underlying"),
            estimated_margin=hint.get("estimated_margin"),
        )

        portfolio = await self._get_portfolio()
        decision: RiskDecision = self._risk_engine.check_entry(
            approval.signal, portfolio, proposal,
        )
        if not decision.allowed:
            approval.status = ApprovalStatus.REJECTED.value
            approval.failure_reason = decision.reason
            self._db_upsert(approval)
            self._publish_proposal_event("rejected", approval)
            # Publish RISK_ALERT (subscribers exist; publisher was missing)
            self._publish_risk_alert(approval, decision)
            raise RuntimeError(f"pre-execution risk check rejected: {decision.reason}")

        self._validator.validate(order)

        result = await self._executor.place_order(order)
        approval.order = order
        if result is not None:
            status = getattr(result, "status", None)
            status_name = getattr(status, "name", None) or str(status or "").upper()
            if status_name in ("REJECTED", "CANCELLED"):
                approval.status = ApprovalStatus.REJECTED.value
                approval.failure_reason = (
                    getattr(result, "message", "") or "order placement rejected"
                )
                self._db_upsert(approval)
                self._publish_proposal_event("rejected", approval)
                raise RuntimeError(approval.failure_reason)

        approval.status = ApprovalStatus.APPROVED.value
        self._db_upsert(approval)
        self._publish_proposal_event("approved", approval)
        return order

    def reject(self, approval_id: str, reason: str) -> None:
        """Reject an approval; no order is placed."""
        approval = self._approvals.get(approval_id)
        if approval is None:
            raise KeyError(f"unknown approval_id: {approval_id}")
        approval.status = ApprovalStatus.REJECTED.value
        approval.failure_reason = reason or "rejected by operator"
        self._db_upsert(approval)
        self._publish_proposal_event("rejected", approval)

    def _publish_risk_alert(
        self, approval: PendingApproval, decision: RiskDecision,
    ) -> None:
        """Publish RISK_ALERT on risk rejection. No-op when event bus is absent."""
        if self._event_bus is None:
            return
        try:
            from shettyxtreme.core.event_bus.event_bus import Event, Topic
            alert_data = {
                "symbol": approval.strategy_hint.get("symbol", ""),
                "filter_name": decision.filter_name,
                "reason": decision.reason,
                "proposal_id": approval.id,
            }
            # Best-effort publish; the bus may not be running in tests.
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._event_bus.publish(
                    Event(topic=Topic.RISK_ALERT, data=alert_data, source="risk_engine"),
                ))
            except RuntimeError:
                pass
        except Exception:
            logger.debug("failed to publish RISK_ALERT", exc_info=True)

    def _publish_proposal_event(
        self, action: str, approval: PendingApproval,
    ) -> None:
        """Publish PROPOSAL_CHANGED (action: created/approved/rejected/expired).

        Best-effort, mirroring ``_publish_risk_alert``: no-op when the event
        bus is absent or no running loop is available (unit tests). The
        ProposalProjection turns this into the ``proposal`` WS topic.
        """
        if self._event_bus is None:
            return
        try:
            from shettyxtreme.core.event_bus.event_bus import Event, Topic
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._event_bus.publish(
                    Event(
                        topic=Topic.PROPOSAL_CHANGED,
                        data={"action": action, "approval": approval},
                        source="execution_engine",
                    ),
                ))
            except RuntimeError:
                pass
        except Exception:
            logger.debug("failed to publish PROPOSAL_CHANGED", exc_info=True)

    def expire_stale(self, now: datetime | None = None) -> int:
        """Mark PENDING approvals past their timeout as EXPIRED.

        Returns the count of newly expired approvals.
        """
        cutoff = now or datetime.now(UTC)
        count = 0
        for approval in self._approvals.values():
            if approval.status != ApprovalStatus.PENDING.value:
                continue
            if approval.expires_at <= cutoff:
                approval.status = ApprovalStatus.EXPIRED.value
                self._db_upsert(approval)
                self._publish_proposal_event("expired", approval)
                count += 1
        return count

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def get_pending_approvals(self) -> list[PendingApproval]:
        return [a for a in self._approvals.values() if a.status == ApprovalStatus.PENDING.value]

    def get_all_approvals(self) -> list[PendingApproval]:
        """Return every approval, newest first (for proposal queue listing)."""
        return sorted(
            self._approvals.values(),
            key=lambda a: a.timestamp,
            reverse=True,
        )

    def get_approval(self, approval_id: str) -> PendingApproval | None:
        return self._approvals.get(approval_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_order(self, signal: Signal, strategy_hint: dict[str, Any]) -> OrderRequest:
        if signal.direction == SignalDirection.UP:
            side = OrderSide.BUY
        elif signal.direction == SignalDirection.DOWN:
            side = OrderSide.SELL
        else:
            raise ValueError(f"cannot build order for NEUTRAL signal: {signal.direction}")

        price = strategy_hint.get("price")
        order_type = strategy_hint.get("order_type")
        if order_type is None:
            order_type = OrderType.LIMIT if price is not None else OrderType.MARKET

        product = strategy_hint.get("product", ProductType.MIS)

        return OrderRequest(
            symbol=strategy_hint["symbol"],
            exchange=strategy_hint["exchange"],
            side=side,
            order_type=order_type,
            quantity=int(strategy_hint.get("quantity") or 0),
            price=price,
            trigger_price=strategy_hint.get("trigger_price"),
            product=product,
            validity=strategy_hint.get("validity", "DAY"),
            tag=strategy_hint.get("tag"),
            client_id=strategy_hint.get("client_id"),
            strike=strategy_hint.get("strike"),
            expiry=strategy_hint.get("expiry"),
            option_type=strategy_hint.get("option_type"),
            lot_size=strategy_hint.get("lot_size"),
            # Trade context (P3-4.3) — carried from hint for order history.
            stop_loss=strategy_hint.get("stop_loss"),
            target=strategy_hint.get("target"),
            rationale=strategy_hint.get("rationale"),
            confidence=strategy_hint.get("confidence"),
        )
