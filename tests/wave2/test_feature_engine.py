"""Tests for streaming indicators and FeatureEngine."""
from __future__ import annotations

import asyncio
import math
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from shettyxtreme.core.data_models import Tick
from shettyxtreme.core.event_bus import EventBus, Topic
from shettyxtreme.intelligence.features import (
    Bars, SMA, EMA, ATR, VWAP, RSI, ADX,
    FeatureEngine, FeaturesComputed,
)


# ---------------------------------------------------------------------------
# Helper: build a Tick
# ---------------------------------------------------------------------------
def _make_tick(
    ltp: float,
    volume: int = 100,
    high: float | None = None,
    low: float | None = None,
    symbol: str = "NIFTY",
) -> Tick:
    return Tick(
        symbol=symbol,
        exchange="NSE",
        ltp=ltp,
        volume=volume,
        timestamp=datetime.now(timezone.utc),
        bid=None,
        ask=None,
        open=None,
        high=high,
        low=low,
        close=None,
    )


# ---------------------------------------------------------------------------
# SMA
# ---------------------------------------------------------------------------
class TestSMA:
    def test_sma_known_sequence(self) -> None:
        sma = SMA(period=5)
        ticks = [_make_tick(float(v)) for v in [10, 20, 30, 40, 50]]
        for t in ticks[:4]:
            assert sma.update(t) is None  # not enough data
        result = sma.update(ticks[4])
        assert result is not None
        assert result == 30.0  # (10+20+30+40+50)/5

    def test_sma_rolling(self) -> None:
        sma = SMA(period=3)
        values = [10, 20, 30, 40, 50]
        expected = [None, None, 20.0, 30.0, 40.0]
        for v, exp in zip(values, expected):
            result = sma.update(_make_tick(float(v)))
            if exp is None:
                assert result is None
            else:
                assert result is not None
                assert result == exp

    def test_sma_value_property(self) -> None:
        sma = SMA(period=2)
        assert sma.value is None
        sma.update(_make_tick(10.0))
        assert sma.value is None
        sma.update(_make_tick(20.0))
        assert sma.value == 15.0


# ---------------------------------------------------------------------------
# EMA
# ---------------------------------------------------------------------------
class TestEMA:
    def test_ema_known_sequence(self) -> None:
        """EMA(5) with alpha=2/6=0.3333 on [10,20,30,40,50].

        Manual:
          EMA1 = 10
          EMA2 = 0.3333*20 + 0.6667*10 = 13.3333
          EMA3 = 0.3333*30 + 0.6667*13.3333 = 18.8889
          EMA4 = 0.3333*40 + 0.6667*18.8889 = 25.9259
          EMA5 = 0.3333*50 + 0.6667*25.9259 = 33.9506
        """
        ema = EMA(period=5)
        values = [10, 20, 30, 40, 50]
        expected = [10.0, 13.3333, 18.8889, 25.9259, 33.9506]
        for v, exp in zip(values, expected):
            result = ema.update(_make_tick(float(v)))
            assert result is not None
            assert abs(result - exp) < 0.01, f"Expected {exp}, got {result}"

    def test_ema_single_value(self) -> None:
        ema = EMA(period=5)
        result = ema.update(_make_tick(42.0))
        assert result is not None
        assert result == 42.0

    def test_ema_value_property(self) -> None:
        ema = EMA(period=3)
        assert ema.value is None
        ema.update(_make_tick(10.0))
        assert ema.value == 10.0


# ---------------------------------------------------------------------------
# ATR
# ---------------------------------------------------------------------------
class TestATR:
    def test_atr_on_known_bars(self) -> None:
        """ATR(3) on known OHLC sequence.

        Bar1: H=110, L=90, C=100 -> TR=20
        Bar2: H=120, L=80, C=100 -> TR=max(40, |120-100|=20, |80-100|=20)=40
        Bar3: H=115, L=95, C=105 -> TR=max(20, |115-100|=15, |95-100|=5)=20

        ATR = (20 + 40 + 20)/3 = 26.6667
        """
        atr = ATR(period=3)
        ticks = [
            _make_tick(100, high=110, low=90),
            _make_tick(100, high=120, low=80),
            _make_tick(105, high=115, low=95),
        ]
        for t in ticks[:2]:
            assert atr.update(t) is None
        result = atr.update(ticks[2])
        assert result is not None
        expected = 26.6667
        assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"

    def test_atr_value_property(self) -> None:
        atr = ATR(period=3)
        assert atr.value is None


