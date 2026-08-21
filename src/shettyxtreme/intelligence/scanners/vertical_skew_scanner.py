"""VerticalSkewScanner — detects IV skew > 5% between 25Δ and 75Δ (opportunity 8).

Snapshot-driven: estimates strikes at 25Δ and 75Δ from the enriched chain
(computed delta per row) and flags when |IV(25Δ) − IV(75Δ)| > 5%.
"""
from __future__ import annotations

import logging
from typing import Any

from shettyxtreme.core.event_bus import EventBus
from shettyxtreme.intelligence.scanners.base_scanner import BaseScanner, ScannerType

logger = logging.getLogger(__name__)

_SKEW_THRESHOLD = 5.0  # percent


class VerticalSkewScanner(BaseScanner):
    """Detects vertical skew: |IV(25Δ) − IV(75Δ)| > 5% (opportunity 8)."""

    scanner_type = ScannerType.VERTICAL_SKEW

    def __init__(self, event_bus: EventBus, **params: Any) -> None:
        super().__init__(event_bus, **params)

    async def start(self) -> None:
        self._running = True
        logger.info("VerticalSkewScanner started")

    async def stop(self) -> None:
        self._running = False
        logger.info("VerticalSkewScanner stopped")

    async def scan(
        self,
        symbol: str,
        contracts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Scan for vertical skew in option chain.

        Args:
            symbol: Underlying symbol.
            contracts: Enriched contracts with strike, delta, iv, option_type.

        Returns:
            List of findings.
        """
        # Find contracts closest to 25Δ and 75Δ (calls only for standard skew)
        calls = [c for c in contracts if c.get("option_type") in ("CE", "CALL")]
        if len(calls) < 2:
            return []

        # Sort by delta
        calls_with_delta = [
            (float(c.get("delta", 0)), float(c.get("iv", 0)), float(c.get("strike", 0)))
            for c in calls
            if c.get("delta") is not None and c.get("iv") is not None
        ]
        calls_with_delta.sort(key=lambda x: x[0])

        # Find closest to 0.25 and 0.75
        iv_25delta = self._find_closest_delta_iv(calls_with_delta, 0.25)
        iv_75delta = self._find_closest_delta_iv(calls_with_delta, 0.75)

        if iv_25delta is None or iv_75delta is None:
            return []
        if iv_25delta <= 0:
            return []

        skew_pct = abs((iv_25delta - iv_75delta) / iv_25delta) * 100.0
        if skew_pct > _SKEW_THRESHOLD:
            finding_detail = {
                "iv_25delta": iv_25delta,
                "iv_75delta": iv_75delta,
                "skew_pct": round(skew_pct, 2),
                "otm_puts_more_expensive": iv_25delta > iv_75delta,
            }
            await self._emit_finding(
                symbol=symbol,
                severity="MEDIUM",
                detail=finding_detail,
            )
            return [{"scanner_type": self.scanner_type.value, "symbol": symbol, "detail": finding_detail}]
        return []

    @staticmethod
    def _find_closest_delta_iv(
        sorted_contracts: list[tuple[float, float, float]],
        target_delta: float,
    ) -> float | None:
        """Find IV of the contract closest to target_delta."""
        if not sorted_contracts:
            return None
        best_iv = None
        best_diff = float("inf")
        for delta, iv, _strike in sorted_contracts:
            diff = abs(delta - target_delta)
            if diff < best_diff:
                best_diff = diff
                best_iv = iv
        return best_iv
