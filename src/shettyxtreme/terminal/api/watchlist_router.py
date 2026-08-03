"""Watchlist router — manage and view watchlist instruments."""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request

from shettyxtreme.integration.dhan.data_adapter import EXCHANGE_MAP
from shettyxtreme.terminal.api.models import WatchlistItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

# Same segment mapping the data pipeline uses (data_adapter.EXCHANGE_MAP).
_SEGMENT_FOR_EXCHANGE: dict[str, str] = {**EXCHANGE_MAP}


def _segment_for(exchange: str) -> str:
    """Map a friendly exchange name to its Dhan feed segment."""
    key = exchange.upper()
    return _SEGMENT_FOR_EXCHANGE.get(key, key)


def _parse_last_price(instrument: Any) -> float | None:
    """Parse a Dhan marketfeed last_price defensively (None for halted)."""
    if not isinstance(instrument, dict):
        return None
    try:
        return float(instrument.get("last_price"))
    except (TypeError, ValueError):
        return None


async def _hydrate_from_rest(proj_rows: dict[str, dict[str, Any]], request: Request) -> None:
    """Backfill ltp/change_pct from Dhan REST when the live feed is idle.

    Mutates proj_rows in place — the rows ARE the projection's live objects
    (get() is a shallow copy), so a backfilled price persists for the
    session. That is deliberate: post-close the value is today's close and
    the feed polls every ~2s must not hammer Dhan REST. Live ticks always
    overwrite. Never raises — REST failures leave stored values untouched.
    """
    adapter = getattr(request.app.state, "data_adapter", None)
    if adapter is None:
        return
    segments: dict[str, list[str]] = {}
    pending: set[str] = set()
    for info in proj_rows.values():
        sec_id = info.get("security_id")
        if not sec_id:
            continue
        seg = _segment_for(info.get("exchange", "NSE"))
        segments.setdefault(seg, []).append(sec_id)
        if (info.get("ltp") or 0) <= 0:
            pending.add(sec_id)
    if not segments or not pending:
        return
    try:
        result = await adapter.get_ohlc(segments)
        if result.get("status") != "success":
            fallback = await adapter.get_ltp(segments)
            if fallback.get("status") != "success":
                return
            result = fallback
        data = result.get("data", {})
        if not isinstance(data, dict):
            return
        for info in proj_rows.values():
            sec_id = info.get("security_id")
            if sec_id not in pending:
                continue
            segment_data = data.get(_segment_for(info.get("exchange", "NSE")))
            if not isinstance(segment_data, dict):
                continue
            instrument = segment_data.get(sec_id)
            last_price = _parse_last_price(instrument)
            if last_price is None:
                continue
            info["ltp"] = last_price
            prev_close: float | None = None
            ohlc = instrument.get("ohlc") if isinstance(instrument, dict) else None
            if isinstance(ohlc, dict):
                try:
                    prev_close = float(ohlc.get("close"))
                except (TypeError, ValueError):
                    prev_close = None
            if prev_close and prev_close > 0:
                info["change_pct"] = round(((last_price - prev_close) / prev_close) * 100, 2)
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
