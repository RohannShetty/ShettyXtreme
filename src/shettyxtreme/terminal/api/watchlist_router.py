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

import json
import logging
import re
import time
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from shettyxtreme.terminal.api.models import WatchlistItem

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])

#: How long a REST hydration outcome (hit or miss) is trusted before a
#: watchlist GET re-fetches ``/data/quotes`` for that security.
_HYDRATION_TTL = 10.0

#: Upper bound on :data:`_hydration_cache` entries — watchlists are small,
#: the cap only stops unbounded growth on long-running terminals.
_MAX_HYDRATION_CACHE = 512

#: security_id -> (time.monotonic() stamp, ltp, change_pct) of the last REST
#: hydration outcome. A miss (halted / no data) records ltp 0.0.
_hydration_cache: dict[str, tuple[float, float, float]] = {}

#: Path to the persisted watchlist JSON file.
_WATCHLIST_JSON = Path("data/watchlist.json")

# ── Suffix normalization ──────────────────────────────────────────────────
# Strip common trading-symbol suffixes before resolution.  Order matters:
# check longer suffixes first to avoid partial matches.
_SUFFIXES_TO_STRIP = ("-INDEX", "-FUT", "-EQ", "-BE", "-FO")


def _strip_suffix(symbol: str) -> str:
    """Strip common trading suffixes from a symbol name."""
    s = symbol.strip().upper()
    for suffix in _SUFFIXES_TO_STRIP:
        if s.endswith(suffix):
            s = s[: -len(suffix)]
            break
    # CE/PE are option-type markers, not symbol suffixes — strip only when
    # they appear as a standalone trailing token (e.g. "NIFTY CE" → "NIFTY").
    # But "NIFTY24AUG24000CE" is a Fyers ticker — don't touch that.
    return s


def _infer_instrument_type_from_input(symbol: str) -> str | None:
    """Infer instrument type from the raw input (suffix heuristics).

    Returns ``None`` when the type cannot be determined (caller should
    consult the master).
    """
    s = symbol.strip().upper()
    if s.endswith("-INDEX"):
        return "INDEX"
    if s.endswith("-FUT") or s.endswith("-FO") or s.endswith("FUT"):
        return "FUTURES"
    # CE/PE suffix → OPTION. Only match when the string is short enough to
    # be a user-input option token (e.g. "NIFTY24000CE") and NOT a common
    # equity name that happens to end with those letters (e.g. "RELIANCE").
    # Heuristic: must have a digit before the CE/PE to count as an option.
    if len(s) < 20:
        if (s.endswith("CE") or s.endswith("PE")) and any(c.isdigit() for c in s[:-2]):
            return "OPTION"
    return None


# ── Persistence helpers ───────────────────────────────────────────────────

def _load_persisted_watchlist() -> dict[str, dict[str, Any]]:
    """Load user-added watchlist entries from ``data/watchlist.json``.

    Returns a dict keyed by symbol name, each value having
    ``exchange``, ``security_id``, ``expiry``, ``lot_size``.
    """
    if not _WATCHLIST_JSON.exists():
        return {}
    try:
        with open(_WATCHLIST_JSON, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        logger.warning("Failed to load persisted watchlist from %s", _WATCHLIST_JSON, exc_info=True)
    return {}


def _save_persisted_watchlist(data: dict[str, dict[str, Any]]) -> None:
    """Persist watchlist entries to ``data/watchlist.json``."""
    try:
        _WATCHLIST_JSON.parent.mkdir(parents=True, exist_ok=True)
        with open(_WATCHLIST_JSON, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)
    except Exception:
        logger.warning("Failed to persist watchlist to %s", _WATCHLIST_JSON, exc_info=True)


def _serialize_projection(proj: Any) -> dict[str, dict[str, Any]]:
    """Extract persistable fields from the projection."""
    result: dict[str, dict[str, Any]] = {}
    for symbol, d in proj.get().items():
        result[symbol] = {
            "exchange": d.get("exchange", "NSE"),
            "security_id": d.get("security_id"),
            "expiry": d.get("expiry"),
            "lot_size": d.get("lot_size"),
        }
    return result


# ── Hydration helpers ─────────────────────────────────────────────────────

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


def _stamp_hydrated(info: dict[str, Any]) -> None:
    """Stamp when a row's price was last refreshed from REST.

    The frontend's STALE chip keys on data freshness: rows backfilled by
    hydration carry ``timestamp=None`` otherwise, so a REST-fresh watchlist
    was painted STALE for every symbol whose feed was idle (Task 2.1).
    Live ticks overwrite the stamp on the next MARKET_DATA_TICK. Only rows
    that actually carry a price are stamped — a halted security (ltp 0)
    keeps an honest null timestamp.
    """
    if (info.get("ltp") or 0) > 0:
        info["timestamp"] = datetime.now(UTC).isoformat()


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
                _stamp_hydrated(info)
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
                _stamp_hydrated(info)
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
                _stamp_hydrated(info)
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
            expiry=d.get("expiry"),
            lot_size=d.get("lot_size"),
        )
        for symbol, d in data.items()
    ]


def _resolve_security_id(request: Request, symbol: str, exchange: str) -> tuple[str | None, str | None, str | None, int | None]:
    """Resolve a trading symbol to its internal (broker-neutral) symbol.

    Returns:
        ``(security_id, resolved_exchange, expiry, lot_size)`` —
        ``(None, None, None, None)`` when the symbol is unresolvable.
    """
    s = str(symbol).strip()
    if not s:
        return None, None, None, None

    # Already a Fyers ticker (contains :) — pass through
    if ":" in s:
        return s, exchange, None, None

    resolver = getattr(request.app.state, "symbol_resolver", None)
    master = getattr(request.app.state, "instrument_master", None)

    # Step 1: Strip suffixes and alias-map
    from shettyxtreme.core.knowledge.lexicons import SYMBOL_ALIASES

    normalized = _strip_suffix(s)
    canonical = SYMBOL_ALIASES.get(normalized, normalized)

    # Step 2: Infer instrument type from suffix heuristics or master
    inferred_type = _infer_instrument_type_from_input(s)

    # Step 3: Try master-first resolution (most accurate)
    if master is not None:
        rows = master.search(canonical)
        if rows:
            # Pick the best row: prefer INDEX > EQUITY > FUTURES > OPTION
            type_priority = {"INDEX": 0, "EQUITY": 1, "FUTURES": 2, "OPTION": 3}
            rows.sort(key=lambda r: type_priority.get(r["instrument_type"], 9))
            best = rows[0]

            # For futures: find nearest monthly expiry
            if best["instrument_type"] == "FUTURES" or inferred_type == "FUTURES":
                fut_rows = master.search(canonical, instrument_type="FUTURES")
                if fut_rows:
                    today = date.today()
                    future_exps = []
                    for r in fut_rows:
                        exp_str = r.get("expiry")
                        if not exp_str:
                            continue
                        try:
                            exp = date.fromisoformat(exp_str)
                        except ValueError:
                            continue
                        if exp >= today:
                            future_exps.append((exp, r))
                    if future_exps:
                        future_exps.sort(key=lambda x: x[0])
                        nearest_exp, nearest_row = future_exps[0]
                        lot_size = nearest_row.get("lot_size")
                        # Build the monthly FUT ticker
                        if resolver is not None:
                            try:
                                resolver.to_fyers(
                                    canonical,
                                    exchange or "NSE_FNO",
                                    "FUTURES",
                                    expiry=nearest_exp,
                                    is_monthly=True,
                                )
                            except ValueError:
                                pass
                        return (
                            nearest_row["fyers_symbol"],
                            exchange or "NSE_FNO",
                            nearest_exp.isoformat(),
                            lot_size,
                        )
                    # No future expiries — fall through to INDEX/EQUITY
                    pass

            # For options: find nearest weekly
            if best["instrument_type"] == "OPTION":
                return best["fyers_symbol"], exchange or "NSE_FNO", best.get("expiry"), best.get("lot_size")

            # INDEX or EQUITY
            security_id = best["internal_symbol"]
            lot_size = best.get("lot_size")

            # Validate via resolver if available
            if resolver is not None:
                try:
                    resolver.to_fyers(security_id, exchange or "NSE", best["instrument_type"])
                except ValueError:
                    return None, None, None, None

            return security_id, exchange or "NSE", None, lot_size

    # Step 4: Fallback — try resolver directly with inferred type
    if resolver is not None:
        inst_type = inferred_type or "EQUITY"
        try:
            resolver.to_fyers(canonical, exchange, inst_type)
            return canonical, exchange, None, None
        except ValueError:
            return None, None, None, None

    # No resolver, no master — pass through (legacy behavior)
    return canonical, exchange, None, None


