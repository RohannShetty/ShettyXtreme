"""PriceBreakoutScanner — detects price breaking above resistance or below support levels."""

from __future__ import annotations
import logging
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any
from shettyxtreme.core.data_models import Bar
from shettyxtreme.core.event_bus import Event, EventBus, Topic

logger = logging.getLogger(__name__)


class PriceBreakoutScanner:
    """Scans for price breakouts above resistance or below support levels.

    Configurable lookback period and breakout threshold percentage.
    Subscribes to MARKET_DATA_BAR to receive live bar data.

    Attributes:
        lookback: Number of bars used for resistance/support calculation (default 20).
        threshold_pct: Minimum breakout percentage required (default 2.0).
    """

    def __init__(self, event_bus: EventBus, lookback: int = 20, threshold_pct: float = 2.0) -> None:
        """Initialise the scanner.

        Args:
            event_bus: Shared EventBus instance for subscribing to bar events.
            lookback: Rolling window size for high/low/volume computation.
            threshold_pct: Minimum percent change from the level to qualify as breakout.
        """
        self._event_bus = event_bus
        self.lookback = lookback
        self.threshold_pct = threshold_pct
        self._bar_history: dict[str, list[Bar]] = defaultdict(list)
        self._last_results: list[dict[str, Any]] = []
        self._running = False

    async def start(self) -> None:
        """Subscribe to MARKET_DATA_BAR events and begin scanning."""
        if self._running:
            logger.warning("PriceBreakoutScanner already running")
            return
        self._running = True
        self._event_bus.subscribe(Topic.MARKET_DATA_BAR, self._on_bar)
        logger.info("PriceBreakoutScanner started (lookback=%d, threshold=%.1f%%)", self.lookback, self.threshold_pct)

    async def stop(self) -> None:
        """Unsubscribe from bar events."""
        self._running = False
        self._event_bus.unsubscribe(Topic.MARKET_DATA_BAR, self._on_bar)
        logger.info("PriceBreakoutScanner stopped")

    async def _on_bar(self, event: Event) -> None:
        """Handle an incoming Bar event, update history, run scan."""
        bar = event.data
        if not isinstance(bar, Bar):
            return
        history = self._bar_history[bar.symbol]
        history.append(bar)
        if len(history) > self.lookback + 1:
            history.pop(0)
        if len(history) >= self.lookback + 1:
            results = self._scan_symbol(bar.symbol, history)
            if results:
                self._last_results = results
                logger.debug("Breakout scan for %s: %d result(s)", bar.symbol, len(results))

    def _scan_symbol(self, symbol: str, history: list[Bar]) -> list[dict[str, Any]]:
        """Run breakout detection on a symbol bar history.

        The lookback window excludes the current (latest) bar, which is
        the bar being evaluated for a breakout.
        """
        current_bar = history[-1]
        window = history[:-1]
        if len(window) < self.lookback:
            return []
        resistance = max(b.high for b in window)
        support = min(b.low for b in window)
        avg_volume = int(mean(b.volume for b in window)) if window else 0
        results: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        if resistance > 0:
            breakout_pct = ((current_bar.close - resistance) / resistance) * 100.0
            if breakout_pct >= self.threshold_pct and current_bar.close > resistance:
                confidence = self._compute_confidence(breakout_pct, current_bar.volume, avg_volume, "bullish")
                results.append({
                    "symbol": symbol,
                    "direction": "bullish",
                    "breakout_price": current_bar.close,
                    "level": resistance,
                    "confidence": confidence,
                    "timestamp": now,
                    "volume_confirmed": current_bar.volume > avg_volume if avg_volume > 0 else False,
                })

        if support > 0:
            breakdown_pct = ((support - current_bar.close) / support) * 100.0
            if breakdown_pct >= self.threshold_pct and current_bar.close < support:
                confidence = self._compute_confidence(breakdown_pct, current_bar.volume, avg_volume, "bearish")
                results.append({
                    "symbol": symbol,
                    "direction": "bearish",
                    "breakout_price": current_bar.close,
                    "level": support,
                    "confidence": confidence,
                    "timestamp": now,
                    "volume_confirmed": current_bar.volume > avg_volume if avg_volume > 0 else False,
                })
        return results

    def _compute_confidence(self, breakout_pct: float, volume: int, avg_volume: int, direction: str) -> float:
        """Compute a confidence score from 0-100 for a breakout signal."""
        magnitude_factor = min(breakout_pct / (self.threshold_pct * 3), 1.0)
        score = magnitude_factor * 60.0
        if avg_volume > 0 and volume > avg_volume:
            vol_ratio = min(volume / avg_volume, 3.0)
            score += (vol_ratio / 3.0) * 40.0
        return round(min(score, 100.0), 1)

    def scan_bars(self, symbol: str, bars: list[Bar]) -> list[dict[str, Any]]:
        """Standalone scan against an arbitrary bar list (useful for testing)."""
        if len(bars) < self.lookback + 1:
            return []
        return self._scan_symbol(symbol, bars)

    @property
    def last_results(self) -> list[dict[str, Any]]:
        """Return the most recent scan results."""
        return list(self._last_results)

    @property
    def tracked_symbols(self) -> list[str]:
        """Return symbols currently tracked in bar history."""
        return list(self._bar_history.keys())
