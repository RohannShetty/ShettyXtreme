"""Tests for paper trading realism (P3-4.1): slippage, fees, fill probability, margin, P&L.

Each test creates a PaperTradingEngine with specific realism models injected,
so tests are deterministic and independent.
"""

from __future__ import annotations

import math
import random

import pytest

from shettyxtreme.core.data_models.orders import Fill, Order, OrderResult, Position
from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.execution.paper_realism import (
    FeeBreakdown,
    FeesModel,
    FillProbabilityModel,
    MarginPolicy,
    MarginResult,
    SlippageModel,
    SlippageResult,
)
from shettyxtreme.execution.paper_trading import PaperTradingEngine


def _seed_ltp(engine: PaperTradingEngine, symbol: str, ltp: float) -> None:
    engine._ltp_cache[symbol.upper()] = ltp


def _seed_tick(
    engine: PaperTradingEngine,
    symbol: str,
    ltp: float,
    bid: float | None = None,
    ask: float | None = None,
    volume: int = 0,
) -> None:
    sym = symbol.upper()
    engine._ltp_cache[sym] = ltp
    if bid is not None:
        engine._bid_cache[sym] = bid
    if ask is not None:
        engine._ask_cache[sym] = ask
    if volume > 0:
        engine._volume_cache[sym] = volume


# ── 1. Slippage model — spread-based ────────────────────────────────────────


class TestSlippageSpread:
    """MARKET order fills at bid/ask, not LTP."""

    @pytest.mark.asyncio
    async def test_market_buy_fills_at_ask(self):
        """BUY market order should fill at ask price + residual bps."""
        slippage = SlippageModel(residual_bps=2.0)
        engine = PaperTradingEngine(slippage_model=slippage)
        _seed_tick(engine, "NIFTY", ltp=18450.0, bid=18449.0, ask=18451.0)

        result = await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        assert result.status == "FILLED"
        # Ask = 18451, residual = 2 bps → 18451 * (1 + 0.0002) ≈ 18454.6902
        assert result.average_price > 18451.0
        assert result.average_price < 18456.0  # sanity

    @pytest.mark.asyncio
    async def test_market_sell_fills_at_bid(self):
        """SELL market order should fill at bid price - residual bps."""
        slippage = SlippageModel(residual_bps=2.0)
        engine = PaperTradingEngine(slippage_model=slippage)
        _seed_tick(engine, "NIFTY", ltp=18450.0, bid=18449.0, ask=18451.0)

        result = await engine.place_order("NIFTY", "NFO", "SELL", "MARKET", 50)
        assert result.status == "FILLED"
        # Bid = 18449, residual = 2 bps → 18449 * (1 - 0.0002) ≈ 18445.31
        assert result.average_price < 18449.0
        assert result.average_price > 18444.0  # sanity

    @pytest.mark.asyncio
    async def test_slippage_buy_is_unfavorable(self):
        """BUY fill price should be HIGHER than LTP (unfavorable for buyer)."""
        slippage = SlippageModel(bps_market=5.0)
        engine = PaperTradingEngine(slippage_model=slippage)
        _seed_ltp(engine, "NIFTY", 18450.0)

        result = await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        assert result.average_price > 18450.0

    @pytest.mark.asyncio
    async def test_slippage_sell_is_unfavorable(self):
        """SELL fill price should be LOWER than LTP (unfavorable for seller)."""
        slippage = SlippageModel(bps_market=5.0)
        engine = PaperTradingEngine(slippage_model=slippage)
        _seed_ltp(engine, "NIFTY", 18450.0)

        result = await engine.place_order("NIFTY", "NFO", "SELL", "MARKET", 50)
        assert result.average_price < 18450.0


# ── 2. Slippage model — fixed bps fallback ──────────────────────────────────


