"""Scanner findings SQLite store — persistent history for scanner alerts.

Backs ``GET /api/scanner/findings/history`` with the same schema the plan
specifies: ``scanner_findings`` (id, scanner_type, symbol, severity,
detail_json, timestamp). The in-memory ring buffer in ``ScannerProjection``
remains the fast path for the live findings endpoint; this store is the
durable record written alongside it.

Convention follows the other terminal stores (``knowledge/store.py``,
``learning/sessions.py``): stdlib ``sqlite3`` with ``timeout=5.0`` and
``CREATE TABLE IF NOT EXISTS`` on open.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scanner_findings (
    id TEXT PRIMARY KEY,
    scanner_type TEXT NOT NULL,
    symbol TEXT NOT NULL,
    severity TEXT NOT NULL,
    detail_json TEXT NOT NULL,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scanner_findings_type ON scanner_findings(scanner_type);
CREATE INDEX IF NOT EXISTS idx_scanner_findings_ts ON scanner_findings(timestamp);
"""


def _normalize_ts(value: Any) -> str:
    """Canonical UTC ISO-8601 string, sortable lexicographically."""
    if not value:
        return datetime.now(UTC).isoformat()
    try:
        dt = datetime.fromisoformat(str(value))
    except ValueError:
        return str(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


class ScannerStore:
    """SQLite-backed store for scanner findings."""

    def __init__(self, db_path: str | Path = "data/scanner_findings.db") -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), timeout=5.0)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record(self, finding: dict[str, Any]) -> str:
        """Persist one finding. Returns its row id.

        ``detail`` is JSON-serialised into ``detail_json``; ``timestamp`` is
        normalised to a sortable UTC ISO string. The id is taken from the
        finding when present, else generated.
        """
        finding_id = str(finding.get("id") or uuid.uuid4().hex)
        detail = finding.get("detail", {})
        try:
            detail_json = json.dumps(detail, default=str)
        except (TypeError, ValueError):
            detail_json = "{}"
        self._conn.execute(
            "INSERT OR REPLACE INTO scanner_findings "
            "(id, scanner_type, symbol, severity, detail_json, timestamp) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                finding_id,
                str(finding.get("scanner_type", "unknown")),
                str(finding.get("symbol", "")),
                str(finding.get("severity", "MEDIUM")),
                detail_json,
                _normalize_ts(finding.get("timestamp")),
            ),
        )
        self._conn.commit()
        return finding_id

    def list(
        self,
        scanner_type: str | None = None,
        limit: int = 100,
        since: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return findings, newest first, with the persisted detail un-JSON'd.

        Args:
            scanner_type: Optional filter by scanner type.
            limit: Max rows returned (clamped to 1..1000).
            since: Optional ISO timestamp — rows at or after it (string
                comparison on the canonical UTC format).
        """
        query = "SELECT id, scanner_type, symbol, severity, detail_json, timestamp FROM scanner_findings"
        clauses: list[str] = []
        params: list[Any] = []
        if scanner_type:
            clauses.append("scanner_type = ?")
            params.append(scanner_type)
        if since:
            clauses.append("timestamp >= ?")
            params.append(_normalize_ts(since))
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(max(1, min(int(limit), 1000)))
        rows = self._conn.execute(query, params).fetchall()
        findings: list[dict[str, Any]] = []
        for row_id, stype, symbol, severity, detail_json, ts in rows:
            try:
                detail = json.loads(detail_json) if detail_json else {}
            except ValueError:
                detail = {}
            findings.append({
                "id": row_id,
                "scanner_type": stype,
                "symbol": symbol,
                "severity": severity,
                "detail": detail,
                "timestamp": ts,
            })
        return findings

    def close(self) -> None:
        """Close the underlying connection (idempotent)."""
        try:
            self._conn.close()
        except Exception:
            logger.debug("scanner store close failed", exc_info=True)
