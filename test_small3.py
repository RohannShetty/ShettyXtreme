"""Test module."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any

from shettyxtreme.core.data_models import Bar
from shettyxtreme.core.event_bus import Event, EventBus, Topic

logger = logging.getLogger(__name__)


class PriceBreakoutScanner:
    """Scans for price breakouts."""

    def __init__(
        self,
        event_bus: EventBus,
        lookback: int = 20,
        threshold_pct: float = 2.0,
    ) -> None:
        """Initialise."""
        self._event_bus = event_bus
        self.lookback = lookback
        self.threshold_pct = threshold_pct
        self._bar_history: dict[str, list[Bar]] = defaultdict(list)
        self._last_results: list[dict[str, Any]] = []
        self._running = False

    async def start(self) -> None:
        """Subscribe to MARKET_DATA_BAR events."""
        if self._running:
            logger.warning("PriceBreakoutScanner already running")
            return
        self._running = True
        self._event_bus.subscribe(Topic.MARKET_DATA_BAR, self._on_bar)
        logger.info(
            "PriceBreakoutScanner started (lookback=%d, threshold=%.1f%%)",
            self.lookback,
            self.threshold_pct,
        )