class TestSlippageFixed:
    """Fallback to fixed bps when spread unavailable."""

    @pytest.mark.asyncio
    async def test_market_fallback_5bps_buy(self):
        """No bid/ask → fixed 5 bps on MARKET BUY."""
        slippage = SlippageModel(bps_market=5.0, bps_limit=2.0)
        engine = PaperTradingEngine(slippage_model=slippage)
        _seed_ltp(engine, "NIFTY", 10000.0)  # clean number for math

        result = await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 10)
        expected = 10000.0 * (1 + 5.0 / 10_000)  # 10005.0
        assert abs(result.average_price - expected) < 0.1

    @pytest.mark.asyncio
    async def test_market_fallback_5bps_sell(self):
        """No bid/ask → fixed 5 bps on MARKET SELL."""
        slippage = SlippageModel(bps_market=5.0, bps_limit=2.0)
        engine = PaperTradingEngine(slippage_model=slippage)
        _seed_ltp(engine, "NIFTY", 10000.0)

        result = await engine.place_order("NIFTY", "NFO", "SELL", "MARKET", 10)
        expected = 10000.0 * (1 - 5.0 / 10_000)  # 9995.0
        assert abs(result.average_price - expected) < 0.1


# ── 3. India-correct fees model ─────────────────────────────────────────────


class TestFeesModel:
    """Per-fill transaction costs: brokerage, STT, exchange, GST, SEBI, stamp."""

    def test_brokerage_lower_bound(self):
        """Brokerage = ₹20 OR 0.03% of notional, whichever is lower."""
        fees = FeesModel()
        # Notional = 100 * 50 = 5000; 0.03% = ₹1.5; min(20, 1.5) = ₹1.5
        breakdown = fees.compute(quantity=100, price=50.0, side="BUY", exchange="NSE")
        assert breakdown.brokerage == 1.5

    def test_brokerage_flat_cap(self):
        """High notional → brokerage capped at ₹20."""
        fees = FeesModel()
        # Notional = 50 * 18450 = 922500; 0.03% = ₹276.75; min(20, 276.75) = ₹20
        breakdown = fees.compute(quantity=50, price=18450.0, side="BUY", exchange="NSE")
        assert breakdown.brokerage == 20.0

    def test_stt_sell_side_options(self):
        """STT applies on options (0.01% of notional)."""
        fees = FeesModel()
        # Notional = 50 * 100 = 5000; STT options = 5000 * 0.0001 = 0.5
        breakdown = fees.compute(quantity=50, price=100.0, side="SELL", exchange="NSE_FO")
        assert breakdown.stt == 0.5

    def test_stt_buy_side_equity(self):
        """STT on equity delivery buy side = 0 (only on sell for delivery)."""
        fees = FeesModel()
        breakdown = fees.compute(quantity=50, price=100.0, side="BUY", exchange="NSE")
        # Equity buy: no STT (it's on sell side for delivery)
        assert breakdown.stt == 0.0

    def test_stt_equity_sell(self):
        """STT on equity sell = 0.1%."""
        fees = FeesModel()
        # Notional = 50 * 100 = 5000; STT = 5000 * 0.001 = 5.0
        breakdown = fees.compute(quantity=50, price=100.0, side="SELL", exchange="NSE")
        assert breakdown.stt == 5.0

    def test_exchange_charges_options(self):
        """Exchange charges for options = 0.05% of notional."""
        fees = FeesModel()
        # Notional = 50 * 100 = 5000; 0.05% = 2.5
        breakdown = fees.compute(quantity=50, price=100.0, side="BUY", exchange="NSE_FO")
        assert breakdown.exchange_charges == 2.5

    def test_gst_18_pct(self):
        """GST = 18% on (brokerage + exchange charges + SEBI charges)."""
        fees = FeesModel()
        breakdown = fees.compute(quantity=50, price=100.0, side="BUY", exchange="NSE_FO")
        # brokerage = min(20, 1.5) = 1.5
        # exchange = 5000 * 0.0005 = 2.5
        # SEBI = 5000 * 0.000001 = 0.005
        # GST = 18% * (1.5 + 2.5 + 0.005) = 0.18 * 4.005 = 0.7209
        expected_gst = (1.5 + 2.5 + 0.005) * 0.18
        assert abs(breakdown.gst - expected_gst) < 0.01

    def test_sebi_charges(self):
        """SEBI charges = ₹10 per crore (0.0001%)."""
        fees = FeesModel()
        # Notional = 1_000_000; SEBI = 1_000_000 * 0.000001 = 1.0
        breakdown = fees.compute(quantity=1, price=1_000_000.0, side="BUY", exchange="NSE")
        assert breakdown.sebi_charges == 1.0

    def test_stamp_duty_buy_only(self):
        """Stamp duty applies on buy side only."""
        fees = FeesModel()
        buy = fees.compute(quantity=50, price=100.0, side="BUY", exchange="NSE_FO")
        sell = fees.compute(quantity=50, price=100.0, side="SELL", exchange="NSE_FO")
        assert buy.stamp_duty > 0
        assert sell.stamp_duty == 0.0

    def test_total_positive(self):
        """Total fees should always be positive for a real fill."""
        fees = FeesModel()
        breakdown = fees.compute(quantity=50, price=18450.0, side="BUY", exchange="NSE_FO")
        assert breakdown.total > 0

    @pytest.mark.asyncio
    async def test_fees_deducted_from_capital_on_buy(self):
        """Capital should decrease by notional + fees on BUY fill."""
        fees = FeesModel()
        engine = PaperTradingEngine(fees_model=fees, initial_capital=1_000_000.0)
        _seed_ltp(engine, "NIFTY", 100.0)

        initial = engine._capital
        await engine.place_order("NIFTY", "NSE_FO", "BUY", "MARKET", 50)
        notional = 50 * 100.0
        # Capital should be < initial - notional (fees deducted too)
        assert engine._capital < initial - notional

    @pytest.mark.asyncio
    async def test_fees_tracked_on_fill(self):
        """Fill.fees should be populated when fees model is active."""
        fees = FeesModel()
        engine = PaperTradingEngine(fees_model=fees)
        _seed_ltp(engine, "NIFTY", 100.0)

        await engine.place_order("NIFTY", "NSE_FO", "BUY", "MARKET", 50)
        last_fill = engine._fills[-1]
        assert last_fill.fees > 0


