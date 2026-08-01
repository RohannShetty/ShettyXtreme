"""Learning router — calibration curve and shadow graduation status.

Read-only status endpoints over the learning databases. A missing or
unreadable database yields an empty/neutral 200 payload — never a 500.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from fastapi import APIRouter

from shettyxtreme.intelligence.signals.shadow_manager import ShadowManager
from shettyxtreme.learning.calibration import CalibrationCurve
from shettyxtreme.learning.outcome_tracker import OutcomeTracker
from shettyxtreme.terminal.api.models import (
    CalibrationPointResponse,
    CalibrationResponse,
    ShadowStatusItem,
    ShadowStatusResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/learning", tags=["learning"])

LEARNING_DB_PATH = "data/learning.db"
SHADOW_DB_PATH = "data/shadow.db"


def _fit_calibration(db_path: str) -> tuple[bool, list[CalibrationPointResponse]]:
    """Fit the calibration curve over recorded decisions.

    Missing or unreadable databases return `(False, [])` — the exists()
    guard matters: OutcomeTracker eagerly sqlite3.connect()s, which would
    otherwise CREATE a database file for a path that never existed.
    """
    if not Path(db_path).exists():
        return False, []
    try:
        tracker = OutcomeTracker(db_path)
        try:
            decisions = tracker.get_all_decisions()
            curve = CalibrationCurve()
            curve.fit(decisions)
            points = [
                CalibrationPointResponse(
                    conviction_bin=list(p.conviction_bin),
                    actual_win_rate=p.actual_win_rate,
                    sample_size=p.sample_size,
                    confidence_interval=list(p.confidence_interval),
                )
                for p in curve.get_curve()
            ]
            return curve.is_reliable(decisions), points
        finally:
            tracker.close()
    except (FileNotFoundError, sqlite3.Error, Exception) as exc:
        logger.warning("Calibration read failed for %s: %s", db_path, exc)
        return False, []


def _shadow_status(db_path: str) -> list[ShadowStatusItem]:
    """Per-shadow graduation status from the shadow database.

    graduation_status() only knows shadows registered in-memory, so register
    a no-op voter per distinct shadow name persisted in the DB first.
    """
    if not Path(db_path).exists():
        return []
    try:
        conn = sqlite3.connect(db_path)
        try:
            names = [
                str(row[0])
                for row in conn.execute(
                    "SELECT DISTINCT shadow_name FROM shadow_sessions"
                )
            ]
        finally:
            conn.close()
        mgr = ShadowManager(db_path=db_path)
        try:
            for name in names:
                mgr.register_shadow(name, _noop_shadow)
            return [
                ShadowStatusItem(
                    name=item["name"],
                    sessions=item["sessions"],
                    evaluated=item["evaluated"],
                    hit_rate=item["hit_rate"],
                    graduated=item["graduated"],
                    registered=item["registered"],
                )
                for item in mgr.graduation_status()
            ]
        finally:
            mgr.close()
    except (FileNotFoundError, sqlite3.Error, Exception) as exc:
        logger.warning("Shadow status read failed for %s: %s", db_path, exc)
        return []


def _noop_shadow(features: dict, regime: Any, options_context: dict) -> Any:
    """Stand-in voter so graduation_status() can enumerate persisted names."""
    return None


@router.get("/calibration", response_model=CalibrationResponse)
async def calibration() -> CalibrationResponse:
    """Calibration curve status: reliability flag + fitted bins."""
    reliable, points = _fit_calibration(LEARNING_DB_PATH)
    return CalibrationResponse(reliable=reliable, points=points)


@router.get("/shadows", response_model=ShadowStatusResponse)
async def shadows() -> ShadowStatusResponse:
    """Shadow voter graduation status."""
    return ShadowStatusResponse(shadows=_shadow_status(SHADOW_DB_PATH))
