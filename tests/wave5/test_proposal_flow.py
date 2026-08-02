"""P4b tests: OBSERVER proposal→approve flow, PAPER mode, mode routing, kill switch.

Covers: SIGNAL_V2 → proposal, dedup, approve→PAPER (real PaperTradingEngine),
approve→LIVE (mocked adapter), reject, risk-fail→400, kill-switch block,
mode gate (OBSERVER blocks, LIVE needs confirm), expiry.
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import AsyncIterator
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pathlib import Path

from shettyxtreme.core.event_bus.event_bus import Event, EventBus, Topic
from shettyxtreme.core.interfaces.order_executor import OrderResult, OrderStatus
from shettyxtreme.execution.execution_engine import ExecutionEngine
from shettyxtreme.execution.mode_router import ModeRoutingExecutor
from shettyxtreme.execution.paper_trading import PaperTradingEngine
from shettyxtreme.execution.signal_bridge import ExecutionSignalBridge, default_hint_builder
from shettyxtreme.intelligence.risk.risk_engine import Portfolio, RiskDecision, RiskEngine
from shettyxtreme.terminal.api import execution_router
from shettyxtreme.terminal.api.app import app

# Import-time default of a fresh process (captured before the per-test fixture
# resets the module state, which would hide it).
_KILL_SWITCH_DEFAULT = execution_router._kill_switch_path

_SIGNAL_UP = {
    "direction": "UP",
    "conviction": 0.8,
    "D": 0.9,
    "P": 0.8,
    "G": "high_conviction",
    "voters": [],
    "timestamp": datetime.now(UTC),
}
_SIGNAL_DOWN = {
    "direction": "DOWN",
    "conviction": 0.7,
    "D": 0.8,
    "P": 0.7,
    "G": "high_conviction",
    "voters": [],
    "timestamp": datetime.now(UTC),
}
_SIGNAL_NEUTRAL = {
    "direction": "NEUTRAL",
    "conviction": 0.1,
    "D": 0.2,
    "P": 0.9,
    "G": "contested",
    "voters": [],
    "timestamp": datetime.now(UTC),
}


def _make_engine(
    mode: str = "PAPER",
    kill_path: str = "",
    live_adapter: object | None = None,
    risk_engine: RiskEngine | None = None,
) -> tuple[ExecutionEngine, PaperTradingEngine]:
    paper = PaperTradingEngine()
    executor = ModeRoutingExecutor(
        paper_engine=paper,
        mode_provider=lambda: mode,
        kill_switch_provider=lambda: bool(kill_path),
        live_provider=lambda: live_adapter,
    )

    def _portfolio() -> Portfolio:
        return Portfolio(positions=[], daily_pnl=0.0, total_margin_used=0.0, available_margin=1_000_000.0)

    engine = ExecutionEngine(
        executor=executor,
        risk_engine=risk_engine or RiskEngine(),
        portfolio_provider=_portfolio,
    )
    return engine, paper


def _signal_event(data: dict) -> Event:
    return Event(topic=Topic.SIGNAL_V2, data=data, source="test")


@pytest_asyncio.fixture(autouse=True)
async def setup_state(monkeypatch, tmp_path) -> AsyncIterator[None]:
    """Fresh module mode/kill-switch state per test; clear app.state engine."""
    mode_file = tmp_path / "mode.txt"
    monkeypatch.setattr(execution_router, "_MODE_FILE", mode_file)
    execution_router._current_mode = execution_router._load_mode()
    execution_router._kill_switch_path = ""
    app.state.execution_engine = None
    app.state.paper_engine = None
    yield
    app.state.execution_engine = None
    app.state.paper_engine = None


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _proposals(client: AsyncClient, status: str | None = None) -> list[dict]:
    resp = await client.get(
        "/api/execution/proposals"
        + (f"?status={status}" if status else "")
    )
    assert resp.status_code == 200
    return resp.json()


# ── Signal → proposal ──────────────────────────────────────────────────────

def test_signal_v2_creates_proposal() -> None:
    engine, _ = _make_engine()
    bridge = ExecutionSignalBridge(engine=engine, event_bus=EventBus())
    asyncio.run(bridge._on_signal_v2(_signal_event(_SIGNAL_UP)))

    approvals = engine.get_all_approvals()
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval.status == "PENDING"
    assert approval.signal.direction.name == "UP"
    assert approval.signal_id
    hint = approval.strategy_hint
    assert hint["symbol"] == "NIFTY"
    assert hint["quantity"] == 75
    assert hint["hint_kind"] == "default"


def test_default_hint_builder_marks_hint_kind_default() -> None:
    hint = default_hint_builder({})
    assert hint["hint_kind"] == "default"
    assert hint["symbol"] == "NIFTY"


def test_signal_v2_down_side_is_sell() -> None:
    engine, _ = _make_engine()
    bridge = ExecutionSignalBridge(engine=engine, event_bus=EventBus())
    asyncio.run(bridge._on_signal_v2(_signal_event(_SIGNAL_DOWN)))
    approvals = engine.get_all_approvals()
    assert len(approvals) == 1
    assert approvals[0].signal.direction.name == "DOWN"


def test_neutral_signal_ignored() -> None:
    engine, _ = _make_engine()
    bridge = ExecutionSignalBridge(engine=engine, event_bus=EventBus())
    asyncio.run(bridge._on_signal_v2(_signal_event(_SIGNAL_NEUTRAL)))
    assert engine.get_all_approvals() == []


def test_duplicate_signal_deduped_while_pending() -> None:
    engine, _ = _make_engine()
    bridge = ExecutionSignalBridge(engine=engine, event_bus=EventBus())
    for _ in range(3):
        asyncio.run(bridge._on_signal_v2(_signal_event(_SIGNAL_UP)))
    assert len(engine.get_all_approvals()) == 1
    # After reject, a new signal may propose again
    engine.reject(engine.get_all_approvals()[0].id, "no")
    asyncio.run(bridge._on_signal_v2(_signal_event(_SIGNAL_UP)))
    assert len(engine.get_all_approvals()) == 2


# ── Approve → PAPER (real engine) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_paper_routes_to_paper_engine(client: AsyncClient) -> None:
    execution_router._current_mode = "PAPER"
    engine, paper = _make_engine(mode="PAPER")
    app.state.execution_engine = engine
    app.state.paper_engine = paper

    assert await _proposals(client) == []
    bridge = ExecutionSignalBridge(engine=engine, event_bus=EventBus())
    await bridge._on_signal_v2(_signal_event(_SIGNAL_UP))
    proposal = (await _proposals(client))[0]
    assert proposal["side"] == "BUY"
    assert proposal["symbol"] == "NIFTY"

    resp = await client.post(f"/api/execution/proposals/{proposal['id']}/approve")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "APPROVED"
    assert data["side"] == "BUY"
    assert data["hint_kind"] == "default"

    orders = paper.get_order_book()
    assert len(orders) == 1
    assert orders[0].symbol == "NIFTY"
    assert orders[0].side == "BUY"
    assert orders[0].status == "FILLED"


# ── Approve → LIVE (mocked adapter) ────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_live_routes_to_adapter_with_confirm(client: AsyncClient) -> None:
    execution_router._current_mode = "LIVE"
    fake = AsyncMock()
    fake.place_order = AsyncMock(
        return_value=OrderResult(order_id="D123", status=OrderStatus.OPEN, message="ok")
    )
    engine, _ = _make_engine(mode="LIVE", live_adapter=fake)
    app.state.execution_engine = engine
    bridge = ExecutionSignalBridge(engine=engine, event_bus=EventBus())
    await bridge._on_signal_v2(_signal_event(_SIGNAL_UP))
    proposal = (await _proposals(client))[0]

    resp = await client.post(f"/api/execution/proposals/{proposal['id']}/approve?confirm=true")
    assert resp.status_code == 200
    assert resp.json()["status"] == "APPROVED"
    assert fake.place_order.await_count == 1
    placed = fake.place_order.call_args.args[0]
    assert placed.symbol == "NIFTY"
    assert placed.side.value == "BUY"
    assert placed.quantity == 75


@pytest.mark.asyncio
async def test_approve_live_requires_confirm(client: AsyncClient) -> None:
    execution_router._current_mode = "LIVE"
    fake = AsyncMock()
    engine, _ = _make_engine(mode="LIVE", live_adapter=fake)
    app.state.execution_engine = engine
    bridge = ExecutionSignalBridge(engine=engine, event_bus=EventBus())
    await bridge._on_signal_v2(_signal_event(_SIGNAL_UP))
    proposal = (await _proposals(client))[0]

    resp = await client.post(f"/api/execution/proposals/{proposal['id']}/approve")
    assert resp.status_code == 400
    assert "confirmation" in resp.json()["detail"]
    assert fake.place_order.await_count == 0
    assert (await _proposals(client))[0]["status"] == "PENDING"


# ── OBSERVER mode gate ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_observer_blocked(client: AsyncClient) -> None:
    execution_router._current_mode = "OBSERVER"
    engine, paper = _make_engine(mode="OBSERVER")
    app.state.execution_engine = engine
    bridge = ExecutionSignalBridge(engine=engine, event_bus=EventBus())
    await bridge._on_signal_v2(_signal_event(_SIGNAL_UP))
    proposal = (await _proposals(client))[0]

    resp = await client.post(f"/api/execution/proposals/{proposal['id']}/approve")
    assert resp.status_code == 400
    assert "OBSERVER" in resp.json()["detail"]
    assert paper.get_order_book() == []
    assert (await _proposals(client))[0]["status"] == "PENDING"


# ── Reject ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reject_marks_rejected_no_order(client: AsyncClient) -> None:
    execution_router._current_mode = "PAPER"
    engine, paper = _make_engine(mode="PAPER")
    app.state.execution_engine = engine
    bridge = ExecutionSignalBridge(engine=engine, event_bus=EventBus())
    await bridge._on_signal_v2(_signal_event(_SIGNAL_UP))
    proposal = (await _proposals(client))[0]

    resp = await client.post(
        f"/api/execution/proposals/{proposal['id']}/reject?reason=manual+reject"
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "REJECTED"
    assert data["reason"] == "manual reject"
    assert paper.get_order_book() == []
    assert await _proposals(client, status="PENDING") == []


# ── Risk check failure → 400 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_risk_fail_returns_400_no_order(client: AsyncClient) -> None:
    execution_router._current_mode = "PAPER"
    risk = RiskEngine()
    risk.check_entry = lambda signal, portfolio: RiskDecision.reject(  # type: ignore[assignment]
        "daily loss limit reached", filter_name="loss_limit"
    )
    engine, paper = _make_engine(mode="PAPER", risk_engine=risk)
    app.state.execution_engine = engine
    bridge = ExecutionSignalBridge(engine=engine, event_bus=EventBus())
    await bridge._on_signal_v2(_signal_event(_SIGNAL_UP))
    proposal = (await _proposals(client))[0]

    resp = await client.post(f"/api/execution/proposals/{proposal['id']}/approve")
    assert resp.status_code == 400
    assert "daily loss limit" in resp.json()["detail"]
    assert paper.get_order_book() == []
    assert (await _proposals(client))[0]["status"] == "REJECTED"


# ── Kill switch ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_kill_switch_blocks_approve(client: AsyncClient, tmp_path) -> None:
    execution_router._current_mode = "PAPER"
    kill_file = tmp_path / "kill"
    execution_router._kill_switch_path = str(kill_file)
    kill_file.touch()
    engine, paper = _make_engine(mode="PAPER", kill_path=str(kill_file))
    app.state.execution_engine = engine
    bridge = ExecutionSignalBridge(engine=engine, event_bus=EventBus())
    await bridge._on_signal_v2(_signal_event(_SIGNAL_UP))
    proposal = (await _proposals(client))[0]

    resp = await client.post(f"/api/execution/proposals/{proposal['id']}/approve")
    assert resp.status_code == 400
    assert "kill switch" in resp.json()["detail"]
    assert paper.get_order_book() == []
    assert (await _proposals(client))[0]["status"] == "PENDING"


@pytest.mark.asyncio
async def test_stale_kill_switch_file_armed_across_restart(
    client: AsyncClient, tmp_path, monkeypatch,
) -> None:
    """A file armed by a previous process blocks placement after a fresh start.

    The module default is set at import time (not lazily on activation), so a
    fresh process must honor a stale armed file without any explicit call.
    """
    # Fresh-process default points at the armed-file path, never "".
    assert _KILL_SWITCH_DEFAULT == str(Path.home() / ".shetty_kill_switch")
    kill_file = tmp_path / ".shetty_kill_switch"
    kill_file.touch()  # armed by a previous process
    monkeypatch.setattr(execution_router, "_kill_switch_path", str(kill_file))

    execution_router._current_mode = "PAPER"
    engine, paper = _make_engine(mode="PAPER", kill_path=str(kill_file))
    app.state.execution_engine = engine
    bridge = ExecutionSignalBridge(engine=engine, event_bus=EventBus())
    await bridge._on_signal_v2(_signal_event(_SIGNAL_UP))
    proposal = (await _proposals(client))[0]

    assert execution_router.is_kill_switch_armed() is True
    resp = await client.get("/api/execution/kill-switch")
    assert resp.status_code == 200
    assert resp.json()["active"] is True

    resp = await client.post(f"/api/execution/proposals/{proposal['id']}/approve")
    assert resp.status_code == 400
    assert "kill switch" in resp.json()["detail"]
    assert paper.get_order_book() == []


def test_mode_router_blocks_when_kill_switch_armed() -> None:
    paper = PaperTradingEngine()
    router = ModeRoutingExecutor(
        paper_engine=paper,
        mode_provider=lambda: "PAPER",
        kill_switch_provider=lambda: True,
    )
    from shettyxtreme.core.interfaces.order_executor import Order, OrderSide, OrderType

    result = asyncio.run(router.place_order(Order(
        symbol="NIFTY", exchange="NFO", side=OrderSide.BUY,
        order_type=OrderType.MARKET, quantity=75,
    )))
    assert result.status == OrderStatus.REJECTED
    assert "kill switch" in result.message
    assert paper.get_order_book() == []


# ── Expiry ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_proposal_expires_on_list(client: AsyncClient) -> None:
    execution_router._current_mode = "PAPER"
    engine, _ = _make_engine(mode="PAPER")
    app.state.execution_engine = engine
    bridge = ExecutionSignalBridge(engine=engine, event_bus=EventBus())
    await bridge._on_signal_v2(_signal_event(_SIGNAL_UP))
    proposal = (await _proposals(client))[0]
    approval = engine.get_approval(proposal["id"])
    assert approval is not None
    approval.expires_at = datetime.now(UTC) - timedelta(seconds=10)

    resp = await client.get("/api/execution/proposals")
    assert resp.status_code == 200
    assert resp.json()[0]["status"] == "EXPIRED"


# ── Engine without wiring degrades ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_proposals_empty_without_engine(client: AsyncClient) -> None:
    resp = await client.get("/api/execution/proposals")
    assert resp.status_code == 200
    assert resp.json() == []
    resp = await client.post("/api/execution/proposals/x/approve")
    assert resp.status_code == 503
