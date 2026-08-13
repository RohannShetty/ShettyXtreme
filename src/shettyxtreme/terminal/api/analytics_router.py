"""Analytics router — scorecard-core dashboards surface (Phase 4B).

Assembles session, research-decision, and calibration data into the scorecard.
All DB opens degrade to available:false metrics and empty payloads — never 500.
Phase 3A.3 adds the time-series history endpoints (IV rank, PCR, max pain,
regime) and the combined data export.
"""
from __future__ import annotations

import csv
import io
import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response

from shettyxtreme.learning.sessions import SessionLog
from shettyxtreme.research.store import ResearchStore
from shettyxtreme.terminal.api.analytics_models import (
    LedgerResponse,
    LedgerSessionResponse,
    LedgerFillResponse,
    RegimeRowResponse,
    ScorecardMetricResponse,
    ScorecardResponse,
    SessionsResponse,
)
from shettyxtreme.terminal.api.learning_router import _fit_calibration
from shettyxtreme.execution.ledger import TradeLedger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

RESEARCH_DB_PATH = "data/research.db"
SESSIONS_DB_PATH = "data/sessions.db"
LEARNING_DB_PATH = "data/learning.db"
LEDGER_DB_PATH = "data/ledger.db"
_COST_PER_FILL = 25.0


def _metric(
    key: str,
    label: str,
    value: str | float | None,
    available: bool,
    note: str | None = None,
    unit: str | None = None,
) -> ScorecardMetricResponse:
    return ScorecardMetricResponse(
        key=key, label=label, value=value, unit=unit, available=available, note=note
    )


def _current_regime(request: Request) -> str | None:
    """Best-effort current regime from the intelligence projection.

    Mirrors the defensive access used by the research router: a missing or
    broken projection must never 500 the scorecard — it degrades to None
    (accent bar falls back to "all regimes current" on the SPA).
    """
    proj = getattr(request.app.state, "intelligence_projection", None)
    if proj is None:
        return None
    try:
        regime = proj.get_regime() or {}
    except Exception as exc:
        logger.warning("Regime lookup failed for scorecard: %s", exc)
        return None
    value = regime.get("regime")
    return value if isinstance(value, str) and value else None


@router.get("/sessions", response_model=SessionsResponse)
async def sessions(limit: int = Query(100, ge=1, le=500)) -> SessionsResponse:
    """Session log rows + counts; missing DB -> empty payload."""
    try:
        log = SessionLog(SESSIONS_DB_PATH)
    except Exception as exc:
        logger.warning("SessionLog unavailable: %s", exc)
        return SessionsResponse()
    try:
        return SessionsResponse(sessions=log.list(limit=limit), counts=log.counts())
    except Exception as exc:
        logger.warning("Sessions read failed: %s", exc)
        return SessionsResponse()
    finally:
        log.close()


