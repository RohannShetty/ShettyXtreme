"""Tests for P3-4.2 — Pre-Execution Risk Check Enhancement.

Covers:
  - ProposalRiskContext propagation
  - MaxLossPerTradeFilter (equity %, no-stop handling)
  - RiskRewardFilter (RR ratio)
  - MarginHeatFilter (post-trade utilization)
  - UnderlyingConcentrationFilter
  - SectorConcentrationFilter
  - DirectionConcentrationFilter
  - StopHitCooldownFilter
  - Portfolio.equity (paper/live)
  - RISK_ALERT publishing on rejection
  - Settings-backed filter behavior
"""
from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock

import pytest

from shettyxtreme.core.data_models import Position
from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.core.settings import (
    get_settings_store,
    init_settings_store,
    reset_settings_store,
)
from shettyxtreme.intelligence.risk.risk_engine import (
    DirectionConcentrationFilter,
    MarginHeatFilter,
    MaxLossPerTradeFilter,
    Portfolio,
    ProposalRiskContext,
    RiskDecision,
    RiskEngine,
    RiskRewardFilter,
    SectorConcentrationFilter,
    StopHitCooldownFilter,
    UnderlyingConcentrationFilter,
)
from shettyxtreme.intelligence.signals.signal_engine import Signal, SignalDirection, Vote


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _isolated_store(tmp_path):
    init_settings_store(tmp_path / "settings.db")
    yield
    reset_settings_store()


def _signal(direction: SignalDirection = SignalDirection.UP) -> Signal:
    return Signal(
        direction=direction,
        conviction=0.8,
        voters=[Vote(direction=1.0, confidence=0.8, weight=1.0, name="test")],
    )


def _portfolio(
    daily_pnl: float = 0.0,
    positions: list[Position] | None = None,
    available_margin: float = 100000.0,
    total_margin_used: float = 0.0,
    equity: float | None = 1_000_000.0,
) -> Portfolio:
    return Portfolio(
        positions=positions or [],
        daily_pnl=daily_pnl,
        total_margin_used=total_margin_used,
        available_margin=available_margin,
        equity=equity,
    )


def _proposal(
    symbol: str = "NIFTY",
    side: str = "BUY",
    quantity: int = 75,
    entry_price: float = 100.0,
    stop_loss: float | None = 50.0,
    target: float | None = 200.0,
    lot_size: int | None = 75,
    underlying: str | None = None,
    estimated_margin: float | None = None,
) -> ProposalRiskContext:
    return ProposalRiskContext(
        symbol=symbol,
        side=side,
        quantity=quantity,
        entry_price=entry_price,
        stop_loss=stop_loss,
        target=target,
        product="MIS",
        lot_size=lot_size,
        underlying=underlying,
        estimated_margin=estimated_margin,
    )


def _position(symbol: str, net_qty: int = 75, buy_avg: float = 100.0) -> Position:
    return Position(
        symbol=symbol, exchange="NSE_FNO", quantity=abs(net_qty),
        buy_avg=buy_avg, sell_avg=0.0, net_quantity=net_qty,
        m2m=0.0, pnl=0.0, product="MIS",
    )


# ---------------------------------------------------------------------------
# 1. test_risk_filter_proposal_context
# ---------------------------------------------------------------------------
class TestProposalContext:
    def test_filter_receives_proposal(self) -> None:
        """Filters that need proposal ALLOW when it's None (backward compat)."""
        filt = MaxLossPerTradeFilter(max_loss_pct=0.02)
        decision = filt.check(_signal(), _portfolio(), proposal=None)
        assert decision.allowed  # no context = cannot evaluate = allow passively

    def test_filters_pass_proposal_through_chain(self) -> None:
        """RiskEngine passes proposal to all filters."""
        engine = RiskEngine(filters=[MaxLossPerTradeFilter(max_loss_pct=0.05)])
        # loss = (100 - 99) * 1 * 1 = 1; 5% of 1000000 = 50000 → passes
        proposal = _proposal(entry_price=100.0, stop_loss=99.0, quantity=1, lot_size=1)
        decision = engine.check_entry(_signal(), _portfolio(equity=1_000_000.0), proposal)
        assert decision.allowed


