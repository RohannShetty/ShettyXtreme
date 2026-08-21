"""IVExpansionScanner — detects IV Rank < 20% + VIX up 10% in 1D (opportunity 3).

Snapshot-driven: uses IVRankCalculator + VIX quote. When IV rank is
below 20% and VIX has moved up ≥ 10% in one day, emits a finding.

Falls back to ATM-IV 1D change as VIX proxy when INDIAVIX is unavailable.
"""
from __future__ import annotations

import logging
from typing import Any

from shettyxtreme.core.event_bus import EventBus
from shettyxtreme.intelligence.scanners.base_scanner import BaseScanner, ScannerType
from shettyxtreme.options.iv_rank import IVRankCalculator

logger = logging.getLogger(__name__)

_IV_RANK_LOW = 20.0  # percent
_VIX_1D_RETURN_THRESHOLD = 10.0  # percent


class IVExpansionScanner(BaseScanner):
    """Detects IV expansion candidates: IV Rank < 20% + VIX up 10% (opportunity 3)."""

    scanner_type = ScannerType.IV_EXPANSION

    def __init__(
        self,
        event_bus: EventBus,
        iv_rank_calculator: IVRankCalculator | None = None,
        **params: Any,
    ) -> None:
        super().__init__(event_bus, **params)
        self._iv_rank_calc = iv_rank_calculator or IVRankCalculator()
        self._prev_vix: dict[str, float] = {}

    async def start(self) -> None:
        self._running = True
        logger.info("IVExpansionScanner started")

    async def stop(self) -> None:
        self._running = False
        logger.info("IVExpansionScanner stopped")

    async def scan(
        self,
        symbol: str,
        atm_iv: float,
        vix_current: float | None = None,
        vix_prev_close: float | None = None,
    ) -> list[dict[str, Any]]:
        """Scan for IV expansion conditions.

        Args:
            symbol: Underlying symbol.
            atm_iv: Current ATM implied volatility (decimal).
            vix_current: Current VIX value (None = use ATM-IV proxy).
            vix_prev_close: Previous day VIX close (None = use internal tracking).

        Returns:
            List of findings.
        """
        self._iv_rank_calc.record_iv(symbol, atm_iv)
        result = self._iv_rank_calc.compute_iv_rank_percent(symbol, atm_iv)
        if result is None:
            return []
        if result.iv_rank_percent >= _IV_RANK_LOW:
            return []

        # Compute VIX 1D return
        vix_return_pct: float | None = None
        if vix_current is not None and vix_prev_close is not None and vix_prev_close > 0:
            vix_return_pct = ((vix_current - vix_prev_close) / vix_prev_close) * 100.0
        elif symbol in self._prev_vix and self._prev_vix[symbol] > 0:
            # Use ATM-IV as proxy
            vix_return_pct = ((atm_iv - self._prev_vix[symbol]) / self._prev_vix[symbol]) * 100.0

        self._prev_vix[symbol] = atm_iv

        if vix_return_pct is not None and vix_return_pct >= _VIX_1D_RETURN_THRESHOLD:
            finding_detail = {
                "iv_rank_percent": result.iv_rank_percent,
                "current_iv": atm_iv,
                "vix_return_pct": round(vix_return_pct, 2),
                "vix_current": vix_current,
                "classification": result.classification,
                "vix_source": "INDIAVIX" if vix_current is not None else "atm_iv_proxy",
            }
            await self._emit_finding(
                symbol=symbol,
                severity="HIGH",
                detail=finding_detail,
            )
            return [{"scanner_type": self.scanner_type.value, "symbol": symbol, "detail": finding_detail}]
        return []
