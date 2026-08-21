"""Tests for ExecutionEngine (semi-auto approval flow)."""
from __future__ import annotations

import asyncio
import sqlite3
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from shettyxtreme.core.data_models import (
    OrderRequest,
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
    return Signal(direction=direction, conviction=0.8, voters=[])


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
        equity=1_000_000.0,
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
    assert isinstance(order, OrderRequest)
    assert order.side == OrderSide.BUY
    assert executor.place_order.await_count == 1
    placed = executor.place_order.call_args.args[0]
    assert isinstance(placed, OrderRequest)
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
    risk_engine.check_entry = lambda signal, portfolio, proposal=None: RiskDecision.reject(  # type: ignore[assignment]
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


def test_proposal_persists_across_engine_restart(tmp_path) -> None:
    """F-KNOW-002: a proposal survives a restart via db_path persistence.

    Submit on one engine, construct a fresh engine on the same db path
    (simulated process restart), and the proposal must be listed again with
    its full signal + strategy_hint payload.
    """
    db_path = str(tmp_path / "proposals.db")
    signal = _make_signal(SignalDirection.UP)
    hint = _make_hint()
    engine = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio, db_path=db_path,
    )
    approval_id = engine.submit_signal(signal, hint)

    engine2 = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio, db_path=db_path,
    )
    restored = engine2.get_approval(approval_id)
    assert restored is not None
    assert restored.id == approval_id
    assert restored.status == ApprovalStatus.PENDING.value
    assert restored.signal.direction == SignalDirection.UP
    assert restored.signal.conviction == signal.conviction
    assert restored.strategy_hint == hint


def test_db_failure_does_not_abort_submit(tmp_path, monkeypatch) -> None:
    """A broken DB must not abort proposal submission (in-memory fallback)."""
    db_path = str(tmp_path / "proposals.db")
    engine = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio, db_path=db_path,
    )

    def broken_connect(*args, **kwargs):
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(sqlite3, "connect", broken_connect)
    approval_id = engine.submit_signal(_make_signal(), _make_hint())
    approval = engine.get_approval(approval_id)
    assert approval is not None
    assert approval.status == ApprovalStatus.PENDING.value


    @pytest.mark.asyncio
    async def test_paper_mode_approve_succeeds_with_funded_portfolio() -> None:
        """PAPER-mode approve() succeeds when portfolio has real available margin.

        This is the end-to-end scenario that was failing before the P0-1.3 fix:
        paper engine provides available_margin=1_000_000 → MarginFilter allows.
        """
        from shettyxtreme.execution.paper_trading import PaperTradingEngine

        paper_engine = PaperTradingEngine(initial_capital=1_000_000.0)

        def paper_portfolio():
            return paper_engine.get_portfolio()

        executor = _make_executor()
        engine = ExecutionEngine(
            executor=executor, risk_engine=RiskEngine(),
            portfolio_provider=paper_portfolio,
        )
        approval_id = engine.submit_signal(_make_signal(), _make_hint())
        order = await engine.approve(approval_id)
        assert isinstance(order, OrderRequest)
        assert executor.place_order.await_count == 1


# ── P4: Durable proposal history (all lifecycle statuses survive restarts) ─

def test_rejected_proposal_survives_restart(tmp_path) -> None:
    """A REJECTED proposal is restored from the DB — history, not just queue."""
    db_path = str(tmp_path / "proposals.db")
    engine = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio, db_path=db_path,
    )
    approval_id = engine.submit_signal(_make_signal(), _make_hint())
    engine.reject(approval_id, "not today")

    engine2 = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio, db_path=db_path,
    )
    restored = engine2.get_approval(approval_id)
    assert restored is not None
    assert restored.status == ApprovalStatus.REJECTED.value
    assert restored.failure_reason == "not today"
    all_approvals = engine2.get_all_approvals()
    assert any(a.id == approval_id for a in all_approvals)


def test_expired_proposal_survives_restart(tmp_path) -> None:
    """An EXPIRED proposal is restored from the DB."""
    db_path = str(tmp_path / "proposals.db")
    engine = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio, db_path=db_path,
        approval_timeout_seconds=1,
    )
    approval_id = engine.submit_signal(_make_signal(), _make_hint())
    approval = engine.get_approval(approval_id)
    assert approval is not None
    approval.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    assert engine.expire_stale() == 1

    engine2 = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio, db_path=db_path,
    )
    restored = engine2.get_approval(approval_id)
    assert restored is not None
    assert restored.status == ApprovalStatus.EXPIRED.value


@pytest.mark.asyncio
async def test_approved_proposal_survives_restart(tmp_path) -> None:
    """An APPROVED proposal is restored from the DB."""
    db_path = str(tmp_path / "proposals.db")
    engine = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio, db_path=db_path,
    )
    approval_id = engine.submit_signal(_make_signal(), _make_hint())
    await engine.approve(approval_id)

    engine2 = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio, db_path=db_path,
    )
    restored = engine2.get_approval(approval_id)
    assert restored is not None
    assert restored.status == ApprovalStatus.APPROVED.value


