
"""GapScanner — detects overnight and intraday price gaps.

Monitors MARKET_DATA_BAR events and identifies gaps between consecutive
bars. Categorises gaps into common (<1%), breakaway (>1.5%), and
exhaustion (gap against prevailing trend) types.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from shettyxtreme.core.data_models import Bar
from shettyxtreme.core.event_bus import Event, EventBus, Topic

logger = logging.getLogger(__name__)

_COMMON_GAP_THRESHOLD = 1.0
_BREAKAWAY_GAP_THRESHOLD = 1.5


class GapScanner:
    """Detects price gaps between consecutive bars and categorises them.

    Two gap types:
      - overnight: gap between yesterday close and today open.
      - intraday:  gap between the previous bar close and current bar open.

    Subscribes to MARKET_DATA_BAR to receive live bar data.
    """

    def __init__(
        self,
        event_bus: EventBus,
        lookback: int = 10,
    ) -> None:
        """Initialise the scanner."""
        self._event_bus = event_bus
        self.lookback = lookback
        self._bar_history: dict[str, list[Bar]] = defaultdict(list)
        self._last_results: list[dict[str, Any]] = []
        self._running = False

    async def start(self) -> None:
        """Subscribe to MARKET_DATA_BAR events and begin scanning."""
        if self._running:
            logger.warning("GapScanner already running")
            return
        self._running = True
        self._event_bus.subscribe(Topic.MARKET_DATA_BAR, self._on_bar)
        logger.info("GapScanner started (lookback=%d)", self.lookback)

    async def stop(self) -> None:
        """Unsubscribe from bar events."""
        self._running = False
        self._event_bus.unsubscribe(Topic.MARKET_DATA_BAR, self._on_bar)
        logger.info("GapScanner stopped")

    async def _on_bar(self, event: Event) -> None:
        """Handle an incoming Bar event, check for gaps."""
        bar = event.data
        if not isinstance(bar, Bar):
            return

        history = self._bar_history[bar.symbol]
        history.append(bar)
        if len(history) > self.lookback + 5:
            history.pop(0)

        if len(history) >= 2:
            results = self._scan_gaps(bar.symbol, history)
            if results:
                self._last_results = results
                logger.debug("Gap scan for %s: %d result(s)", bar.symbol, len(results))

    def _scan_gaps(
        self, symbol: str, history: list[Bar]
    ) -> list[dict[str, Any]]:
        """Detect gaps between consecutive bars."""
        results: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        if len(history) < 2:
            return results

        prev_bar = history[-2]
        curr_bar = history[-1]

        # Overnight gap (session transition)
        if prev_bar.timestamp.date() != curr_bar.timestamp.date():
            gap_pct = self._compute_gap_percent(prev_bar.close, curr_bar.open)
            if abs(gap_pct) > 0.01:
                direction = "bullish" if gap_pct > 0 else "bearish"
                gap_type = self._categorise_gap(gap_pct, history, direction)
                results.append({
                    "symbol": symbol,
                    "gap_type": gap_type,
                    "gap_percent": round(abs(gap_pct), 2),
                    "direction": direction,
                    "timestamp": now,
                    "open": curr_bar.open,
                    "prev_close": prev_bar.close,
                })
        else:
            # Intraday gap (only when same session)
            gap_pct = self._compute_gap_percent(prev_bar.close, curr_bar.open)
            if abs(gap_pct) > 0.01:
                direction = "bullish" if gap_pct > 0 else "bearish"
                gap_type = self._categorise_gap(gap_pct, history, direction)
                results.append({
                    "symbol": symbol,
                    "gap_type": gap_type,
                    "gap_percent": round(abs(gap_pct), 2),
                    "direction": direction,
                    "timestamp": now,
                    "open": curr_bar.open,
                    "prev_close": prev_bar.close,
                })

        return results

    def _compute_gap_percent(self, prev_close: float, curr_open: float) -> float:
        """Compute the percentage gap between two prices."""
        if prev_close == 0:
            return 0.0
        return ((curr_open - prev_close) / prev_close) * 100.0

    def _categorise_gap(
        self,
        gap_pct: float,
        history: list[Bar],
        direction: str,
    ) -> str:
        """Categorise a gap into common, breakaway, or exhaustion."""
        abs_gap = abs(gap_pct)

        if abs_gap >= _BREAKAWAY_GAP_THRESHOLD:
            return "breakaway"

        if abs_gap < _COMMON_GAP_THRESHOLD:
            return "common"

        # 1.0-1.5% range: check if gap opposes short-term trend (exhaustion)
        if len(history) >= 3:
            trend_window = history[-(min(self.lookback, len(history) - 1)):-1]
            if trend_window:
                trend_change = trend_window[-1].close - trend_window[0].close
                trend_direction = "bullish" if trend_change >= 0 else "bearish"
                if trend_direction != direction:
                    return "exhaustion"

        return "breakaway"

    def scan_bars(self, symbol: str, bars: list[Bar]) -> list[dict[str, Any]]:
        """Standalone scan against an arbitrary bar list (useful for testing)."""
        if len(bars) < 2:
            return []
        return self._scan_gaps(symbol, bars)

    @property
    def last_results(self) -> list[dict[str, Any]]:
        """Return the most recent scan results."""
        return list(self._last_results)

    @property
    def tracked_symbols(self) -> list[str]:
        """Return symbols currently tracked in bar history."""
        return list(self._bar_history.keys())
