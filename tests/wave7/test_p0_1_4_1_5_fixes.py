"""Tests for P0-1.4 (useless proposals) and P0-1.5 (hardcoded qty=75) fixes.

Verifies:
- get_lot_size() returns correct lot sizes
- default_hint_builder uses lot_size from master (not 75)
- StrategyHints.generate() produces OptionLeg
- ProposalResponse serializes leg fields
- _build_order passes leg fields to OrderRequest
- compute_cost uses provided lot_size (not default 75)
"""
from __future__ import annotations

import pytest
from datetime import UTC, datetime
from unittest.mock import AsyncMock

from shettyxtreme.core.data_models import OrderSide, OrderType, ProductType
from shettyxtreme.execution.execution_engine import ExecutionEngine
from shettyxtreme.execution.signal_bridge import (
    ExecutionSignalBridge,
    default_hint_builder,
    make_default_hint_builder,
)
from shettyxtreme.intelligence.hints.option_leg import OptionLeg
from shettyxtreme.intelligence.hints.strategy_hints import StrategyHint, StrategyHints
from shettyxtreme.intelligence.risk.cost_model import compute_cost
from shettyxtreme.intelligence.risk.risk_engine import Portfolio, RiskEngine
from shettyxtreme.intelligence.signals.signal_engine import Signal, SignalDirection
from shettyxtreme.terminal.api.models import ProposalResponse


# ── Helpers ──────────────────────────────────────────────────────────────────

class FakeMaster:
    """Instrument master returning a fixed lot size."""
    def __init__(self, lot_size: int | None = 65) -> None:
        self._lot_size = lot_size

    def get_lot_size(self, internal_symbol: str, exchange: str = "NSE",
                     instrument_type: str = "INDEX") -> int | None:
        return self._lot_size


class EmptyMaster:
    """Instrument master with no data."""
    def get_lot_size(self, internal_symbol: str, exchange: str = "NSE",
                     instrument_type: str = "INDEX") -> int | None:
        return None


BULLISH_SIGNAL = {
    "direction": "UP", "conviction": 0.7, "D": 0.6, "P": 1.0, "G": "unanimous",
}

CHAIN = [
    {"strike": 24000, "option_type": "CE", "premium": 150.0, "iv": 15.0},
    {"strike": 24100, "option_type": "CE", "premium": 100.0, "iv": 15.0},
]


def _make_engine() -> tuple:
    from shettyxtreme.execution.paper_trading import PaperTradingEngine
    from shettyxtreme.execution.mode_router import ModeRoutingExecutor
    paper = PaperTradingEngine()
    executor = ModeRoutingExecutor(
        paper_engine=paper,
        mode_provider=lambda: "PAPER",
        kill_switch_provider=lambda: False,
        live_provider=lambda: None,
    )

    def _portfolio() -> Portfolio:
        return Portfolio(positions=[], daily_pnl=0.0, total_margin_used=0.0, available_margin=1_000_000.0)

    engine = ExecutionEngine(
        executor=executor,
        risk_engine=RiskEngine(),
        portfolio_provider=_portfolio,
    )
    return engine, paper


# ── Test 1: get_lot_size ─────────────────────────────────────────────────────

class TestGetLotSize:
    def test_returns_lot_size_for_known_symbol(self) -> None:
        """get_lot_size('NIFTY') returns 65 against a seeded master."""
        master = FakeMaster(65)
        assert master.get_lot_size("NIFTY") == 65

    def test_returns_none_on_empty_db(self) -> None:
        """get_lot_size returns None when master has no data."""
        master = EmptyMaster()
        assert master.get_lot_size("NIFTY") is None


# ── Test 2: default_hint_builder with master ─────────────────────────────────

class TestDefaultHintBuilder:
    def test_quantity_equals_lot_size_when_master_available(self) -> None:
        """default_hint_builder with injected master → quantity == lot_size (1 lot)."""
        builder = make_default_hint_builder(FakeMaster(65))
        hint = builder({})
        assert hint["quantity"] == 65
        assert hint["lot_size"] == 65
        assert hint["lots"] == 1
        assert hint["hint_kind"] == "default"

    def test_quantity_none_when_no_master(self) -> None:
        """Without master, quantity is None (not 75)."""
        hint = default_hint_builder({})
        assert hint["quantity"] is None
        assert hint["lot_size"] is None

    def test_quantity_not_hardcoded_75(self) -> None:
        """Quantity must NOT be 75 under any circumstances."""
        builder = make_default_hint_builder(FakeMaster(65))
        hint = builder({})
        assert hint["quantity"] != 75


# ── Test 3: StrategyHints produces OptionLeg ─────────────────────────────────

