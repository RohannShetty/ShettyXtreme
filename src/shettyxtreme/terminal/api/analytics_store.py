"""SQLite persistence for analytics time series (max pain + regime history).

Phase 3A.3: persists max-pain and regime-change snapshots so the
``/api/analytics/max-pain-history`` and ``/api/analytics/regime-history``
endpoints can serve chart-ready time series across restarts.

Design notes:
- Two small tables, five public methods; timestamps are stored as ISO-8601
  strings (UTC), so the ``timestamp >= cutoff`` filters in the getters are
  plain lexicographic comparisons.
- All methods raise ``sqlite3.Error`` on failure; callers (router endpoints,
  projection hooks) translate that into empty payloads or logged warnings —
  the store itself never swallows errors.
- ``timeout=5.0`` on connect so a busy locked database degrades instead of
  hanging the terminal.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Any

_MAX_PAIN_DDL = """
CREATE TABLE IF NOT EXISTS max_pain_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    expiry TEXT NOT NULL DEFAULT '',
    max_pain REAL NOT NULL,
    spot_price REAL,
    timestamp TEXT NOT NULL
)
"""

_REGIME_DDL = """
CREATE TABLE IF NOT EXISTS regime_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    regime TEXT NOT NULL,
    confidence REAL NOT NULL,
    adx REAL,
    di_plus REAL,
    di_minus REAL,
    timestamp TEXT NOT NULL
)
"""


class AnalyticsStore:
    """SQLite store for max-pain and regime time series."""

    def __init__(self, db_path: str = "data/analytics.db") -> None:
        """Open (creating if needed) the analytics database.

        Args:
            db_path: SQLite database file path.
        """
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, timeout=5.0)
        self._conn.execute(_MAX_PAIN_DDL)
        self._conn.execute(_REGIME_DDL)
        self._conn.commit()

    # ── Recording ──────────────────────────────────────────────────────────

    def record_max_pain(
        self,
        symbol: str,
        expiry: str,
        max_pain: float,
        spot_price: float | None = None,
    ) -> None:
        """Record one max-pain snapshot (one per chain poll).

        Args:
            symbol: Underlying symbol.
            expiry: Expiry string the max pain was computed for.
            max_pain: The max-pain strike price.
            spot_price: Optional underlying spot price at record time.
        """
        self._conn.execute(
            "INSERT INTO max_pain_history (symbol, expiry, max_pain, spot_price, timestamp)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                symbol,
                expiry,
                float(max_pain),
                spot_price,
                datetime.now(UTC).isoformat(),
            ),
        )
        self._conn.commit()

    def record_regime(
        self,
        regime: str,
        confidence: float,
        adx: float | None = None,
        di_plus: float | None = None,
        di_minus: float | None = None,
    ) -> None:
        """Record one regime snapshot (one per regime change).

        Args:
            regime: Regime name (e.g. ``trending_up``, ``range_bound``).
            confidence: Regime confidence (0-1).
            adx: Optional ADX value at record time.
            di_plus: Optional +DI value at record time.
            di_minus: Optional -DI value at record time.
        """
        self._conn.execute(
            "INSERT INTO regime_history (regime, confidence, adx, di_plus, di_minus, timestamp)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                regime,
                float(confidence),
                adx,
                di_plus,
                di_minus,
                datetime.now(UTC).isoformat(),
            ),
        )
        self._conn.commit()

    # ── History queries ────────────────────────────────────────────────────

    def get_max_pain_history(self, symbol: str, days: int = 30) -> list[dict[str, Any]]:
        """Return max-pain snapshots for a symbol within the last N days.

        Args:
            symbol: Underlying symbol to filter by.
            days: How many days of history to return (default 30). Clamped
                to >= 1.

        Returns:
            Chronological list of ``{timestamp, max_pain, spot_price}`` dicts.
        """
        cutoff = (datetime.now(UTC) - timedelta(days=max(1, days))).isoformat()
        rows = self._conn.execute(
            "SELECT timestamp, max_pain, spot_price FROM max_pain_history"
            " WHERE symbol = ? AND timestamp >= ? ORDER BY timestamp",
            (symbol, cutoff),
        ).fetchall()
        return [
            {"timestamp": row[0], "max_pain": row[1], "spot_price": row[2]}
            for row in rows
        ]

    def get_regime_history(self, days: int = 30) -> list[dict[str, Any]]:
        """Return regime snapshots within the last N days.

        Args:
            days: How many days of history to return (default 30). Clamped
                to >= 1.

        Returns:
            Chronological list of ``{timestamp, regime, confidence, adx}``
            dicts.
        """
        cutoff = (datetime.now(UTC) - timedelta(days=max(1, days))).isoformat()
        rows = self._conn.execute(
            "SELECT timestamp, regime, confidence, adx FROM regime_history"
            " WHERE timestamp >= ? ORDER BY timestamp",
            (cutoff,),
        ).fetchall()
        return [
            {"timestamp": row[0], "regime": row[1], "confidence": row[2], "adx": row[3]}
            for row in rows
        ]

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        self._conn.close()
