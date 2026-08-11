"""Risk-side settings integration (Phase 7 Wave 3).

The risk engine filters, bus bridge, projection and execution router must
all read their risk caps from the shared settings store — no hardcoded
constants left. This is the regression net for the 4 hardcoded locations
that used to carry ``-5000.0`` / ``5``.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from shettyxtreme.core.data_models import Position
from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.core.settings import get_settings_store, init_settings_store, reset_settings_store
from shettyxtreme.intelligence.risk.bus_bridge import RiskBusBridge
from shettyxtreme.intelligence.risk.risk_engine import (
    LossLimitFilter,
    MaxPositionFilter,
    Portfolio,
    RiskEngine,
)
from shettyxtreme.intelligence.signals.signal_engine import (
    Signal,
    SignalDirection,
    Vote,
)
from shettyxtreme.terminal.api.execution_router import get_risk
from shettyxtreme.terminal.projections import RiskProjection


@pytest.fixture(autouse=True)
def _isolated_store(tmp_path):
    init_settings_store(tmp_path / "settings.db")
    yield
    reset_settings_store()


def _signal() -> Signal:
    return Signal(
        direction=SignalDirection.UP,
        conviction=0.8,
        voters=[Vote(direction=1.0, confidence=0.8, weight=1.0, name="test")],
    )


def _portfolio(daily_pnl: float = 0.0, positions: list[Position] | None = None) -> Portfolio:
    return Portfolio(
        positions=positions or [],
        daily_pnl=daily_pnl,
        total_margin_used=0.0,
        available_margin=100000.0,
    )


def _position(symbol: str) -> Position:
    return Position(
        symbol=symbol, exchange="NSE", quantity=10, buy_avg=100.0,
        sell_avg=0.0, net_quantity=10, m2m=0.0, pnl=0.0, product="NRML",
    )


class TestLossLimitFilter:
    def test_default_reads_store(self) -> None:
        get_settings_store().update({"loss_limit": -2500.0})
        filt = LossLimitFilter()
        assert filt.loss_limit == -2500.0

    def test_check_honors_runtime_change(self) -> None:
        store = get_settings_store()
        store.update({"loss_limit": -1000.0})
        filt = LossLimitFilter()
        portfolio = _portfolio(daily_pnl=-500.0)
        assert filt.check(_signal(), portfolio).allowed
        # Change the cap while the same filter instance is alive.
        store.update({"loss_limit": -100.0})
        assert not filt.check(_signal(), portfolio).allowed

    def test_explicit_value_is_pinned(self) -> None:
        get_settings_store().update({"loss_limit": -100.0})
        filt = LossLimitFilter(loss_limit=-9000.0)
        # Explicit cap wins over the store: -5000 > -9000 → not breached.
        assert filt.check(_signal(), _portfolio(daily_pnl=-5000.0)).allowed


class TestMaxPositionFilter:
    def test_default_reads_store(self) -> None:
        get_settings_store().update({"max_positions": 3})
        filt = MaxPositionFilter()
        assert filt.max_positions == 3

    def test_check_honors_runtime_change(self) -> None:
        store = get_settings_store()
        store.update({"max_positions": 2})
        filt = MaxPositionFilter()
        portfolio = _portfolio(positions=[_position("A"), _position("B")])
        assert not filt.check(_signal(), portfolio).allowed
        store.update({"max_positions": 5})
        assert filt.check(_signal(), portfolio).allowed


class TestRiskEngineChain:
    def test_default_engine_reads_store(self) -> None:
        get_settings_store().update({"loss_limit": -50.0, "max_positions": 1})
        engine = RiskEngine()
        decision = engine.check_entry(_signal(), _portfolio(daily_pnl=-100.0))
        assert not decision.allowed
        assert decision.filter_name == "loss_limit"


class TestRiskProjection:
    def test_initial_state_reads_store(self) -> None:
        get_settings_store().update({"loss_limit": -3333.0, "max_positions": 7})
        state = RiskProjection().get()
        assert state["loss_limit"] == -3333.0
        assert state["max_positions"] == 7
        assert state["margin_available"] is None  # honesty rule intact


class TestRiskBusBridge:
    @pytest.mark.asyncio
    async def test_decision_publishes_store_limits(self) -> None:
        get_settings_store().update({"loss_limit": -2000.0, "max_positions": 4})
        bus = EventBus()
        bridge = RiskBusBridge(bus)
        received: list[Event] = []

        async def spy(ev: Event) -> None:
            received.append(ev)

        await bridge.start()
        bus.subscribe(Topic.RISK_DECISION, spy)
        task = asyncio.create_task(bus.start())
        try:
            await bus.publish(Event(
                Topic.POSITION_CHANGED,
                {"symbol": "NIFTY", "daily_pnl": -100.0},
                source="test",
            ))
            for _ in range(100):
                if received:
                    break
                await asyncio.sleep(0.02)
            assert received, "RiskBusBridge never published a RISK_DECISION"
            decision = received[0].data
            assert decision["loss_limit"] == -2000.0
            assert decision["max_positions"] == 4
            assert "margin_available" not in decision  # honesty rule intact
        finally:
            await bridge.stop()
            await bus.stop()
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


class TestExecutionRouterFallback:
    @pytest.mark.asyncio
    async def test_risk_fallback_reads_store(self) -> None:
        """GET /api/execution/risk must fall back to the store when the
        projection carries no caps (the old ``-5000.0`` default)."""
        get_settings_store().update({"loss_limit": -1500.0, "max_positions": 6})
        request = SimpleNamespace(app=SimpleNamespace(
            state=SimpleNamespace(
                risk_projection=SimpleNamespace(get=lambda: {}),
                position_projection=SimpleNamespace(get=lambda: []),
            )
        ))
        resp = await get_risk(request)
        assert resp.loss_limit == -1500.0
        assert resp.max_positions == 6