# ---------------------------------------------------------------------------
# 2. test_max_loss_per_trade_filter
# ---------------------------------------------------------------------------
class TestMaxLossPerTradeFilter:
    def test_rejects_when_loss_exceeds_equity_pct(self) -> None:
        """potential_loss (entry-SL)*qty*lot > 2% equity → REJECT."""
        filt = MaxLossPerTradeFilter(max_loss_pct=0.02)
        # loss = (100 - 50) * 75 * 1 = 3750; 2% of 100000 = 2000
        proposal = _proposal(entry_price=100.0, stop_loss=50.0, quantity=75, lot_size=1)
        decision = filt.check(_signal(), _portfolio(equity=100000.0), proposal)
        assert not decision.allowed
        assert "potential loss" in decision.reason.lower()

    def test_allows_when_loss_within_equity_pct(self) -> None:
        """potential_loss ≤ 2% equity → ALLOW."""
        filt = MaxLossPerTradeFilter(max_loss_pct=0.02)
        # loss = (100 - 99) * 75 * 1 = 75; 2% of 100000 = 2000
        proposal = _proposal(entry_price=100.0, stop_loss=99.0, quantity=75, lot_size=1)
        decision = filt.check(_signal(), _portfolio(equity=100000.0), proposal)
        assert decision.allowed

    def test_short_side_loss_calculation(self) -> None:
        """Short: loss = (stop - entry) * qty * lot."""
        filt = MaxLossPerTradeFilter(max_loss_pct=0.02)
        # loss = (150 - 100) * 10 * 1 = 500; 2% of 10000 = 200
        proposal = _proposal(
            side="SELL", entry_price=100.0, stop_loss=150.0, quantity=10, lot_size=1,
        )
        decision = filt.check(_signal(), _portfolio(equity=10000.0), proposal)
        assert not decision.allowed


# ---------------------------------------------------------------------------
# 3. test_max_loss_per_trade_no_stop_live
# ---------------------------------------------------------------------------
class TestMaxLossNoStop:
    def test_no_stop_rejects_when_equity_present(self) -> None:
        """No stop → full premium at risk; rejects when > equity %."""
        filt = MaxLossPerTradeFilter(max_loss_pct=0.02)
        # loss = 100 * 75 * 1 = 7500; 2% of 100000 = 2000
        proposal = _proposal(
            entry_price=100.0, stop_loss=None, quantity=75, lot_size=1,
        )
        decision = filt.check(_signal(), _portfolio(equity=100000.0), proposal)
        assert not decision.allowed

    def test_no_stop_allows_when_within_pct(self) -> None:
        """No stop but premium within equity % → ALLOW."""
        filt = MaxLossPerTradeFilter(max_loss_pct=0.02)
        # loss = 10 * 1 * 1 = 10; 2% of 100000 = 2000
        proposal = _proposal(
            entry_price=10.0, stop_loss=None, quantity=1, lot_size=1,
        )
        decision = filt.check(_signal(), _portfolio(equity=100000.0), proposal)
        assert decision.allowed


