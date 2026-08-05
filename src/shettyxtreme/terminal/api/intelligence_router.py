"""Intelligence router — regime, signal, voters, options, strategy hints.

Option-chain rows come from the Fyers ``/data/options-chain-v3`` endpoint
(F4 adapter) whose field names are handled defensively via aliases.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from shettyxtreme.integration.fyers._util import IST
from shettyxtreme.intelligence.hints.strategy_hints import StrategyHints
from shettyxtreme.options.greeks import GreeksCalculator
from shettyxtreme.terminal.api.models import (
    OptionsChainItem,
    OptionsChainResponse,
    RegimeResponse,
    SignalResponse,
    StrategyHintResponse,
    VoterBreakdown,
)

router = APIRouter(prefix="/api/intelligence", tags=["intelligence"])

logger = logging.getLogger(__name__)

# Spot-field aliases across the row and top-level options-chain bodies.
_SPOT_ALIASES: tuple[str, ...] = ("underlying_ltp", "spot", "underlying_spot")

#: User-facing entitlement message (Fyers 403 / -373 — data-API entitlement).
_ENTITLEMENT_MSG = (
    "Data API entitlement missing — subscribe to Data APIs (Fyers 403/-373)"
)

#: Fallback time-to-expiry (years) when no expiry is supplied/parseable.
#: Historical default (~91 days) — real expiries are derived per contract.
_DEFAULT_TTE = 0.25

#: Options settle at 15:30 IST on the expiry day (market close).
_EXPIRY_SETTLE_HOUR, _EXPIRY_SETTLE_MINUTE = 15, 30

_SECONDS_PER_YEAR = 365.25 * 24 * 3600
_MIN_TTE = 1 / 365  # Floor — never divide by zero / never model an expired day.

_MONTH_ABBR_REV: dict[str, int] = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _parse_expiry_date(value: Any) -> date | None:
    """Parse a Fyers expiry into a calendar ``date``, or None when unknown.

    Accepts ISO strings (``2026-08-07``), Fyers symbol-style strings
    (``24OCT2026``), epoch seconds (int or digit string), and date/datetime
    objects. Returns None for anything unparseable so greeks fall back to
    ``_DEFAULT_TTE`` instead of crashing the chain.
    """
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # ISO date.
    try:
        return date.fromisoformat(s)
    except ValueError:
        pass
    # Fyers symbol style: 24OCT2026 / 24OCT26.
    if len(s) >= 5:
        day_str, mon_str, year_str = s[:2], s[2:5], s[5:]
        if (
            day_str.isdigit()
            and mon_str.upper() in _MONTH_ABBR_REV
            and year_str.isdigit()
        ):
            try:
                year = int(year_str)
                if year < 100:
                    year += 2000
                return date(year, _MONTH_ABBR_REV[mon_str.upper()], int(day_str))
            except ValueError:
                return None
    # Epoch seconds (digits only).
    if s.isdigit():
        try:
            return datetime.fromtimestamp(int(s), tz=IST).date()
        except (OverflowError, OSError, ValueError):
            return None
    return None


def _expiry_to_tte(expiry: Any, now_ist: datetime | None = None) -> float:
    """Years to expiry from the Fyers expiry, floored at 1 day.

    Expiry is treated as 15:30 IST (market close) on the expiry day.
    ``now_ist`` is injectable for tests; defaults to current IST time.
    """
    exp_date = _parse_expiry_date(expiry)
    if exp_date is None:
        return _DEFAULT_TTE
    expiry_dt = datetime(
        exp_date.year, exp_date.month, exp_date.day,
        _EXPIRY_SETTLE_HOUR, _EXPIRY_SETTLE_MINUTE, tzinfo=IST,
    )
    now = now_ist if now_ist is not None else datetime.now(IST)
    tte = (expiry_dt - now).total_seconds() / _SECONDS_PER_YEAR
    return max(tte, _MIN_TTE)


class DataEntitlementError(Exception):
    """Raised when the data adapter reports a missing data entitlement (Fyers 403/-373)."""


class DataAdapterUnavailable(Exception):
    """Raised when no data adapter is wired — chain data cannot be fetched."""


def _row_value(row: dict[str, Any], *aliases: str, default: Any = None) -> Any:
    """Return the first non-None alias value present in a row."""
    for key in aliases:
        if row.get(key) is not None:
            return row[key]
    return default


def _safe_float(value: Any) -> float:
    """Coerce a chain row value to float, defaulting to 0.0 on junk."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_float_opt(value: Any) -> float | None:
    """Coerce to float, returning None on junk (used for the spot scan)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalized_type(row: dict[str, Any]) -> str:
    """Normalize option_type/drv_option_type/optionType to CE or PE (uppercased)."""
    raw = str(
        _row_value(row, "option_type", "drv_option_type", "optionType", default="CE")
    ).upper()
    if raw == "CALL":
        return "CE"
    if raw == "PUT":
        return "PE"
    return raw if raw in ("CE", "PE") else "CE"


async def _fetch_chain_with_spot(
    adapter: Any, symbol: str, expiry: str | None,
) -> tuple[list[dict[str, Any]], float | None]:
    """Fetch the option chain from the Fyers data adapter.

    ``FyersDataAdapter.get_option_chain`` returns the raw
    ``/data/options-chain-v3`` payload (``{"s": "ok", "option_chain": [...],
    "spot": ...}``). Raises DataEntitlementError on 403/-373 so callers
    surface the missing data entitlement instead of silently returning an
    empty chain. Raises DataAdapterUnavailable when no adapter is wired —
    an empty chain must never be presented as data. Takes the adapter
    directly (not a Request) so the startup prime can reuse it.
    """
    if adapter is None:
        raise DataAdapterUnavailable(
            "market data adapter not available — check credentials / Fyers feed"
        )
    result = await adapter.get_option_chain(
        underlying=symbol,
        expiry=expiry or "",
        strike_count=50,
    )
    if result.get("entitlement") is True:
        raise DataEntitlementError(_ENTITLEMENT_MSG)
    if result.get("s") != "ok":
        return [], None
    chain = result.get("option_chain", [])
    if not isinstance(chain, list):
        return [], None
    spot = _safe_float_opt(_row_value(result, *_SPOT_ALIASES))
    return chain, spot


async def prime_options_chain(app: Any) -> None:
    """Fetch the NIFTY chain once and populate ``app.state.options_chain``.

    Closes the write-only-cache gap: the research ``options_posture`` tool
    reads ``app.state.options_chain`` (research_source.py), which was only
    ever populated as a side-effect of ``GET /api/intelligence/options``.
    Called from the terminal bootstrap (lifespan and post-login paths both
    flow through ``init_terminal_adapters``) once the data adapter exists.

    Degrades gracefully and leaves the cache untouched on any failure —
    entitlement errors, missing adapters, and network faults all log and
    return, so ``[UNSOURCED]`` remains the honest rendering while no real
    chain data exists. Never raises.
    """
    adapter = getattr(app.state, "data_adapter", None)
    if adapter is None:
        logger.info("options chain prime skipped: no data adapter")
        return
    try:
        chain, spot = await _fetch_chain_with_spot(adapter, "NIFTY", None)
    except DataEntitlementError as exc:
        logger.warning("options chain prime skipped: %s", exc)
        return
    except DataAdapterUnavailable as exc:
        logger.warning("options chain prime skipped: %s", exc)
        return
    except Exception:
        logger.exception("options chain prime failed (network/adapter fault)")
        return
    if not chain:
        logger.info("options chain prime: empty chain for NIFTY — leaving cache untouched")
        return
    app.state.options_chain = {
        **getattr(app.state, "options_chain", {}),
        "NIFTY": {"spot": spot, "contracts": chain},
    }
    logger.info("options chain primed: NIFTY (%d contracts)", len(chain))


def _enrich_chain(
    chain: list[dict[str, Any]], spot: float | None = None, tte: float = _DEFAULT_TTE,
) -> list[OptionsChainItem]:
    """Map raw chain rows to OptionsChainItem, enriching with pure-Python greeks.

    ``tte`` is the time-to-expiry in years derived from the requested expiry;
    it is floored upstream (``_expiry_to_tte``) so greeks never see a
    non-positive tte.
    """
    calc = GreeksCalculator(use_quantlib=False)
    contracts: list[OptionsChainItem] = []
    for row in chain:
        if not isinstance(row, dict):
            continue
        try:
            strike = _safe_float(_row_value(row, "strike", "strike_price", "strikePrice"))
            option_type = _normalized_type(row)
            ltp = _safe_float(_row_value(row, "ltp", "last_price"))
            iv = _safe_float(row.get("iv"))
            row_spot = _safe_float_opt(_row_value(row, *_SPOT_ALIASES))
            spot_val = row_spot if row_spot is not None else spot
            greeks: dict[str, float] = {}
            if spot_val and iv > 0 and strike > 0:
                greeks = calc.calculate_all(
                    spot=spot_val,
                    strike=strike,
                    tte=tte,
                    iv=iv,
                    option_type="CALL" if option_type == "CE" else "PUT",
                )
            contracts.append(OptionsChainItem(
                strike=strike,
                option_type=option_type,
                ltp=ltp,
                iv=iv,
                delta=float(greeks.get("delta", 0.0)),
                gamma=float(greeks.get("gamma", 0.0)),
                theta=float(greeks.get("theta", 0.0)),
                vega=float(greeks.get("vega", 0.0)),
                oi=int(row.get("oi", 0) or 0),
                volume=int(row.get("volume", 0) or 0),
                bid=float(row.get("bid", 0.0) or 0.0),
                ask=float(row.get("ask", 0.0) or 0.0),
            ))
        except (TypeError, ValueError):
            contracts.append(OptionsChainItem(
                strike=_safe_float(_row_value(row, "strike", "strike_price")),
                option_type=_normalized_type(row),
                ltp=0.0, iv=0.0, delta=0.0, gamma=0.0, theta=0.0, vega=0.0,
                oi=0, volume=0, bid=0.0, ask=0.0,
            ))
    return contracts


@router.get("/regime", response_model=RegimeResponse)
async def get_regime(request: Request) -> RegimeResponse:
    """Return current market regime classification."""
    r = request.app.state.intelligence_projection.get_regime()
    return RegimeResponse(
        regime=r.get("regime", "range_bound"),
        confidence=r.get("confidence", 0.5),
        transition=r.get("transition", False),
        adx=r.get("adx"),
        di_plus=r.get("di_plus"),
        di_minus=r.get("di_minus"),
    )


@router.get("/signal", response_model=SignalResponse)
async def get_signal(request: Request) -> SignalResponse:
    """Return current aggregate signal from all voters."""
    s = request.app.state.intelligence_projection.get_signal()
    voters_raw = s.get("voters", [])
    voters = [
        VoterBreakdown(
            name=v.get("name", "unknown"),
            direction=v.get("direction", 0.0),
            confidence=v.get("confidence", 0.0),
            weight=v.get("weight", 1.0),
        )
        for v in voters_raw
    ]
    return SignalResponse(
        direction=s.get("direction", "NEUTRAL"),
        conviction=s.get("conviction", 0.0),
        D=s.get("D", 0.0),
        P=s.get("P", 0.0),
        G=s.get("G", 0.0),
        voters=voters,
        timestamp=s.get("timestamp"),
    )


@router.get("/voters", response_model=list[VoterBreakdown])
async def get_voters(request: Request) -> list[VoterBreakdown]:
    """Return all active voters and their current votes."""
    s = request.app.state.intelligence_projection.get_signal()
    voters_raw = s.get("voters", [])
    return [
        VoterBreakdown(
            name=v.get("name", "unknown"),
            direction=v.get("direction", 0.0),
            confidence=v.get("confidence", 0.0),
            weight=v.get("weight", 1.0),
        )
        for v in voters_raw
    ]


@router.get("/options", response_model=OptionsChainResponse)
async def get_options(
    request: Request,
    symbol: str = Query("NIFTY"),
    expiry: str | None = None,
) -> OptionsChainResponse:
    """Return option chain for a given symbol and expiry."""
    try:
        chain, spot = await _fetch_chain_with_spot(
            request.app.state.data_adapter, symbol, expiry
        )
    except DataEntitlementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DataAdapterUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    contracts = _enrich_chain(chain, spot, tte=_expiry_to_tte(expiry))
    # Cache the RAW rows (pre-enrichment) so the research layer's
    # options_posture tool can derive IV/PCR/OI posture from live data.
    request.app.state.options_chain = {
        **getattr(request.app.state, "options_chain", {}),
        symbol: {"spot": spot, "contracts": chain},
    }
    return OptionsChainResponse(underlying=symbol, expiry=expiry or "", contracts=contracts)


@router.get("/strategy-hint", response_model=StrategyHintResponse)
async def get_strategy_hint(request: Request) -> StrategyHintResponse:
    """Return a strategy hint with EV analysis."""
    signal = request.app.state.intelligence_projection.get_signal() or {}
    try:
        chain, chain_spot = await _fetch_chain_with_spot(
            request.app.state.data_adapter, "NIFTY", None
        )
    except DataEntitlementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DataAdapterUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    current_price = chain_spot
    if current_price is None:
        for row in chain:
            if not isinstance(row, dict):
                continue
            spot = _row_value(row, *_SPOT_ALIASES)
            if spot is None:
                continue
            current_price = _safe_float_opt(spot)
            if current_price is not None:
                break
    hint = StrategyHints(signal=signal, chain=chain, current_price=current_price).generate()
    return StrategyHintResponse(
        direction=hint.direction,
        strike=hint.strike,
        premium=hint.premium,
        ev_after_cost=hint.ev_after_cost,
        rationale=hint.rationale,
    )
