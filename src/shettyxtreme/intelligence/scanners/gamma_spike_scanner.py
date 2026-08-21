"""GammaSpikeScanner — detects strikes where gamma > 2× historical mean (opportunity 1).

Snapshot-driven: called by the chain poller after each chain refresh.
Maintains per-symbol+strike gamma history (in-memory ring) and flags
strikes where current gamma exceeds 2× the mean.
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from typing import Any

from shettyxtreme.core.event_bus import EventBus
from shettyxtreme.intelligence.scanners.base_scanner import BaseScanner, ScannerType

logger = logging.getLogger(__name__)

_GAMMA_SPIKE_MULTIPLIER = 2.0
_MIN_OBSERVATIONS = 2


class GammaSpikeScanner(BaseScanner):
    """Detects strikes with gamma > 2× historical mean (opportunity 1)."""

    scanner_type = ScannerType.GAMMA_SPIKE

    def __init__(self, event_bus: EventBus, max_history: int = 100, **params: Any) -> None:
        super().__init__(event_bus, **params)
        self._max_history = max_history
        # {symbol: {strike: deque[gamma]}}
        self._gamma_history: dict[str, dict[float, deque[float]]] = defaultdict(
            lambda: defaultdict(lambda: deque(maxlen=max_history))
        )

    async def start(self) -> None:
        self._running = True
        logger.info("GammaSpikeScanner started")

    async def stop(self) -> None:
        self._running = False
        logger.info("GammaSpikeScanner stopped")

    async def scan_chain(
        self,
        symbol: str,
        contracts: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Scan enriched chain contracts for gamma spikes.

        Each contract dict should have: strike, gamma (computed by _enrich_chain).
        Returns findings list AND emits events.
        """
        findings: list[dict[str, Any]] = []
        for c in contracts:
            strike = float(c.get("strike", 0))
            gamma = float(c.get("gamma", 0))
            if strike <= 0 or gamma <= 0:
                continue
            history = self._gamma_history[symbol][strike]
            if len(history) >= _MIN_OBSERVATIONS:
                mean_gamma = sum(history) / len(history)
                if mean_gamma > 0 and gamma > mean_gamma * _GAMMA_SPIKE_MULTIPLIER:
                    finding = {
                        "scanner_type": self.scanner_type.value,
                        "symbol": symbol,
                        "severity": "HIGH",
                        "detail": {
                            "strike": strike,
                            "gamma": gamma,
                            "mean_gamma": round(mean_gamma, 6),
                            "gamma_ratio": round(gamma / mean_gamma, 2),
                            "option_type": c.get("option_type", ""),
                        },
                    }
                    findings.append(finding)
                    await self._emit_finding(
                        symbol=symbol,
                        severity="HIGH",
                        detail=finding["detail"],
                    )
            history.append(gamma)
        return findings