# ---------------------------------------------------------------------------
# 4. test_risk_reward_filter
# ---------------------------------------------------------------------------
class TestRiskRewardFilter:
    def test_rejects_when_rr_below_minimum(self) -> None:
        """RR = (target-entry)/(entry-stop) < min → REJECT."""
        filt = RiskRewardFilter(min_risk_reward=1.5)
        # RR = (120 - 100) / (100 - 90) = 20/10 = 2.0 → passes
        # Change: RR = (105 - 100) / (100 - 90) = 5/10 = 0.5 → fails
        proposal = _proposal(entry_price=100.0, stop_loss=90.0, target=105.0)
        decision = filt.check(_signal(), _portfolio(), proposal)
        assert not decision.allowed
        assert "rr" in decision.reason.lower()

    def test_allows_when_rr_above_minimum(self) -> None:
        """RR >= min → ALLOW."""
        filt = RiskRewardFilter(min_risk_reward=1.5)
        # RR = (200 - 100) / (100 - 50) = 100/50 = 2.0
        proposal = _proposal(entry_price=100.0, stop_loss=50.0, target=200.0)
        decision = filt.check(_signal(), _portfolio(), proposal)
        assert decision.allowed

    def test_allows_when_no_target(self) -> None:
        """No target → allow (target is a nicety)."""
        filt = RiskRewardFilter(min_risk_reward=1.5)
        proposal = _proposal(entry_price=100.0, stop_loss=50.0, target=None)
        decision = filt.check(_signal(), _portfolio(), proposal)
        assert decision.allowed

    def test_short_side_rr(self) -> None:
        """Short: RR = (entry-target)/(stop-entry)."""
        filt = RiskRewardFilter(min_risk_reward=1.5)
        # RR = (100 - 80) / (110 - 100) = 20/10 = 2.0
        proposal = _proposal(
            side="SELL", entry_price=100.0, stop_loss=110.0, target=80.0,
        )
        decision = filt.check(_signal(), _portfolio(), proposal)
        assert decision.allowed


# ---------------------------------------------------------------------------
# 5. test_margin_heat_filter
# ---------------------------------------------------------------------------
class TestMarginHeatFilter:
    def test_rejects_when_utilization_exceeds_cap(self) -> None:
        """Post-trade utilization > 50% → REJECT."""
        filt = MarginHeatFilter(max_utilization_pct=0.50)
        # margin_used=30000, available=70000 → total=100000
        # new margin = 50000 → post_trade = (30000+50000)/100000 = 80%
        proposal = _proposal(entry_price=50000.0, quantity=1, lot_size=1)
        portfolio = _portfolio(total_margin_used=30000.0, available_margin=70000.0)
        decision = filt.check(_signal(), portfolio, proposal)
        assert not decision.allowed
        assert "utilization" in decision.reason.lower()

    def test_allows_when_within_cap(self) -> None:
        """Post-trade utilization ≤ 50% → ALLOW."""
        filt = MarginHeatFilter(max_utilization_pct=0.50)
        # margin_used=10000, available=90000 → total=100000
        # new margin = 5000 → post_trade = (10000+5000)/100000 = 15%
        proposal = _proposal(entry_price=5000.0, quantity=1, lot_size=1)
        portfolio = _portfolio(total_margin_used=10000.0, available_margin=90000.0)
        decision = filt.check(_signal(), portfolio, proposal)
        assert decision.allowed

    def test_no_margin_data_rejects(self) -> None:
        """No margin data at all → REJECT (honesty)."""
        filt = MarginHeatFilter(max_utilization_pct=0.50)
        proposal = _proposal(entry_price=100.0, quantity=1, lot_size=1)
        portfolio = _portfolio(total_margin_used=0.0, available_margin=0.0)
        decision = filt.check(_signal(), portfolio, proposal)
        assert not decision.allowed


# ---------------------------------------------------------------------------
# 6. test_underlying_concentration_filter
# ---------------------------------------------------------------------------
class TestUnderlyingConcentrationFilter:
    def test_rejects_when_exceeds_per_underlying(self) -> None:
        """> 3 positions per underlying → REJECT."""
        filt = UnderlyingConcentrationFilter(max_per_underlying=3)
        positions = [
            _position("NSE_FNO:NIFTY24AUG24000CE"),
            _position("NSE_FNO:NIFTY24AUG24500CE"),
            _position("NSE_FNO:NIFTY24AUG25000CE"),
        ]
        # Proposing a 4th NIFTY position
        proposal = _proposal(symbol="NSE_FNO:NIFTY24AUG25500CE", underlying="NIFTY")
        decision = filt.check(_signal(), _portfolio(positions=positions), proposal)
        assert not decision.allowed
        assert "nifty" in decision.reason.lower()

    def test_allows_within_limit(self) -> None:
        """≤ 3 positions per underlying → ALLOW."""
        filt = UnderlyingConcentrationFilter(max_per_underlying=3)
        positions = [
            _position("NSE_FNO:NIFTY24AUG24000CE"),
            _position("NSE_FNO:NIFTY24AUG24500CE"),
        ]
        proposal = _proposal(symbol="NSE_FNO:NIFTY24AUG25000CE", underlying="NIFTY")
        decision = filt.check(_signal(), _portfolio(positions=positions), proposal)
        assert decision.allowed


