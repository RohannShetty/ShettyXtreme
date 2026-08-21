"""Shadow model manager — run experimental voters without affecting live signals.

Shadow voters are logged for promotion evaluation ONLY; they are not counted
in conviction / D / P / G. They enter the global voter registry only via
`graduate()`, after the session gate (min sessions + hit-rate threshold) passes.
"""
from __future__ import annotations

import logging
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from shettyxtreme.intelligence.regime import Regime
from shettyxtreme.intelligence.signals.signal_engine import Vote, get_registry
from shettyxtreme.core.data_models.outcomes import OutcomeLabel

logger = logging.getLogger(__name__)

ShadowFn = Callable[[dict[str, float], Regime, dict], Vote]

MIN_SESSIONS = 20
PROMOTION_HIT_RATE = 0.55


@dataclass
class ShadowComparison:
    """Result of comparing one shadow vote against a realized live outcome."""

    shadow_name: str
    vote_direction: float
    vote_confidence: float
    actual_outcome: OutcomeLabel
    was_correct: bool


class ShadowManager:
    """Run, log, and evaluate shadow voters separate from live conviction."""

    def __init__(self, db_path: str | None = None) -> None:
        self._shadows: dict[str, ShadowFn] = {}
        self._db_path: str | None = db_path
        self._conn: sqlite3.Connection | None = None
        if db_path is not None:
            self._conn = sqlite3.connect(db_path)
            self._conn.row_factory = sqlite3.Row
            self._init_schema()

    def _init_schema(self) -> None:
        assert self._conn is not None
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_sessions (
                shadow_name TEXT,
                signal_id TEXT,
                vote_direction REAL,
                vote_confidence REAL,
                outcome TEXT,
                was_correct INTEGER,
                session_date TEXT
            )
            """
        )
        cols = [row["name"] for row in cur.execute("PRAGMA table_info(shadow_sessions)")]
        if "session_date" not in cols:
            cur.execute("ALTER TABLE shadow_sessions ADD COLUMN session_date TEXT")
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_shadow_sessions_name "
            "ON shadow_sessions(shadow_name)"
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS shadow_graduates (
                shadow_name TEXT PRIMARY KEY,
                graduated_at TEXT
            )
            """
        )
        self._conn.commit()

    def register_shadow(self, name: str, voter: ShadowFn) -> None:
        """Register a standalone shadow voter callable."""
        self._shadows[name] = voter

    def run_shadow(
        self,
        features: dict[str, float],
        regime: Regime,
        options_context: dict,
    ) -> dict[str, Vote]:
        """Run ALL registered shadow voters; returns {name: Vote}."""
        results: dict[str, Vote] = {}
        for name, fn in self._shadows.items():
            results[name] = fn(features, regime, options_context)
        return results

    def log_shadow_results(
        self,
        signal_id: str,
        shadow_votes: dict[str, Vote],
        session_date: str | None = None,
    ) -> None:
        """Persist each shadow vote for a signal (outcome not yet known)."""
        if self._conn is None:
            return
        cur = self._conn.cursor()
        for name, vote in shadow_votes.items():
            cur.execute(
                "INSERT INTO shadow_sessions "
                "(shadow_name, signal_id, vote_direction, vote_confidence, "
                "outcome, was_correct, session_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    name,
                    signal_id,
                    float(vote.direction),
                    float(vote.confidence),
                    None,
                    None,
                    session_date,
                ),
            )
        self._conn.commit()

    def compare_shadow_vs_live(
        self,
        signal_id: str,
        live_outcome: OutcomeLabel,
        live_direction: float = 1.0,
    ) -> dict[str, ShadowComparison]:
        """Build ShadowComparison for each logged shadow vote of a signal."""
        comparisons: dict[str, ShadowComparison] = {}
        if self._conn is None:
            return comparisons
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT * FROM shadow_sessions WHERE signal_id = ?", (signal_id,)
        ).fetchall()
        for row in rows:
            direction = float(row["vote_direction"])
            confidence = float(row["vote_confidence"])
            was_correct = self._is_correct(direction, live_direction, live_outcome)
            cur.execute(
                "UPDATE shadow_sessions SET outcome = ?, was_correct = ? "
                "WHERE signal_id = ? AND shadow_name = ?",
                (
                    live_outcome.value,
                    1 if was_correct else 0,
                    signal_id,
                    row["shadow_name"],
                ),
            )
            comparisons[row["shadow_name"]] = ShadowComparison(
                shadow_name=row["shadow_name"],
                vote_direction=direction,
                vote_confidence=confidence,
                actual_outcome=live_outcome,
                was_correct=was_correct,
            )
        self._conn.commit()
        return comparisons

    def should_promote(self, name: str) -> bool:
        """True if >= MIN_SESSIONS distinct sessions and hit rate > threshold."""
        if self._conn is None:
            return False
        cur = self._conn.cursor()
        sessions = cur.execute(
            "SELECT COUNT(DISTINCT session_date) FROM shadow_sessions "
            "WHERE shadow_name = ? AND session_date IS NOT NULL",
            (name,),
        ).fetchone()[0]
        if sessions < MIN_SESSIONS:
            return False
        rows = cur.execute(
            "SELECT * FROM shadow_sessions WHERE shadow_name = ?", (name,)
        ).fetchall()
        known = [r for r in rows if r["was_correct"] is not None]
        if not known:
            return False
        hits = sum(1 for r in known if r["was_correct"] == 1)
        return (hits / len(known)) > PROMOTION_HIT_RATE

    def graduate(self, name: str) -> ShadowFn | None:
        """Promote a shadow into the default registry once the gate passes.

        Persists first, then registers: a DB write failure is logged and
        returns None without touching the registry. Idempotent: re-graduating
        returns the same fn and replaces the persisted row
        (PRIMARY KEY + INSERT OR REPLACE).
        """
        if not self.should_promote(name):
            return None
        fn = self._shadows.get(name)
        if fn is None:
            return None
        if self._conn is not None:
            try:
                self._conn.execute(
                    "INSERT OR REPLACE INTO shadow_graduates "
                    "(shadow_name, graduated_at) VALUES (?, ?)",
                    (name, datetime.now(UTC).isoformat()),
                )
                self._conn.commit()
            except sqlite3.Error:
                logger.exception("Failed to persist graduation for shadow %r", name)
                self._conn.rollback()
                return None
        get_registry().register(name, fn, weight=1.0)
        return fn

    def graduation_status(self) -> list[dict]:
        """Per-shadow: sessions, evaluated, hit_rate, graduated, registered.

        Enumerates in-memory shadows plus any shadow persisted in the DB, so
        persisted-but-unregistered shadows (e.g. from another process) also
        show up. Runs 2 queries total regardless of shadow count.
        """
        if self._conn is None:
            return []
        cur = self._conn.cursor()
        aggregates = {
            str(row["shadow_name"]): row
            for row in cur.execute(
                "SELECT shadow_name, "
                "COUNT(DISTINCT session_date) AS sessions, "
                "COUNT(was_correct) AS evaluated, "
                "COALESCE(SUM(was_correct), 0) AS hits "
                "FROM shadow_sessions GROUP BY shadow_name"
            ).fetchall()
        }
        graduated_names = {
            str(row[0])
            for row in cur.execute("SELECT shadow_name FROM shadow_graduates").fetchall()
        }
        registered_names = set(get_registry().names())
        names = list(self._shadows) + sorted(set(aggregates) - set(self._shadows))
        statuses: list[dict] = []
        for name in names:
            agg = aggregates.get(name)
            sessions = agg["sessions"] if agg is not None else 0
            evaluated = agg["evaluated"] if agg is not None else 0
            hits = agg["hits"] if agg is not None else 0
            statuses.append(
                {
                    "name": name,
                    "sessions": sessions,
                    "evaluated": evaluated,
                    "hit_rate": hits / evaluated if evaluated else 0.0,
                    "graduated": name in graduated_names,
                    "registered": name in registered_names,
                }
            )
        return statuses

    @staticmethod
    def _is_correct(
        vote_direction: float, live_direction: float, outcome: OutcomeLabel
    ) -> bool:
        if vote_direction == 0.0 or live_direction == 0.0:
            return False
        return (vote_direction > 0) == (live_direction > 0) and outcome == OutcomeLabel.WIN

    def close(self) -> None:
        """Close the underlying database connection if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
