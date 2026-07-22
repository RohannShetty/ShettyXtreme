"""Tests for ExecutionEngine (semi-auto approval flow)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from shettyxtreme.core.interfaces.order_executor import (
    Order,
    OrderSide,
    OrderType,
    ProductType,
)
from shettyxtreme.execution.execution_engine import (
    ApprovalStatus,
    ExecutionEngine,
    PendingApproval,
)
from shettyxtreme.integration.order_validator import OrderValidator
from shettyxtreme.intelligence.risk.risk_engine import Portfolio, RiskDecision, RiskEngine
from shettyxtreme.intelligence.signals.signal_engine import (
    Signal,
    SignalDirection,
)


def _make_signal(direction: SignalDirection = SignalDirection.UP) -> Signal:
    return Signal(direction=direction, conviction=0.8, D=0.6, P=1.0, G=0.1, voters=[])


def _make_hint() -> dict:
    return {
        "symbol": "NIFTY",
        "exchange": "NSE",
        "quantity": 75,
        "price": 100.0,
        "order_type": OrderType.LIMIT,
        "product": ProductType.MIS,
        "tag": "wave5",
    }


def _make_executor() -> AsyncMock:
    executor = AsyncMock()
    executor.place_order = AsyncMock(return_value=None)
    return executor


def _make_portfolio() -> Portfolio:
    return Portfolio(
        positions=[],
        daily_pnl=0.0,
        total_margin_used=0.0,
        available_margin=1_000_000.0,
    )


def test_submit_signal_creates_pending() -> None:
    engine = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio,
    )
    approval_id = engine.submit_signal(_make_signal(), _make_hint())
    pending = engine.get_pending_approvals()
    assert len(pending) == 1
    assert isinstance(pending[0], PendingApproval)
    assert pending[0].id == approval_id
    assert pending[0].status == ApprovalStatus.PENDING.value
    assert engine.get_approval(approval_id) is not None


@pytest.mark.asyncio
async def test_approve_places_order() -> None:
    executor = _make_executor()
    engine = ExecutionEngine(
        executor=executor, risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio,
    )
    approval_id = engine.submit_signal(_make_signal(), _make_hint())
    order = await engine.approve(approval_id)
    assert isinstance(order, Order)
    assert order.side == OrderSide.BUY
    assert executor.place_order.await_count == 1
    placed = executor.place_order.call_args.args[0]
    assert isinstance(placed, Order)
    assert placed.symbol == "NIFTY"
    assert engine.get_approval(approval_id).status == ApprovalStatus.APPROVED.value


@pytest.mark.asyncio
async def test_approve_down_signal_is_sell() -> None:
    executor = _make_executor()
    engine = ExecutionEngine(
        executor=executor, risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio,
    )
    approval_id = engine.submit_signal(_make_signal(SignalDirection.DOWN), _make_hint())
    order = await engine.approve(approval_id)
    assert order.side == OrderSide.SELL


@pytest.mark.asyncio
async def test_reject_no_order_placed() -> None:
    executor = _make_executor()
    engine = ExecutionEngine(
        executor=executor, risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio,
    )
    approval_id = engine.submit_signal(_make_signal(), _make_hint())
    engine.reject(approval_id, "manual reject")
    assert executor.place_order.await_count == 0
    assert engine.get_approval(approval_id).status == ApprovalStatus.REJECTED.value


@pytest.mark.asyncio
async def test_pre_execution_risk_reject_blocks_order() -> None:
    executor = _make_executor()
    risk_engine = RiskEngine()
    risk_engine.check_entry = lambda signal, portfolio: RiskDecision.reject(  # type: ignore[assignment]
        "daily loss limit reached", filter_name="loss_limit"
    )
    engine = ExecutionEngine(
        executor=executor, risk_engine=risk_engine,
        portfolio_provider=_make_portfolio,
    )
    approval_id = engine.submit_signal(_make_signal(), _make_hint())
    with pytest.raises(RuntimeError):
        await engine.approve(approval_id)
    assert executor.place_order.await_count == 0
    assert engine.get_approval(approval_id).status == ApprovalStatus.REJECTED.value


@pytest.mark.asyncio
async def test_invalid_order_raises_before_place() -> None:
    executor = _make_executor()
    engine = ExecutionEngine(
        executor=executor, risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio,
    )
    hint = _make_hint()
    hint["exchange"] = "BADX"  # invalid exchange -> validator raises
    approval_id = engine.submit_signal(_make_signal(), hint)
    with pytest.raises(ValueError):
        await engine.approve(approval_id)
    assert executor.place_order.await_count == 0


def test_expire_stale_marks_expired() -> None:
    engine = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(), approval_timeout_seconds=300,
        portfolio_provider=_make_portfolio,
    )
    approval_id = engine.submit_signal(_make_signal(), _make_hint())
    # Force the approval to be past its timeout window
    approval = engine.get_approval(approval_id)
    assert approval is not None
    approval.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    count = engine.expire_stale()
    assert count == 1
    assert engine.get_approval(approval_id).status == ApprovalStatus.EXPIRED.value
    # Already expired, not double counted
    assert engine.expire_stale() == 0


def test_lifecycle_transitions() -> None:
    engine = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio,
    )
    approval_id = engine.submit_signal(_make_signal(), _make_hint())
    assert engine.get_approval(approval_id).status == ApprovalStatus.PENDING.value