# ---------------------------------------------------------------------------
# 7. test_sector_concentration_filter
# ---------------------------------------------------------------------------
class TestSectorConcentrationFilter:
    def test_rejects_when_sector_exceeds_cap(self) -> None:
        """Sector > 20% of portfolio notional → REJECT."""
        filt = SectorConcentrationFilter(max_sector_pct=0.20)
        # Two existing sectors: Index (NIFTY) and IT (INFY)
        positions = [
            _position("NIFTY", net_qty=10, buy_avg=10000.0),  # Index: 100000
            _position("INFY", net_qty=100, buy_avg=100.0),    # IT: 10000
        ]
        # Proposing more NIFTY → Index becomes 200000/210000 = 95% > 20%
        proposal = _proposal(symbol="NIFTY", entry_price=10000.0, quantity=10, lot_size=1)
        decision = filt.check(_signal(), _portfolio(positions=positions), proposal)
        assert not decision.allowed

    def test_allows_diversified(self) -> None:
        """Diversified sectors → ALLOW."""
        filt = SectorConcentrationFilter(max_sector_pct=0.50)
        positions = [
            _position("NIFTY", net_qty=75, buy_avg=100.0),   # Index: notional=7500
            _position("INFY", net_qty=75, buy_avg=100.0),    # IT: notional=7500
        ]
        # Adding HDFCBANK: Banking notional=7500, total=22500, Banking=33% < 50%
        proposal = _proposal(symbol="HDFCBANK", entry_price=100.0, quantity=75, lot_size=1)
        decision = filt.check(_signal(), _portfolio(positions=positions), proposal)
        assert decision.allowed


# ---------------------------------------------------------------------------
# 8. test_direction_concentration_filter
# ---------------------------------------------------------------------------
class TestDirectionConcentrationFilter:
    def test_rejects_when_one_sided(self) -> None:
        """One direction > 80% → REJECT."""
        filt = DirectionConcentrationFilter(max_direction_pct=0.80)
        # Mixed: long 90000 + short 10000 = 100000 total
        positions = [
            _position("NIFTY", net_qty=90, buy_avg=1000.0),   # long: 90000
            _position("BANKNIFTY", net_qty=-10, buy_avg=1000.0),  # short: 10000
        ]
        # Proposing more long → long=90000+7500=97500, total=107500, long=90.7% > 80%
        proposal = _proposal(side="BUY", entry_price=100.0, quantity=75, lot_size=1)
        decision = filt.check(_signal(), _portfolio(positions=positions), proposal)
        assert not decision.allowed
        assert "long" in decision.reason.lower()

    def test_allows_balanced(self) -> None:
        """Balanced long/short → ALLOW."""
        filt = DirectionConcentrationFilter(max_direction_pct=0.80)
        positions = [
            _position("NIFTY", net_qty=75, buy_avg=100.0),  # long
            _position("BANKNIFTY", net_qty=-75, buy_avg=100.0),  # short
        ]
        proposal = _proposal(side="BUY", entry_price=100.0, quantity=10, lot_size=10)
        decision = filt.check(_signal(), _portfolio(positions=positions), proposal)
        assert decision.allowed


