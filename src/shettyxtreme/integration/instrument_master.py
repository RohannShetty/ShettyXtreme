"""Instrument master: fetch security list from Dhan, store in SQLite.

Fetches the Dhan security list via dhanhq.fetch_security_list, stores
instruments in a local SQLite database, resolves symbols to security IDs,
and calculates next expiry dates (Thursday-based) with holiday awareness.
"""
from __future__ import annotations

import calendar
import logging
import os
import sqlite3
from datetime import date, datetime, timedelta
from typing import Any

from dhanhq import dhanhq as DhanHQClient

logger = logging.getLogger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)

# Simple holiday set (can be expanded or loaded from a config).
# These are examples of Indian market holidays that fall on/near Thursdays.
DEFAULT_HOLIDAYS: set[str] = set()


class InstrumentMaster:
    """Manages instrument metadata from Dhan API.

    Fetches security list, stores in SQLite for offline lookups,
    resolves symbols to security IDs, and calculates expiry dates
    with holiday awareness.
    """

    def __init__(
        self,
        db_path: str = "data/instruments.db",
        dhan_client: DhanHQClient | None = None,
        holidays: set[str] | None = None,
    ) -> None:
        """Initialize the instrument master.

        Args:
            db_path: Path to the SQLite database file.
            dhan_client: Optional pre-configured DhanHQ client.
            holidays: Set of holiday date strings (YYYY-MM-DD) to skip.
        """
        self._db_path: str = db_path
        self._dhan: DhanHQClient | None = dhan_client
        self._holidays: set[str] = holidays if holidays is not None else set(DEFAULT_HOLIDAYS)
        self._conn: sqlite3.Connection | None = None
        self._ensure_db_dir()
        self._init_db()

    def _ensure_db_dir(self) -> None:
        """Ensure the directory for the SQLite file exists."""
        db_dir: str = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    def _init_db(self) -> None:
        """Initialize the SQLite database with schema."""
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS instruments (
                security_id TEXT PRIMARY KEY,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                instrument_type TEXT,
                isin TEXT,
                company_name TEXT,
                UNIQUE(symbol, exchange)
            )
            """
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_symbol ON instruments(symbol)"
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_exchange ON instruments(exchange)"
        )
        self._conn.commit()

    def fetch_security_list(self) -> int:
        """Fetch security list from Dhan API and store in SQLite.

        Returns:
            Number of instruments inserted/updated.
        """
        if self._dhan is None:
            logger.warning("No Dhan client configured for fetch_security_list.")
            return 0
        try:
            data: Any = self._dhan.fetch_security_list()
            count: int = 0
            if isinstance(data, list):
                for row in data:
                    if not isinstance(row, dict):
                        continue
                    self._conn.execute(
                        """
                        INSERT OR REPLACE INTO instruments
                        (security_id, symbol, exchange, instrument_type, isin, company_name)
                        VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            str(row.get("SECURITY_ID", row.get("security_id", ""))),
                            str(row.get("TRADING_SYMBOL", row.get("symbol", ""))),
                            str(row.get("EXCHANGE", row.get("exchange", ""))),
                            str(row.get("INSTRUMENT_TYPE", row.get("instrument_type", ""))),
                            str(row.get("ISIN", row.get("isin", ""))),
                            str(row.get("COMPANY_NAME", row.get("company_name", ""))),
                        ),
                    )
                    count += 1
            self._conn.commit()
            logger.info("Fetched %d instruments from Dhan.", count)
            return count
        except Exception as exc:
            logger.error("fetch_security_list failed: %s", exc)
            return 0

    def resolve_symbol(self, symbol: str, exchange: str = "NSE") -> str | None:
        """Resolve a trading symbol to its Dhan security ID.

        Args:
            symbol: The trading symbol (e.g., 'RELIANCE').
            exchange: The exchange (NSE, BSE, etc.).

        Returns:
            The security ID string, or None if not found.
        """
        cursor = self._conn.execute(
            "SELECT security_id FROM instruments WHERE symbol = ? AND exchange = ?",
            (symbol.upper(), exchange.upper()),
        )
        row: tuple[Any, ...] | None = cursor.fetchone()
        if row is not None:
            return str(row[0])

        # Fallback: try case-insensitive
        cursor = self._conn.execute(
            "SELECT security_id FROM instruments WHERE UPPER(symbol) = ? AND UPPER(exchange) = ?",
            (symbol.upper(), exchange.upper()),
        )
        row = cursor.fetchone()
        return str(row[0]) if row is not None else None

    def get_next_weekly_expiry(self, from_date: date | None = None) -> date:
        """Calculate the next weekly expiry (Thursday).

        If the calculated Thursday is a holiday, skip to the next
        trading day (Friday, or Monday if Friday is also a holiday).

        Args:
            from_date: Starting date. Defaults to today.

        Returns:
            The next weekly expiry date.
        """
        start: date = from_date if from_date is not None else date.today()
        days_until_thursday: int = (3 - start.weekday()) % 7
        if days_until_thursday == 0 and start in self._holidays_as_dates():
            # Today is Thursday but it's a holiday
            days_until_thursday = 7
        expiry: date = start + timedelta(days=days_until_thursday)
        return self._adjust_for_holiday(expiry)

    def get_next_monthly_expiry(self, from_date: date | None = None) -> date:
        """Calculate the next monthly expiry (last Thursday of month).

        If the last Thursday is a holiday, skip to the previous trading
        day (Wednesday).

        Args:
            from_date: Starting date. Defaults to today.

        Returns:
            The next monthly expiry date.
        """
        start: date = from_date if from_date is not None else date.today()

        # Find the last Thursday of the current month
        last_day: int = calendar.monthrange(start.year, start.month)[1]
        last_date: date = date(start.year, start.month, last_day)
        # Last Thursday: go back from last day to the most recent Thursday
        days_back: int = (last_date.weekday() - 3) % 7
        last_thursday: date = last_date - timedelta(days=days_back)

        if last_thursday <= start:
            # This month's expiry has passed, use next month
            if start.month == 12:
                next_month: date = date(start.year + 1, 1, 1)
            else:
                next_month = date(start.year, start.month + 1, 1)
            last_day = calendar.monthrange(next_month.year, next_month.month)[1]
            last_date = date(next_month.year, next_month.month, last_day)
            days_back = (last_date.weekday() - 3) % 7
            last_thursday = last_date - timedelta(days=days_back)

        # Monthly expiry: if holiday, go to previous day (Wednesday)
        return self._adjust_monthly_expiry_for_holiday(last_thursday)

    def _holidays_as_dates(self) -> set[date]:
        """Convert holiday strings to date objects."""
        result: set[date] = set()
        for h in self._holidays:
            try:
                result.add(date.fromisoformat(h))
            except ValueError:
                pass
        return result

    def _adjust_for_holiday(self, expiry: date) -> date:
        """If expiry is a holiday, move to next trading day (weekly)."""
        holidays: set[date] = self._holidays_as_dates()
        current: date = expiry
        while current in holidays or current.weekday() >= 5:
            current += timedelta(days=1)
        return current

    def _adjust_monthly_expiry_for_holiday(self, expiry: date) -> date:
        """If monthly expiry is a holiday, move to previous trading day."""
        holidays: set[date] = self._holidays_as_dates()
        current: date = expiry
        while current in holidays or current.weekday() >= 5:
            current -= timedelta(days=1)
        return current

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