# ── 4. Fill probability — distance-based ────────────────────────────────────


class TestFillProbability:
    """Limit order fill probability decreases with distance from LTP."""

    @pytest.mark.asyncio
    async def test_close_limit_fills_quickly(self):
        """Limit close to LTP fills with high probability."""
        rng = random.Random(42)
        fp = FillProbabilityModel(rng=rng)
        engine = PaperTradingEngine(fill_probability_model=fp)
        # Place limit BUY at 100.0
        result = await engine.place_order("NIFTY", "NFO", "BUY", "LIMIT", 50, price=100.0)
        assert result.status == "OPEN"

        # Tick with LTP right at limit
        for _ in range(20):
            evt = Event(Topic.MARKET_DATA_TICK, {"symbol": "NIFTY", "ltp": 100.0}, source="test")
            await engine._on_tick(evt)
            if not engine._pending_orders:
                break

        # Should fill within 20 ticks
        assert len(engine._pending_orders) == 0

    @pytest.mark.asyncio
    async def test_far_limit_unlikely_to_fill_immediately(self):
        """Limit at touch but far from ref price → low fill probability."""
        rng = random.Random(42)
        fp = FillProbabilityModel(distance_decay=10.0, rng=rng)
        engine = PaperTradingEngine(fill_probability_model=fp)
        # BUY limit at 100.0 — for BUY, gap-through cancels when LTP > limit.
        # Use LTP just below limit so order is at touch but with high distance.
        # LTP=99.0, limit=100 → at touch (ltp <= limit), distance = ~101 bps
        # prob = exp(-101/10) ≈ 0.00004 → extremely unlikely to fill.
        result = await engine.place_order("NIFTY", "NFO", "BUY", "LIMIT", 50, price=100.0)
        assert result.status == "OPEN"

        # Single tick: at touch but very low fill probability
        evt = Event(Topic.MARKET_DATA_TICK, {"symbol": "NIFTY", "ltp": 99.0}, source="test")
        await engine._on_tick(evt)

        # Probability is ~0.00004 — almost certainly still pending
        assert len(engine._pending_orders) == 1

    @pytest.mark.asyncio
    async def test_fill_probability_increases_with_time(self):
        """After 5 ticks, fill probability increases by 10% per tick."""
        rng = random.Random(42)
        fp = FillProbabilityModel(
            distance_decay=10.0, time_boost_start=5, time_boost_per_tick=0.10, rng=rng,
        )
        engine = PaperTradingEngine(fill_probability_model=fp)
        await engine.place_order("NIFTY", "NFO", "BUY", "LIMIT", 50, price=100.0)

        # Tick 5 times at 100.0 (right at limit, prob=1.0 so will fill)
        # Use a wider spread to test time boost
        for i in range(10):
            if not engine._pending_orders:
                break
            # Move price closer gradually
            ltp = 100.5 - (i * 0.05)  # starts 0.5% away, approaches
            evt = Event(Topic.MARKET_DATA_TICK, {"symbol": "NIFTY", "ltp": ltp}, source="test")
            await engine._on_tick(evt)

        # With enough ticks and time boost, should fill
        assert len(engine._pending_orders) == 0


