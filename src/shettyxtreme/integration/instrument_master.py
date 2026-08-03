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
from datetime import date, timedelta
from typing import Any

from dhanhq import dhanhq as DhanHQClient

logger = logging.getLogger(__name__)

IST_OFFSET = timedelta(hours=5, minutes=30)

# Simple holiday set (can be expanded or loaded from a config).
# These are examples of Indian market holidays that fall on/near Thursdays.
DEFAULT_HOLIDAYS: set[str] = set()

# Exchange aliases: UI/exchange names ↔ Dhan feed segment names stored in
# the security CSV (e.g. NSE_EQ is stored for NSE equities).
_EXCHANGE_ALIASES: dict[str, tuple[str, ...]] = {
    "NSE": ("NSE", "NSE_EQ"),
    "NFO": ("NFO", "NSE_FNO"),
    "BSE": ("BSE", "BSE_EQ"),
    "BFO": ("BFO", "BSE_FNO"),
    "NSE_FNO": ("NSE_FNO", "NFO"),
    "NSE_EQ": ("NSE_EQ", "NSE"),
    "BSE_EQ": ("BSE_EQ", "BSE"),
    "BSE_FNO": ("BSE_FNO", "BFO"),
}

# CSV (SEM_EXM_EXCH_ID, SEM_SEGMENT) -> Dhan feed segment stored in `exchange`.
_SEGMENT_EXCHANGE: dict[tuple[str, str], str] = {
    ("NSE", "E"): "NSE_EQ", ("NSE", "I"): "NSE_FNO",
    ("NSE", "F"): "NSE_FNO", ("NSE", "C"): "NSE_FNO",
    ("BSE", "E"): "BSE_EQ", ("BSE", "I"): "BSE_FNO",
    ("BSE", "F"): "BSE_FNO", ("BSE", "C"): "BSE_FNO",
}

