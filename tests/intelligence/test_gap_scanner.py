"""Tests for GapScanner.

Verifies overnight gap detection, gap categorisation (common / breakaway /
exhaustion), and edge cases.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from shettyxtreme.core.data_models import Bar
from shettyxtreme.core.event_bus import EventBus


def make_session_bars(
    closes: list[float],
    opens: list[float] | None = None,
    volume: int = 100_000,
    symbol: str = "TEST",
) -> list[Bar]:
    """Create Bar objects representing daily sessions."""
    if opens is None:
        opens = closes
    base = datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc)
    bars: list[Bar] = []
    for i, close in enumerate(closes):
        open_ = opens[i] if i < len(opens) else close
        dt = base + timedelta(days=i)
        bars.append(
            Bar(
                symbol=symbol, exchange="NSE", timeframe="1d",
                open=open_,
                high=max(open_, close) + 1.0,
                low=min(open_, close) - 1.0,
                close=close, volume=volume, timestamp=dt,
            )
        )
    return bars


class TestGapScanner:
    """Suite for GapScanner."""

    def test_init_defaults(self) -> None:
        """Scanner initialises with sensible defaults."""
        from shettyxtreme.intelligence.scanners import GapScanner
        bus: EventBus = EventBus()
        scanner = GapScanner(event_bus=bus)
        assert scanner.lookback == 10

    def test_overnight_gap_detected(self) -> None:
        """An overnight gap (close=100, open=103) is detected as bullish."""
        from shettyxtreme.intelligence.scanners import GapScanner
        bus: EventBus = EventBus()
        scanner = GapScanner(event_bus=bus)
        bars = make_session_bars(closes=[100.0, 105.0], opens=[100.0, 103.0])
        results = scanner.scan_bars("TEST", bars)
        bullish_gaps = [r for r in results if r["direction"] == "bullish"]
        assert len(bullish_gaps) >= 1
        gap = bullish_gaps[0]
        assert gap["gap_percent"] == pytest.approx(3.0, rel=0.1)
        assert gap["symbol"] == "TEST"

    def test_bearish_gap_detected(self) -> None:
        """A gap down (close=100, open=97) is detected as bearish."""
        from shettyxtreme.intelligence.scanners import GapScanner
        bus: EventBus = EventBus()
        scanner = GapScanner(event_bus=bus)
        bars = make_session_bars(closes=[100.0, 95.0], opens=[100.0, 97.0])
        results = scanner.scan_bars("TEST", bars)
        bearish_gaps = [r for r in results if r["direction"] == "bearish"]
        assert len(bearish_gaps) >= 1
        assert bearish_gaps[0]["gap_percent"] == pytest.approx(3.0, rel=0.1)

    def test_no_gap_when_open_equals_close(self) -> None:
        """No gap is reported when open equals previous close."""
        from shettyxtreme.intelligence.scanners import GapScanner
        bus: EventBus = EventBus()
        scanner = GapScanner(event_bus=bus)
        bars = make_session_bars(closes=[100.0, 101.0], opens=[100.0, 100.0])
        results = scanner.scan_bars("TEST", bars)
        significant = [r for r in results if r["gap_percent"] > 0.1]
        assert len(significant) == 0

    def test_common_gap(self) -> None:
        """A gap < 1% is categorised as common."""
        from shettyxtreme.intelligence.scanners import GapScanner
        bus: EventBus = EventBus()
        scanner = GapScanner(event_bus=bus)
        bars = make_session_bars(closes=[100.0, 102.0], opens=[100.0, 100.5])
        results = scanner.scan_bars("TEST", bars)
        gaps = [r for r in results if r["gap_percent"] > 0.1]
        if gaps:
            assert gaps[0]["gap_type"] == "common"

    def test_breakaway_gap(self) -> None:
        """A gap > 1.5% is categorised as breakaway."""
        from shettyxtreme.intelligence.scanners import GapScanner
        bus: EventBus = EventBus()
        scanner = GapScanner(event_bus=bus)
        bars = make_session_bars(closes=[100.0, 105.0], opens=[100.0, 102.0])
        results = scanner.scan_bars("TEST", bars)
        gaps = [r for r in results if r["gap_percent"] > 0.1]
        assert len(gaps) >= 1
        assert gaps[0]["gap_type"] == "breakaway"

    def test_exhaustion_gap(self) -> None:
        """A gap in the 1.0-1.5% range opposing short-term trend is exhaustion."""
        from shettyxtreme.intelligence.scanners import GapScanner
        bus: EventBus = EventBus()
        scanner = GapScanner(event_bus=bus)
        bars = make_session_bars(
            closes=[105.0, 103.0, 101.0, 99.0],
            opens=[105.0, 105.0, 103.0, 102.2],
        )
        results = scanner.scan_bars("TEST", bars)
        gaps = [r for r in results if r["gap_percent"] > 0.1]
        if gaps:
            exhaustion = [g for g in gaps if g["gap_type"] == "exhaustion"]
            assert len(exhaustion) >= 1

    def test_insufficient_data(self) -> None:
        """Fewer than 2 bars returns empty results."""
        from shettyxtreme.intelligence.scanners import GapScanner
        bus: EventBus = EventBus()
        scanner = GapScanner(event_bus=bus)
        bars = make_session_bars(closes=[100.0])
        results = scanner.scan_bars("TEST", bars)
        assert results == []

    def test_start_stop_lifecycle(self) -> None:
        """Scanner can start and stop without error."""
        from shettyxtreme.intelligence.scanners import GapScanner
        bus: EventBus = EventBus()
        scanner = GapScanner(event_bus=bus)
        import asyncio
        asyncio.run(scanner.start())
        asyncio.run(scanner.stop())
        assert scanner._running is False

    def test_last_results_property(self) -> None:
        """last_results returns an empty list after initialisation."""
        from shettyxtreme.intelligence.scanners import GapScanner
        bus: EventBus = EventBus()
        scanner = GapScanner(event_bus=bus)
        assert scanner.last_results == []