# ---------------------------------------------------------------------------
# 9. test_stop_hit_cooldown_filter
# ---------------------------------------------------------------------------
class TestStopHitCooldownFilter:
    def test_rejects_within_cooldown_window(self) -> None:
        """Re-entry within cooldown → REJECT."""
        filt = StopHitCooldownFilter(cooldown_minutes=30.0)
        filt.record_stop_hit("NIFTY")
        proposal = _proposal(symbol="NIFTY")
        decision = filt.check(_signal(), _portfolio(), proposal)
        assert not decision.allowed
        assert "cooldown" in decision.reason.lower()

    def test_allows_after_cooldown(self) -> None:
        """Re-entry after cooldown → ALLOW."""
        filt = StopHitCooldownFilter(cooldown_minutes=0.001)  # very short
        filt.record_stop_hit("NIFTY")
        time.sleep(0.1)
        proposal = _proposal(symbol="NIFTY")
        decision = filt.check(_signal(), _portfolio(), proposal)
        assert decision.allowed

    def test_allows_different_symbol(self) -> None:
        """Different symbol → ALLOW."""
        filt = StopHitCooldownFilter(cooldown_minutes=30.0)
        filt.record_stop_hit("NIFTY")
        proposal = _proposal(symbol="BANKNIFTY")
        decision = filt.check(_signal(), _portfolio(), proposal)
        assert decision.allowed

    def test_allows_no_cooldown(self) -> None:
        """Cooldown = 0 → always ALLOW."""
        filt = StopHitCooldownFilter(cooldown_minutes=0.0)
        filt.record_stop_hit("NIFTY")
        proposal = _proposal(symbol="NIFTY")
        decision = filt.check(_signal(), _portfolio(), proposal)
        assert decision.allowed


# ---------------------------------------------------------------------------
# 10. test_portfolio_equity_paper
# ---------------------------------------------------------------------------
class TestPortfolioEquity:
    def test_equity_field_present(self) -> None:
        """Portfolio carries equity field."""
        p = _portfolio(equity=500000.0)
        assert p.equity == 500000.0

    def test_equity_none_when_unknown(self) -> None:
        """Equity None = unknown."""
        p = _portfolio(equity=None)
        assert p.equity is None

    def test_equity_used_by_max_loss_filter(self) -> None:
        """MaxLossPerTradeFilter uses equity as denominator."""
        filt = MaxLossPerTradeFilter(max_loss_pct=0.02)
        # equity=10000, loss=100*75=7500 → 7500 > 200 → REJECT
        proposal = _proposal(entry_price=100.0, stop_loss=None, quantity=75, lot_size=1)
        decision = filt.check(_signal(), _portfolio(equity=10000.0), proposal)
        assert not decision.allowed

    def test_no_equity_rejects(self) -> None:
        """Unknown equity → REJECT (honesty rule)."""
        filt = MaxLossPerTradeFilter(max_loss_pct=0.02)
        proposal = _proposal(entry_price=100.0, stop_loss=50.0, quantity=75, lot_size=1)
        decision = filt.check(_signal(), _portfolio(equity=None), proposal)
        assert not decision.allowed
        assert "equity unknown" in decision.reason.lower()


# ---------------------------------------------------------------------------
# 11. test_risk_alert_published_on_rejection
# ---------------------------------------------------------------------------
class TestRiskAlertPublishing:
    @pytest.mark.asyncio
    async def test_risk_alert_emitted_on_rejection(self) -> None:
        """RISK_ALERT is published when risk check rejects."""
        from shettyxtreme.execution.execution_engine import ExecutionEngine

        bus = EventBus()
        received: list[Event] = []

        async def spy(ev: Event) -> None:
            received.append(ev)

        bus.subscribe(Topic.RISK_ALERT, spy)

        # Create engine with a filter that always rejects
        class AlwaysReject:
            name = "always_reject"
            def check(self, signal, portfolio, proposal=None):
                return RiskDecision.reject("test rejection", filter_name="always_reject")

        executor = AsyncMock()
        executor.place_order = AsyncMock(return_value=None)

        engine = ExecutionEngine(
            executor=executor,
            risk_engine=RiskEngine(filters=[AlwaysReject()]),
            portfolio_provider=lambda: _portfolio(equity=1_000_000.0),
            event_bus=bus,
        )

        signal = _signal()
        hint = {"symbol": "NIFTY", "exchange": "NSE", "quantity": 75, "price": 100.0}
        approval_id = engine.submit_signal(signal, hint)

        task = asyncio.create_task(bus.start())
        try:
            with pytest.raises(RuntimeError, match="risk check rejected"):
                await engine.approve(approval_id)

            # Give the event loop a chance to deliver
            for _ in range(100):
                if received:
                    break
                await asyncio.sleep(0.02)

            assert received, "RISK_ALERT was never published"
            alert = received[0].data
            assert alert["filter_name"] == "always_reject"
            assert alert["proposal_id"] == approval_id
            assert "test rejection" in alert["reason"]
        finally:
            await bus.stop()
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass


