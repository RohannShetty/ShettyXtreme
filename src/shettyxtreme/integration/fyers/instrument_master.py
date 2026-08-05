"""Fyers instrument master: download public symbol masters into SQLite.

Fyers publishes a daily instrument master as JSON at
``https://public.fyers.in/sym_details/<MASTER>_sym_master.json``. Each file
is a dict keyed by ``symTicker`` (e.g. ``NSE:SBIN-EQ``) whose value carries
the contract metadata (``expiryDate`` as epoch, ``optType``, ``strikePrice``,
``minLotSize``, ``tickSize``, ``isin``, ...). The master is refreshed every
trading day, so call :meth:`FyersInstrumentMaster.refresh` before relying on
lookups, and treat the master as the single source of truth for Fyers symbol
format (never hand-construct symbols).

Schema — table ``fyers_instruments``:

    fyers_symbol     TEXT PRIMARY KEY — raw ticker, e.g. ``NSE:SBIN-EQ``
    internal_symbol  TEXT             — e.g. ``SBIN``, ``NIFTY``, ``M&M``
    exchange         TEXT             — ``NSE`` | ``BSE`` | ``MCX`` (ticker prefix)
    instrument_type  TEXT             — ``EQUITY`` | ``INDEX`` | ``FUTURES``
                                       | ``OPTION`` | ``UNKNOWN``
    expiry           TEXT             — ISO date (YYYY-MM-DD), NULL for equity/index
    strike           REAL             — NULL for non-options
    option_type      TEXT             — ``CE`` | ``PE`` | ``XX``
    lot_size         INTEGER
    tick_size        REAL
    isin             TEXT
    raw_json         TEXT             — full original master row
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Self

import httpx

logger = logging.getLogger(__name__)

MASTER_BASE_URL = "https://public.fyers.in/sym_details"
DEFAULT_MASTERS: tuple[str, ...] = (
    "NSE_CM",
    "NSE_FO",
    "NSE_CD",
    "NSE_COM",
    "BSE_CM",
    "BSE_FO",
    "MCX_COM",
)
DEFAULT_DB_PATH = "data/fyers_instruments.db"

_COLUMNS = (
    "fyers_symbol",
    "internal_symbol",
    "exchange",
    "instrument_type",
    "expiry",
    "strike",
    "option_type",
    "lot_size",
    "tick_size",
    "isin",
    "raw_json",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS fyers_instruments (
    fyers_symbol TEXT PRIMARY KEY,
    internal_symbol TEXT NOT NULL,
    exchange TEXT NOT NULL,
    instrument_type TEXT NOT NULL,
    expiry TEXT,
    strike REAL,
    option_type TEXT,
    lot_size INTEGER,
    tick_size REAL,
    isin TEXT,
    raw_json TEXT NOT NULL
)
"""

# Instrument type derived from the ticker suffix. Order matters: check the
# most specific suffixes first.
_INST_RE = (
    (r"-INDEX$", "INDEX"),
    (r"FUT$", "FUTURES"),
    (r"(CE|PE)$", "OPTION"),
    (r"-[A-Z]{1,2}$", "EQUITY"),
)


def _parse_expiry(value: Any) -> str | None:
    """Convert the master's epoch ``expiryDate`` to an ISO date string."""
    if value is None:
        return None
    raw = str(value).strip()
    if raw in ("", "0", "-1", "None"):
        return None
    try:
        epoch = int(float(raw))
    except (TypeError, ValueError):
        return None
    if epoch <= 0:
        return None
    return datetime.fromtimestamp(epoch, tz=UTC).date().isoformat()


def _parse_strike(value: Any) -> float | None:
    """Convert ``strikePrice``; None for non-options (master uses -1.0)."""
    if value is None:
        return None
    try:
        strike = float(value)
    except (TypeError, ValueError):
        return None
    return strike if strike > 0 else None