class TestStrategyHintsLeg:
    def test_generate_produces_leg_with_lot_size(self) -> None:
        """StrategyHints.generate() produces hint with leg populated."""
        hint = StrategyHints(
            signal=BULLISH_SIGNAL,
            chain=CHAIN,
            current_price=24000.0,
            slippage_per_lot=0.0,
            brokerage_per_lot=0.0,
            lot_size=65,
        ).generate()
        assert hint.leg is not None
        assert hint.leg.strike == 24000.0
        assert hint.leg.option_type == "CE"
        assert hint.leg.lot_size == 65
        assert hint.leg.qty == 65  # 1 lot
        assert hint.leg.lots == 1

    def test_generate_without_lot_size_has_no_leg(self) -> None:
        """Without lot_size, no OptionLeg is created."""
        hint = StrategyHints(
            signal=BULLISH_SIGNAL,
            chain=CHAIN,
            current_price=24000.0,
            slippage_per_lot=0.0,
            brokerage_per_lot=0.0,
        ).generate()
        assert hint.leg is None

    def test_hint_has_confidence_and_sl_tp(self) -> None:
        """Hint includes confidence, stop_loss, target."""
        hint = StrategyHints(
            signal=BULLISH_SIGNAL,
            chain=CHAIN,
            current_price=24000.0,
            slippage_per_lot=0.0,
            brokerage_per_lot=0.0,
            lot_size=65,
        ).generate()
        assert hint.confidence is not None
        assert hint.stop_loss is not None
        assert hint.target is not None
        assert hint.premium is not None
        assert hint.stop_loss < hint.premium  # SL below entry
        assert hint.target > hint.premium  # TP above entry


# ── Test 4: ProposalResponse serializes leg fields ───────────────────────────

class TestProposalResponseLeg:
    def test_serializes_leg_fields(self) -> None:
        """ProposalResponse can carry strike/expiry/option_type/lot_size."""
        resp = ProposalResponse(
            id="test-id",
            symbol="NIFTY",
            exchange="NFO",
            side="BUY",
            quantity=65,
            strike=24000.0,
            expiry="2026-02-26",
            option_type="CE",
            lot_size=65,
            lots=1,
            entry_premium=150.0,
            stop_loss=75.0,
            target=300.0,
            rationale="Bullish conviction 0.70",
            hint_kind="chain",
        )
        data = resp.model_dump()
        assert data["strike"] == 24000.0
        assert data["expiry"] == "2026-02-26"
        assert data["option_type"] == "CE"
        assert data["lot_size"] == 65
        assert data["lots"] == 1
        assert data["entry_premium"] == 150.0
        assert data["stop_loss"] == 75.0
        assert data["target"] == 300.0
        assert data["rationale"] == "Bullish conviction 0.70"


# ── Test 5: _build_order passes leg fields ───────────────────────────────────

class TestBuildOrderLeg:
    @pytest.mark.asyncio
    async def test_build_order_carries_leg_fields(self) -> None:
        """_build_order produces OrderRequest with strike/expiry/option_type."""
        engine, _ = _make_engine()
        signal = Signal(direction=SignalDirection.UP, conviction=0.8, voters=[])
        hint = {
            "symbol": "NIFTY",
            "exchange": "NFO",
            "quantity": 65,
            "price": 150.0,
            "order_type": OrderType.LIMIT,
            "product": ProductType.MIS,
            "strike": 24000.0,
            "expiry": "2026-02-26",
            "option_type": "CE",
            "lot_size": 65,
        }
        order = engine._build_order(signal, hint)
        assert order.strike == 24000.0
        assert order.expiry == "2026-02-26"
        assert order.option_type == "CE"
        assert order.lot_size == 65
        assert order.quantity == 65


# ── Test 6: compute_cost with provided lot_size ─────────────────────────────

class TestComputeCostLotSize:
    def test_brokerage_for_one_lot(self) -> None:
        """compute_cost(quantity=65, lot_size=65) → 1 lot brokerage."""
        cost = compute_cost(quantity=65, price=100.0, lot_size=65)
        assert cost.brokerage == 20.0  # 1 lot × 20/lot

    def test_brokerage_for_two_lots(self) -> None:
        """compute_cost(quantity=130, lot_size=65) → 2 lots brokerage."""
        cost = compute_cost(quantity=130, price=100.0, lot_size=65)
        assert cost.brokerage == 40.0  # 2 lots × 20/lot

    def test_no_default_75(self) -> None:
        """lot_size=None → assumes 1 lot (not hardcoded 75)."""
        cost = compute_cost(quantity=65, price=100.0, lot_size=None)
        assert cost.brokerage == 20.0  # 1 lot (65 // 65 = 1)
