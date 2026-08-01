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

    def decide(self, brief_id: str, decision: str) -> ResearchBrief:
        """Set status to approved/rejected; raises AlreadyDecidedError if set."""
        brief = self.get(brief_id)
        if brief is None:
            raise KeyError(brief_id)
        if brief.status != "proposed":
            raise AlreadyDecidedError(brief_id)
        payload = json.loads(brief.model_dump_json())
        payload["status"] = decision
        self._conn.execute(
            "UPDATE briefs SET payload = ?, status = ?, decided_at = ? WHERE brief_id = ?",
            (json.dumps(payload), decision, datetime.now(UTC).isoformat(), brief_id),
        )
        self._conn.commit()
        return self._row_to_brief(
            self._conn.execute(
                "SELECT * FROM briefs WHERE brief_id = ?", (brief_id,)
            ).fetchone()
        )

    def set_outcome(self, brief_id: str, outcome: str) -> ResearchBrief:
        """Tracking stub: link a realized outcome (WIN/LOSS) to a brief."""
        brief = self.get(brief_id)
        if brief is None:
            raise KeyError(brief_id)
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

    def close(self) -> None:
        self._conn.close()
