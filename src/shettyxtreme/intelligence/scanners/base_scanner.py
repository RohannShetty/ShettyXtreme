"""Base class for all opportunity scanners.

Provides common finding-emission logic. Each scanner subclass implements
its own detection logic and calls ``_emit_finding`` when an opportunity
is identified.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from shettyxtreme.core.event_bus import Event, EventBus, Topic

logger = logging.getLogger(__name__)


class ScannerType(str, Enum):
    """Canonical scanner type identifiers (11 scanners)."""
    GAMMA_SPIKE = "gamma_spike"
    IV_CRUSH = "iv_crush"
    IV_EXPANSION = "iv_expansion"
    PCR_EXTREMES = "pcr_extremes"
    MAX_PAIN_DRIFT = "max_pain_drift"
    THETA_HARVEST = "theta_harvest"
    CALENDAR_SPREAD = "calendar_spread"
    VERTICAL_SKEW = "vertical_skew"
    GAP_FILL = "gap_fill"
    VOLUME_ANOMALY = "volume_anomaly"
    OI_BUILDUP = "oi_buildup"


class BaseScanner(ABC):
    """Abstract base for all scanners.

    Subclasses must implement ``start()`` and ``stop()``.
    Call ``_emit_finding`` to publish a ``SCANNER_FINDING`` event.
    """

    scanner_type: ScannerType

    def __init__(self, event_bus: EventBus, **params: Any) -> None:
        self._event_bus = event_bus
        self._running = False
        self._params = params

    @abstractmethod
    async def start(self) -> None:
        """Begin scanning (subscribe to inputs)."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop scanning (unsubscribe)."""

    async def _emit_finding(
        self,
        symbol: str,
        detail: dict[str, Any],
        severity: str = "MEDIUM",
    ) -> None:
        """Publish a SCANNER_FINDING event on the bus.

        Args:
            symbol: The instrument symbol.
            detail: Scanner-specific detail dict.
            severity: LOW / MEDIUM / HIGH.
        """
        payload = {
            "scanner_type": self.scanner_type.value,
            "symbol": symbol,
            "severity": severity,
            "detail": detail,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        try:
            await self._event_bus.publish_nowait(
                Event(topic=Topic.SCANNER_FINDING, data=payload, source="scanner")
            )
        except Exception:
            logger.exception(
                "Failed to emit finding from %s for %s",
                self.scanner_type.value,
                symbol,
            )