def test_mixed_statuses_all_restored(tmp_path) -> None:
    """Pending + rejected + expired coexist in the restored history."""
    db_path = str(tmp_path / "proposals.db")
    engine = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio, db_path=db_path,
    )
    pending_id = engine.submit_signal(_make_signal(), _make_hint())
    rejected_id = engine.submit_signal(_make_signal(), _make_hint())
    engine.reject(rejected_id, "nope")
    expired_id = engine.submit_signal(_make_signal(), _make_hint())
    expired = engine.get_approval(expired_id)
    assert expired is not None
    expired.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
    engine.expire_stale()

    engine2 = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio, db_path=db_path,
    )
    statuses = {a.id: a.status for a in engine2.get_all_approvals()}
    assert statuses[pending_id] == ApprovalStatus.PENDING.value
    assert statuses[rejected_id] == ApprovalStatus.REJECTED.value
    assert statuses[expired_id] == ApprovalStatus.EXPIRED.value


# ── P4: PROPOSAL_CHANGED events on the EventBus ─────────────────────────────

@pytest.mark.asyncio
async def test_submit_publishes_proposal_created_event() -> None:
    """submit_signal() publishes PROPOSAL_CHANGED(action=created) via the bus."""
    from shettyxtreme.core.event_bus.event_bus import EventBus, Topic

    bus = EventBus()
    captured: list[dict] = []

    async def _capture(event) -> None:
        captured.append(event.data)

    bus.subscribe(Topic.PROPOSAL_CHANGED, _capture)
    bus_task = asyncio.create_task(bus.start())
    try:
        engine = ExecutionEngine(
            executor=_make_executor(), risk_engine=RiskEngine(),
            portfolio_provider=_make_portfolio, event_bus=bus,
        )
        approval_id = engine.submit_signal(_make_signal(), _make_hint())
        await asyncio.sleep(0.05)
        assert len(captured) == 1
        assert captured[0]["action"] == "created"
        assert captured[0]["approval"].id == approval_id
    finally:
        bus_task.cancel()
        try:
            await bus_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_approve_publishes_approved_event() -> None:
    """approve() publishes PROPOSAL_CHANGED(action=approved) via the bus."""
    from shettyxtreme.core.event_bus.event_bus import EventBus, Topic

    bus = EventBus()
    captured: list[dict] = []

    async def _capture(event) -> None:
        captured.append(event.data)

    bus.subscribe(Topic.PROPOSAL_CHANGED, _capture)
    bus_task = asyncio.create_task(bus.start())
    try:
        engine = ExecutionEngine(
            executor=_make_executor(), risk_engine=RiskEngine(),
            portfolio_provider=_make_portfolio, event_bus=bus,
        )
        approval_id = engine.submit_signal(_make_signal(), _make_hint())
        await engine.approve(approval_id)
        await asyncio.sleep(0.05)
        actions = [c["action"] for c in captured]
        assert actions == ["created", "approved"]
    finally:
        bus_task.cancel()
        try:
            await bus_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_reject_publishes_rejected_event() -> None:
    """reject() publishes PROPOSAL_CHANGED(action=rejected) via the bus."""
    from shettyxtreme.core.event_bus.event_bus import EventBus, Topic

    bus = EventBus()
    captured: list[dict] = []

    async def _capture(event) -> None:
        captured.append(event.data)

    bus.subscribe(Topic.PROPOSAL_CHANGED, _capture)
    bus_task = asyncio.create_task(bus.start())
    try:
        engine = ExecutionEngine(
            executor=_make_executor(), risk_engine=RiskEngine(),
            portfolio_provider=_make_portfolio, event_bus=bus,
        )
        approval_id = engine.submit_signal(_make_signal(), _make_hint())
        engine.reject(approval_id, "manual")
        await asyncio.sleep(0.05)
        actions = [c["action"] for c in captured]
        assert actions == ["created", "rejected"]
    finally:
        bus_task.cancel()
        try:
            await bus_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_expire_publishes_expired_event() -> None:
    """expire_stale() publishes PROPOSAL_CHANGED(action=expired) via the bus."""
    from shettyxtreme.core.event_bus.event_bus import EventBus, Topic

    bus = EventBus()
    captured: list[dict] = []

    async def _capture(event) -> None:
        captured.append(event.data)

    bus.subscribe(Topic.PROPOSAL_CHANGED, _capture)
    bus_task = asyncio.create_task(bus.start())
    try:
        engine = ExecutionEngine(
            executor=_make_executor(), risk_engine=RiskEngine(),
            portfolio_provider=_make_portfolio, event_bus=bus,
        )
        approval_id = engine.submit_signal(_make_signal(), _make_hint())
        approval = engine.get_approval(approval_id)
        assert approval is not None
        approval.expires_at = datetime.now(timezone.utc) - timedelta(seconds=10)
        engine.expire_stale()
        await asyncio.sleep(0.05)
        actions = [c["action"] for c in captured]
        assert actions == ["created", "expired"]
    finally:
        bus_task.cancel()
        try:
            await bus_task
        except asyncio.CancelledError:
            pass


@pytest.mark.asyncio
async def test_no_bus_no_proposal_events() -> None:
    """Without an event bus the engine stays silent (no crash, no publish)."""
    engine = ExecutionEngine(
        executor=_make_executor(), risk_engine=RiskEngine(),
        portfolio_provider=_make_portfolio,
    )
    approval_id = engine.submit_signal(_make_signal(), _make_hint())
    assert engine.get_approval(approval_id) is not None  # flow intact
