"""MaxPainDriftScanner — detects spot > 2% from max pain with DTE < 3 (opportunity 5).

Snapshot-driven: uses compute_max_pain() to find the max pain strike and
compares to current spot price. Flags when drift exceeds 2% and DTE < 3.
"""
from __future__ import annotations

import logging
from typing import Any

from shettyxtreme.core.event_bus import EventBus
from shettyxtreme.intelligence.scanners.base_scanner import BaseScanner, ScannerType
from shettyxtreme.options.max_pain import compute_max_pain

logger = logging.getLogger(__name__)

_DRIFT_THRESHOLD = 2.0  # percent
_DTE_THRESHOLD = 3


class MaxPainDriftScanner(BaseScanner):
    """Detects max pain drift > 2% with DTE < 3 (opportunity 5)."""

    scanner_type = ScannerType.MAX_PAIN_DRIFT

    def __init__(self, event_bus: EventBus, **params: Any) -> None:
        super().__init__(event_bus, **params)

    async def start(self) -> None:
        self._running = True
        logger.info("MaxPainDriftScanner started")

    async def stop(self) -> None:
        self._running = False
        logger.info("MaxPainDriftScanner stopped")

    async def scan(
        self,
        symbol: str,
        spot: float,
        contracts: list[dict[str, Any]],
        dte: int,
    ) -> list[dict[str, Any]]:
        """Scan for max pain drift.

        Args:
            symbol: Underlying symbol.
            spot: Current underlying price.
            contracts: Option chain contracts with strike, oi, option_type.
            dte: Days to expiry.

        Returns:
            List of findings.
        """
        if dte >= _DTE_THRESHOLD:
            return []
        max_pain = compute_max_pain(contracts)
        if max_pain is None or max_pain <= 0 or spot <= 0:
            return []
        drift_pct = abs((spot / max_pain - 1.0) * 100.0)
        if drift_pct > _DRIFT_THRESHOLD:
            direction = "above" if spot > max_pain else "below"
            finding_detail = {
                "spot": spot,
                "max_pain": max_pain,
                "drift_pct": round(drift_pct, 2),
                "direction": direction,
                "dte": dte,
            }
            await self._emit_finding(
                symbol=symbol,
                severity="HIGH" if drift_pct > 5.0 else "MEDIUM",
                detail=finding_detail,
            )
            return [{"scanner_type": self.scanner_type.value, "symbol": symbol, "detail": finding_detail}]
        return []