@router.get("/scorecard", response_model=ScorecardResponse)
async def scorecard(request: Request) -> ScorecardResponse:
    """Scorecard-core aggregates over sessions, decisions, and calibration."""
    metrics: list[ScorecardMetricResponse] = []

    sessions_total = 0
    sessions_open = 0
    try:
        log = SessionLog(SESSIONS_DB_PATH)
        try:
            counts = log.counts()
            sessions_total = counts["total"]
            sessions_open = counts["open"]
        finally:
            log.close()
    except Exception as exc:
        logger.warning("Sessions stats unavailable: %s", exc)
    metrics.append(
        _metric(
            "sessions_total",
            "Sessions logged",
            sessions_total,
            sessions_total > 0,
            note=None if sessions_total > 0 else "Recorded automatically at terminal start/stop.",
            unit="sessions",
        )
    )
    metrics.append(
        _metric(
            "sessions_open",
            "Sessions open",
            sessions_open,
            sessions_open > 0,
            note=None if sessions_open > 0 else "No session is currently running.",
            unit="sessions",
        )
    )

    decisions = 0
    with_outcome = 0
    wins = 0
    confidence_sum = 0.0
    by_regime: dict[str, dict] = {}
    try:
        rstore = ResearchStore(RESEARCH_DB_PATH)
        try:
            for brief in rstore.list():
                if brief.status == "proposed":
                    continue
                decisions += 1
                confidence_sum += brief.confidence
                regime = brief.regime_at_decision or "unknown"
                row = by_regime.setdefault(
                    regime, {"regime": regime, "decided": 0, "with_outcome": 0, "wins": 0}
                )
                row["decided"] += 1
                if brief.outcome in ("WIN", "LOSS"):
                    with_outcome += 1
                    row["with_outcome"] += 1
                    if brief.outcome == "WIN":
                        wins += 1
                        row["wins"] += 1
        finally:
            rstore.close()
    except Exception as exc:
        logger.warning("Research stats unavailable: %s", exc)

    win_rate = round(wins / with_outcome, 4) if with_outcome else 0.0
    avg_confidence = round(confidence_sum / decisions, 4) if decisions else 0.0
    metrics.append(
        _metric(
            "decisions",
            "Decisions",
            decisions,
            decisions > 0,
            note=None if decisions > 0 else "Approve/reject research briefs to record decisions.",
            unit="briefs",
        )
    )
    metrics.append(
        _metric(
            "with_outcome",
            "With outcome",
            with_outcome,
            with_outcome > 0,
            note=None
            if with_outcome > 0
            else "Record outcomes via /api/research/briefs/{id}/outcome.",
            unit="briefs",
        )
    )
    metrics.append(
        _metric(
            "win_rate",
            "Win rate",
            win_rate,
            with_outcome > 0,
            note=None if with_outcome > 0 else "Needs outcomes recorded.",
        )
    )
    metrics.append(
        _metric(
            "avg_confidence",
            "Avg confidence",
            avg_confidence,
            decisions > 0,
            note=None if decisions > 0 else "Needs decided briefs.",
        )
    )

    regime_rows = [
        RegimeRowResponse(
            regime=r["regime"],
            decided=r["decided"],
            with_outcome=r["with_outcome"],
            win_rate=round(r["wins"] / r["with_outcome"], 4) if r["with_outcome"] else 0.0,
        )
        for r in sorted(by_regime.values(), key=lambda x: x["regime"])
    ]

    reliable_calibration = False
    calibration_points = []
    try:
        reliable_calibration, calibration_points = _fit_calibration(LEARNING_DB_PATH)
    except Exception as exc:
        logger.warning("Calibration unavailable: %s", exc)
    metrics.append(
        _metric(
            "calibration_reliable",
            "Calibration reliable",
            reliable_calibration,
            reliable_calibration,
            note=None if reliable_calibration else "Needs >=30 recorded outcomes.",
        )
    )

    fills_total = 0
    net_ev: float | None = None
    try:
        lstore = TradeLedger(LEDGER_DB_PATH)
        try:
            session_rows = lstore.per_session_summary()
            fills_total = sum(s["fills"] for s in session_rows)
            closed = [s for s in session_rows if s["realized_pnl"] != 0.0]
            if closed:
                net_ev = round(
                    sum(s["realized_pnl"] for s in closed) - fills_total * _COST_PER_FILL,
                    4,
                )
        finally:
            lstore.close()
    except Exception as exc:
        logger.warning("Ledger stats unavailable: %s", exc)
    metrics.append(
        _metric(
            "fills",
            "Fills recorded",
            fills_total,
            fills_total > 0,
            note=None if fills_total > 0 else "Recorded automatically from order fills (paper + postback).",
            unit="fills",
        )
    )
    metrics.append(
        _metric(
            "net_ev_per_session",
            "Net EV per session",
            net_ev,
            net_ev is not None,
            note=None
            if net_ev is not None
            else "Needs closed fill pairs (entry+exit) in the ledger.",
        )
    )

    return ScorecardResponse(
        reliable_calibration=reliable_calibration,
        metrics=metrics,
        by_regime=regime_rows,
        calibration=calibration_points,
        current_regime=_current_regime(request),
    )


