"""Hint accuracy tracking — SQLite persistence for hint outcomes (Phase 3, 3A.2).

Every hint that becomes a proposal is recorded (``record_hint``, called by
``POST /api/intelligence/propose-from-hint``). When the resulting position
closes, ``PositionProjection`` looks the hint up (``find_hint``) and records
the outcome (``record_outcome``) with the actual PnL. Accuracy stats (win
rate, average PnL, sample size) are served by
``GET /api/intelligence/hint-stats`` via ``get_stats``.

F-KNOW-002: persistence is best-effort — a broken or unwritable database
never crashes the terminal; every method degrades to a no-op and logs.
Connections are short-lived (one per operation, ``timeout=5.0``), matching
the ExecutionEngine's SQLite pattern, so ``close()`` is a no-op kept for
lifespan symmetry.
"""
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

_DEFAULT_DB_PATH = "data/hints.db"


def _safe_float(value: Any) -> float | None:
    """Coerce to float; None on junk (strike column is REAL)."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class HintStore:
    """SQLite-backed store of hint outcomes for accuracy tracking."""

    def __init__(self, db_path: str = _DEFAULT_DB_PATH) -> None:
        self._db_path = db_path
        self._init_db()

    # ------------------------------------------------------------------
    # Plumbing
    # ------------------------------------------------------------------
    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._db_path, timeout=5.0)

    def _init_db(self) -> None:
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        try:
            with self._connect() as conn:
                conn.execute(
                    """CREATE TABLE IF NOT EXISTS hint_outcomes (
                        hint_id TEXT PRIMARY KEY,
                        symbol TEXT,
                        direction TEXT,
                        strike REAL,
                        suggested_at TEXT,
                        outcome TEXT,
                        actual_pnl REAL,
                        recorded_at TEXT
                    )"""
                )
                conn.commit()
        except sqlite3.Error:
            logger.exception("failed to open hints db at %s", self._db_path)

    def close(self) -> None:
        """Lifespan shutdown hook. Connections are short-lived per operation,
        so there is nothing persistent to close."""

    @staticmethod
    def _normalize_direction(value: str) -> str:
        """Normalize a hint direction to bullish / bearish / neutral."""
        v = str(value or "").strip().upper()
        if v in ("UP", "BULLISH", "BUY"):
            return "bullish"
        if v in ("DOWN", "BEARISH", "SELL"):
            return "bearish"
        return "neutral"

    # ------------------------------------------------------------------
    # Write paths
    # ------------------------------------------------------------------
    def record_hint(self, hint_data: dict[str, Any]) -> str:
        """Persist a hinted trade; returns the generated hint_id."""
        hint_id = uuid4().hex
        now = datetime.now(UTC).isoformat()
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO hint_outcomes "
                    "(hint_id, symbol, direction, strike, suggested_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (
                        hint_id,
                        str(hint_data.get("symbol", "")),
                        self._normalize_direction(str(hint_data.get("direction", ""))),
                        _safe_float(hint_data.get("strike")),
                        now,
                    ),
                )
                conn.commit()
        except sqlite3.Error:
            logger.exception("failed to record hint; continuing")
        return hint_id

    def record_outcome(
        self, hint_id: str, outcome: str, actual_pnl: float | None,
    ) -> bool:
        """Record the outcome for a hint; first recorded outcome wins.

        Returns True when a row was updated (False when the hint is unknown
        or already resolved — idempotent close events never double-count).
        """
        try:
            with self._connect() as conn:
                cur = conn.execute(
                    "UPDATE hint_outcomes SET outcome = ?, actual_pnl = ?, "
                    "recorded_at = ? WHERE hint_id = ? AND outcome IS NULL",
                    (outcome, actual_pnl, datetime.now(UTC).isoformat(), hint_id),
                )
                conn.commit()
                return cur.rowcount > 0
        except sqlite3.Error:
            logger.exception("failed to record outcome for %s", hint_id)
            return False

    # ------------------------------------------------------------------
    # Read paths
    # ------------------------------------------------------------------
    def find_hint(self, symbol: str, direction: str) -> str | None:
        """Return the most recent unresolved hint for symbol + direction.

        Position symbols may be Fyers tickers (``NIFTY26AUG…CE``) while
        hints record internal symbols (``NIFTY``) — prefix matching on either
        side covers that. Only hints with no outcome yet are eligible, so a
        resolved hint is never re-scored.
        """
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT hint_id, symbol FROM hint_outcomes "
                    "WHERE outcome IS NULL AND direction = ? "
                    "ORDER BY suggested_at DESC",
                    (self._normalize_direction(direction),),
                ).fetchall()
        except sqlite3.Error:
            logger.exception("hint lookup failed for %s/%s", symbol, direction)
            return None
        sym = str(symbol or "")
        for hint_id, hint_symbol in rows:
            if not hint_symbol:
                continue
            if hint_symbol == sym or sym.startswith(hint_symbol) or hint_symbol.startswith(sym):
                return hint_id
        return None

    def get_hint(self, hint_id: str) -> dict[str, Any] | None:
        """Return one hint row as a dict, or None when unknown."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT hint_id, symbol, direction, strike, suggested_at, "
                    "outcome, actual_pnl, recorded_at FROM hint_outcomes "
                    "WHERE hint_id = ?",
                    (hint_id,),
                ).fetchone()
        except sqlite3.Error:
            logger.exception("hint read failed for %s", hint_id)
            return None
        if row is None:
            return None
        return {
            "hint_id": row[0],
            "symbol": row[1],
            "direction": row[2],
            "strike": row[3],
            "suggested_at": row[4],
            "outcome": row[5],
            "actual_pnl": row[6],
            "recorded_at": row[7],
        }

    def get_stats(self, days: int = 30) -> dict[str, Any]:
        """Accuracy stats over the trailing ``days`` window.

        Returns::

            {"win_rate": float | None, "avg_pnl": float | None,
             "sample_size": int, "total_hints": int, "days": int}

        ``win_rate`` is wins / resolved hints; ``avg_pnl`` is the mean
        actual PnL across resolved hints; both are None with no sample.
        """
        since = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        try:
            with self._connect() as conn:
                total = conn.execute(
                    "SELECT COUNT(*) FROM hint_outcomes WHERE suggested_at >= ?",
                    (since,),
                ).fetchone()[0]
                rows = conn.execute(
                    "SELECT outcome, actual_pnl FROM hint_outcomes "
                    "WHERE recorded_at >= ? AND outcome IS NOT NULL",
                    (since,),
                ).fetchall()
        except sqlite3.Error:
            logger.exception("hint stats read failed")
            return {
                "win_rate": None,
                "avg_pnl": None,
                "sample_size": 0,
                "total_hints": 0,
                "days": days,
            }
        sample = [r for r in rows if r[0] is not None]
        wins = sum(1 for outcome, _pnl in sample if outcome == "win")
        pnls = [float(pnl) for _outcome, pnl in sample if pnl is not None]
        return {
            "win_rate": round(wins / len(sample), 4) if sample else None,
            "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else None,
            "sample_size": len(sample),
            "total_hints": int(total),
            "days": days,
        }
