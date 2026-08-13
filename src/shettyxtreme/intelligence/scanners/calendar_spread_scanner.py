"""CalendarSpreadScanner — detects IV diff > 15% between weekly and monthly chains (opportunity 7).

Snapshot-driven: fetches week + month chains for the same underlying,
compares IV at common strikes, and flags when |IV_week − IV_month|/IV_week > 15%.
"""
from __future__ import annotations

import logging
from typing import Any

from shettyxtreme.core.event_bus import EventBus
from shettyxtreme.intelligence.scanners.base_scanner import BaseScanner, ScannerType

logger = logging.getLogger(__name__)

_IV_DIFF_THRESHOLD = 15.0  # percent


class CalendarSpreadScanner(BaseScanner):
    """Detects calendar spread opportunities: weekly vs monthly IV diff > 15% (opportunity 7)."""

    scanner_type = ScannerType.CALENDAR_SPREAD

    def __init__(self, event_bus: EventBus, **params: Any) -> None:
        super().__init__(event_bus, **params)

    async def start(self) -> None:
        self._running = True
        logger.info("CalendarSpreadScanner started")

    async def stop(self) -> None:
        self._running = False
        logger.info("CalendarSpreadScanner stopped")

    async def scan(
        self,
        symbol: str,
        weekly_contracts: list[dict[str, Any]],
        monthly_contracts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Scan for calendar spread opportunities.

        Args:
            symbol: Underlying symbol.
            weekly_contracts: Weekly expiry chain contracts with strike, iv.
            monthly_contracts: Monthly expiry chain contracts with strike, iv.

        Returns:
            List of findings.
        """
        # Build strike→IV maps
        weekly_iv: dict[float, float] = {}
        for c in weekly_contracts:
            strike = float(c.get("strike", 0))
            iv = float(c.get("iv", 0))
            if strike > 0 and iv > 0:
                # Average CE and PE IV at same strike
                if strike in weekly_iv:
                    weekly_iv[strike] = (weekly_iv[strike] + iv) / 2.0
                else:
                    weekly_iv[strike] = iv

        monthly_iv: dict[float, float] = {}
        for c in monthly_contracts:
            strike = float(c.get("strike", 0))
            iv = float(c.get("iv", 0))
            if strike > 0 and iv > 0:
                if strike in monthly_iv:
                    monthly_iv[strike] = (monthly_iv[strike] + iv) / 2.0
                else:
                    monthly_iv[strike] = iv

        findings: list[dict[str, Any]] = []
        for strike, w_iv in weekly_iv.items():
            m_iv = monthly_iv.get(strike)
            if m_iv is None or w_iv <= 0:
                continue
            diff_pct = abs((w_iv - m_iv) / w_iv) * 100.0
            if diff_pct > _IV_DIFF_THRESHOLD:
                finding_detail = {
                    "strike": strike,
                    "weekly_iv": w_iv,
                    "monthly_iv": m_iv,
                    "iv_diff_pct": round(diff_pct, 2),
                    "weekly_expensive": w_iv > m_iv,
                }
                findings.append({
                    "scanner_type": self.scanner_type.value,
                    "symbol": symbol,
                    "detail": finding_detail,
                })
                await self._emit_finding(
                    symbol=symbol,
                    severity="MEDIUM",
                    detail=finding_detail,
                )
        return findings