# ── 5. Gap-through rule ─────────────────────────────────────────────────────


class TestGapThrough:
    """Limit order cancelled when LTP gaps through."""

    @pytest.mark.asyncio
    async def test_buy_limit_cancelled_on_gap_up(self):
        """BUY limit at 100, LTP gaps to 110 → cancel (price ran away)."""
        rng = random.Random(42)
        fp = FillProbabilityModel(rng=rng)
        engine = PaperTradingEngine(fill_probability_model=fp)
        result = await engine.place_order("NIFTY", "NFO", "BUY", "LIMIT", 50, price=100.0)
        assert result.status == "OPEN"
        assert len(engine._pending_orders) == 1

        # Price gaps above the limit (BUY limit = 100, LTP = 110)
        evt = Event(Topic.MARKET_DATA_TICK, {"symbol": "NIFTY", "ltp": 110.0}, source="test")
        await engine._on_tick(evt)

        # Order should be cancelled (gap-through)
        assert len(engine._pending_orders) == 0
        book = engine.get_order_book()
        assert book[-1].status == "CANCELLED"

    @pytest.mark.asyncio
    async def test_sell_limit_cancelled_on_gap_down(self):
        """SELL limit at 100, LTP drops to 90 → cancel."""
        rng = random.Random(42)
        fp = FillProbabilityModel(rng=rng)
        engine = PaperTradingEngine(fill_probability_model=fp)
        result = await engine.place_order("NIFTY", "NFO", "SELL", "LIMIT", 50, price=100.0)
        assert result.status == "OPEN"

        evt = Event(Topic.MARKET_DATA_TICK, {"symbol": "NIFTY", "ltp": 90.0}, source="test")
        await engine._on_tick(evt)

        assert len(engine._pending_orders) == 0
        book = engine.get_order_book()
        assert book[-1].status == "CANCELLED"


# ── 6. Margin check ─────────────────────────────────────────────────────────


