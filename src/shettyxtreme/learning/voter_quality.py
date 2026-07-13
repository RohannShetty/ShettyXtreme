"""Voter quality tracking — per-voter hit rate and adjusted weights.

Tracks how each voter's directional calls resolve into outcomes, then derives
an adjusted weight so that good voters get amplified and bad voters get muted.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime

from shettyxtreme.learning.outcome_tracker import OutcomeLabel


@dataclass
class VoterQualityReport:
    """Aggregate quality report for a single voter."""

    name: str
    total_signals: int
    wins: int
    losses: int
    hit_rate: float
    adjusted_weight: float
    last_10_outcomes: list[OutcomeLabel]


class VoterQualityTracker:
    """Persist per-voter vote/outcome rows and compute quality metrics."""

    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        cur = self._conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS voter_outcomes (
                voter_name TEXT,
                signal_id TEXT,
                direction REAL,
                confidence REAL,
                outcome TEXT,
                timestamp TEXT
            )
            """
        )
        self._conn.commit()

    def record_vote(
        self, voter_name: str, direction: float, confidence: float, signal_id: str
    ) -> None:
        """Record a vote for a signal. Creates the voter_outcome row."""
        cur = self._conn.cursor()
        cur.execute(
            "INSERT INTO voter_outcomes "
            "(voter_name, signal_id, direction, confidence, outcome, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                voter_name,
                signal_id,
                float(direction),
                float(confidence),
                None,
                datetime.now().isoformat(),
            ),
        )
        self._conn.commit()

    def record_outcome(
        self, voter_name: str, signal_id: str, outcome: OutcomeLabel
    ) -> None:
        """Record the outcome for a voter/signal pair."""
        cur = self._conn.cursor()
        row = cur.execute(
            "SELECT 1 FROM voter_outcomes WHERE voter_name = ? AND signal_id = ?",
            (voter_name, signal_id),
        ).fetchone()
        if row is None:
            cur.execute(
                "INSERT INTO voter_outcomes "
                "(voter_name, signal_id, direction, confidence, outcome, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    voter_name,
                    signal_id,
                    0.0,
                    0.0,
                    outcome.value,
                    datetime.now().isoformat(),
                ),
            )
        else:
            cur.execute(
                "UPDATE voter_outcomes SET outcome = ? "
                "WHERE voter_name = ? AND signal_id = ?",
                (outcome.value, voter_name, signal_id),
            )
        self._conn.commit()

    def get_hit_rate(self, voter_name: str, window: int = 20) -> float:
        """Hit rate over the last `window` resolved signals for a voter."""
        cur = self._conn.cursor()
        rows = cur.execute(
            "SELECT outcome FROM voter_outcomes "
            "WHERE voter_name = ? AND outcome IS NOT NULL "
            "ORDER BY timestamp DESC LIMIT ?",
            (voter_name, window),
        ).fetchall()
        wins = 0
        losses = 0
        for r in rows:
            if r["outcome"] == OutcomeLabel.WIN.value:
                wins += 1
            elif r["outcome"] == OutcomeLabel.LOSS.value:
                losses += 1
        total = wins + losses
        return wins / total if total > 0 else 0.0

    def get_adjusted_weight(self, voter_name: str, base_weight: float) -> float:
        """Return a clamped weight scaled by the voter's full-history hit rate."""
        hit_rate = self.get_hit_rate(voter_name, window=10_000_000)
        if hit_rate < 0.3:
            return 0.1
        adjusted = base_weight * (hit_rate / 0.5)
        return max(0.1, min(2.0, adjusted))

    def get_voter_report(self) -> list[VoterQualityReport]:
        """Return quality reports for all voters."""
        cur = self._conn.cursor()
        names = cur.execute(
            "SELECT DISTINCT voter_name FROM voter_outcomes"
        ).fetchall()
        reports: list[VoterQualityReport] = []
        for n in names:
            name = n["voter_name"]
            rows = cur.execute(
                "SELECT outcome FROM voter_outcomes WHERE voter_name = ? "
                "ORDER BY timestamp DESC",
                (name,),
            ).fetchall()
            total = 0
            wins = 0
            losses = 0
            last_10: list[OutcomeLabel] = []
            for r in rows:
                outcome_val = r["outcome"]
                if outcome_val is None:
                    continue
                total += 1
                label = OutcomeLabel(outcome_val)
                if label == OutcomeLabel.WIN:
                    wins += 1
                elif label == OutcomeLabel.LOSS:
                    losses += 1
                if len(last_10) < 10:
                    last_10.append(label)
            resolved = wins + losses
            hit_rate = wins / resolved if resolved > 0 else 0.0
            adjusted = (
                self.get_adjusted_weight(name, base_weight=1.0)
                if total > 0
                else 1.0
            )
            reports.append(
                VoterQualityReport(
                    name=name,
                    total_signals=total,
                    wins=wins,
                    losses=losses,
                    hit_rate=hit_rate,
                    adjusted_weight=adjusted,
                    last_10_outcomes=last_10,
                )
            )
        return reports

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
