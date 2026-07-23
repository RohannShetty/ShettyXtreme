"""Tests for RiskEngine."""
from __future__ import annotations

import pytest

from shettyxtreme.core.data_models import Position
from shettyxtreme.intelligence.risk import (
    RiskEngine, RiskDecision, Portfolio,
    LossLimitFilter, MarginFilter, MaxPositionFilter,
)
from shettyxtreme.intelligence.signals.signal_engine import (
    Signal, SignalDirection, Vote,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_signal(direction: SignalDirection = SignalDirection.UP) -> Signal:
    return Signal(
        direction=direction,
        conviction=0.8,
        voters=[Vote(direction=1.0, confidence=0.8, weight=1.0, name="test")],
    )


def _make_portfolio(
    daily_pnl: float = 0.0,
    positions: list[Position] | None = None,
    available_margin: float = 100000.0,
    total_margin_used: float = 0.0,
) -> Portfolio:
    return Portfolio(
        positions=positions or [],
        daily_pnl=daily_pnl,
        total_margin_used=total_margin_used,
        available_margin=available_margin,
    )


# ---------------------------------------------------------------------------
# Loss Limit — entry rejection
# ---------------------------------------------------------------------------
class TestLossLimitFilter:
    def test_loss_limit_rejects_entry(self) -> None:
        """Daily loss below limit → REJECT for entry."""
        engine = RiskEngine(filters=[LossLimitFilter(loss_limit=-5000.0)])
        signal = _make_signal()
        portfolio = _make_portfolio(daily_pnl=-6000.0)
        decision = engine.check_entry(signal, portfolio)
        assert not decision.allowed
        assert "loss limit" in decision.reason.lower()

    def test_loss_limit_allows_entry(self) -> None:
        """Daily loss within limit → ALLOW for entry."""
        engine = RiskEngine(filters=[LossLimitFilter(loss_limit=-5000.0)])
        signal = _make_signal()
        portfolio = _make_portfolio(daily_pnl=-1000.0)
        decision = engine.check_entry(signal, portfolio)
        assert decision.allowed

    # ------------------------------------------------------------------
    # CRITICAL TEST: Loss limit does NOT block position management
    # ------------------------------------------------------------------
    def test_loss_limit_does_not_block_position_management(self) -> None:
        """Position management always ALLOW even when daily loss limit reached."""
        engine = RiskEngine(
            filters=[LossLimitFilter(loss_limit=-5000.0)],
        )
        portfolio = _make_portfolio(daily_pnl=-6000.0)
        position = Position(
            symbol="NIFTY", exchange="NSE",
            quantity=75, buy_avg=18000.0, sell_avg=0.0,
            net_quantity=75, m2m=-2000.0, pnl=-2000.0,
            product="NRML",
        )
        decision = engine.check_position_management(position, portfolio)
        assert decision.allowed, "Position management must be allowed regardless of loss limit"


# ---------------------------------------------------------------------------
# Margin
# ---------------------------------------------------------------------------
class TestMarginFilter:
    def test_margin_sufficient_allows_entry(self) -> None:
        engine = RiskEngine(filters=[MarginFilter(margin_threshold_ratio=0.1)])
        signal = _make_signal()
        portfolio = _make_portfolio(
            available_margin=100000.0,
            total_margin_used=50000.0,
        )
        decision = engine.check_entry(signal, portfolio)
        assert decision.allowed

    def test_margin_insufficient_rejects_entry(self) -> None:
        engine = RiskEngine(filters=[MarginFilter(margin_threshold_ratio=0.1)])
        signal = _make_signal()
        portfolio = _make_portfolio(
            available_margin=100.0,  # very low
            total_margin_used=50000.0,
        )
        decision = engine.check_entry(signal, portfolio)
        assert not decision.allowed
        assert "margin" in decision.reason.lower()


# ---------------------------------------------------------------------------
# Max Positions
# ---------------------------------------------------------------------------
class TestMaxPositionFilter:
    def test_max_positions_rejects(self) -> None:
        engine = RiskEngine(filters=[MaxPositionFilter(max_positions=2)])
        signal = _make_signal()
        positions = [
            Position("A", "NSE", 75, 100, 0, 75, 0, 0, "NRML"),
            Position("B", "NSE", -75, 0, 105, -75, 0, 0, "NRML"),
        ]
        portfolio = _make_portfolio(positions=positions)
        decision = engine.check_entry(signal, portfolio)
        assert not decision.allowed
        assert "max positions" in decision.reason.lower()

    def test_max_positions_allows(self) -> None:
        engine = RiskEngine(filters=[MaxPositionFilter(max_positions=2)])
        signal = _make_signal()
        positions = [
            Position("A", "NSE", 75, 100, 0, 75, 0, 0, "NRML"),
        ]
        portfolio = _make_portfolio(positions=positions)
        decision = engine.check_entry(signal, portfolio)
        assert decision.allowed


# ---------------------------------------------------------------------------
# Filter chain — all must pass
# ---------------------------------------------------------------------------
class TestFilterChain:
    def test_all_filters_pass(self) -> None:
        """All filters allow → entry ALLOW."""
        engine = RiskEngine()
        signal = _make_signal()
        portfolio = _make_portfolio(
            daily_pnl=0.0,
            available_margin=500000.0,
            total_margin_used=50000.0,
        )
        decision = engine.check_entry(signal, portfolio)
        assert decision.allowed

    def test_one_filter_fails(self) -> None:
        """If any filter fails → entry REJECT."""
        engine = RiskEngine(filters=[
            LossLimitFilter(loss_limit=-5000.0),
            MarginFilter(margin_threshold_ratio=0.1),
            MaxPositionFilter(max_positions=2),
        ])
        signal = _make_signal()
        portfolio = _make_portfolio(
            daily_pnl=-10000.0,  # triggers loss limit
            available_margin=500000.0,
            total_margin_used=50000.0,
        )
        decision = engine.check_entry(signal, portfolio)
        assert not decision.allowed

    def test_filter_name_in_decision(self) -> None:
        engine = RiskEngine(filters=[LossLimitFilter(loss_limit=0.0)])
        signal = _make_signal()
        portfolio = _make_portfolio(daily_pnl=-1.0)
        decision = engine.check_entry(signal, portfolio)
        assert decision.filter_name == "loss_limit"
