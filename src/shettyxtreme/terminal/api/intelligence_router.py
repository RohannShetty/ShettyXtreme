"""Intelligence router — regime, signal, voters, options, strategy hints.

Option-chain rows come from the Fyers ``/data/options-chain-v3`` endpoint
(F4 adapter) whose field names are handled defensively via aliases.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Request

from shettyxtreme.core.data_models import OrderType, ProductType
from shettyxtreme.integration.fyers._util import IST
from shettyxtreme.intelligence.hints.strategy_hints import StrategyHints
from shettyxtreme.intelligence.signals.signal_engine import Signal, SignalDirection
from shettyxtreme.options.greeks import GreeksCalculator
from shettyxtreme.options.max_pain import compute_max_pain
from shettyxtreme.options.strategy_analyzer import StrategyAnalyzer
from shettyxtreme.terminal.api.models import (
    ExpiryCalendarItem,
    ExpiryCalendarResponse,
    HintStatsResponse,
    OptionsChainItem,
    OptionsChainResponse,
    OptionsSummaryResponse,
    ProposeFromHintRequest,
    ProposalResponse,
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
        code = result.get("code", 0)
        msg = result.get("message", str(result))
        if code == -373:
            raise DataEntitlementError(_ENTITLEMENT_MSG)
        raise HTTPException(status_code=503, detail=f"Fyers options chain error (code {code}): {msg}")
    chain = result.get("option_chain", [])
    if not isinstance(chain, list):
        return [], None
    spot = _safe_float_opt(_row_value(result, *_SPOT_ALIASES))
    return chain, spot


def _feed_options_calculators(
    app: Any, chain: list[dict[str, Any]], symbol: str, expiry: str,
) -> None:
    """Feed IV rank calculator and OI tracker from chain rows."""
    iv_calc = getattr(app.state, "iv_rank_calculator", None)
    oi_track = getattr(app.state, "oi_tracker", None)
    if not iv_calc and not oi_track:
        return
    for row in chain:
        if not isinstance(row, dict):
            continue
        # Feed IV rank calculator
        if iv_calc:
            iv_val = row.get("iv") or row.get("impl_volatility") or 0.0
            try:
                iv_float = float(iv_val)
            except (TypeError, ValueError):
                iv_float = 0.0
            if iv_float > 0:
                strike = _safe_float(_row_value(row, "strike", "strike_price"))
                opt_type = _normalized_type(row)
                iv_calc.record_iv(
                    symbol, iv_float, strike=strike, expiry=expiry, option_type=opt_type,
                )
    # Feed OI tracker with the full chain at once
    if oi_track:
        try:
            oi_track.update_from_chain(symbol=symbol, expiry=expiry, contracts=chain)
        except Exception:
            logger.debug("OI tracker feed failed for %s/%s", symbol, expiry, exc_info=True)


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
    # Feed IV rank calculator and OI tracker from primed chain
    _feed_options_calculators(app, chain, "NIFTY", "")
    # Seed IV cache for per-position greeks (raw chain rows)
    try:
        from shettyxtreme.terminal.api.execution_router import update_iv_cache
        update_iv_cache(chain, spot)
    except Exception:
        pass
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
    """Return option chain for a given symbol and expiry.

    When ``expiry`` is empty, resolves the calendar default server-side
    (index → nearest weekly, stock → nearest monthly) instead of relying
    on Fyers' opaque nearest-expiry behavior.
    """
    from shettyxtreme.integration.fyers.symbols import resolve_default_expiry

    resolved_expiry = expiry
    if not resolved_expiry or not resolved_expiry.strip():
        master = getattr(request.app.state, "instrument_master", None)
        if master is not None:
            expiries = master.list_expiries(
                symbol.strip().upper(), exchange="NSE", instrument_type="OPTION",
            )
            if expiries:
                resolved_expiry = resolve_default_expiry(symbol.strip().upper(), expiries)
    try:
        chain, spot = await _fetch_chain_with_spot(
            request.app.state.data_adapter, symbol, resolved_expiry
        )
    except DataEntitlementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except DataAdapterUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    contracts = _enrich_chain(chain, spot, tte=_expiry_to_tte(resolved_expiry))
    # Cache the RAW rows (pre-enrichment) so the research layer's
    # options_posture tool can derive IV/PCR/OI posture from live data.
    request.app.state.options_chain = {
        **getattr(request.app.state, "options_chain", {}),
        symbol: {"spot": spot, "contracts": chain},
    }
    # Feed IV rank calculator and OI tracker with live chain data
    _feed_options_calculators(request.app, chain, symbol, resolved_expiry or "")
    # Update the execution router's IV cache so per-position greeks can be
    # computed on the positions endpoint (the chain poll and position poll
    # are independent; this bridges them).
    try:
        from shettyxtreme.terminal.api.execution_router import update_iv_cache
        # Convert OptionsChainItem pydantic models to dicts for the cache
        enriched_dicts = [c.model_dump() for c in contracts]
        update_iv_cache(enriched_dicts, spot)
    except Exception:
        logger.debug("IV cache update failed", exc_info=True)
    return OptionsChainResponse(underlying=symbol, expiry=resolved_expiry or "", contracts=contracts)


@router.get("/expiry-calendar", response_model=ExpiryCalendarResponse)
async def get_expiry_calendar(
    request: Request,
    symbol: str = Query("NIFTY"),
) -> ExpiryCalendarResponse:
    """Return distinct future expiries classified as weekly/monthly.

    Uses the instrument master as the source of truth. Returns the
    policy-driven default expiry for the symbol.
    """
    from shettyxtreme.integration.fyers._util import INDEX_SYMBOLS
    from shettyxtreme.integration.fyers.symbols import (
        classify_expiry,
        resolve_default_expiry,
    )

    master = getattr(request.app.state, "instrument_master", None)
    if master is None:
        raise HTTPException(
            status_code=503,
            detail="Instrument master not available",
        )

    sym = symbol.strip().upper()
    # Indices use OPTION expiries; equities also query OPTION (F&O segment).
    instrument_type = "OPTION"
    expiries = master.list_expiries(sym, exchange="NSE", instrument_type=instrument_type)

    items = [
        ExpiryCalendarItem(date=e, kind=classify_expiry(sym, e))
        for e in expiries
    ]
    default = resolve_default_expiry(sym, expiries)

    return ExpiryCalendarResponse(
        symbol=sym,
        instrument_type=instrument_type,
        expiries=items,
        default=default,
    )


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
        strategy=hint.strategy,
        strike=hint.strike,
        premium=hint.premium,
        ev_after_cost=hint.ev_after_cost,
        rationale=hint.rationale,
        expiry=hint.leg.expiry if hint.leg else None,
        option_type=hint.leg.option_type if hint.leg else None,
        lot_size=hint.leg.lot_size if hint.leg else None,
        lots=hint.leg.lots if hint.leg else None,
        entry_premium=hint.leg.entry_premium if hint.leg else None,
        stop_loss=hint.stop_loss,
        target=hint.target,
        confidence=hint.confidence,
    )


@router.get("/options-summary", response_model=OptionsSummaryResponse)
async def get_options_summary(
    request: Request,
    symbol: str = Query("NIFTY"),
) -> OptionsSummaryResponse:
    """Return options analytics summary: max pain, PCR, IV rank."""
    # Get chain data — use cache if available, otherwise fetch
    cached = getattr(request.app.state, "options_chain", {}).get(symbol)
    if cached and cached.get("contracts"):
        chain = cached["contracts"]
    else:
        try:
            chain, _spot = await _fetch_chain_with_spot(
                request.app.state.data_adapter, symbol, None,
            )
        except (DataEntitlementError, DataAdapterUnavailable):
            chain = []
        except Exception:
            logger.debug("options-summary fetch failed for %s", symbol, exc_info=True)
            chain = []

    max_pain_val = compute_max_pain(chain) if chain else None

    # PCR from OI tracker
    oi_track = getattr(request.app.state, "oi_tracker", None)
    pcr_val = oi_track.get_pcr(symbol) if oi_track else None
    if pcr_val == 0.0:
        pcr_val = None

    # IV rank from calculator
    iv_calc = getattr(request.app.state, "iv_rank_calculator", None)
    iv_rank_val: float | None = None
    iv_class_val: str | None = None
    if iv_calc:
        result = iv_calc.compute_iv_rank_percent(symbol)
        if result is not None:
            iv_rank_val = result.iv_rank_percent
            iv_class_val = result.classification

    return OptionsSummaryResponse(
        underlying=symbol,
        max_pain=max_pain_val,
        pcr=pcr_val,
        iv_rank_percent=iv_rank_val,
        iv_classification=iv_class_val,
    )


def _hint_direction(value: str) -> SignalDirection | None:
    """Map a hint direction onto a SignalDirection; None for neutral/unknown.

    Accepts both the hint vocabulary (bullish / bearish) and the signal
    vocabulary (UP / DOWN). Neutral or unrecognized directions return None —
    callers reject them, since a neutral hint must never become a proposal.
    """
    v = str(value or "").strip().upper()
    if v in ("UP", "BULLISH"):
        return SignalDirection.UP
    if v in ("DOWN", "BEARISH"):
        return SignalDirection.DOWN
    return None


@router.post("/propose-from-hint", response_model=ProposalResponse)
async def propose_from_hint(
    request: Request, payload: ProposeFromHintRequest,
) -> ProposalResponse:
    """One-click proposal generation from a strategy hint (3A.2).

    Builds a SignalV2-shaped signal from the hint payload and queues a
    PENDING proposal on the ExecutionEngine — OBSERVER-first (D10): the
    human always approves before anything is placed. The response uses the
    same ``ProposalResponse`` as the execution router, with ``source`` set
    to ``manual_hint`` so hint-generated proposals are distinguishable from
    pipeline-driven ones. The hint is also recorded in the hint store so
    its outcome can be scored when the position closes.
    """
    engine = getattr(request.app.state, "execution_engine", None)
    if engine is None:
        raise HTTPException(
            status_code=503, detail="execution engine not available",
        )

    direction = _hint_direction(payload.direction)
    if direction is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "direction must be bullish/bearish (or UP/DOWN) — "
                "neutral hints cannot become proposals"
            ),
        )

    bullish = direction == SignalDirection.UP
    option_type = str(payload.option_type or ("CE" if bullish else "PE")).upper()

    lot_size = int(payload.lot_size or 0)
    lots = int(payload.lots or 1)
    quantity = payload.quantity
    if quantity is None:
        quantity = lot_size * lots if lot_size > 0 else None
    if quantity == 0:
        quantity = None

    conviction = payload.conviction
    if conviction is None:
        conviction = payload.confidence or 0.0

    signal = Signal(
        direction=direction,
        conviction=float(conviction),
        voters=[],
        timestamp=datetime.now(UTC),
        D=0.0,
        P=1.0,
        G="contested",
    )

    premium = payload.premium
    hint: dict[str, Any] = {
        "symbol": payload.symbol,
        "exchange": "NFO",
        "quantity": quantity,
        "lot_size": lot_size or None,
        "lots": lots,
        "price": premium,
        "order_type": OrderType.LIMIT if premium is not None else OrderType.MARKET,
        "product": ProductType.MIS,
        "tag": "manual_hint",
        "hint_kind": "manual_hint",
        "source": "manual_hint",
        "strike": payload.strike,
        "expiry": payload.expiry,
        "option_type": option_type,
        "entry_premium": premium,
        "stop_loss": payload.stop_loss,
        "target": payload.target,
        "rationale": payload.rationale,
        "confidence": payload.confidence,
        "strategy": StrategyAnalyzer.display_name(
            "long_call" if bullish else "long_put"
        ),
        "underlying": payload.symbol,
    }

    approval_id = engine.submit_signal(signal, hint, signal_id=uuid4().hex)
    approval = engine.get_approval(approval_id)

    # Best-effort hint tracking (3A.2): record the hint so a closing
    # position can later resolve its outcome. Never fails the request.
    # Phase 3C.1: capture the current regime for regime-aware accuracy stats.
    store = getattr(request.app.state, "hint_store", None)
    if store is not None:
        try:
            proj = getattr(request.app.state, "intelligence_projection", None)
            regime = None
            if proj is not None:
                try:
                    regime = proj.get_regime().get("regime")
                except Exception:
                    pass
            hint["hint_id"] = store.record_hint(payload.model_dump(), regime=regime)
        except Exception:
            logger.debug(
                "hint record failed for %s/%s",
                payload.symbol, payload.direction, exc_info=True,
            )

    from shettyxtreme.terminal.api.execution_router import _proposal_response

    response = _proposal_response(approval)
    response.source = "manual_hint"
    return response


@router.get("/hint-stats", response_model=HintStatsResponse)
async def get_hint_stats(
    request: Request, days: int = Query(30, ge=1, le=365),
) -> HintStatsResponse:
    """Return hint accuracy stats over the trailing ``days`` window (3A.2).

    Win rate and average PnL are computed over hints that resolved (a
    matching position closed); ``total_hints`` counts every hint recorded
    in the window regardless of resolution.
    """
    store = getattr(request.app.state, "hint_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="hint store not available")
    return HintStatsResponse(**store.get_stats(days=days))
