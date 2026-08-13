"""IVCrushScanner — detects IV Rank > 80% + DTE ≤ 2 (opportunity 2).

Snapshot-driven: called by the chain poller. Uses IVRankCalculator to
compute IV rank. When rank > 80% and DTE ≤ 2, emits a finding.
(DTE ≤ 2 is an earnings-proxy fallback when no earnings calendar exists.)
"""
from __future__ import annotations

import logging
from typing import Any

from shettyxtreme.core.event_bus import EventBus
from shettyxtreme.intelligence.scanners.base_scanner import BaseScanner, ScannerType
from shettyxtreme.options.iv_rank import IVRankCalculator

logger = logging.getLogger(__name__)

_IV_RANK_THRESHOLD = 80.0  # percent
_DTE_THRESHOLD = 2


class IVCrushScanner(BaseScanner):
    """Detects IV crush candidates: IV Rank > 80% + DTE ≤ 2 (opportunity 2)."""

    scanner_type = ScannerType.IV_CRUSH

    def __init__(
        self,
        event_bus: EventBus,
        iv_rank_calculator: IVRankCalculator | None = None,
        **params: Any,
    ) -> None:
        super().__init__(event_bus, **params)
        self._iv_rank_calc = iv_rank_calculator or IVRankCalculator()

    async def start(self) -> None:
        self._running = True
        logger.info("IVCrushScanner started")

    async def stop(self) -> None:
        self._running = False
        logger.info("IVCrushScanner stopped")

    async def scan(
        self,
        symbol: str,
        atm_iv: float,
        dte: int,
    ) -> list[dict[str, Any]]:
        """Scan for IV crush conditions.

        Args:
            symbol: Underlying symbol.
            atm_iv: Current ATM implied volatility (decimal).
            dte: Days to expiry.

        Returns:
            List of findings.
        """
        self._iv_rank_calc.record_iv(symbol, atm_iv)
        result = self._iv_rank_calc.compute_iv_rank_percent(symbol, atm_iv)
        if result is None:
            return []
        if result.iv_rank_percent > _IV_RANK_THRESHOLD and dte <= _DTE_THRESHOLD:
            finding_detail = {
                "iv_rank_percent": result.iv_rank_percent,
                "iv_percentile": result.iv_percentile,
                "current_iv": atm_iv,
                "dte": dte,
                "classification": result.classification,
                "catalyst_known": False,  # no earnings calendar yet
            }
            await self._emit_finding(
                symbol=symbol,
                severity="HIGH",
                detail=finding_detail,
            )
            return [{"scanner_type": self.scanner_type.value, "symbol": symbol, "detail": finding_detail}]
        return []