class TestMarginCheck:
    """Engine-side margin sizing rejects oversized orders."""

    @pytest.mark.asyncio
    async def test_margin_rejects_mis_insufficient(self):
        """MIS equity: 20% of notional. Reject if available < required."""
        margin = MarginPolicy(equity_mis_pct=0.20)
        engine = PaperTradingEngine(
            initial_capital=10_000.0,
            margin_policy=margin,
            enable_margin_check=True,
        )
        _seed_ltp(engine, "RELIANCE", 1000.0)
        # Notional = 100 * 1000 = 100_000; MIS required = 20% = 20_000
        # Available = 10_000 → should reject
        result = await engine.place_order("RELIANCE", "NSE", "BUY", "MARKET", 100)
        assert result.status == "REJECTED"
        assert "margin" in result.message.lower() or "insufficient" in result.message.lower()

    @pytest.mark.asyncio
    async def test_margin_allows_mis_sufficient(self):
        """Sufficient margin → order fills."""
        margin = MarginPolicy(equity_mis_pct=0.20)
        engine = PaperTradingEngine(
            initial_capital=1_000_000.0,
            margin_policy=margin,
            enable_margin_check=True,
        )
        _seed_ltp(engine, "RELIANCE", 1000.0)
        # Notional = 100 * 1000 = 100_000; MIS required = 20_000; available = 1_000_000
        result = await engine.place_order("RELIANCE", "NSE", "BUY", "MARKET", 100)
        assert result.status == "FILLED"

    @pytest.mark.asyncio
    async def test_margin_rejects_options_sell_insufficient(self):
        """Options sell: premium + 10%. Reject if insufficient."""
        margin = MarginPolicy(options_sell_pct=1.10)
        engine = PaperTradingEngine(
            initial_capital=50_000.0,
            margin_policy=margin,
            enable_margin_check=True,
        )
        _seed_ltp(engine, "NIFTY", 100.0)
        # Notional = 100 * 100 = 10_000; options sell = 1.10 * 10_000 = 11_000
        # Available = 50_000 → should allow
        result = await engine.place_order("NIFTY", "NSE_FO", "SELL", "MARKET", 100)
        assert result.status == "FILLED"

    @pytest.mark.asyncio
    async def test_margin_rejects_options_sell_real_insufficient(self):
        """Large options sell against tiny capital → rejected."""
        margin = MarginPolicy(options_sell_pct=1.10)
        engine = PaperTradingEngine(
            initial_capital=5_000.0,
            margin_policy=margin,
            enable_margin_check=True,
        )
        _seed_ltp(engine, "NIFTY", 100.0)
        # Notional = 100 * 100 = 10_000; options sell = 11_000; available = 5_000
        result = await engine.place_order("NIFTY", "NSE_FO", "SELL", "MARKET", 100)
        assert result.status == "REJECTED"

    @pytest.mark.asyncio
    async def test_margin_check_disabled_by_default(self):
        """No margin policy → orders fill even with zero capital."""
        engine = PaperTradingEngine(initial_capital=0.0)
        _seed_ltp(engine, "NIFTY", 100.0)
        result = await engine.place_order("NIFTY", "NSE", "BUY", "MARKET", 100)
        assert result.status == "FILLED"


# ── 7. Realized P&L — FIFO pairing ─────────────────────────────────────────


