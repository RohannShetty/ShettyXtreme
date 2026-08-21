"""PCRExtremesScanner — detects PCR outside [0.5, 1.5] (opportunity 4).

Snapshot-driven: called by the chain poller. Uses OITracker.get_pcr()
to compute put/call OI ratio and flags extremes.
"""
from __future__ import annotations

import logging
from typing import Any

from shettyxtreme.core.event_bus import EventBus
from shettyxtreme.intelligence.scanners.base_scanner import BaseScanner, ScannerType
from shettyxtreme.options.oi_tracker import OITracker

logger = logging.getLogger(__name__)

_PCR_LOW = 0.5
_PCR_HIGH = 1.5


class PCRExtremesScanner(BaseScanner):
    """Detects PCR extremes outside [0.5, 1.5] (opportunity 4)."""

    scanner_type = ScannerType.PCR_EXTREMES

    def __init__(
        self,
        event_bus: EventBus,
        oi_tracker: OITracker | None = None,
        pcr_low: float = _PCR_LOW,
        pcr_high: float = _PCR_HIGH,
        **params: Any,
    ) -> None:
        super().__init__(event_bus, **params)
        self._oi_tracker = oi_tracker or OITracker()
        self._pcr_low = pcr_low
        self._pcr_high = pcr_high

    async def start(self) -> None:
        self._running = True
        logger.info("PCRExtremesScanner started (low=%.2f, high=%.2f)", self._pcr_low, self._pcr_high)

    async def stop(self) -> None:
        self._running = False
        logger.info("PCRExtremesScanner stopped")

    async def scan(self, symbol: str, expiry: str | None = None) -> list[dict[str, Any]]:
        """Scan for PCR extremes.

        Args:
            symbol: Underlying symbol.
            expiry: Optional expiry filter.

        Returns:
            List of findings.
        """
        pcr = self._oi_tracker.get_pcr(symbol, expiry)
        if pcr == 0.0:
            return []
        if pcr < self._pcr_low or pcr > self._pcr_high:
            direction = "bearish_extreme" if pcr < self._pcr_low else "bullish_extreme"
            severity = "HIGH" if pcr < 0.3 or pcr > 2.0 else "MEDIUM"
            finding_detail = {
                "pcr": pcr,
                "direction": direction,
                "threshold_low": self._pcr_low,
                "threshold_high": self._pcr_high,
            }
            await self._emit_finding(
                symbol=symbol,
                severity=severity,
                detail=finding_detail,
            )
            return [{"scanner_type": self.scanner_type.value, "symbol": symbol, "detail": finding_detail}]
        return []