# Expected columns for the instruments table (schema v2: no PK on security_id).
_EXPECTED_COLUMNS: frozenset[str] = frozenset({
    "security_id", "symbol", "exchange", "instrument_type",
    "isin", "company_name", "strike", "expiry",
})


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
        self._drop_legacy_schema()
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS instruments (
                security_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                exchange TEXT NOT NULL,
                instrument_type TEXT,
                isin TEXT,
                company_name TEXT,
                strike TEXT,
                expiry TEXT,
                UNIQUE(symbol, exchange),
                UNIQUE(exchange, security_id)
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

    def _drop_legacy_schema(self) -> None:
        """Drop a pre-v2 instruments table (security_id PRIMARY KEY, no strike/expiry)."""
        columns: set[str] = set()
        try:
            for row in self._conn.execute("PRAGMA table_info(instruments)"):
                columns.add(str(row[1]))
        except sqlite3.Error:
            columns = set()
        if columns and columns != _EXPECTED_COLUMNS:
            logger.warning("instruments table has incompatible schema — dropping and recreating")
            self._conn.execute("DROP TABLE IF EXISTS instruments")
            self._conn.commit()

    def count_instruments(self) -> int:
        """Return the number of instruments stored in the local database."""
        cursor = self._conn.execute("SELECT COUNT(*) FROM instruments")
        row = cursor.fetchone()
        return int(row[0]) if row is not None else 0

    def fetch_security_list(self) -> int:
        """Fetch security list from Dhan API and store in SQLite.

        Accepts the dhanhq SDK shapes (a pandas DataFrame from the static
        CSV download with SEM_* columns, or a list of row dicts with
        SECURITY_ID / TRADING_SYMBOL / EXCHANGE keys) and stores the
        security ID, trading symbol, feed segment, type, and company name.

        Returns:
            Number of instruments inserted/updated, or 0 if nothing was
            inserted (the caller must not report a fake population).
        """
        if self._dhan is None:
            logger.warning("No Dhan client configured for fetch_security_list.")
            return 0
        try:
            data: Any = self._dhan.fetch_security_list()
            if hasattr(data, "to_dict"):  # pandas DataFrame from the real SDK
                rows = data.to_dict("records")
            elif isinstance(data, list):
                rows = data
            else:
                rows = []
            count: int = 0
            for row in rows:
                if not isinstance(row, dict):
                    continue
                security_id = str(row.get("SEM_SMST_SECURITY_ID", row.get("SECURITY_ID", row.get("security_id", ""))))
                if not security_id:
                    continue
                self._conn.execute(
                    """
                    INSERT OR REPLACE INTO instruments
                    (security_id, symbol, exchange, instrument_type, isin, company_name, strike, expiry)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        security_id,
                        str(row.get("SEM_TRADING_SYMBOL", row.get("TRADING_SYMBOL", row.get("symbol", "")))),
                        self._row_exchange(row),
                        str(row.get("SEM_EXCH_INSTRUMENT_TYPE", row.get("INSTRUMENT_TYPE", row.get("instrument_type", "")))),
                        str(row.get("ISIN", row.get("isin", ""))),
                        str(row.get("SM_SYMBOL_NAME", row.get("COMPANY_NAME", row.get("company_name", "")))),
                        str(row.get("SEM_STRIKE_PRICE", row.get("strike", ""))),
                        str(row.get("SEM_EXPIRY_DATE", row.get("expiry", ""))),
                    ),
                )
                count += 1
            self._conn.commit()
            if count == 0:
                logger.error("fetch_security_list: zero rows inserted — source keys mismatched?")
                return 0
            logger.info("Fetched %d instruments from Dhan.", count)
            return count
        except Exception as exc:
            logger.error("fetch_security_list failed: %s", exc)
            return 0

    @staticmethod
    def _row_exchange(row: dict[str, Any]) -> str:
        """Derive the Dhan feed segment from a CSV row (SEM_EXM_EXCH_ID + SEM_SEGMENT).

        Falls back to the legacy EXCHANGE/EXCHANGE_SEGMENT keys verbatim.
        """
        sem_exch = row.get("SEM_EXM_EXCH_ID")
        sem_seg = row.get("SEM_SEGMENT")
        if sem_exch and sem_seg:
            ex = str(sem_exch).upper()
            seg = str(sem_seg).upper()
            if ex == "MCX":
                return "MCX"
            return _SEGMENT_EXCHANGE.get((ex, seg), ex)
        return str(
            row.get("EXCHANGE_SEGMENT", row.get("EXCHANGE", row.get("exchange", "")))
        )

    def resolve_symbol(self, symbol: str, exchange: str = "NSE") -> str | None:
        """Resolve a trading symbol to its Dhan security ID.

        Args:
            symbol: The trading symbol (e.g., 'RELIANCE').
            exchange: The exchange (NSE, BSE, etc.) or a feed segment
                (NSE_EQ, NSE_FNO) — aliases are normalized.

        Returns:
            The security ID string, or None if not found.
        """
        exchange_upper = exchange.upper()
        aliases = _EXCHANGE_ALIASES.get(exchange_upper, (exchange_upper,))
        placeholders = ",".join("?" for _ in aliases)
        cursor = self._conn.execute(
            f"SELECT security_id FROM instruments WHERE UPPER(symbol) = ? AND UPPER(exchange) IN ({placeholders})",
            (symbol.upper(), *aliases),
        )
        row = cursor.fetchone()
        if row is not None:
            return str(row[0])

        # Fallback: ignore the exchange entirely (one security ID per scrip).
        # ORDER BY exchange keeps the result deterministic when a symbol lists
        # on several exchanges (NSE_* sorts before BSE_*).
        cursor = self._conn.execute(
            "SELECT security_id FROM instruments WHERE UPPER(symbol) = ? ORDER BY exchange",
            (symbol.upper(),),
        )
        row = cursor.fetchone()
        return str(row[0]) if row is not None else None

    def resolve_security_id(self, security_id: str | int, exchange: str | None = None) -> str | None:
        """Resolve a Dhan security ID to its trading symbol (reverse lookup).

        Args:
            security_id: The Dhan security ID (e.g., '13' for NIFTY).
            exchange: Optional exchange filter (NSE, NSE_FNO, etc.).

        Returns:
            The trading symbol (e.g., 'NIFTY'), or None if not found.
        """
        if exchange:
            exchange_upper = exchange.upper()
            aliases = _EXCHANGE_ALIASES.get(exchange_upper, (exchange_upper,))
            placeholders = ",".join("?" for _ in aliases)
            cursor = self._conn.execute(
                f"SELECT symbol FROM instruments WHERE security_id = ? AND UPPER(exchange) IN ({placeholders})",
                (str(security_id), *aliases),
            )
            row = cursor.fetchone()
            if row is not None:
                return str(row[0])
        # Fallback without an exchange: security IDs repeat across segments
        # (13 = ABB on NSE_EQ and NIFTY on NSE_FNO), so the result is
        # ambiguous — callers should pass an exchange. ORDER BY exchange keeps
        # whatever it returns deterministic.
        cursor = self._conn.execute(
            "SELECT symbol FROM instruments WHERE security_id = ? ORDER BY exchange",
            (str(security_id),),
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
