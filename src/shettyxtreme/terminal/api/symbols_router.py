"""Symbol search router — prefix/substring search over the instrument master.

Provides ``GET /api/symbols/search`` for typeahead and ``GET /api/symbols/resolve``
for natural-contract parsing (e.g. ``nifty 24k ce``).
"""
from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from shettyxtreme.terminal.api.models import SymbolSearchHit, SymbolSearchResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/symbols", tags=["symbols"])

# ── Natural contract parser ───────────────────────────────────────────────
# Tokenizes inputs like "nifty 24k ce" → {underlying: NIFTY, strike: 24000, option_type: CE}
_OPTION_RE = re.compile(
    r"^(?P<underlying>[A-Z]+)\s+(?P<strike>[0-9]+(?:\.[0-9]+)?[kK]?)\s*(?P<otype>CE|PE|CALL|PUT)$",
    re.IGNORECASE,
)
_K_RE = re.compile(r"^([0-9]+(?:\.[0-9]+)?)k$", re.IGNORECASE)


def _parse_natural_contract(q: str) -> dict[str, Any] | None:
    """Parse a natural-language option query like 'NIFTY 24K CE'.

    Returns:
        ``{underlying, strike, option_type}`` or ``None`` when the query
        doesn't match the pattern.
    """
    m = _OPTION_RE.match(q.strip())
    if not m:
        return None
    underlying = m.group("underlying").upper()
    raw_strike = m.group("strike")
    otype = m.group("otype").upper()

    # Normalize strike: 24k → 24000, 24.5k → 24500, 24000 → 24000
    km = _K_RE.match(raw_strike)
    if km:
        strike = int(float(km.group(1)) * 1000)
    else:
        try:
            strike = int(float(raw_strike))
        except ValueError:
            return None

    option_type = "CE" if otype in ("CE", "CALL") else "PE"
    return {"underlying": underlying, "strike": strike, "option_type": option_type}


@router.get("/search", response_model=SymbolSearchResponse)
async def search_symbols(
    request: Request,
    q: str = Query("", min_length=0, max_length=100),
    instrument_type: str | None = Query(None),
    exchange: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> SymbolSearchResponse:
    """Prefix/substring search over the Fyers instrument master.

    Returns matching instruments deduped per (internal_symbol, instrument_type),
    preferring INDEX/EQUITY rows. Alias-maps ``BNF`` → ``BANKNIFTY`` etc.
    Returns 503 when the instrument master is not available.
    """
    master = getattr(request.app.state, "instrument_master", None)
    if master is None:
        raise HTTPException(
            status_code=503,
            detail="Instrument master not available — check credentials / login",
        )

    # Alias-map the query
    from shettyxtreme.core.knowledge.lexicons import SYMBOL_ALIASES

    query = q.strip().upper()
    canonical = SYMBOL_ALIASES.get(query, query)

    if not canonical:
        return SymbolSearchResponse(query=q, canonical=query, hits=[])

    hits = master.search_prefix(
        canonical,
        exchange=exchange,
        instrument_type=instrument_type,
        limit=limit,
    )

    return SymbolSearchResponse(
        query=q,
        canonical=canonical,
        hits=[
            SymbolSearchHit(
                internal_symbol=h["internal_symbol"],
                fyers_symbol=h["fyers_symbol"],
                exchange=h["exchange"],
                instrument_type=h["instrument_type"],
                expiry=h.get("expiry"),
                strike=h.get("strike"),
                option_type=h.get("option_type"),
                lot_size=h.get("lot_size"),
                tick_size=h.get("tick_size"),
            )
            for h in hits
        ],
    )


@router.get("/resolve", response_model=SymbolSearchResponse)
async def resolve_symbol(
    request: Request,
    q: str = Query(..., min_length=1, max_length=200),
) -> SymbolSearchResponse:
    """Resolve a natural-language symbol query.

    Handles plain names (``RELIANCE``), aliases (``BNF``), and natural
    option contracts (``NIFTY 24K CE``). For option contracts, resolves
    to the nearest-weekly matching contract.
    """
    master = getattr(request.app.state, "instrument_master", None)
    if master is None:
        raise HTTPException(
            status_code=503,
            detail="Instrument master not available — check credentials / login",
        )

    from shettyxtreme.core.knowledge.lexicons import SYMBOL_ALIASES

    query = q.strip().upper()
    if not query:
        return SymbolSearchResponse(query=q, canonical=query, hits=[])

    # Try natural-contract parse first
    parsed = _parse_natural_contract(query)
    if parsed is not None:
        underlying = str(parsed["underlying"])
        underlying = str(SYMBOL_ALIASES.get(underlying, underlying))
        strike = int(parsed["strike"])
        option_type = parsed["option_type"]

        # Search for matching OPTION rows
        rows = master.search(
            underlying,
            instrument_type="OPTION",
            strike=strike,
            option_type=option_type,
        )
        if not rows:
            # Try alias-mapped
            return SymbolSearchResponse(
                query=q,
                canonical=underlying,
                hits=[],
            )

        # Prefer nearest future expiry, weekly over monthly
        from shettyxtreme.integration.fyers.symbols import is_monthly_expiry
        from datetime import date as _date

        today = _date.today()
        future_rows = []
        for r in rows:
            exp_str = r.get("expiry")
            if not exp_str:
                continue
            try:
                exp = _date.fromisoformat(exp_str)
            except ValueError:
                continue
            if exp >= today:
                future_rows.append(r)

        if future_rows:
            # Prefer weekly (not monthly) over monthly
            weekly = [r for r in future_rows if not is_monthly_expiry(r["expiry"])]
            if weekly:
                # Sort by expiry ascending
                weekly.sort(key=lambda r: r.get("expiry", ""))
                best = weekly[0]
            else:
                future_rows.sort(key=lambda r: r.get("expiry", ""))
                best = future_rows[0]
        else:
            # All in the past — pick the latest
            rows.sort(key=lambda r: r.get("expiry", ""), reverse=True)
            best = rows[0]

        return SymbolSearchResponse(
            query=q,
            canonical=underlying,
            hits=[
                SymbolSearchHit(
                    internal_symbol=best["internal_symbol"],
                    fyers_symbol=best["fyers_symbol"],
                    exchange=best["exchange"],
                    instrument_type=best["instrument_type"],
                    expiry=best.get("expiry"),
                    strike=best.get("strike"),
                    option_type=best.get("option_type"),
                    lot_size=best.get("lot_size"),
                    tick_size=best.get("tick_size"),
                )
            ],
        )

    # Plain symbol — delegate to search endpoint logic
    canonical = SYMBOL_ALIASES.get(query, query)
    hits = master.search_prefix(canonical, limit=5)

    return SymbolSearchResponse(
        query=q,
        canonical=canonical,
        hits=[
            SymbolSearchHit(
                internal_symbol=h["internal_symbol"],
                fyers_symbol=h["fyers_symbol"],
                exchange=h["exchange"],
                instrument_type=h["instrument_type"],
                expiry=h.get("expiry"),
                strike=h.get("strike"),
                option_type=h.get("option_type"),
                lot_size=h.get("lot_size"),
                tick_size=h.get("tick_size"),
            )
            for h in hits
        ],
    )