async def _subscribe_symbol(request: Request, security_id: str, exchange: str) -> None:
    """Subscribe a symbol to the live Fyers data feed."""
    data_adapter = getattr(request.app.state, "data_adapter", None)
    if data_adapter is None:
        return
    try:
        # Use the tick callback stored by terminal_init
        tick_callback = getattr(request.app.state, "_publish_market_tick", None)
        if tick_callback is None:
            logger.debug("No tick callback on app.state — skipping subscribe for %s", security_id)
            return
        await data_adapter.subscribe_ticks([security_id], tick_callback)
        logger.info("Subscribed %s to live data feed", security_id)
    except Exception:
        logger.warning("Failed to subscribe %s to live feed", security_id, exc_info=True)


async def _unsubscribe_symbol(request: Request, symbol: str) -> None:
    """Unsubscribe a symbol from the live Fyers data feed."""
    data_adapter = getattr(request.app.state, "data_adapter", None)
    if data_adapter is None:
        return
    try:
        await data_adapter.unsubscribe(symbol)
        logger.info("Unsubscribed %s from live data feed", symbol)
    except Exception:
        logger.warning("Failed to unsubscribe %s from live feed", symbol, exc_info=True)


@router.post("/{symbol}", response_model=WatchlistItem)
async def add_to_watchlist(symbol: str, request: Request, exchange: str = "NSE") -> WatchlistItem:
    """Add an instrument to the watchlist.

    Returns 404 when the symbol is unresolvable, 422 when unparseable.
    On success, subscribes the symbol to the live data feed and persists
    the watchlist.
    """
    proj = request.app.state.watchlist_projection
    security_id, resolved_exchange, expiry, lot_size = _resolve_security_id(request, symbol, exchange)

    if security_id is None:
        logger.warning("watchlist add: %s not resolvable via the Fyers symbol resolver", symbol)
        raise HTTPException(
            status_code=404,
            detail=f"Symbol {symbol!r} not found in the instrument master",
        )

    # Add to projection with extended metadata
    proj.add(
        security_id,
        resolved_exchange or exchange,
        security_id=security_id,
        expiry=expiry,
        lot_size=lot_size,
    )

    # Dynamic feed subscription
    await _subscribe_symbol(request, security_id, resolved_exchange or exchange)

    # Persist
    _save_persisted_watchlist(_serialize_projection(proj))

    return WatchlistItem(
        symbol=security_id,
        exchange=resolved_exchange or exchange,
        security_id=security_id,
        expiry=expiry,
        lot_size=lot_size,
    )


@router.delete("/{symbol}", status_code=204)
async def remove_from_watchlist(symbol: str, request: Request) -> None:
    """Remove an instrument from the watchlist."""
    proj = request.app.state.watchlist_projection
    proj.remove(symbol)
    await _unsubscribe_symbol(request, symbol)
    _save_persisted_watchlist(_serialize_projection(proj))