def _parse_opt_type(value: Any) -> str | None:
    raw = str(value or "").strip().upper()
    return raw or None


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _derive_instrument_type(ticker: str) -> str:
    for pattern, inst_type in _INST_RE:
        if re.search(pattern, ticker):
            return inst_type
    return "UNKNOWN"


class FyersInstrumentMaster:
    """Local SQLite mirror of the Fyers instrument master."""

    def __init__(
        self,
        db_path: str = DEFAULT_DB_PATH,
        masters: Sequence[str] | None = None,
    ) -> None:
        """Initialize the SQLite store.

        Args:
            db_path: Path to the SQLite database file.
            masters: Names of the master files to refresh
                (defaults to ``DEFAULT_MASTERS``).
        """
        self._db_path: str = db_path
        self._masters: tuple[str, ...] = tuple(masters) if masters else DEFAULT_MASTERS
        self._conn: sqlite3.Connection | None = None
        self._ensure_db_dir()
        self._init_db()

    # ------------------------------------------------------------------ setup

    def _ensure_db_dir(self) -> None:
        db_dir = os.path.dirname(self._db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

    def _init_db(self) -> None:
        self._conn = sqlite3.connect(self._db_path)
        self._conn.execute(_SCHEMA)
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_fi_internal ON "
            "fyers_instruments(internal_symbol, exchange)"
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ----------------------------------------------------------------- refresh

    def refresh(
        self,
        masters: Sequence[str] | None = None,
        http_get: Callable[[str], bytes] | None = None,
        timeout: float = 120.0,
    ) -> dict[str, int]:
        """Download and upsert the master files.

        Args:
            masters: Subset of masters to refresh (defaults to the ones
                configured at construction).
            http_get: Optional callable ``url -> bytes`` used to fetch a
                master file. Defaults to ``httpx`` with the given timeout;
                injectable for tests and proxy use.
            timeout: HTTP timeout in seconds for the default fetcher.

        Returns:
            Mapping ``{master_name: rows_upserted}``. A failed download is
            logged and counted as 0 — it never aborts the other masters.
        """
        if http_get is None:
            http_get = self._default_http_get(timeout)
        selected = tuple(masters) if masters is not None else self._masters
        counts: dict[str, int] = {}
        for master in selected:
            url = f"{MASTER_BASE_URL}/{master}_sym_master.json"
            try:
                raw = http_get(url)
                data = json.loads(raw)
            except Exception as exc:  # noqa: BLE001 — a bad master must not kill refresh
                logger.warning("Fyers master download failed for %s: %s", master, exc)
                counts[master] = 0
                continue
            if not isinstance(data, dict):
                logger.warning("Fyers master %s is not a dict — skipping", master)
                counts[master] = 0
                continue
            counts[master] = self._upsert_master(data)
            logger.info("Fyers master %s: %d instruments upserted", master, counts[master])
        return counts

    def _default_http_get(self, timeout: float) -> Callable[[str], bytes]:
        def _get(url: str) -> bytes:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                resp = client.get(url)
                resp.raise_for_status()
                return resp.content

        return _get

    def _upsert_master(self, data: Mapping[str, Any]) -> int:
        """Insert/update every row from one parsed master file."""
        count = 0
        for ticker, row in data.items():
            if not isinstance(ticker, str) or not isinstance(row, dict):
                continue
            if not ticker.strip():
                continue
            self._upsert_row(ticker, row)
            count += 1
        self._conn.commit()
        return count

    def _upsert_row(self, ticker: str, row: Mapping[str, Any]) -> None:
        internal = str(row.get("exSymbol", row.get("symbol", ""))).strip()
        if not internal:
            internal = ticker.split(":", 1)[-1]
        exchange = ticker.split(":", 1)[0]
        self._conn.execute(
            """
            INSERT INTO fyers_instruments
            (fyers_symbol, internal_symbol, exchange, instrument_type,
             expiry, strike, option_type, lot_size, tick_size, isin, raw_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fyers_symbol) DO UPDATE SET
                internal_symbol=excluded.internal_symbol,
                exchange=excluded.exchange,
                instrument_type=excluded.instrument_type,
                expiry=excluded.expiry,
                strike=excluded.strike,
                option_type=excluded.option_type,
                lot_size=excluded.lot_size,
                tick_size=excluded.tick_size,
                isin=excluded.isin,
                raw_json=excluded.raw_json
            """,
            (
                ticker,
                internal,
                exchange,
                _derive_instrument_type(ticker),
                _parse_expiry(row.get("expiryDate")),
                _parse_strike(row.get("strikePrice")),
                _parse_opt_type(row.get("optType")),
                _as_int(row.get("minLotSize")),
                _as_float(row.get("tickSize")),
                str(row.get("isin", "")).strip() or None,
                json.dumps(row, ensure_ascii=False),
            ),
        )

    # ---------------------------------------------------------------- queries

    def count_instruments(self) -> int:
        """Number of instrument rows currently stored."""
        if self._conn is None:
            return 0
        row = self._conn.execute("SELECT COUNT(*) FROM fyers_instruments").fetchone()
        return int(row[0]) if row is not None else 0

    def lookup(self, fyers_symbol: str) -> dict[str, Any] | None:
        """Look up one instrument by its Fyers ticker.

        Accepts both the raw ticker (``NSE:M&M-EQ``) and its URL-encoded
        form (``NSE:M%26M-EQ``). Returns a row dict or ``None``.
        """
        if not isinstance(fyers_symbol, str):
            return None
        # The DB stores raw tickers; also accept URL-encoded input.
        from urllib.parse import unquote

        candidates = [fyers_symbol.strip()]
        decoded = unquote(fyers_symbol.strip())
        if decoded != candidates[0]:
            candidates.append(decoded)
        for candidate in candidates:
            row = self._conn.execute(
                "SELECT fyers_symbol, internal_symbol, exchange, instrument_type, "
                "expiry, strike, option_type, lot_size, tick_size, isin, raw_json "
                "FROM fyers_instruments WHERE fyers_symbol = ?",
                (candidate,),
            ).fetchone()
            if row is not None:
                return self._row_to_dict(row)
        return None

    def search(
        self,
        internal_symbol: str,
        exchange: str | None = None,
        instrument_type: str | None = None,
        expiry: Any = None,
        strike: float | None = None,
        option_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Search instruments by internal symbol with optional filters.

        Args:
            internal_symbol: Internal symbol (e.g. ``NIFTY``, ``M&M``).
            exchange: ``NSE`` | ``BSE`` | ``MCX`` (ticker prefix).
            instrument_type: ``EQUITY`` | ``INDEX`` | ``FUTURES`` | ``OPTION``.
            expiry: ISO date string or ``datetime.date``.
            strike: Exact strike price.
            option_type: ``CE`` | ``PE``.

        Returns:
            All matching rows (ordered by ticker).
        """
        if self._conn is None:
            return []
        clauses = ["internal_symbol = ?"]
        params: list[Any] = [internal_symbol]
        if exchange:
            clauses.append("exchange = ?")
            params.append(exchange.upper())
        if instrument_type:
            clauses.append("instrument_type = ?")
            params.append(instrument_type.upper())
        if expiry is not None:
            if hasattr(expiry, "isoformat"):
                expiry = expiry.isoformat()
            clauses.append("expiry = ?")
            params.append(str(expiry))
        if strike is not None:
            clauses.append("strike = ?")
            params.append(float(strike))
        if option_type:
            clauses.append("option_type = ?")
            params.append(option_type.upper())
        where = " AND ".join(clauses)
        rows = self._conn.execute(
            f"SELECT fyers_symbol, internal_symbol, exchange, instrument_type, "
            f"expiry, strike, option_type, lot_size, tick_size, isin, raw_json "
            f"FROM fyers_instruments WHERE {where} ORDER BY fyers_symbol",
            params,
        ).fetchall()
        return [self._row_to_dict(row) for row in rows]

    def _row_to_dict(self, row: tuple[Any, ...]) -> dict[str, Any]:
        return dict(zip(_COLUMNS, row))
