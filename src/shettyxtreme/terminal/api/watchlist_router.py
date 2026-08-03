"""Watchlist router — manage and view watchlist instruments."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from shettyxtreme.terminal.api.models import WatchlistItem

logger = logging.getLogger(__name__)

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
            security_id=d.get("security_id"),
        )
        for symbol, d in data.items()
    ]


def _resolve_security_id(request: Request, symbol: str, exchange: str) -> str | None:
    """Resolve a trading symbol to its Dhan security ID, if the master is loaded.

    Numeric symbols are assumed to already be security IDs and pass through.
    """
    if symbol.isdigit():
        return symbol
    master = getattr(request.app.state, "instrument_master", None)
    if master is None:
        return None
    return master.resolve_symbol(symbol, exchange)


@router.post("/{symbol}", response_model=WatchlistItem)
async def add_to_watchlist(symbol: str, request: Request, exchange: str = "NSE") -> WatchlistItem:
    """Add an instrument to the watchlist."""
    proj = request.app.state.watchlist_projection
    security_id = _resolve_security_id(request, symbol, exchange)
    if security_id is None and not symbol.isdigit():
        logger.warning(
            "watchlist add: %s not resolvable via instrument master — no live ticks until the feed knows its security ID",
            symbol,
        )
    proj.add(symbol, exchange, security_id=security_id)
    return WatchlistItem(symbol=symbol, exchange=exchange, security_id=security_id)


@router.delete("/{symbol}", status_code=204)
async def remove_from_watchlist(symbol: str, request: Request) -> None:
    """Remove an instrument from the watchlist."""
    request.app.state.watchlist_projection.remove(symbol)
