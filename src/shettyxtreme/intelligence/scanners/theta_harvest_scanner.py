"""ThetaHarvestScanner — detects ATM contracts with theta/vega > 3, DTE < 10 (opportunity 6).

Snapshot-driven: per ATM contract, computes theta/vega ratio using
GreeksCalculator. Flags when ratio > 3 and DTE < 10.
"""
from __future__ import annotations

import logging
from typing import Any

from shettyxtreme.core.event_bus import EventBus
from shettyxtreme.intelligence.scanners.base_scanner import BaseScanner, ScannerType
from shettyxtreme.options.greeks import GreeksCalculator

logger = logging.getLogger(__name__)

_THETA_VEGA_RATIO = 3.0
_DTE_THRESHOLD = 10


class ThetaHarvestScanner(BaseScanner):
    """Detects ATM contracts with theta/vega > 3 and DTE < 10 (opportunity 6)."""

    scanner_type = ScannerType.THETA_HARVEST

    def __init__(self, event_bus: EventBus, **params: Any) -> None:
        super().__init__(event_bus, **params)
        self._greeks_calc = GreeksCalculator()

    async def start(self) -> None:
        self._running = True
        logger.info("ThetaHarvestScanner started")

    async def stop(self) -> None:
        self._running = False
        logger.info("ThetaHarvestScanner stopped")

    async def scan(
        self,
        symbol: str,
        spot: float,
        contracts: list[dict[str, Any]],
        dte: int,
    ) -> list[dict[str, Any]]:
        """Scan for theta harvest opportunities.

        Args:
            symbol: Underlying symbol.
            spot: Current underlying price.
            contracts: Enriched contracts with strike, iv, option_type.
            dte: Days to expiry.

        Returns:
            List of findings.
        """
        if dte >= _DTE_THRESHOLD:
            return []
        findings: list[dict[str, Any]] = []
        # Find ATM contracts (within 2% of spot)
        atm_threshold = spot * 0.02
        for c in contracts:
            strike = float(c.get("strike", 0))
            iv = float(c.get("iv", 0))
            option_type = c.get("option_type", "CE")
            if abs(strike - spot) > atm_threshold:
                continue
            if iv <= 0:
                continue
            tte = dte / 365.0
            greeks = self._greeks_calc.calculate_all(
                spot=spot,
                strike=strike,
                tte=tte,
                iv=iv,
                option_type=option_type if option_type in ("CALL", "PUT") else "CALL",
            )
            theta = abs(greeks["theta"])
            vega = greeks["vega"]
            if vega > 0 and theta / vega > _THETA_VEGA_RATIO:
                finding_detail = {
                    "strike": strike,
                    "option_type": option_type,
                    "theta": greeks["theta"],
                    "vega": vega,
                    "theta_vega_ratio": round(theta / vega, 2),
                    "iv": iv,
                    "dte": dte,
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