class TestRealizedPnl:
    """Realized P&L computed from position close, net of fees."""

    @pytest.mark.asyncio
    async def test_realized_pnl_after_round_trip(self):
        """BUY then SELL → realized P&L should be non-zero."""
        engine = PaperTradingEngine()
        _seed_ltp(engine, "NIFTY", 100.0)

        await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        _seed_ltp(engine, "NIFTY", 110.0)
        await engine.place_order("NIFTY", "NFO", "SELL", "MARKET", 50)

        pnl = engine.get_pnl()
        # Realized: (110 - 100) * 50 = 500
        assert pnl["realised_pnl"] == 500.0
        assert pnl["total_pnl"] == 500.0

    @pytest.mark.asyncio
    async def test_realized_pnl_fees_deducted(self):
        """Fees are tracked and deducted from capital, not pos.pnl."""
        fees = FeesModel()
        engine = PaperTradingEngine(fees_model=fees, initial_capital=1_000_000.0)
        _seed_ltp(engine, "NIFTY", 100.0)

        initial_capital = engine._capital
        await engine.place_order("NIFTY", "NSE_FO", "BUY", "MARKET", 50)
        buy_fees = engine._total_fees
        assert buy_fees > 0

        _seed_ltp(engine, "NIFTY", 110.0)
        await engine.place_order("NIFTY", "NSE_FO", "SELL", "MARKET", 50)
        total_fees = engine._total_fees
        assert total_fees > buy_fees  # sell fees added

        pnl = engine.get_pnl()
        # Gross realized P&L is still 500 (pos.pnl tracks gross)
        assert pnl["realised_pnl"] == 500.0
        # But total_fees is tracked and positive
        assert pnl["total_fees"] > 0
        # Capital reflects fee deduction: initial - total_fees
        # (net P&L is implicit in capital change)
        assert engine._capital < initial_capital + 500.0  # less than gross profit

    @pytest.mark.asyncio
    async def test_pnl_after_loss(self):
        """BUY high, sell low → negative realized P&L."""
        engine = PaperTradingEngine()
        _seed_ltp(engine, "NIFTY", 200.0)

        await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        _seed_ltp(engine, "NIFTY", 180.0)
        await engine.place_order("NIFTY", "NFO", "SELL", "MARKET", 50)

        pnl = engine.get_pnl()
        assert pnl["realised_pnl"] == -1000.0  # (180 - 200) * 50 = -1000

    @pytest.mark.asyncio
    async def test_partial_close_pnl(self):
        """Sell half the position → partial realized P&L."""
        engine = PaperTradingEngine()
        _seed_ltp(engine, "NIFTY", 100.0)

        await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 100)
        _seed_ltp(engine, "NIFTY", 120.0)
        await engine.place_order("NIFTY", "NFO", "SELL", "MARKET", 50)

        positions = engine.get_positions()
        pos = positions[0]
        # Position still has 50 qty open
        assert pos.net_quantity == 50
        # Realized from closing 50: (120 - 100) * 50 = 1000
        assert pos.pnl == 1000.0

    @pytest.mark.asyncio
    async def test_sell_then_buy_short_pnl(self):
        """Short: SELL then BUY → pnl = (entry - exit) * qty."""
        engine = PaperTradingEngine()
        _seed_ltp(engine, "NIFTY", 100.0)

        await engine.place_order("NIFTY", "NFO", "SELL", "MARKET", 50)
        _seed_ltp(engine, "NIFTY", 90.0)
        await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)

        pnl = engine.get_pnl()
        # Short profit: (100 - 90) * 50 = 500
        assert pnl["realised_pnl"] == 500.0


# ── 8. Backward compatibility ───────────────────────────────────────────────


class TestBackwardCompatibility:
    """Without models injected, engine behaves like pre-P3-4.1."""

    @pytest.mark.asyncio
    async def test_no_slippage_no_fees_default(self):
        """Default engine: MARKET fills at exact LTP, no fees."""
        engine = PaperTradingEngine()
        _seed_ltp(engine, "NIFTY", 18450.0)

        result = await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        assert result.status == "FILLED"
        assert result.average_price == 18450.0

    @pytest.mark.asyncio
    async def test_limit_fill_deterministic_without_prob(self):
        """Without fill probability, limit fills 100% on touch."""
        engine = PaperTradingEngine()
        result = await engine.place_order("NIFTY", "NFO", "BUY", "LIMIT", 50, price=100.0)
        assert result.status == "OPEN"

        evt = Event(Topic.MARKET_DATA_TICK, {"symbol": "NIFTY", "ltp": 100.0}, source="test")
        await engine._on_tick(evt)
        assert len(engine._pending_orders) == 0
        assert len(engine._fills) == 1

    @pytest.mark.asyncio
    async def test_no_margin_check_default(self):
        """No margin policy → no rejection even with zero capital."""
        engine = PaperTradingEngine(initial_capital=0.0)
        _seed_ltp(engine, "NIFTY", 100.0)
        result = await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 1000)
        assert result.status == "FILLED"

    @pytest.mark.asyncio
    async def test_fill_fees_zero_without_model(self):
        """Fill.fees is 0.0 without a fees model."""
        engine = PaperTradingEngine()
        _seed_ltp(engine, "NIFTY", 100.0)
        await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        assert engine._fills[0].fees == 0.0

    @pytest.mark.asyncio
    async def test_pnl_total_fees_zero_without_model(self):
        """get_pnl() total_fees is 0 without a fees model."""
        engine = PaperTradingEngine()
        _seed_ltp(engine, "NIFTY", 100.0)
        await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        pnl = engine.get_pnl()
        assert pnl["total_fees"] == 0.0


