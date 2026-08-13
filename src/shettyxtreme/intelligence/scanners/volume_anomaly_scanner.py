"""VolumeAnomalyScanner — detects volume > 3× 20-day avg with price unchanged (opportunity 10).

Subscribes to MARKET_DATA_BAR, maintains per-symbol 20-bar volume history,
and emits SCANNER_FINDING when current volume exceeds 3× the rolling average
while |Δ close| < 0.5%.
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Any

from shettyxtreme.core.data_models import Bar
from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.intelligence.scanners.base_scanner import BaseScanner, ScannerType

logger = logging.getLogger(__name__)

_VOLUME_MULTIPLIER = 3.0
_PRICE_CHANGE_EPSILON = 0.5  # percent


class VolumeAnomalyScanner(BaseScanner):
    """Detects volume spikes with unchanged price (opportunity 10)."""

    scanner_type = ScannerType.VOLUME_ANOMALY

    def __init__(self, event_bus: EventBus, lookback: int = 20, **params: Any) -> None:
        super().__init__(event_bus, **params)
        self.lookback = lookback
        self._volume_history: dict[str, deque[int]] = defaultdict(
            lambda: deque(maxlen=lookback)
        )

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._event_bus.subscribe(Topic.MARKET_DATA_BAR, self._on_bar)
        logger.info("VolumeAnomalyScanner started (lookback=%d)", self.lookback)

    async def stop(self) -> None:
        self._running = False
        self._event_bus.unsubscribe(Topic.MARKET_DATA_BAR, self._on_bar)
        logger.info("VolumeAnomalyScanner stopped")

    async def _on_bar(self, event: Event) -> None:
        bar = event.data
        if not isinstance(bar, Bar):
            return
        history = self._volume_history[bar.symbol]
        if len(history) >= 2:
            avg_volume = sum(history) / len(history)
            if avg_volume > 0 and bar.volume > avg_volume * _VOLUME_MULTIPLIER:
                if bar.open > 0:
                    price_change_pct = abs(((bar.close - bar.open) / bar.open) * 100.0)
                    if price_change_pct < _PRICE_CHANGE_EPSILON:
                        await self._emit_finding(
                            symbol=bar.symbol,
                            severity="HIGH",
                            detail={
                                "volume": bar.volume,
                                "avg_volume": round(avg_volume),
                                "volume_ratio": round(bar.volume / avg_volume, 2),
                                "price_change_pct": round(price_change_pct, 2),
                                "close": bar.close,
                            },
                        )
        history.append(bar.volume)

    def scan_bar(self, symbol: str, bar: Bar, history: list[int]) -> list[dict[str, Any]]:
        """Standalone scan for testing."""
        if len(history) < 2:
            return []
        avg_volume = sum(history) / len(history)
        if avg_volume > 0 and bar.volume > avg_volume * _VOLUME_MULTIPLIER:
            if bar.open > 0:
                price_change_pct = abs(((bar.close - bar.open) / bar.open) * 100.0)
                if price_change_pct < _PRICE_CHANGE_EPSILON:
                    return [{
                        "scanner_type": self.scanner_type.value,
                        "symbol": symbol,
                        "volume": bar.volume,
                        "avg_volume": round(avg_volume),
                        "volume_ratio": round(bar.volume / avg_volume, 2),
                        "price_change_pct": round(price_change_pct, 2),
                    }]
        return []

    @property
    def tracked_symbols(self) -> list[str]:
        return list(self._volume_history.keys())
