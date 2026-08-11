"""Watchlist router — manage and view watchlist instruments.

For Fyers the watchlist ``security_id`` holds the *internal* symbol (broker
neutral since F1) — the Fyers symbol resolver converts it to a ticker at
hydration/subscribe time. REST hydration backfills ltp/change_pct from
``/data/quotes`` when the live feed is idle; live ticks always win. Idle
rows are hydrated in one batched ``adapter.get_quotes(symbols)`` call (the
adapter groups them into <=50-ticker REST requests), and every outcome is
TTL-cached so a fast-clicking client — or a halted security whose ltp stays
0 — does not re-trigger Fyers REST on every GET.
"""
from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, Request

from shettyxtreme.terminal.api.models import WatchlistItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

#: Internal index names that resolve to the Fyers INDEX instrument type.
_INDEX_SYMBOLS: frozenset[str] = frozenset({"NIFTY", "BANKNIFTY", "FINNIFTY"})

#: How long a REST hydration outcome (hit or miss) is trusted before a
#: watchlist GET re-fetches ``/data/quotes`` for that security.
_HYDRATION_TTL = 10.0

#: Upper bound on :data:`_hydration_cache` entries — watchlists are small,
#: the cap only stops unbounded growth on long-running terminals.
_MAX_HYDRATION_CACHE = 512

#: security_id -> (time.monotonic() stamp, ltp, change_pct) of the last REST
#: hydration outcome. A miss (halted / no data) records ltp 0.0.
_hydration_cache: dict[str, tuple[float, float, float]] = {}


def _as_price(value: Any) -> float | None:
    """Coerce a price value to float; None for junk/halted (<=0)."""
    if not isinstance(value, (int, float, str)):
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def _apply_quote(info: dict[str, Any], ohlc: dict[str, Any] | None) -> None:
    """Backfill ltp/change_pct into one projection row from a quotes payload."""
    if not isinstance(ohlc, dict):
        return
    ltp = _as_price(ohlc.get("ltp"))
    if ltp is None:
        return  # halted security / no data — keep stored values
    info["ltp"] = ltp
    prev_close = _as_price(ohlc.get("close"))
    if prev_close is not None:
        info["change_pct"] = round(((ltp - prev_close) / prev_close) * 100, 2)
    else:
        info["change_pct"] = 0.0


def _record(query: str, info: dict[str, Any]) -> None:
    """Remember the hydration outcome for ``query`` until the TTL expires."""
    if len(_hydration_cache) >= _MAX_HYDRATION_CACHE:
        _hydration_cache.clear()
    _hydration_cache[query] = (
        time.monotonic(),
        info.get("ltp", 0.0) or 0.0,
        info.get("change_pct", 0.0) or 0.0,
    )


async def _hydrate_from_rest(proj_rows: dict[str, dict[str, Any]], request: Request) -> None:
    """Backfill ltp/change_pct from Fyers REST when the live feed is idle.

    Mutates proj_rows in place — the rows ARE the projection's live objects
    (get() is a shallow copy), so a backfilled price persists for the
    session. That is deliberate: post-close the value is today's close and
    the feed polls must not hammer Fyers REST (10 req/s limit). Live ticks
    always overwrite.

    Idle rows are fetched in one batched ``adapter.get_quotes(symbols)``
    call (the adapter groups them into <=50-ticker REST requests); adapters
    that predate batching fall back to the per-symbol ``get_ohlc`` /
    ``get_ltp`` pair. Every outcome — hit or miss — is TTL-cached so repeat
    GETs within :data:`_HYDRATION_TTL` do not re-trigger the loop. Never
    raises — REST failures leave stored values untouched.
    """
    adapter = getattr(request.app.state, "data_adapter", None)
    if adapter is None:
        return
    try:
        now = time.monotonic()
        queries: list[tuple[str, dict[str, Any], str]] = []
        for symbol, info in proj_rows.items():
            if (info.get("ltp") or 0) > 0:
                continue
            query = str(info.get("security_id") or symbol).strip()
            if not query:
                continue
            cached = _hydration_cache.get(query)
            if cached is not None and now - cached[0] < _HYDRATION_TTL:
                info["ltp"], info["change_pct"] = cached[1], cached[2]
                continue
            queries.append((symbol, info, query))
        if not queries:
            return
        get_quotes = getattr(adapter, "get_quotes", None)
        if callable(get_quotes):
            quotes = await get_quotes([q for _, _, q in queries])
            if not isinstance(quotes, dict):
                quotes = {}
            for _, info, query in queries:
                _apply_quote(info, quotes.get(query))
                _record(query, info)
        else:
            for _, info, query in queries:
                ohlc = await adapter.get_ohlc(query)
                _apply_quote(info, ohlc)
                if (info.get("ltp") or 0) <= 0:
                    ltp = _as_price(await adapter.get_ltp(query))
                    if ltp is not None:
                        info["ltp"] = ltp
                        prev_close = (
                            _as_price(ohlc.get("close")) if isinstance(ohlc, dict) else None
                        )
                        if prev_close is not None:
                            info["change_pct"] = round(
                                ((ltp - prev_close) / prev_close) * 100, 2
                            )
                        else:
                            info["change_pct"] = 0.0
                _record(query, info)
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