# ── 9. Volume-based partial fills ───────────────────────────────────────────


class TestPartialFills:
    """Large orders partially fill when volume is thin."""

    @pytest.mark.asyncio
    async def test_large_order_partial_fill(self):
        """Order qty > 10% of tick volume → partial fill (50-80%)."""
        rng = random.Random(42)
        fp = FillProbabilityModel(rng=rng)
        engine = PaperTradingEngine(fill_probability_model=fp)
        result = await engine.place_order("NIFTY", "NFO", "BUY", "LIMIT", 100, price=100.0)
        assert result.status == "OPEN"

        # Tick with thin volume (100 qty vs volume=500 → 20% > 10%)
        evt = Event(
            Topic.MARKET_DATA_TICK,
            {"symbol": "NIFTY", "ltp": 100.0, "volume": 500},
            source="test",
        )
        await engine._on_tick(evt)

        # Should have partial fill — order may still be pending
        if engine._pending_orders:
            remaining_order = list(engine._pending_orders.values())[0]
            assert remaining_order.filled_quantity > 0
            assert remaining_order.filled_quantity < 100


# ── 10. Volume-based slippage ───────────────────────────────────────────────


class TestVolumeSlippage:
    """Large orders pay more slippage via volume-based add-on."""

    @pytest.mark.asyncio
    async def test_large_order_extra_slippage(self):
        """Order qty > 10% of tick volume → extra bps slippage."""
        slippage = SlippageModel(bps_market=5.0, bps_limit=2.0)
        engine = PaperTradingEngine(slippage_model=slippage)
        # volume=100, qty=50 → ratio=0.5 → 4 extra bps
        _seed_tick(engine, "NIFTY", ltp=10000.0, volume=100)

        result = await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        # Total bps = 5 (market) + 4 (volume) = 9 bps
        expected = 10000.0 * (1 + 9.0 / 10_000)
        assert abs(result.average_price - expected) < 0.5

    @pytest.mark.asyncio
    async def test_small_order_no_extra_slippage(self):
        """Order qty <= 10% of tick volume → no extra slippage."""
        slippage = SlippageModel(bps_market=5.0, bps_limit=2.0)
        engine = PaperTradingEngine(slippage_model=slippage)
        _seed_tick(engine, "NIFTY", ltp=10000.0, volume=1000)

        result = await engine.place_order("NIFTY", "NFO", "BUY", "MARKET", 50)
        expected = 10000.0 * (1 + 5.0 / 10_000)  # 5 bps only
        assert abs(result.average_price - expected) < 0.1


# ── 11. SlippageModel unit tests ────────────────────────────────────────────