@router.get("/ledger", response_model=LedgerResponse)
async def ledger(
    session_id: str | None = None,
    symbol: str | None = None,
    limit: int = Query(200, ge=1, le=1000),
) -> LedgerResponse:
    """Trade fills + per-session aggregates; missing DB -> empty payload."""
    try:
        store = TradeLedger(LEDGER_DB_PATH)
    except Exception as exc:
        logger.warning("Ledger unavailable: %s", exc)
        return LedgerResponse()
    try:
        return LedgerResponse(
            fills=[LedgerFillResponse(**f) for f in store.list(session_id=session_id, symbol=symbol, limit=limit)],
            sessions=[LedgerSessionResponse(**s) for s in store.per_session_summary()],
        )
    except Exception as exc:
        logger.warning("Ledger read failed: %s", exc)
        return LedgerResponse()
    finally:
        store.close()


# ── Phase 3A.3: time-series history endpoints ────────────────────────────────
# All history endpoints degrade to an empty list when the backing calculator /
# store is missing or raises — never 500 (same contract as the scorecard).


def _days_query() -> int:
    """Reusable days query param (1..365, default 30)."""
    return Query(30, ge=1, le=365)


@router.get("/iv-rank-history")
async def iv_rank_history(
    request: Request,
    symbol: str = Query("NIFTY"),
    days: int = _days_query(),
) -> list[dict]:
    """IV rank history from the in-memory IVRankCalculator snapshots.

    Returns ``[{timestamp, iv_rank_percent, iv_classification}]`` for the
    given symbol, filtered to the last ``days`` days.
    """
    calc = getattr(request.app.state, "iv_rank_calculator", None)
    if calc is None or not hasattr(calc, "get_history"):
        return []
    try:
        return calc.get_history(symbol, days)
    except Exception as exc:
        logger.warning("IV rank history read failed: %s", exc)
        return []


@router.get("/pcr-history")
async def pcr_history(
    request: Request,
    symbol: str = Query("NIFTY"),
    days: int = _days_query(),
) -> list[dict]:
    """PCR (put/call OI ratio) history from the OITracker snapshots.

    Returns ``[{timestamp, pcr, total_call_oi, total_put_oi}]`` for the given
    symbol, filtered to the last ``days`` days.
    """
    tracker = getattr(request.app.state, "oi_tracker", None)
    if tracker is None or not hasattr(tracker, "get_pcr_history"):
        return []
    try:
        return tracker.get_pcr_history(symbol, days)
    except Exception as exc:
        logger.warning("PCR history read failed: %s", exc)
        return []


@router.get("/max-pain-history")
async def max_pain_history(
    request: Request,
    symbol: str = Query("NIFTY"),
    days: int = _days_query(),
) -> list[dict]:
    """Max pain history from the analytics store (SQLite).

    Returns ``[{timestamp, max_pain, spot_price}]`` for the given symbol,
    filtered to the last ``days`` days.
    """
    store = getattr(request.app.state, "analytics_store", None)
    if store is None or not hasattr(store, "get_max_pain_history"):
        return []
    try:
        return store.get_max_pain_history(symbol, days)
    except Exception as exc:
        logger.warning("Max pain history read failed: %s", exc)
        return []


@router.get("/regime-history")
async def regime_history(
    request: Request,
    days: int = _days_query(),
) -> list[dict]:
    """Regime history from the analytics store (SQLite).

    Returns ``[{timestamp, regime, confidence, adx}]`` filtered to the last
    ``days`` days.
    """
    store = getattr(request.app.state, "analytics_store", None)
    if store is None or not hasattr(store, "get_regime_history"):
        return []
    try:
        return store.get_regime_history(days)
    except Exception as exc:
        logger.warning("Regime history read failed: %s", exc)
        return []


