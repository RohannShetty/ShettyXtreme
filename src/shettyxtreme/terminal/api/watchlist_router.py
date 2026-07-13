"""Watchlist router — manage and view watchlist instruments."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from shettyxtreme.terminal.api.models import WatchlistItem

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

# In-memory watchlist store (replaced with persistent storage in production)
_watchlist: dict[str, dict[str, Any]] = {}


@router.get("", response_model=list[WatchlistItem])
async def get_watchlist() -> list[WatchlistItem]:
    """Return all watchlist instruments with live prices."""
    items: list[WatchlistItem] = []
    for symbol, data in _watchlist.items():
        items.append(WatchlistItem(
            symbol=symbol,
            exchange=data.get("exchange", "NSE"),
            ltp=data.get("ltp", 0.0),
            change_pct=data.get("change_pct", 0.0),
            volume=data.get("volume", 0),
            timestamp=data.get("timestamp"),
        ))
    return items


@router.post("/{symbol}", response_model=WatchlistItem)
async def add_to_watchlist(symbol: str, exchange: str = "NSE") -> WatchlistItem:
    """Add an instrument to the watchlist."""
    if symbol not in _watchlist:
        _watchlist[symbol] = {"exchange": exchange, "ltp": 0.0, "change_pct": 0.0, "volume": 0, "timestamp": None}
    return WatchlistItem(symbol=symbol, exchange=exchange)


@router.delete("/{symbol}", status_code=204)
async def remove_from_watchlist(symbol: str) -> None:
    """Remove an instrument from the watchlist."""
    _watchlist.pop(symbol, None)