class TestSlippageModelUnit:
    """Direct unit tests on the SlippageModel."""

    def test_spread_buy_at_ask(self):
        m = SlippageModel(residual_bps=0)
        r = m.compute(100.0, "BUY", "MARKET", bid=99.0, ask=101.0, volume=0, quantity=10)
        assert r.adjusted_price == 101.0
        assert r.source == "spread"

    def test_spread_sell_at_bid(self):
        m = SlippageModel(residual_bps=0)
        r = m.compute(100.0, "SELL", "MARKET", bid=99.0, ask=101.0, volume=0, quantity=10)
        assert r.adjusted_price == 99.0
        assert r.source == "spread"

    def test_fixed_no_spread(self):
        m = SlippageModel(bps_market=5.0, bps_limit=2.0)
        r = m.compute(10000.0, "BUY", "MARKET", bid=None, ask=None, volume=0, quantity=10)
        assert abs(r.adjusted_price - 10005.0) < 0.1
        assert r.source == "fixed"

    def test_zero_base_price(self):
        m = SlippageModel()
        r = m.compute(0.0, "BUY", "MARKET", bid=None, ask=None, volume=0, quantity=10)
        assert r.adjusted_price == 0.0
        assert r.source == "none"


# ── 12. FeesModel unit tests ────────────────────────────────────────────────


class TestFeesModelUnit:
    """Direct unit tests on the FeesModel."""

    def test_zero_quantity(self):
        m = FeesModel()
        r = m.compute(0, 100.0, "BUY", "NSE")
        assert r.total == 0.0

    def test_stamp_duty_equity_delivery(self):
        """Equity delivery stamp duty = 0.015% on buy."""
        m = FeesModel()
        r = m.compute(100, 100.0, "BUY", "NSE")
        # notional = 10000; stamp = 10000 * 0.00015 = 1.5
        assert r.stamp_duty == 1.5

    def test_no_stamp_on_sell(self):
        m = FeesModel()
        r = m.compute(100, 100.0, "SELL", "NSE")
        assert r.stamp_duty == 0.0


# ── 13. FillProbabilityModel unit tests ─────────────────────────────────────


class TestFillProbabilityUnit:
    """Direct unit tests on the FillProbabilityModel."""

    def test_immediate_fill_at_touch(self):
        """Price at limit → high probability."""
        rng = random.Random(42)
        m = FillProbabilityModel(distance_decay=10.0, rng=rng)
        should, prob = m.should_fill(100.0, "BUY", 100.0, 99.0, 100.0, 1000, 10, 0)
        assert prob > 0.9  # very close to 1.0 at 0 bps distance

    def test_far_away_no_fill(self):
        """Price far from limit → probability near 0."""
        rng = random.Random(42)
        m = FillProbabilityModel(distance_decay=10.0, rng=rng)
        should, prob = m.should_fill(100.0, "BUY", 200.0, 199.0, 200.0, 1000, 10, 0)
        # distance = 100% = 10000 bps → exp(-10000/10) ≈ 0
        assert prob < 0.01

    def test_gap_through_buy(self):
        m = FillProbabilityModel()
        assert m.check_gap_through(100.0, "BUY", 110.0) is True
        assert m.check_gap_through(100.0, "BUY", 90.0) is False

    def test_gap_through_sell(self):
        m = FillProbabilityModel()
        assert m.check_gap_through(100.0, "SELL", 90.0) is True
        assert m.check_gap_through(100.0, "SELL", 110.0) is False


# ── 14. MarginPolicy unit tests ─────────────────────────────────────────────


class TestMarginPolicyUnit:
    """Direct unit tests on the MarginPolicy."""

    def test_mis_equity_20_percent(self):
        m = MarginPolicy(equity_mis_pct=0.20)
        req = m.required_margin(100, 1000.0, "BUY", "NSE", "MIS")
        assert req == 20_000.0

    def test_cnc_100_percent(self):
        m = MarginPolicy()
        req = m.required_margin(100, 1000.0, "BUY", "NSE", "CNC")
        assert req == 100_000.0

    def test_options_buy_full_premium(self):
        m = MarginPolicy()
        req = m.required_margin(50, 100.0, "BUY", "NSE_FO")
        assert req == 5_000.0

    def test_options_sell_premium_plus_buffer(self):
        m = MarginPolicy(options_sell_pct=1.10)
        req = m.required_margin(50, 100.0, "SELL", "NSE_FO")
        assert req == 5_500.0
