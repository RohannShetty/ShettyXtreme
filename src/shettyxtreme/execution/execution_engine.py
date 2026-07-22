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

import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable
from uuid import uuid4

from shettyxtreme.core.interfaces.order_executor import (
    Order,
    OrderExecutor,
    OrderSide,
    OrderType,
    ProductType,
)
from shettyxtreme.integration.order_validator import OrderValidator
from shettyxtreme.intelligence.risk.risk_engine import Portfolio, RiskDecision, RiskEngine
from shettyxtreme.intelligence.signals.signal_engine import Signal, SignalDirection


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
    expires_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    order: Order | None = None


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
    ) -> None:
        self._executor = executor
        self._risk_engine = risk_engine
        self._validator = validator or OrderValidator()
        self._approval_timeout = approval_timeout_seconds
        self._db_path = db_path
        self._approvals: dict[str, PendingApproval] = {}
        self._portfolio_provider = portfolio_provider
        if db_path is not None:
            self._init_db()

    # ------------------------------------------------------------------
    # DB (optional)
    # ------------------------------------------------------------------
    def _init_db(self) -> None:
        assert self._db_path is not None
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS pending_approvals (
                    id TEXT PRIMARY KEY,
                    status TEXT,
                    created_at TEXT
                )"""
            )
            conn.commit()

    def _db_upsert(self, approval: PendingApproval) -> None:
        if self._db_path is None:
            return
        with sqlite3.connect(self._db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO pending_approvals (id, status, created_at) VALUES (?, ?, ?)",
                (approval.id, approval.status, approval.timestamp.isoformat()),
            )
            conn.commit()

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

    def submit_signal(self, signal: Signal, strategy_hint: dict[str, Any]) -> str:
        """Create a PENDING approval and return its id."""
        now = datetime.now(timezone.utc)
        approval_id = uuid4().hex
        expires_at = now + timedelta(seconds=self._approval_timeout)
        approval = PendingApproval(
            id=approval_id,
            signal=signal,
            strategy_hint=strategy_hint,
            timestamp=now,
            status=ApprovalStatus.PENDING.value,
            expires_at=expires_at,
        )
        self._approvals[approval_id] = approval
        self._db_upsert(approval)
        return approval_id

    async def approve(self, approval_id: str) -> Order:
        """Operator approves an approval: risk check -> validate -> place order."""
        approval = self._approvals.get(approval_id)
        if approval is None:
            raise KeyError(f"unknown approval_id: {approval_id}")
        if approval.status != ApprovalStatus.PENDING.value:
            raise RuntimeError(f"approval {approval_id} is not pending (status={approval.status})")

        order = self._build_order(approval.signal, approval.strategy_hint)

        portfolio = await self._get_portfolio()
        decision: RiskDecision = self._risk_engine.check_entry(approval.signal, portfolio)
        if not decision.allowed:
            approval.status = ApprovalStatus.REJECTED.value
            self._db_upsert(approval)
            raise RuntimeError(f"pre-execution risk check rejected: {decision.reason}")

        self._validator.validate(order)

        await self._executor.place_order(order)

        approval.status = ApprovalStatus.APPROVED.value
        approval.order = order
        self._db_upsert(approval)
        return order

    def reject(self, approval_id: str, reason: str) -> None:
        """Reject an approval; no order is placed."""
        approval = self._approvals.get(approval_id)
        if approval is None:
            raise KeyError(f"unknown approval_id: {approval_id}")
        approval.status = ApprovalStatus.REJECTED.value
        self._db_upsert(approval)

    def expire_stale(self, now: datetime | None = None) -> int:
        """Mark PENDING approvals past their timeout as EXPIRED.

        Returns the count of newly expired approvals.
        """
        cutoff = now or datetime.now(timezone.utc)
        count = 0
        for approval in self._approvals.values():
            if approval.status != ApprovalStatus.PENDING.value:
                continue
            if approval.expires_at <= cutoff:
                approval.status = ApprovalStatus.EXPIRED.value
                self._db_upsert(approval)
                count += 1
        return count

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def get_pending_approvals(self) -> list[PendingApproval]:
        return [a for a in self._approvals.values() if a.status == ApprovalStatus.PENDING.value]

    def get_approval(self, approval_id: str) -> PendingApproval | None:
        return self._approvals.get(approval_id)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _build_order(self, signal: Signal, strategy_hint: dict[str, Any]) -> Order:
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

        return Order(
            symbol=strategy_hint["symbol"],
            exchange=strategy_hint["exchange"],
            side=side,
            order_type=order_type,
            quantity=int(strategy_hint["quantity"]),
            price=price,
            trigger_price=strategy_hint.get("trigger_price"),
            product=product,
            validity=strategy_hint.get("validity", "DAY"),
            tag=strategy_hint.get("tag"),
            client_id=strategy_hint.get("client_id"),
        )
