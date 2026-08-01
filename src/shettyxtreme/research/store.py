"""Sqlite store for research briefs and immutable decisions.

Decision records are append-only: once a brief leaves `proposed` its status
never changes. Expiry is computed at read time, never persisted.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from shettyxtreme.research.briefs import ResearchBrief

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS briefs (
    brief_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    decided_at TEXT,
    created_at TEXT NOT NULL
);
"""


class AlreadyDecidedError(Exception):
    """Raised when a decision is attempted on an already-decided brief."""


class BriefNotDecidedError(Exception):
    """Raised when an outcome is recorded for a proposed (undecided) brief."""


VALID_OUTCOMES = {"WIN", "LOSS"}


class ResearchStore:
    """Sqlite persistence for briefs; decisions are immutable once made."""

    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def insert(self, brief: ResearchBrief) -> ResearchBrief:
        self._conn.execute(
            "INSERT INTO briefs (brief_id, payload, status, created_at) VALUES (?, ?, ?, ?)",
            (brief.brief_id, brief.model_dump_json(), brief.status, brief.as_of),
        )
        self._conn.commit()
        return brief

    @staticmethod
    def _row_to_brief(row: tuple) -> ResearchBrief:
        return ResearchBrief(**json.loads(row[1]))

    def get(self, brief_id: str) -> ResearchBrief | None:
        row = self._conn.execute(
            "SELECT * FROM briefs WHERE brief_id = ?", (brief_id,)
        ).fetchone()
        return self._row_to_brief(row) if row else None

    def list(self, status: str | None = None, lens: str | None = None) -> list[ResearchBrief]:
        sql = "SELECT * FROM briefs"
        clauses: list[str] = []
        params: list[str] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if lens:
            clauses.append("json_extract(payload, '$.lens') = ?")
            params.append(lens)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_brief(r) for r in rows]

    def decide(
        self, brief_id: str, decision: str, regime: str | None = None
    ) -> ResearchBrief:
        """Set status to approved/rejected; raises AlreadyDecidedError if set.

        `regime` (harness-owned, like `decided_at`) is recorded into the
        payload at decision time for later analytics.
        """
        brief = self.get(brief_id)
        if brief is None:
            raise KeyError(brief_id)
        if brief.status != "proposed":
            raise AlreadyDecidedError(brief_id)
        now = datetime.now(UTC).isoformat()
        payload = json.loads(brief.model_dump_json())
        payload["status"] = decision
        payload["decided_at"] = now
        payload["regime_at_decision"] = regime
        self._conn.execute(
            "UPDATE briefs SET payload = ?, status = ?, decided_at = ? WHERE brief_id = ?",
            (json.dumps(payload), decision, now, brief_id),
        )
        self._conn.commit()
        return self._row_to_brief(
            self._conn.execute(
                "SELECT * FROM briefs WHERE brief_id = ?", (brief_id,)
            ).fetchone()
        )

    def set_outcome(self, brief_id: str, outcome: str) -> ResearchBrief:
        """Link a realized outcome (WIN|LOSS) to a decided brief.

        Raises ValueError for invalid outcome values, KeyError for unknown
        briefs, BriefNotDecidedError for proposed briefs.
        """
        if outcome not in VALID_OUTCOMES:
            raise ValueError(f"invalid outcome: {outcome}")
        brief = self.get(brief_id)
        if brief is None:
            raise KeyError(brief_id)
        if brief.status == "proposed":
            raise BriefNotDecidedError(brief_id)
        payload = json.loads(brief.model_dump_json())
        payload["outcome"] = outcome
        self._conn.execute(
            "UPDATE briefs SET payload = ? WHERE brief_id = ?",
            (json.dumps(payload), brief_id),
        )
        self._conn.commit()
        return self._row_to_brief(
            self._conn.execute(
                "SELECT * FROM briefs WHERE brief_id = ?", (brief_id,)
            ).fetchone()
        )

    def scoring(self) -> list[dict]:
        """Per-lens aggregates: total, decided, with_outcome, win_rate, avg_confidence.

        Empty DB -> []. Corrupt rows are skipped, never fatal.
        """
        rows = self._conn.execute("SELECT payload FROM briefs").fetchall()
        per_lens: dict[str, dict[str, float | int]] = {}
        for (payload_json,) in rows:
            try:
                brief = ResearchBrief(**json.loads(payload_json))
            except Exception:
                continue
            agg = per_lens.setdefault(
                brief.lens,
                {
                    "total": 0,
                    "decided": 0,
                    "with_outcome": 0,
                    "wins": 0,
                    "confidence_sum": 0.0,
                },
            )
            agg["total"] = int(agg["total"]) + 1
            if brief.status != "proposed":
                agg["decided"] = int(agg["decided"]) + 1
            if brief.outcome in ("WIN", "LOSS"):
                agg["with_outcome"] = int(agg["with_outcome"]) + 1
                if brief.outcome == "WIN":
                    agg["wins"] = int(agg["wins"]) + 1
            agg["confidence_sum"] = float(agg["confidence_sum"]) + brief.confidence
        results: list[dict] = []
        for lens, agg in sorted(per_lens.items()):
            with_outcome = int(agg["with_outcome"])
            total = int(agg["total"])
            results.append(
                {
                    "lens": lens,
                    "total": total,
                    "decided": int(agg["decided"]),
                    "with_outcome": with_outcome,
                    "win_rate": round(int(agg["wins"]) / with_outcome, 4)
                    if with_outcome
                    else 0.0,
                    "avg_confidence": round(float(agg["confidence_sum"]) / total, 4)
                    if total
                    else 0.0,
                }
            )
        return results

    def close(self) -> None:
        self._conn.close()
