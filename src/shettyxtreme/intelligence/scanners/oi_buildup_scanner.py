"""OIBuildupScanner — detects OI change > 20% (opportunity 11).

Two paths:
  - Per-contract: OITracker.update_from_chain with 20% threshold
  - Bar-level: record_symbol_oi for symbols without chain feeds
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from shettyxtreme.core.data_models import Bar
from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.intelligence.scanners.base_scanner import BaseScanner, ScannerType
from shettyxtreme.options.oi_tracker import OITracker

logger = logging.getLogger(__name__)

_OI_CHANGE_THRESHOLD = 20.0  # percent


class OIBuildupScanner(BaseScanner):
    """Detects unusual OI build-up or decline > 20% (opportunity 11)."""

    scanner_type = ScannerType.OI_BUILDUP

    def __init__(
        self,
        event_bus: EventBus,
        oi_tracker: OITracker | None = None,
        threshold: float = _OI_CHANGE_THRESHOLD,
        **params: Any,
    ) -> None:
        super().__init__(event_bus, **params)
        self._oi_tracker = oi_tracker or OITracker()
        self._threshold = threshold
        self._prev_symbol_oi: dict[str, int] = {}

    async def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._event_bus.subscribe(Topic.MARKET_DATA_BAR, self._on_bar)
        logger.info("OIBuildupScanner started (threshold=%.1f%%)", self._threshold)

    async def stop(self) -> None:
        self._running = False
        self._event_bus.unsubscribe(Topic.MARKET_DATA_BAR, self._on_bar)
        logger.info("OIBuildupScanner stopped")

    async def _on_bar(self, event: Event) -> None:
        bar = event.data
        if not isinstance(bar, Bar):
            return
        if bar.oi is None or bar.oi <= 0:
            return
        prev_oi = self._prev_symbol_oi.get(bar.symbol)
        self._prev_symbol_oi[bar.symbol] = bar.oi
        self._oi_tracker.record_symbol_oi(bar.symbol, bar.oi)
        if prev_oi is not None and prev_oi > 0:
            change_pct = ((bar.oi - prev_oi) / prev_oi) * 100.0
            if abs(change_pct) >= self._threshold:
                await self._emit_finding(
                    symbol=bar.symbol,
                    severity="HIGH" if abs(change_pct) >= 50 else "MEDIUM",
                    detail={
                        "oi_current": bar.oi,
                        "oi_previous": prev_oi,
                        "oi_change_pct": round(change_pct, 2),
                        "close": bar.close,
                        "path": "bar_level",
                    },
                )

    def scan_chain_alerts(self, symbol: str, expiry: str, contracts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Scan chain data for OI buildup (per-contract path).

        Returns findings as dicts (does not emit events — for the poller to emit).
        """
        alerts = self._oi_tracker.update_from_chain(symbol, expiry, contracts)
        findings = []
        for alert in alerts:
            if abs(alert.oi_change_percent) >= self._threshold:
                findings.append({
                    "scanner_type": self.scanner_type.value,
                    "symbol": symbol,
                    "severity": "HIGH" if abs(alert.oi_change_percent) >= 50 else "MEDIUM",
                    "detail": {
                        "strike": alert.strike,
                        "option_type": alert.option_type,
                        "expiry": alert.expiry,
                        "oi_current": alert.current_oi,
                        "oi_previous": alert.previous_oi,
                        "oi_change_pct": alert.oi_change_percent,
                        "significance": alert.significance,
                        "path": "per_contract",
                    },
                })
        return findings
