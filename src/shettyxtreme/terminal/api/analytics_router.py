"""Analytics router — scorecard-core dashboards surface (Phase 4B).

Assembles session, research-decision, and calibration data into the scorecard.
All DB opens degrade to available:false metrics and empty payloads — never 500.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request

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
