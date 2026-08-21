"""Connection state for the header health pip (P1-2.4).

Moved out of projections.py (god-module guard) — re-exported from
``shettyxtreme.terminal.projections`` so existing imports keep working.
"""
from __future__ import annotations

from enum import Enum

# Tick-staleness threshold in seconds: if no market-data tick arrives within
# this window the data-adapter component transitions to STALE.
_TICK_STALE_SECONDS: float = 60.0


class ConnectionState(str, Enum):
    """Single source of truth for the connection pip in the header.

    Transitions:
        DISCONNECTED → CONNECTING → CONNECTED → STALE → EXPIRED
        EXPIRED supersedes all; token re-auth returns to CONNECTING.
    """
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    STALE = "stale"
    EXPIRED = "expired"