# ---------------------------------------------------------------------------
# 12. test_settings_backed_filters
# ---------------------------------------------------------------------------
class TestSettingsBackedFilters:
    def test_max_loss_pct_from_settings(self) -> None:
        get_settings_store().update({"max_loss_pct": 0.05})
        filt = MaxLossPerTradeFilter()
        assert filt.max_loss_pct == 0.05

    def test_min_risk_reward_from_settings(self) -> None:
        get_settings_store().update({"min_risk_reward": 2.0})
        filt = RiskRewardFilter()
        assert filt.min_risk_reward == 2.0

    def test_max_margin_utilization_from_settings(self) -> None:
        get_settings_store().update({"max_margin_utilization_pct": 0.60})
        filt = MarginHeatFilter()
        assert filt.max_utilization_pct == 0.60

    def test_max_positions_per_underlying_from_settings(self) -> None:
        get_settings_store().update({"max_positions_per_underlying": 5})
        filt = UnderlyingConcentrationFilter()
        assert filt.max_per_underlying == 5

    def test_max_sector_pct_from_settings(self) -> None:
        get_settings_store().update({"max_sector_pct": 0.30})
        filt = SectorConcentrationFilter()
        assert filt.max_sector_pct == 0.30

    def test_max_direction_pct_from_settings(self) -> None:
        get_settings_store().update({"max_direction_pct": 0.90})
        filt = DirectionConcentrationFilter()
        assert filt.max_direction_pct == 0.90

    def test_stop_cooldown_from_settings(self) -> None:
        get_settings_store().update({"stop_cooldown_minutes": 60.0})
        filt = StopHitCooldownFilter()
        assert filt.cooldown_minutes == 60.0

    def test_settings_runtime_change_honored(self) -> None:
        """Settings change at runtime is picked up by settings-backed filters."""
        store = get_settings_store()
        store.update({"max_loss_pct": 0.05})
        filt = MaxLossPerTradeFilter()
        # 100*75=7500 > 5% of 100000=5000 → reject
        proposal = _proposal(entry_price=100.0, stop_loss=None, quantity=75, lot_size=1)
        decision = filt.check(_signal(), _portfolio(equity=100000.0), proposal)
        assert not decision.allowed

        store.update({"max_loss_pct": 0.10})
        # 7500 < 10% of 100000=10000 → allow
        decision = filt.check(_signal(), _portfolio(equity=100000.0), proposal)
        assert decision.allowed


# ---------------------------------------------------------------------------
# 13. Default chain order integration
# ---------------------------------------------------------------------------
class TestDefaultChain:
    def test_default_chain_has_all_new_filters(self) -> None:
        """Default RiskEngine chain includes all P3-4.2 filters."""
        engine = RiskEngine()
        filter_names = [f.name for f in engine.filters]
        assert "max_loss_per_trade" in filter_names
        assert "risk_reward" in filter_names
        assert "margin_heat" in filter_names
        assert "underlying_concentration" in filter_names
        assert "sector_concentration" in filter_names
        assert "direction_concentration" in filter_names
        assert "stop_cooldown" in filter_names

    def test_position_management_always_allowed(self) -> None:
        """Position management always allowed (D10/V1 fix)."""
        engine = RiskEngine()
        position = Position(
            symbol="NIFTY", exchange="NSE", quantity=75,
            buy_avg=100.0, sell_avg=0.0, net_quantity=75,
            m2m=-5000.0, pnl=-5000.0, product="NRML",
        )
        decision = engine.check_position_management(position, _portfolio(daily_pnl=-10000.0))
        assert decision.allowed
