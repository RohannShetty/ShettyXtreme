"""Watchlist router — manage and view watchlist instruments."""
from __future__ import annotations

from fastapi import APIRouter, Request

from shettyxtreme.terminal.api.models import WatchlistItem

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchlistItem])
async def get_watchlist(request: Request) -> list[WatchlistItem]:
    """Return all watchlist instruments with live prices."""
    proj = request.app.state.watchlist_projection
    data = proj.get()
    return [
        WatchlistItem(
            symbol=symbol,
            exchange=d.get("exchange", "NSE"),
            ltp=d.get("ltp", 0.0),
            change_pct=d.get("change_pct", 0.0),
            volume=d.get("volume", 0),
            timestamp=d.get("timestamp"),
        )
        for symbol, d in data.items()
    ]


@router.post("/{symbol}", response_model=WatchlistItem)
async def add_to_watchlist(symbol: str, request: Request, exchange: str = "NSE") -> WatchlistItem:
    """Add an instrument to the watchlist."""
    proj = request.app.state.watchlist_projection
    proj.add(symbol, exchange)
    return WatchlistItem(symbol=symbol, exchange=exchange)


@router.delete("/{symbol}", status_code=204)
async def remove_from_watchlist(symbol: str, request: Request) -> None:
    """Remove an instrument from the watchlist."""
    request.app.state.watchlist_projection.remove(symbol)
