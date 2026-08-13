"""Data-adapter health introspection helpers (P1-2.4).

Moved out of projections.py (god-module guard). Used by HealthProjection to
inspect the connected/reconnecting/stale state of both Dhan-era and Fyers
data adapters without importing either adapter.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from shettyxtreme.terminal.connection_state import _TICK_STALE_SECONDS


def data_adapter_connected(adapter: Any) -> bool | None:
    """Sync connectivity view that works for both adapter shapes.

    Dhan-era adapters expose ``_connected``; the Fyers data adapter holds
    the HSM data-socket wrapper (``_data_socket``) whose ``connected``
    property is the live link. Returns None when neither exists — the
    health projection must not claim "disconnected" without evidence.
    """
    connected = getattr(adapter, "_connected", None)
    if connected is not None:
        return bool(connected)
    socket = getattr(adapter, "_data_socket", None)
    if socket is not None:
        return bool(getattr(socket, "connected", False))
    return None


def data_adapter_reconnecting(adapter: Any) -> bool:
    """True when the data-socket supervisor is actively retrying.

    The Fyers data socket sets ``_reconnecting = True`` during backoff
    (``data_socket.py:288``).  During reconnect the ``connected`` property
    returns False, but the UI should show CONNECTING, not DISCONNECTED.
    """
    if getattr(adapter, "_reconnecting", False):
        return True
    socket = getattr(adapter, "_data_socket", None)
    if socket is not None:
        return bool(getattr(socket, "_reconnecting", False))
    return False


def data_adapter_stale(
    adapter: Any,
    threshold: float = _TICK_STALE_SECONDS,
    tick_timestamp: datetime | None = None,
) -> bool:
    """True when no fresh ticks have arrived past the threshold.

    P1-2.4: now checks the adapter's own ``is_stale`` method first (for
    adapters that implement it), then falls back to a tick-activity-based
    check using the projection's ``tick_timestamp`` (set by the
    ``MARKET_DATA_TICK`` subscriber).
    """
    is_stale = getattr(adapter, "is_stale", None)
    if is_stale is not None:
        try:
            return bool(is_stale(threshold=threshold))
        except (TypeError, AttributeError):
            pass
    # Fallback: tick-activity-based staleness (P1-2.4).
    if tick_timestamp is not None:
        return (datetime.now(UTC) - tick_timestamp).total_seconds() > threshold
    return False
