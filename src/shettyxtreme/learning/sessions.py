"""SessionLog — sqlite recording of terminal run sessions (spec 4B §4.1).

One session row per run: started at startup, ended at teardown. `end` on an
unknown id is a silent no-op so teardown never raises. Mirrors the
ResearchStore pattern: single connection, commit per operation.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    ended_at TEXT,
    mode TEXT NOT NULL
);
"""


class SessionLog:
    """Sqlite persistence for terminal session start/end records."""

    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, timeout=5.0)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def start(self, mode: str) -> str:
        """Open a session; returns its session_id (uuid4 string)."""
        session_id = str(uuid4())
        self._conn.execute(
            "INSERT INTO sessions (session_id, started_at, mode) VALUES (?, ?, ?)",
            (session_id, datetime.now(UTC).isoformat(), mode),
        )
        self._conn.commit()
        return session_id

    def end(self, session_id: str) -> None:
        """Close a session; unknown ids are a silent no-op."""
        self._conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE session_id = ? AND ended_at IS NULL",
            (datetime.now(UTC).isoformat(), session_id),
        )
        self._conn.commit()

    def list(self, limit: int = 100) -> list[dict]:
        """Sessions, newest first."""
        rows = self._conn.execute(
            "SELECT session_id, started_at, ended_at, mode FROM sessions ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            {
                "session_id": r[0],
                "started_at": r[1],
                "ended_at": r[2],
                "mode": r[3],
            }
            for r in rows
        ]

    def counts(self) -> dict[str, int]:
        """Aggregate counts: total, open (not ended), live, observer."""
        row = self._conn.execute(
            "SELECT COUNT(*), "
            "SUM(CASE WHEN ended_at IS NULL THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN mode = 'LIVE' THEN 1 ELSE 0 END), "
            "SUM(CASE WHEN mode = 'OBSERVER' THEN 1 ELSE 0 END) "
            "FROM sessions"
        ).fetchone()
        total, open_sessions, live, observer = row
        return {
            "total": int(total or 0),
            "open": int(open_sessions or 0),
            "live": int(live or 0),
            "observer": int(observer or 0),
        }

    def close(self) -> None:
        self._conn.close()
