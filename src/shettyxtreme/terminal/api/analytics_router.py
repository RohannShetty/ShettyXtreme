"""Analytics router — scorecard-core dashboards surface (Phase 4B).

Assembles session, research-decision, and calibration data into the scorecard.
All DB opens degrade to available:false metrics and empty payloads — never 500.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query

from shettyxtreme.learning.sessions import SessionLog
from shettyxtreme.research.store import ResearchStore
from shettyxtreme.terminal.api.analytics_models import (
    RegimeRowResponse,
    ScorecardMetricResponse,
    ScorecardResponse,
    SessionsResponse,
)
from shettyxtreme.terminal.api.learning_router import _fit_calibration

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

RESEARCH_DB_PATH = "data/research.db"
SESSIONS_DB_PATH = "data/sessions.db"
LEARNING_DB_PATH = "data/learning.db"


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
async def scorecard() -> ScorecardResponse:
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

    return ScorecardResponse(
        reliable_calibration=reliable_calibration,
        metrics=metrics,
        by_regime=regime_rows,
        calibration=calibration_points,
    )
