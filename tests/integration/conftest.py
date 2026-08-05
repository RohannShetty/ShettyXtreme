"""Shared fixtures for Fyers F1 tests.

Master rows are built in the live published shape (public.fyers.in) so the
SQLite master pipeline is exercised end-to-end.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any

import pytest

from shettyxtreme.integration.fyers.instrument_master import FyersInstrumentMaster
from shettyxtreme.integration.fyers.symbols import FyersSymbolResolver


def fyers_epoch(year: int, month: int, day: int) -> str:
    """Epoch string the master uses for ``expiryDate``."""
    return str(int(datetime(year, month, day, tzinfo=UTC).timestamp()))


def _default_ex_symbol(ticker: str) -> str:
    body = ticker.split(":", 1)[1]
    if body.endswith("-INDEX"):
        name = body[:-6]
        return {"NIFTY50": "NIFTY", "NIFTYBANK": "BANKNIFTY"}.get(name, name)
    if body.endswith("FUT"):
        return re.sub(
            r"\d{2}(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC|[1-9ONDL]\d{2})FUT$",
            "", body,
        )
    m = re.match(
        r"^(.*?)\d{2}(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC"
        r"|[1-9ONDL]\d{2})\d+(CE|PE)$",
        body,
    )
    if m:
        return m.group(1)
    if re.match(r"^.+-(EQ|BE|A)$", body):
        return body.rsplit("-", 1)[0]
    return body


def fyers_row(
    ticker: str,
    *,
    expiry: str = "",
    opt_type: str = "XX",
    strike: float = -1.0,
    lot: int = 1,
    tick: float = 0.05,
    isin: str = "INE000000000",
    series: str = "XX",
    inst_type: int = 0,
) -> dict[str, Any]:
    """Build a master row in the shape published by public.fyers.in."""
    ex = _default_ex_symbol(ticker)
    return {
        "fyToken": "100000000000001",
        "exToken": 1,
        "exSymbol": ex,
        "exSymName": ex,
        "exchange": 10,
        "segment": 11,
        "exSeries": series,
        "exInstType": inst_type,
        "tradeStatus": 1,
        "underSym": ex,
        "underFyTok": "100000000000001",
        "expiryDate": expiry,
        "optType": opt_type,
        "strikePrice": strike,
        "minLotSize": lot,
        "tickSize": tick,
        "isin": isin,
        "symDetails": "",
        "upperPrice": 0.0,
        "lowerPrice": 0.0,
        "faceValue": 0.0,
        "qtyFreeze": "0",
        "lastUpdate": "2026-08-04",
        "tradingSession": "0915-1530",
        "currencyCode": "INR",
        "symTicker": ticker,
        "exchangeName": ticker.split(":")[0],
        "symbolDesc": "",
        "qtyMultiplier": 1.0,
        "originalExpDate": None,
        "previousOi": 0.0,
        "previousClose": 0.0,
        "is_mtf_tradable": 0,
        "mtf_margin": 0.0,
        "asmGsmVal": "",
        "stream": "",
        "cautionary_msg": "",
        "symbolDetails": "",
        "mpp_flag": 0,
        "allow_pre_open": 1,
        "display_format_mob": "",
        "short_name": "",
        "has_options": False,
        "has_futures": False,
    }


MASTER_FIXTURE: dict[str, dict[str, Any]] = {
    "NSE:NIFTY50-INDEX": fyers_row("NSE:NIFTY50-INDEX", series="XX", inst_type=10),
    "NSE:NIFTYBANK-INDEX": fyers_row("NSE:NIFTYBANK-INDEX", series="XX", inst_type=10),
    "NSE:FINNIFTY-INDEX": fyers_row("NSE:FINNIFTY-INDEX", series="XX", inst_type=10),
    "NSE:SBIN-EQ": fyers_row("NSE:SBIN-EQ", series="EQ", isin="INE062A01020"),
    "NSE:M&M-EQ": fyers_row("NSE:M&M-EQ", series="EQ", isin="INE101A01026"),
    "NSE:NIFTY24OCT25000CE": fyers_row(
        "NSE:NIFTY24OCT25000CE", expiry=fyers_epoch(2024, 10, 31),
        opt_type="CE", strike=25000.0, lot=75, tick=0.05,
    ),
    "NSE:NIFTY24O0825000CE": fyers_row(
        "NSE:NIFTY24O0825000CE", expiry=fyers_epoch(2024, 10, 8),
        opt_type="CE", strike=25000.0, lot=75, tick=0.05,
    ),
    "NSE:NIFTY24OCTFUT": fyers_row(
        "NSE:NIFTY24OCTFUT", expiry=fyers_epoch(2024, 10, 31), lot=75,
    ),
    "NSE:NIFTY24O08FUT": fyers_row(
        "NSE:NIFTY24O08FUT", expiry=fyers_epoch(2024, 10, 8), lot=75,
    ),
    "NSE:NIFTY24N0825000CE": fyers_row(
        "NSE:NIFTY24N0825000CE", expiry=fyers_epoch(2024, 11, 8),
        opt_type="CE", strike=25000.0, lot=75,
    ),
    "NSE:NIFTY24D0825000PE": fyers_row(
        "NSE:NIFTY24D0825000PE", expiry=fyers_epoch(2024, 12, 8),
        opt_type="PE", strike=25000.0, lot=75,
    ),
}


@pytest.fixture
def master(tmp_path) -> FyersInstrumentMaster:
    db = FyersInstrumentMaster(db_path=str(tmp_path / "fyers.db"), masters=("NSE_CM",))
    db._upsert_master(MASTER_FIXTURE)
    yield db
    db.close()


@pytest.fixture
def resolver(master: FyersInstrumentMaster) -> FyersSymbolResolver:
    return FyersSymbolResolver(master=master)
