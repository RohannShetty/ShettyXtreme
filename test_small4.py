"""Test module."""

from __future__ import annotations
import logging
from typing import Any
from shettyxtreme.core.data_models import Bar
from shettyxtreme.core.event_bus import Event, EventBus, Topic

logger = logging.getLogger(__name__)


class PriceBreakoutScanner:
    """Scans for price breakouts."""

    def __init__(self, event_bus: EventBus, lookback: int = 20, threshold_pct: float = 2.0) -> None:
        self._event_bus = event_bus
        self.lookback = lookback
        self.threshold_pct = threshold_pct
        self._bar_history: dict[str, list[Bar]] = {}
        self._last_results: list[dict[str, Any]] = []
        self._running = False

    def _scan_symbol(self, symbol: str, history: list[Bar]) -> list[dict[str, Any]]:
        """Run breakout detection."""
        current_bar = history[-1]
        window = history[:-1]
        if len(window) < self.lookback:
            return []
        resistance = max(b.high for b in window)
        support = min(b.low for b in window)
        results: list[dict[str, Any]] = []
        now = datetime.now(timezone.utc)

        if resistance > 0:
            breakout_pct = ((current_bar.close - resistance) / resistance) * 100.0
            if breakout_pct >= self.threshold_pct and current_bar.close > resistance:
                results.append({
                    "symbol": symbol,
                    "direction": "bullish",
                    "breakout_price": current_bar.close,
                    "level": resistance,
                    "confidence": 50.0,
                    "timestamp": now,
                    "volume_confirmed": False,
                })
        return results
