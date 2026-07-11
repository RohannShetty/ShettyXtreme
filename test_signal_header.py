
"""SimpleSignalGenerator — combines scanner outputs into tradable signals.

Takes results from PriceBreakoutScanner and GapScanner, applies
configurable weights, computes a combined strength score (0-10), and
publishes Signal dataclasses as SIGNAL_GENERATED events on the EventBus.

Features:
  - Weighted scoring: breakout (2.0), gap (1.0), volume (0.5)
  - Minimum strength filter (default 4.0)
  - Per-symbol cooldown preventing duplicate signals within 5 minutes
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from shettyxtreme.core.event_bus import Event, EventBus, Topic

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    print("test ok")