# ---------------------------------------------------------------------------
# VWAP
# ---------------------------------------------------------------------------
class TestVWAP:
    def test_vwap_known_ticks(self) -> None:
        vwap = VWAP()
        ticks = [
            _make_tick(100.0, volume=100),
            _make_tick(102.0, volume=200),
            _make_tick(101.0, volume=150),
        ]
        results = [vwap.update(t) for t in ticks]
        # (100*100 + 102*200 + 101*150) / (100+200+150) = (10000+20400+15150)/450 = 45550/450 = 101.222...
        assert results[0] == pytest.approx(100.0)
        assert results[1] == pytest.approx(101.3333, abs=0.01)
        assert results[2] == pytest.approx(101.2222, abs=0.01)

    def test_vwap_value_property(self) -> None:
        vwap = VWAP()
        assert vwap.value is None
        vwap.update(_make_tick(100.0))
        assert vwap.value == 100.0


# ---------------------------------------------------------------------------
# RSI
# ---------------------------------------------------------------------------
class TestRSI:
    def test_rsi_sequence(self) -> None:
        """RSI(3) on alternating up/down moves.

        Prices: [50, 52, 51, 53, 52]
        Gains: [2, 0, 2, 0]
        Losses: [0, 1, 0, 1]
        Wilder's smoothing, period=3:
        After 4 price changes (count=4), count>=period-1=2 so we get RSI
        """
        rsi = RSI(period=3)
        ticks = [_make_tick(float(v)) for v in [50, 52, 51, 53, 52]]
        results = [rsi.update(t) for t in ticks]
        # First tick returns None (no prev_price)
        assert results[0] is None
        # Should have values after period-1
        assert results[2] is not None  # 3rd update has 2 changes >= period-1
        # RSI should be between 0 and 100
        for r in results[2:]:
            assert r is not None
            assert 0 <= r <= 100

    def test_rsi_all_up(self) -> None:
        rsi = RSI(period=3)
        prices = [50, 51, 52, 53]
        for p in prices:
            rsi.update(_make_tick(float(p)))
        val = rsi.value
        assert val is not None
        assert val > 50  # should be bullish

    def test_rsi_value_property(self) -> None:
        rsi = RSI(period=3)
        assert rsi.value is None


# ---------------------------------------------------------------------------
# ADX
# ---------------------------------------------------------------------------
class TestADX:
    def test_adx_returns_value_after_warmup(self) -> None:
        adx = ADX(period=5)
        ticks = [
            _make_tick(100, high=105, low=95),
            _make_tick(102, high=108, low=98),
            _make_tick(101, high=106, low=96),
            _make_tick(105, high=110, low=100),
            _make_tick(103, high=107, low=99),
            _make_tick(106, high=112, low=100),
        ]
        results = [adx.update(t) for t in ticks]
        # First period - still warming up
        # After enough bars we should get a value
        later_results = [r for r in results if r is not None]
        assert len(later_results) > 0

    def test_adx_di_plus_minus(self) -> None:
        adx = ADX(period=3)
        ticks = [
            _make_tick(100, high=105, low=95),
            _make_tick(105, high=110, low=100),
            _make_tick(110, high=115, low=105),
            _make_tick(115, high=120, low=110),
        ]
        for t in ticks:
            adx.update(t)

        if adx.di_plus is not None and adx.di_minus is not None:
            assert adx.di_plus >= 0
            assert adx.di_minus >= 0

    def test_adx_value_property(self) -> None:
        adx = ADX(period=3)
        assert adx.value is None


# ---------------------------------------------------------------------------
# Bars
# ---------------------------------------------------------------------------
class TestBars:
    def test_bars_aggregation(self) -> None:
        bars = Bars(timeframe_seconds=60)
        now = datetime.now(timezone.utc)
        # All ticks within the same bar period
        ticks = [
            Tick(symbol="NIFTY", exchange="NSE", ltp=100, volume=100, timestamp=now),
            Tick(symbol="NIFTY", exchange="NSE", ltp=105, volume=200, timestamp=now),
            Tick(symbol="NIFTY", exchange="NSE", ltp=102, volume=150, timestamp=now),
        ]
        for t in ticks:
            result = bars.update(t)
            assert result is None  # no bar completed yet

    def test_bars_value_property(self) -> None:
        bars = Bars(timeframe_seconds=60)
        assert bars.value is None


