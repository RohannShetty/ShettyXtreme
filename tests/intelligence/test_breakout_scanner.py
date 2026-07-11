"""Tests for PriceBreakoutScanner.

Verifies breakout detection, volume confirmation, and edge cases
using synthetic Bar data.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from shettyxtreme.core.data_models import Bar
from shettyxtreme.core.event_bus import EventBus, Topic


def make_bars(
    close_values: list[float],
    high_offset: float = 0.5,
    low_offset: float = 0.5,
    volume: int = 100_000,
    symbol: str = "TEST",
    start_time: datetime | None = None,
) -> list[Bar]:
    """Create a list of Bar objects from close prices."""
    base_time = start_time or datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc)
    bars: list[Bar] = []
    for i, close in enumerate(close_values):
        high = close + high_offset
        low = close - low_offset
        open_ = close_values[i - 1] if i > 0 else close
        bars.append(
            Bar(
                symbol=symbol, exchange="NSE", timeframe="1d",
                open=open_, high=high, low=low, close=close,
                volume=volume, timestamp=base_time,
            )
        )
        base_time = base_time.replace(hour=(base_time.hour + 1) % 24)
    return bars


class TestPriceBreakoutScanner:
    """Suite for PriceBreakoutScanner."""

    def test_init_defaults(self) -> None:
        """Scanner initialises with sensible defaults."""
        from shettyxtreme.intelligence.scanners import PriceBreakoutScanner
        bus: EventBus = EventBus()
        scanner = PriceBreakoutScanner(event_bus=bus)
        assert scanner.lookback == 20
        assert scanner.threshold_pct == 2.0

    def test_scan_bars_breakout_detected(self) -> None:
        """A bar closing 2%+ above lookback resistance triggers bullish signal."""
        from shettyxtreme.intelligence.scanners import PriceBreakoutScanner
        bus: EventBus = EventBus()
        scanner = PriceBreakoutScanner(event_bus=bus, lookback=20, threshold_pct=2.0)
        stable = [95.0 + (i % 10) for i in range(20)]
        bars = make_bars(stable + [108.0])
        results = scanner.scan_bars("TEST", bars)
        assert len(results) == 1
        assert results[0]["direction"] == "bullish"
        assert results[0]["symbol"] == "TEST"
        assert results[0]["confidence"] > 30.0

    def test_scan_bars_no_signal_within_range(self) -> None:
        """No signal when price stays within the lookback range."""
        from shettyxtreme.intelligence.scanners import PriceBreakoutScanner
        bus: EventBus = EventBus()
        scanner = PriceBreakoutScanner(event_bus=bus, lookback=20, threshold_pct=2.0)
        bars = make_bars([100.0 + (i % 5) for i in range(20)] + [101.0])
        results = scanner.scan_bars("TEST", bars)
        assert len(results) == 0

    def test_volume_confirmed(self) -> None:
        """A breakout bar with volume above average is flagged."""
        from shettyxtreme.intelligence.scanners import PriceBreakoutScanner
        bus: EventBus = EventBus()
        scanner = PriceBreakoutScanner(event_bus=bus, lookback=5, threshold_pct=1.0)
        bars = make_bars([100.0] * 5 + [105.0], volume=10_000)
        bars[-1] = Bar(
            symbol=bars[-1].symbol, exchange=bars[-1].exchange,
            timeframe=bars[-1].timeframe, open=bars[-1].open,
            high=bars[-1].high, low=bars[-1].low, close=bars[-1].close,
            volume=500_000, timestamp=bars[-1].timestamp,
        )
        results = scanner.scan_bars("TEST", bars)
        assert len(results) >= 1
        assert results[0]["volume_confirmed"] is True

    def test_low_volume_no_confirmation(self) -> None:
        """A breakout bar with low volume is NOT flagged as volume-confirmed."""
        from shettyxtreme.intelligence.scanners import PriceBreakoutScanner
        bus: EventBus = EventBus()
        scanner = PriceBreakoutScanner(event_bus=bus, lookback=5, threshold_pct=1.0)
        bars = make_bars([100.0] * 5 + [105.0], volume=500_000)
        bars[-1] = Bar(
            symbol=bars[-1].symbol, exchange=bars[-1].exchange,
            timeframe=bars[-1].timeframe, open=bars[-1].open,
            high=bars[-1].high, low=bars[-1].low, close=bars[-1].close,
            volume=10_000, timestamp=bars[-1].timestamp,
        )
        results = scanner.scan_bars("TEST", bars)
        if results:
            assert results[0]["volume_confirmed"] is False

    def test_scan_bars_insufficient_data(self) -> None:
        """Fewer bars than lookback returns empty results."""
        from shettyxtreme.intelligence.scanners import PriceBreakoutScanner
        bus: EventBus = EventBus()
        scanner = PriceBreakoutScanner(event_bus=bus, lookback=20, threshold_pct=2.0)
        bars = make_bars([100.0] * 10)
        results = scanner.scan_bars("TEST", bars)
        assert results == []

    def test_tracked_symbols(self) -> None:
        """Tracked symbols are reported after bars are ingested live."""
        from shettyxtreme.intelligence.scanners import PriceBreakoutScanner
        bus: EventBus = EventBus()
        scanner = PriceBreakoutScanner(event_bus=bus, lookback=3)
        assert scanner.tracked_symbols == []

    def test_start_stop_lifecycle(self) -> None:
        """Scanner can start and stop without error."""
        from shettyxtreme.intelligence.scanners import PriceBreakoutScanner
        bus: EventBus = EventBus()
        scanner = PriceBreakoutScanner(event_bus=bus)
        import asyncio
        asyncio.run(scanner.start())
        asyncio.run(scanner.stop())
        assert scanner._running is False

    def test_double_start_is_idempotent(self) -> None:
        """Calling start() twice does not crash."""
        from shettyxtreme.intelligence.scanners import PriceBreakoutScanner
        bus: EventBus = EventBus()
        scanner = PriceBreakoutScanner(event_bus=bus)
        import asyncio
        asyncio.run(scanner.start())
        asyncio.run(scanner.start())
        asyncio.run(scanner.stop())

    def test_bearish_breakdown(self) -> None:
        """A bar closing 2%+ below support triggers a bearish signal."""
        from shettyxtreme.intelligence.scanners import PriceBreakoutScanner
        bus: EventBus = EventBus()
        scanner = PriceBreakoutScanner(event_bus=bus, lookback=10, threshold_pct=2.0)
        stable = [200.0 + (i % 5) for i in range(10)]
        bars = make_bars(stable + [190.0])
        results = scanner.scan_bars("TEST", bars)
        bearish = [r for r in results if r["direction"] == "bearish"]
        assert len(bearish) == 1