async def _export_payload(request: Request, symbol: str, days: int) -> dict:
    """Gather every exportable analytics section (degrades, never raises)."""
    sections: dict = {}

    scorecard_metrics: list[dict] = []
    try:
        sc = await scorecard(request)
        scorecard_metrics = [
            {"key": m.key, "label": m.label, "value": m.value, "available": m.available}
            for m in sc.metrics
        ]
    except Exception as exc:
        logger.warning("Scorecard export section failed: %s", exc)
    sections["scorecard_metrics"] = scorecard_metrics

    calc = getattr(request.app.state, "iv_rank_calculator", None)
    if calc is not None and hasattr(calc, "get_history"):
        try:
            sections["iv_rank_history"] = [
                {"symbol": symbol, **row} for row in calc.get_history(symbol, days)
            ]
        except Exception as exc:
            logger.warning("IV rank export section failed: %s", exc)
    sections.setdefault("iv_rank_history", [])

    tracker = getattr(request.app.state, "oi_tracker", None)
    if tracker is not None and hasattr(tracker, "get_pcr_history"):
        try:
            sections["pcr_history"] = [
                {"symbol": symbol, **row} for row in tracker.get_pcr_history(symbol, days)
            ]
        except Exception as exc:
            logger.warning("PCR export section failed: %s", exc)
    sections.setdefault("pcr_history", [])

    store = getattr(request.app.state, "analytics_store", None)
    if store is not None and hasattr(store, "get_max_pain_history"):
        try:
            sections["max_pain_history"] = [
                {"symbol": symbol, **row} for row in store.get_max_pain_history(symbol, days)
            ]
        except Exception as exc:
            logger.warning("Max pain export section failed: %s", exc)
    sections.setdefault("max_pain_history", [])

    if store is not None and hasattr(store, "get_regime_history"):
        try:
            sections["regime_history"] = store.get_regime_history(days)
        except Exception as exc:
            logger.warning("Regime export section failed: %s", exc)
    sections.setdefault("regime_history", [])

    return sections


_CSV_SECTIONS: list[tuple[str, list[str]]] = [
    ("scorecard_metrics", ["key", "label", "value", "available"]),
    ("regime_history", ["timestamp", "regime", "confidence", "adx"]),
    ("iv_rank_history", ["symbol", "timestamp", "iv_rank_percent", "iv_classification"]),
    ("pcr_history", ["symbol", "timestamp", "pcr", "total_call_oi", "total_put_oi"]),
    ("max_pain_history", ["symbol", "timestamp", "max_pain", "spot_price"]),
]


def _sections_to_csv(sections: dict) -> str:
    """Render export sections to a CSV document (stdlib csv, section headers)."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    for name, columns in _CSV_SECTIONS:
        writer.writerow([f"# {name}"])
        writer.writerow(columns)
        for row in sections.get(name, []):
            writer.writerow([row.get(col) for col in columns])
    return buf.getvalue()


@router.get("/export")
async def export_analytics(
    request: Request,
    format: str = Query("csv", pattern="^(csv|json)$"),
    symbol: str = Query("NIFTY"),
    days: int = _days_query(),
) -> Response:
    """Export analytics time series (scorecard, regime, IV rank, PCR, max pain).

    Args:
        format: ``csv`` (default) or ``json``.
        symbol: Underlying symbol for the per-symbol sections.
        days: How many days of history to include (default 30).

    Returns:
        A file download: ``analytics_export.csv`` (text/csv) or a JSON array
        payload with ``Content-Disposition: attachment``.
    """
    sections = await _export_payload(request, symbol, days)
    if format == "json":
        return JSONResponse(
            content=sections,
            headers={"Content-Disposition": 'attachment; filename="analytics_export.json"'},
        )
    return Response(
        content=_sections_to_csv(sections),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="analytics_export.csv"'},
    )
