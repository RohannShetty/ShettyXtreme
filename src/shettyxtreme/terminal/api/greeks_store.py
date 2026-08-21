"""Greeks history SQLite store — portfolio greeks snapshots for charts (3A.4).

Records the aggregate net portfolio greeks (Δ/Γ/Θ/V) plus position count on
every position change so the frontend can render greeks history charts.
The store is created in the app lifespan and written from PositionProjection;
reads are served by GET /api/execution/greeks-history.
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS greeks_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    net_delta REAL NOT NULL,
    net_gamma REAL NOT NULL,
    net_theta REAL NOT NULL,
    net_vega REAL NOT NULL,
    position_count INTEGER NOT NULL,
    timestamp TEXT NOT NULL
);
"""


class GreeksStore:
    """SQLite persistence for portfolio greeks snapshots.

    A single persistent connection (5s busy timeout) guarded by a lock.
    ``check_same_thread=False`` lets the store be used from the asyncio event
    loop, the Starlette TestClient portal, and worker threads without sqlite
    thread-affinity errors — same philosophy as SettingsStore.
    """

    def __init__(self, db_path: str | Path = "data/greeks.db") -> None:
        self._db_path = str(db_path)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._db_path, timeout=5.0, check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def record(
        self,
        net_delta: float,
        net_gamma: float,
        net_theta: float,
        net_vega: float,
        position_count: int,
    ) -> None:
        """Append a portfolio greeks snapshot stamped with the current time."""
        ts = datetime.now(UTC).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO greeks_history "
                "(net_delta, net_gamma, net_theta, net_vega, position_count, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    float(net_delta),
                    float(net_gamma),
                    float(net_theta),
                    float(net_vega),
                    int(position_count),
                    ts,
                ),
            )
            self._conn.commit()

    def get_history(self, days: int = 7) -> list[dict[str, Any]]:
        """Return snapshots from the last ``days`` days, oldest first.

        Each entry: ``{timestamp, net_delta, net_gamma, net_theta, net_vega,
        position_count}``. Timestamps are stored as UTC ISO-8601 strings, so
        the cutoff comparison is lexicographic over a uniform format.
        """
        cutoff = (datetime.now(UTC) - timedelta(days=max(1, days))).isoformat()
        with self._lock:
            rows = self._conn.execute(
                "SELECT net_delta, net_gamma, net_theta, net_vega, position_count, timestamp "
                "FROM greeks_history WHERE timestamp >= ? ORDER BY id ASC",
                (cutoff,),
            ).fetchall()
        return [
            {
                "timestamp": r[5],
                "net_delta": r[0],
                "net_gamma": r[1],
                "net_theta": r[2],
                "net_vega": r[3],
                "position_count": r[4],
            }
            for r in rows
        ]

    def close(self) -> None:
        """Close the underlying connection (idempotent)."""
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass
