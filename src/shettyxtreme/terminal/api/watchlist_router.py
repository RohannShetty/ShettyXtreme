"""Watchlist router — manage and view watchlist instruments.

For Fyers the watchlist ``security_id`` holds the *internal* symbol (broker
neutral since F1) — the Fyers symbol resolver converts it to a ticker at
hydration/subscribe time. REST hydration backfills ltp/change_pct from
``/data/quotes`` when the live feed is idle; live ticks always win.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from shettyxtreme.terminal.api.models import WatchlistItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

#: Internal index names that resolve to the Fyers INDEX instrument type.
_INDEX_SYMBOLS: frozenset[str] = frozenset({"NIFTY", "BANKNIFTY", "FINNIFTY"})


def _as_price(value: Any) -> float | None:
    """Coerce a price value to float; None for junk/halted (<=0)."""
    if not isinstance(value, (int, float, str)):
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


async def _hydrate_from_rest(proj_rows: dict[str, dict[str, Any]], request: Request) -> None:
    """Backfill ltp/change_pct from Fyers REST when the live feed is idle.

    Mutates proj_rows in place — the rows ARE the projection's live objects
    (get() is a shallow copy), so a backfilled price persists for the
    session. That is deliberate: post-close the value is today's close and
    the feed polls must not hammer Fyers REST (10 req/s limit). Live ticks
    always overwrite. Never raises — REST failures leave stored values
    untouched.
    """
    adapter = getattr(request.app.state, "data_adapter", None)
    if adapter is None:
        return
    try:
        for symbol, info in proj_rows.items():
            if (info.get("ltp") or 0) > 0:
                continue
            query = str(info.get("security_id") or symbol).strip()
            if not query:
                continue
            ohlc = await adapter.get_ohlc(query)
            ltp = _as_price(ohlc.get("ltp") if isinstance(ohlc, dict) else None)
            if ltp is None:
                ltp = _as_price(await adapter.get_ltp(query))
            if ltp is None:
                continue  # halted security / no data — keep stored values
            info["ltp"] = ltp
            prev_close = _as_price(ohlc.get("close")) if isinstance(ohlc, dict) else None
            if prev_close is not None:
                info["change_pct"] = round(((ltp - prev_close) / prev_close) * 100, 2)
            else:
                info["change_pct"] = 0.0
    except Exception:
        logger.warning("watchlist REST hydration failed — keeping stored values", exc_info=True)


@router.get("", response_model=list[WatchlistItem])
async def get_watchlist(request: Request) -> list[WatchlistItem]:
    """Return all watchlist instruments with live prices."""
    proj = request.app.state.watchlist_projection
    data = proj.get()
    await _hydrate_from_rest(data, request)
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
    """Resolve a trading symbol to its internal (broker-neutral) symbol.

    For Fyers the internal symbol IS the security_id; the Fyers symbol
    resolver validates it resolves to a Fyers ticker (round-trip gate).
    """
    s = str(symbol).strip()
    if not s:
        return None
    if ":" in s:
        return s  # already a Fyers ticker
    resolver = getattr(request.app.state, "symbol_resolver", None)
    if resolver is None:
        return s
    try:
        instrument_type = "INDEX" if s.upper() in _INDEX_SYMBOLS else "EQUITY"
        resolver.to_fyers(s, exchange, instrument_type)
        return s
    except ValueError:
        return None


@router.post("/{symbol}", response_model=WatchlistItem)
async def add_to_watchlist(symbol: str, request: Request, exchange: str = "NSE") -> WatchlistItem:
    """Add an instrument to the watchlist."""
    proj = request.app.state.watchlist_projection
    security_id = _resolve_security_id(request, symbol, exchange)
    if security_id is None:
        logger.warning(
            "watchlist add: %s not resolvable via the Fyers symbol resolver — "
            "no live ticks until the resolver knows it",
            symbol,
        )
    proj.add(symbol, exchange, security_id=security_id)
    return WatchlistItem(symbol=symbol, exchange=exchange, security_id=security_id)


@router.delete("/{symbol}", status_code=204)
async def remove_from_watchlist(symbol: str, request: Request) -> None:
    """Remove an instrument from the watchlist."""
    request.app.state.watchlist_projection.remove(symbol)