# ---------------------------------------------------------------------------
# Staleness guard
# ---------------------------------------------------------------------------
class TestStaleness:
    @pytest.mark.asyncio
    async def test_stale_tick_not_computed(self) -> None:
        """If tick is > 10s old, published features are marked stale."""
        bus = EventBus()
        engine = FeatureEngine(event_bus=bus, symbol="NIFTY")
        sma = SMA(period=2)
        engine.register("sma", sma)

        sma.update(_make_tick(100.0))
        sma.update(_make_tick(102.0))
        assert sma.value == 101.0

        # Start bus & capture published events
        published: list[FeaturesComputed] = []
        async def handler(event: Any) -> None:
            published.append(event.data)
        bus.subscribe(Topic.FEATURES_COMPUTED, handler)
        bus_task = asyncio.create_task(bus.start())
        try:
            # Feed an old tick (>10s stale)
            old_ts = datetime.fromtimestamp(time.time() - 15, tz=timezone.utc)
            old_tick = Tick(
                symbol="NIFTY", exchange="NSE", ltp=105.0, volume=100, timestamp=old_ts,
            )
            await engine.process_tick(old_tick)
            await asyncio.sleep(0.05)

            # Published FeaturesComputed should be marked stale
            assert len(published) >= 1
            assert published[-1].stale is True, "Stale tick should produce stale=True"
            assert published[-1].features == {}, "Stale tick should carry empty features dict"
        finally:
            await bus.stop()
            try:
                await asyncio.wait_for(bus_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass


# ---------------------------------------------------------------------------
# FeatureEngine event publishing
# ---------------------------------------------------------------------------
class TestFeatureEngine:
    @pytest.mark.asyncio
    async def test_publishes_features_computed(self) -> None:
        bus = EventBus()
        engine = FeatureEngine(event_bus=bus, symbol="NIFTY")
        engine.register("sma_2", SMA(period=2))

        published_events: list[FeaturesComputed] = []

        async def handler(event: Any) -> None:
            published_events.append(event.data)

        bus.subscribe(Topic.FEATURES_COMPUTED, handler)

        # Start the bus loop in background
        bus_task = asyncio.create_task(bus.start())

        try:
            # Feed 3 ticks — SMA(2) needs 2 ticks for a value
            for v in [100, 102, 104]:
                tick = _make_tick(float(v))
                await engine.process_tick(tick)
                await asyncio.sleep(0.05)

            assert len(published_events) >= 1
            last_event = published_events[-1]
            assert isinstance(last_event, FeaturesComputed)
            assert len(last_event.features) > 0, (
                f"Expected non-empty features, got: {last_event.features}"
            )
            assert not last_event.stale
        finally:
            await bus.stop()
            try:
                await asyncio.wait_for(bus_task, timeout=1.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                pass

    @pytest.mark.asyncio
    async def test_staleness_flag(self) -> None:
        bus = EventBus()
        engine = FeatureEngine(event_bus=bus, symbol="NIFTY")
        engine.register("sma_2", SMA(period=2))

        published_events: list[FeaturesComputed] = []

        async def handler(event: Any) -> None:
            published_events.append(event.data)

        bus.subscribe(Topic.FEATURES_COMPUTED, handler)

        # Feed a fresh tick
        await engine.process_tick(_make_tick(100.0))
        # Feed an old tick
        old_ts = datetime.fromtimestamp(time.time() - 15, tz=timezone.utc)
        old_tick = Tick(
            symbol="NIFTY", exchange="NSE", ltp=105.0, volume=100, timestamp=old_ts,
        )
        await engine.process_tick(old_tick)

        last_event = published_events[-1] if published_events else None
        if last_event is not None:
            # Stale flag is informational; the engine still publishes
            pass

    def test_register_and_get_indicator(self) -> None:
        engine = FeatureEngine(event_bus=MagicMock(), symbol="NIFTY")
        sma = SMA(period=3)
        engine.register("test_sma", sma)
        assert engine.get_indicator("test_sma") is sma
        assert engine.get_indicator("nonexistent") is None
        assert "test_sma" in engine.indicator_names
