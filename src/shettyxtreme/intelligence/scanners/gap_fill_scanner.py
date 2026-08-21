"""GapFillScanner — detects price gaps > 1% (opportunity 9).

Subscribes to MARKET_DATA_BAR, maintains per-symbol bar history, and
emits SCANNER_FINDING when a gap > 1% is detected between consecutive bars.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from shettyxtreme.core.data_models import Bar
from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.intelligence.scanners.base_scanner import BaseScanner, ScannerType

logger = logging.getLogger(__name__)

_GAP_THRESHOLD = 1.0  # percent


class GapFillScanner(BaseScanner):
    """Detects price gaps > 1% between consecutive bars.

    Adopts the existing GapScanner bar logic with the spec threshold (>1%)
    and emits SCANNER_FINDING events instead of storing in _last_results.
    """

    scanner_type = ScannerType.GAP_FILL

    def __init__(self, event_bus: EventBus, lookback: int = 10, **params: Any) -> None:
        super().__init__(event_bus, **params)
        self.lookback = lookback
        self._bar_history: dict[str, list[Bar]] = defaultdict(list)

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._event_bus.subscribe(Topic.MARKET_DATA_BAR, self._on_bar)
        logger.info("GapFillScanner started (lookback=%d)", self.lookback)

    async def stop(self) -> None:
        self._running = False
        self._event_bus.unsubscribe(Topic.MARKET_DATA_BAR, self._on_bar)
        logger.info("GapFillScanner stopped")

    async def _on_bar(self, event: Event) -> None:
        bar = event.data
        if not isinstance(bar, Bar):
            return
        history = self._bar_history[bar.symbol]
        history.append(bar)
        if len(history) > self.lookback + 5:
            history.pop(0)
        if len(history) >= 2:
            await self._scan_gaps(bar.symbol, history)

    async def _scan_gaps(self, symbol: str, history: list[Bar]) -> None:
        prev_bar = history[-2]
        curr_bar = history[-1]
        if prev_bar.close == 0:
            return
        gap_pct = ((curr_bar.open - prev_bar.close) / prev_bar.close) * 100.0
        if abs(gap_pct) >= _GAP_THRESHOLD:
            direction = "gap_up" if gap_pct > 0 else "gap_down"
            if abs(gap_pct) >= 1.5:
                gap_type = "breakaway"
            elif abs(gap_pct) >= 1.0:
                gap_type = "common"
            else:
                gap_type = "common"
            await self._emit_finding(
                symbol=symbol,
                severity="HIGH" if abs(gap_pct) >= 1.5 else "MEDIUM",
                detail={
                    "gap_type": gap_type,
                    "gap_percent": round(abs(gap_pct), 2),
                    "direction": direction,
                    "open": curr_bar.open,
                    "prev_close": prev_bar.close,
                },
            )

    def scan_bars(self, symbol: str, bars: list[Bar]) -> list[dict[str, Any]]:
        """Standalone scan for testing (returns findings without emitting)."""
        if len(bars) < 2:
            return []
        prev_bar = bars[-2]
        curr_bar = bars[-1]
        if prev_bar.close == 0:
            return []
        gap_pct = ((curr_bar.open - prev_bar.close) / prev_bar.close) * 100.0
        if abs(gap_pct) >= _GAP_THRESHOLD:
            direction = "gap_up" if gap_pct > 0 else "gap_down"
            return [{
                "scanner_type": self.scanner_type.value,
                "symbol": symbol,
                "gap_type": "breakaway" if abs(gap_pct) >= 1.5 else "common",
                "gap_percent": round(abs(gap_pct), 2),
                "direction": direction,
                "open": curr_bar.open,
                "prev_close": prev_bar.close,
            }]
        return []

    @property
    def tracked_symbols(self) -> list[str]:
        return list(self._bar_history.keys())
