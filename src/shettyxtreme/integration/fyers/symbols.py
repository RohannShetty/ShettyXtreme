"""Fyers symbol resolution: internal symbols <-> Fyers tickers.

Implements the Fyers symbol format:

    Equity:    ``NSE:SBIN-EQ``                       (series: -EQ, -BE, -A)
    Index:     ``NSE:NIFTY50-INDEX``                 (BANKNIFTY -> NSE:NIFTYBANK-INDEX)
    Futures:   ``NSE:NIFTY24OCTFUT``      (monthly)  ``NSE:NIFTY24O08FUT``    (weekly)
    Options:   ``NSE:NIFTY24OCT25000CE``  (monthly)  ``NSE:NIFTY24O0825000CE`` (weekly)

Weekly month codes: ``1-9`` for Jan-Sep, ``O`` for Oct, ``N`` for Nov, ``D``
for Dec. Weekly days are zero-padded to two digits — verified against the live
master (e.g. ``NSE:EURINR26O01104CE`` = 26-Oct-01). Strike is an integer with
no decimals. Special characters are URL-encoded for the wire form
(``NSE:M&M-EQ`` -> ``NSE:M%26M-EQ``).

Monthly vs weekly detection: a contract is **monthly** when the expiry is the
last occurrence of its weekday within the month (2024-era monthly expiries
were the last Thursday; post-SEBI-2025 index expiries moved to the last
Tuesday — both are handled). Everything else is weekly.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import quote, unquote

# ---------------------------------------------------------------------------
# Month code tables
# ---------------------------------------------------------------------------

_MONTH_ABBR: dict[int, str] = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR", 5: "MAY", 6: "JUN",
    7: "JUL", 8: "AUG", 9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}
_MONTH_ABBR_REV: dict[str, int] = {abbr: month for month, abbr in _MONTH_ABBR.items()}

# Weekly month codes: 1-9 for Jan-Sep, O/N/D for Oct/Nov/Dec.
_WEEKLY_MONTH_CODE: dict[int, str] = {
    1: "1", 2: "2", 3: "3", 4: "4", 5: "5", 6: "6",
    7: "7", 8: "8", 9: "9", 10: "O", 11: "N", 12: "D",
}
_WEEKLY_MONTH_REV: dict[str, int] = {code: month for month, code in _WEEKLY_MONTH_CODE.items()}

# Index ticker mapping: the Fyers index ticker differs from the internal name
# for NIFTY (NIFTY50) and BANKNIFTY (NIFTYBANK).
_INDEX_INTERNAL_TO_TICKER: dict[str, str] = {
    "NIFTY": "NIFTY50-INDEX",
    "BANKNIFTY": "NIFTYBANK-INDEX",
    "FINNIFTY": "FINNIFTY-INDEX",
}
_INDEX_TICKER_TO_INTERNAL: dict[str, str] = {
    ticker[:-6]: internal for internal, ticker in _INDEX_INTERNAL_TO_TICKER.items()
}

# Equity series suffixes (from the master's exSeries values).
_EQUITY_SERIES: frozenset[str] = frozenset(
    {"EQ", "BE", "A", "BZ", "B", "S", "T", "X", "Z"}
)

# Internal exchange names -> Fyers ticker prefix.
_EXCHANGE_TO_PREFIX: dict[str, str] = {
    "NSE": "NSE", "NSE_FNO": "NSE", "NFO": "NSE", "NSE_EQ": "NSE",
    "NSE_CM": "NSE", "NSE_CD": "NSE", "IDX_I": "NSE",
    "BSE": "BSE", "BSE_FNO": "BSE", "BFO": "BSE", "BSE_EQ": "BSE",
    "MCX": "MCX", "MCX_FNO": "MCX", "MCX_COM": "MCX",
}

# Ticker prefixes for derivatives live on the F&O segment of an exchange.
_DERIVATIVE_TYPES: frozenset[str] = frozenset({"INDEX", "FUTURES", "OPTION"})

_MONTHLY_MMM = "(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)"
_WEEKLY_MC = "[1-9ONDL]"
_UNDERLYING = r"[A-Z0-9&]+?"
_OPTION_TAIL = r"(?:CE|PE)"

_RE_MONTHLY_OPTION = re.compile(rf"^({_UNDERLYING})(\d{{2}})({_MONTHLY_MMM})(\d+)({_OPTION_TAIL})$")
_RE_WEEKLY_OPTION = re.compile(rf"^({_UNDERLYING})(\d{{2}})({_WEEKLY_MC})(\d{{2}})(\d+)({_OPTION_TAIL})$")
_RE_MONTHLY_FUTURE = re.compile(rf"^({_UNDERLYING})(\d{{2}})({_MONTHLY_MMM})FUT$")
_RE_WEEKLY_FUTURE = re.compile(rf"^({_UNDERLYING})(\d{{2}})({_WEEKLY_MC})(\d{{2}})FUT$")
_RE_EQUITY = re.compile(r"^(.+)-([A-Z]{1,2})$")


class SymbolNotFoundError(ValueError):
    """Raised when a constructed Fyers symbol is absent from the instrument master."""


class FyersSymbolResolver:
    """Bind ``to_fyers`` / ``from_fyers`` to an instrument master.

    When a master is bound, ``to_fyers`` validates the constructed symbol
    against it and raises :class:`SymbolNotFoundError` for unknown symbols
    (the exact-match gate that prevents the Fyers ``-300`` weekly-vs-monthly
    encoding gotcha from reaching the wire).
    """

    def __init__(self, master: Any = None) -> None:
        self.master = master

    def to_fyers(
        self,
        internal_symbol: str,
        exchange: str,
        instrument_type: str,
        expiry: Any = None,
        strike: Any = None,
        option_type: str | None = None,
        series: str = "EQ",
    ) -> str:
        return to_fyers(
            internal_symbol,
            exchange,
            instrument_type,
            expiry=expiry,
            strike=strike,
            option_type=option_type,
            series=series,
            master=self.master,
        )

    def from_fyers(self, fyers_symbol: str) -> dict[str, Any]:
        return from_fyers(fyers_symbol)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _coerce_date(value: Any, required: bool = False, label: str = "expiry") -> date | None:
    """Coerce a date, ISO string, or datetime to ``datetime.date``."""
    if value is None:
        if required:
            raise ValueError(f"{label} is required for this symbol type")
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value.strip())
        except ValueError as exc:
            raise ValueError(
                f"{label} must be an ISO date (YYYY-MM-DD), got {value!r}"
            ) from exc
    raise ValueError(f"{label} must be a date or ISO string, got {value!r}")


def _exchange_prefix(exchange: str) -> str:
    prefix = _EXCHANGE_TO_PREFIX.get(exchange.upper())
    if prefix is None:
        raise ValueError(f"Unsupported exchange for Fyers: {exchange!r}")
    return prefix


def _prefix_to_exchange(prefix: str, instrument_type: str) -> str:
    """Map a ticker prefix back to the canonical internal exchange name."""
    if prefix == "NSE":
        return "NSE_FNO" if instrument_type in _DERIVATIVE_TYPES else "NSE"
    if prefix == "BSE":
        return "BSE_FNO" if instrument_type in _DERIVATIVE_TYPES else "BSE"
    return prefix  # MCX


def _index_ticker(internal_symbol: str) -> str:
    return _INDEX_INTERNAL_TO_TICKER.get(internal_symbol, f"{internal_symbol}-INDEX")


def _index_internal(ticker_name: str) -> str:
    """Reverse an index ticker name (e.g. ``NIFTY50`` -> ``NIFTY``)."""
    return _INDEX_TICKER_TO_INTERNAL.get(ticker_name, ticker_name)


def _format_strike(strike: Any) -> str:
    """Format a strike as an integer string (Fyers strikes have no decimals)."""
    if isinstance(strike, int):
        return str(strike)
    value = float(strike)
    if value.is_integer():
        return str(int(value))
    return repr(value)


def is_monthly_expiry(expiry: Any) -> bool:
    """True when the expiry is the last occurrence of its weekday in the month.

    Verified against the live master: monthly contracts (``26AUG`` style)
    expire on the last weekday-of-month, weeklies on every other occurrence
    (``26804`` style). This covers both the 2024 Thursday convention and the
    post-2025 Tuesday convention.
    """
    d = _coerce_date(expiry, required=True)
    return (d + timedelta(days=7)).month != d.month


# ---------------------------------------------------------------------------
# to_fyers
# ---------------------------------------------------------------------------

def to_fyers(
    internal_symbol: str,
    exchange: str,
    instrument_type: str,
    expiry: Any = None,
    strike: Any = None,
    option_type: str | None = None,
    series: str = "EQ",
    master: Any = None,
) -> str:
    """Convert an internal symbol to its Fyers ticker (URL-encoded).

    Args:
        internal_symbol: e.g. ``NIFTY``, ``BANKNIFTY``, ``RELIANCE``, ``M&M``.
        exchange: ``NSE``, ``BSE``, ``NFO``, ``BFO``, ``MCX``, ``NSE_FNO`` ...
        instrument_type: ``INDEX`` | ``EQUITY`` | ``FUTURES`` | ``OPTION``.
        expiry: Expiry as ``date``, ISO string, or ``datetime`` (required for
            FUTURES/OPTION). If it is the last weekday-of-month occurrence the
            monthly format is used, otherwise the weekly format.
        strike: Integer strike (required for OPTION).
        option_type: ``CE`` or ``PE`` (required for OPTION).
        series: Equity series suffix (default ``EQ``; also ``BE``, ``A``).
        master: Optional :class:`FyersInstrumentMaster`. When provided, the
            constructed symbol is validated by exact lookup and
            :class:`SymbolNotFoundError` is raised for unknown symbols.

    Returns:
        The Fyers ticker with special characters URL-encoded, e.g.
        ``NSE:M%26M-EQ``.
    """
    if master is not None and not hasattr(master, "lookup"):
        raise TypeError("master must provide a lookup() method")
    symbol = str(internal_symbol).strip().upper()
    if not symbol:
        raise ValueError("internal_symbol is required")
    prefix = _exchange_prefix(str(exchange))
    inst_type = str(instrument_type).strip().upper()

    if inst_type == "INDEX":
        ticker = f"{prefix}:{_index_ticker(symbol)}"
    elif inst_type == "EQUITY":
        ticker = f"{prefix}:{symbol}-{str(series).upper()}"
    elif inst_type in ("FUTURES", "FUTURE", "FUT"):
        exp = _coerce_date(expiry, required=True)
        if is_monthly_expiry(exp):
            ticker = f"{prefix}:{symbol}{exp.year % 100:02d}{_MONTH_ABBR[exp.month]}FUT"
        else:
            ticker = (
                f"{prefix}:{symbol}{exp.year % 100:02d}"
                f"{_WEEKLY_MONTH_CODE[exp.month]}{exp.day:02d}FUT"
            )
    elif inst_type in ("OPTION", "OPTIONS", "OPT"):
        exp = _coerce_date(expiry, required=True)
        if strike is None:
            raise ValueError("strike is required for OPTION symbols")
        opt = str(option_type or "").strip().upper()
        if opt not in ("CE", "PE"):
            raise ValueError(f"option_type must be CE or PE, got {option_type!r}")
        strike_str = _format_strike(strike)
        if is_monthly_expiry(exp):
            ticker = (
                f"{prefix}:{symbol}{exp.year % 100:02d}"
                f"{_MONTH_ABBR[exp.month]}{strike_str}{opt}"
            )
        else:
            ticker = (
                f"{prefix}:{symbol}{exp.year % 100:02d}"
                f"{_WEEKLY_MONTH_CODE[exp.month]}{exp.day:02d}{strike_str}{opt}"
            )
    else:
        raise ValueError(f"Unsupported instrument_type: {instrument_type!r}")

    if master is not None and master.lookup(ticker) is None:
        raise SymbolNotFoundError(
            f"Symbol {ticker} not found in the Fyers instrument master"
        )
    return quote(ticker, safe=":")


# ---------------------------------------------------------------------------
# from_fyers
# ---------------------------------------------------------------------------

def from_fyers(fyers_symbol: str) -> dict[str, Any]:
    """Parse a Fyers ticker into its internal representation.

    Args:
        fyers_symbol: A Fyers ticker, raw (``NSE:M&M-EQ``) or URL-encoded
            (``NSE:M%26M-EQ``).

    Returns:
        ``{"internal_symbol", "exchange", "instrument_type", "expiry",
        "strike", "option_type"}``. ``expiry`` is a ``datetime.date`` (monthly
        contracts encode only the month, so the day is set to the 1st).

    Raises:
        ValueError: When the ticker does not follow a recognized Fyers format.
    """
    if not isinstance(fyers_symbol, str) or ":" not in fyers_symbol:
        raise ValueError(f"Invalid Fyers symbol: {fyers_symbol!r}")
    ticker = unquote(fyers_symbol.strip()).upper()
    prefix, body = ticker.split(":", 1)
    prefix = prefix.strip()
    body = body.strip()
    if not prefix or not body:
        raise ValueError(f"Invalid Fyers symbol: {fyers_symbol!r}")

    # INDEX — NSE:NIFTY50-INDEX
    if body.endswith("-INDEX"):
        name = body[:-6]
        return {
            "internal_symbol": _index_internal(name),
            "exchange": _prefix_to_exchange(prefix, "INDEX"),
            "instrument_type": "INDEX",
            "expiry": None,
            "strike": None,
            "option_type": None,
        }

    # OPTION — monthly: NSE:NIFTY24OCT25000CE
    m = _RE_MONTHLY_OPTION.match(body)
    if m:
        internal, yy, mmm, strike, opt = m.groups()
        expiry = date(2000 + int(yy), _MONTH_ABBR_REV[mmm], 1)
        return {
            "internal_symbol": internal,
            "exchange": _prefix_to_exchange(prefix, "OPTION"),
            "instrument_type": "OPTION",
            "expiry": expiry,
            "strike": int(strike),
            "option_type": opt,
        }

    # OPTION — weekly: NSE:NIFTY24O0825000CE
    m = _RE_WEEKLY_OPTION.match(body)
    if m:
        internal, yy, mcode, dd, strike, opt = m.groups()
        expiry = date(2000 + int(yy), _WEEKLY_MONTH_REV[mcode], int(dd))
        return {
            "internal_symbol": internal,
            "exchange": _prefix_to_exchange(prefix, "OPTION"),
            "instrument_type": "OPTION",
            "expiry": expiry,
            "strike": int(strike),
            "option_type": opt,
        }

    # FUTURES — monthly: NSE:NIFTY24OCTFUT
    m = _RE_MONTHLY_FUTURE.match(body)
    if m:
        internal, yy, mmm = m.groups()
        expiry = date(2000 + int(yy), _MONTH_ABBR_REV[mmm], 1)
        return {
            "internal_symbol": internal,
            "exchange": _prefix_to_exchange(prefix, "FUTURES"),
            "instrument_type": "FUTURES",
            "expiry": expiry,
            "strike": None,
            "option_type": None,
        }

    # FUTURES — weekly: NSE:NIFTY24O08FUT
    m = _RE_WEEKLY_FUTURE.match(body)
    if m:
        internal, yy, mcode, dd = m.groups()
        expiry = date(2000 + int(yy), _WEEKLY_MONTH_REV[mcode], int(dd))
        return {
            "internal_symbol": internal,
            "exchange": _prefix_to_exchange(prefix, "FUTURES"),
            "instrument_type": "FUTURES",
            "expiry": expiry,
            "strike": None,
            "option_type": None,
        }

    # EQUITY — NSE:SBIN-EQ, NSE:M&M-EQ
    m = _RE_EQUITY.match(body)
    if m and m.group(2) in _EQUITY_SERIES:
        return {
            "internal_symbol": m.group(1),
            "exchange": _prefix_to_exchange(prefix, "EQUITY"),
            "instrument_type": "EQUITY",
            "expiry": None,
            "strike": None,
            "option_type": None,
        }

    raise ValueError(f"Unrecognized Fyers symbol: {fyers_symbol!r}")
