"""P1-2.2 — Expiry calendar intelligence tests.

Tests for:
- list_expiries() on the instrument master
- classify_expiry() weekly/monthly classification
- resolve_default_expiry() policy-driven default selection
- MIDCPNIFTY in INDEX_SYMBOLS and _INDEX_INTERNAL_TO_TICKER
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

import pytest

from shettyxtreme.integration.fyers._util import INDEX_SYMBOLS
from shettyxtreme.integration.fyers.instrument_master import FyersInstrumentMaster
from shettyxtreme.integration.fyers.symbols import (
    _INDEX_INTERNAL_TO_TICKER,
    classify_expiry,
    resolve_default_expiry,
)

from .conftest import fyers_epoch, fyers_row


# ── helpers ────────────────────────────────────────────────────────────────


def _future_date(days_ahead: int) -> date:
    """A date `days_ahead` from today."""
    return datetime.now(UTC).date() + timedelta(days=days_ahead)


def _next_weekday(d: date, weekday: int) -> date:
    """Next occurrence of `weekday` (Mon=0..Sun=6) on or after `d`."""
    days_ahead = (weekday - d.weekday()) % 7
    if days_ahead == 0 and d.weekday() != weekday:
        days_ahead = 7
    return d + timedelta(days=days_ahead)


def _build_master_with_future_expiries(tmp_path) -> FyersInstrumentMaster:
    """Build a master with future NIFTY option expiries for testing."""
    db = FyersInstrumentMaster(
        db_path=str(tmp_path / "expiry_test.db"), masters=("NSE_FO",)
    )
    today = datetime.now(UTC).date()

    # Build 4 future Thursdays (NIFTY weekly days)
    thursdays = []
    d = today
    for _ in range(4):
        d = _next_weekday(d + timedelta(days=1), 3)  # Thursday = 3
        thursdays.append(d)

    # Make the last one a monthly expiry (last Thursday of its month)
    last_thu = thursdays[-1]
    while (last_thu + timedelta(days=7)).month == last_thu.month:
        last_thu += timedelta(days=7)
    thursdays[-1] = last_thu

    # Build fixture
    fixture = {}
    for d in thursdays:
        ticker = f"NSE:NIFTY{d.year % 100:02d}O{d.month:01d}{d.day:02d}25000CE"
        fixture[ticker] = fyers_row(
            ticker,
            expiry=fyers_epoch(d.year, d.month, d.day),
            opt_type="CE",
            strike=25000.0,
            lot=75,
        )

    def fake_get(url: str) -> bytes:
        return json.dumps(fixture).encode()

    db.refresh(http_get=fake_get)
    return db


# ── MIDCPNIFTY gaps ──────────────────────────────────────────────────────


class TestMidcpniftyInIndexSymbols:
    """MIDCPNIFTY must resolve as an INDEX."""

    def test_midcpnifty_in_index_symbols(self) -> None:
        assert "MIDCPNIFTY" in INDEX_SYMBOLS

    def test_midcpnifty_in_index_ticker_map(self) -> None:
        assert "MIDCPNIFTY" in _INDEX_INTERNAL_TO_TICKER
        assert _INDEX_INTERNAL_TO_TICKER["MIDCPNIFTY"] == "MIDCPNIFTY-INDEX"

    def test_infer_instrument_type_midcpnifty(self) -> None:
        from shettyxtreme.integration.fyers._util import infer_instrument_type

        assert infer_instrument_type("MIDCPNIFTY") == "INDEX"


# ── classify_expiry ──────────────────────────────────────────────────────


class TestClassifyExpiry:
    """Weekly/monthly classification per underlying policy."""

    def test_nifty_thursday_weekly(self) -> None:
        """A non-last Thursday for NIFTY is weekly."""
        today = datetime.now(UTC).date()
        # Find a Thursday that is NOT the last in its month
        d = _next_weekday(today + timedelta(days=1), 3)
        # If it's the last Thursday, move to the next month's first Thursday
        if (d + timedelta(days=7)).month != d.month:
            # Move to next month
            d = d.replace(day=1) + timedelta(days=31)
            d = _next_weekday(d.replace(day=1), 3)
        assert classify_expiry("NIFTY", d) == "weekly"

    def test_nifty_last_thursday_monthly(self) -> None:
        """Last Thursday of a month for NIFTY is monthly."""
        today = datetime.now(UTC).date()
        d = today.replace(day=1) + timedelta(days=31)  # next month
        d = d.replace(day=1)
        # Find last Thursday
        thu = _next_weekday(d, 3)
        while (thu + timedelta(days=7)).month == thu.month:
            thu += timedelta(days=7)
        assert classify_expiry("NIFTY", thu) == "monthly"

    def test_banknifty_four_weekly_days(self) -> None:
        """BANKNIFTY has weeklies Mon/Tue/Wed/Thu."""
        today = datetime.now(UTC).date()
        for wd in [0, 1, 2, 3]:  # Mon-Thu
            d = _next_weekday(today + timedelta(days=1), wd)
            # Make sure it's not the last occurrence of that weekday
            if (d + timedelta(days=7)).month != d.month:
                continue  # skip if it would be classified as monthly
            assert classify_expiry("BANKNIFTY", d) == "weekly", f"weekday {wd} should be weekly"

    def test_banknifty_last_thursday_is_monthly(self) -> None:
        """BANKNIFTY last Thursday is monthly."""
        today = datetime.now(UTC).date()
        d = today.replace(day=1) + timedelta(days=31)
        d = d.replace(day=1)
        thu = _next_weekday(d, 3)
        while (thu + timedelta(days=7)).month == thu.month:
            thu += timedelta(days=7)
        assert classify_expiry("BANKNIFTY", thu) == "monthly"

    def test_midcpnifty_monday_weekly(self) -> None:
        """MIDCPNIFTY Monday is weekly (unless last Mon of month)."""
        today = datetime.now(UTC).date()
        d = _next_weekday(today + timedelta(days=1), 0)
        if (d + timedelta(days=7)).month != d.month:
            d = d.replace(day=1) + timedelta(days=31)
            d = _next_weekday(d.replace(day=1), 0)
        assert classify_expiry("MIDCPNIFTY", d) == "weekly"

    def test_unknown_symbol_uses_heuristic(self) -> None:
        """Unknown symbols fall back to is_monthly_expiry() heuristic."""
        today = datetime.now(UTC).date()
        # A Thursday that is last in month → monthly
        d = today.replace(day=1) + timedelta(days=31)
        d = d.replace(day=1)
        thu = _next_weekday(d, 3)
        while (thu + timedelta(days=7)).month == thu.month:
            thu += timedelta(days=7)
        assert classify_expiry("SBIN", thu) == "monthly"


# ── resolve_default_expiry ────────────────────────────────────────────────


class TestResolveDefaultExpiry:
    """Default expiry selection per policy."""

    def test_nifty_default_nearest_weekly(self) -> None:
        """NIFTY (index) defaults to nearest weekly."""
        today = datetime.now(UTC).date()
        # Build dates: first non-last Thursday (weekly), then last Thursday (monthly)
        thu1 = _next_weekday(today + timedelta(days=1), 3)
        if (thu1 + timedelta(days=7)).month != thu1.month:
            thu1 = thu1.replace(day=1) + timedelta(days=31)
            thu1 = _next_weekday(thu1.replace(day=1), 3)
        # Monthly
        d = today.replace(day=1) + timedelta(days=31)
        d = d.replace(day=1)
        thu_monthly = _next_weekday(d, 3)
        while (thu_monthly + timedelta(days=7)).month == thu_monthly.month:
            thu_monthly += timedelta(days=7)

        expiries = sorted([thu_monthly.isoformat(), thu1.isoformat()])
        result = resolve_default_expiry("NIFTY", expiries)
        assert result == thu1.isoformat()

    def test_stock_default_nearest_monthly(self) -> None:
        """Stock (non-index) defaults to nearest monthly."""
        today = datetime.now(UTC).date()
        thu1 = _next_weekday(today + timedelta(days=1), 3)
        if (thu1 + timedelta(days=7)).month != thu1.month:
            thu1 = thu1.replace(day=1) + timedelta(days=31)
            thu1 = _next_weekday(thu1.replace(day=1), 3)
        d = today.replace(day=1) + timedelta(days=31)
        d = d.replace(day=1)
        thu_monthly = _next_weekday(d, 3)
        while (thu_monthly + timedelta(days=7)).month == thu_monthly.month:
            thu_monthly += timedelta(days=7)

        expiries = sorted([thu1.isoformat(), thu_monthly.isoformat()])
        result = resolve_default_expiry("RELIANCE", expiries)
        assert result == thu_monthly.isoformat()

    def test_empty_expiries_returns_none(self) -> None:
        assert resolve_default_expiry("NIFTY", []) is None

    def test_single_expiry_returns_it(self) -> None:
        assert resolve_default_expiry("NIFTY", ["2026-08-14"]) == "2026-08-14"


# ── list_expiries on the master ──────────────────────────────────────────


class TestListExpiriesMaster:
    """Integration test: list_expiries() against a real SQLite master."""

    def test_list_expiries_returns_distinct_sorted(self, tmp_path) -> None:
        db = _build_master_with_future_expiries(tmp_path)
        try:
            result = db.list_expiries("NIFTY", exchange="NSE", instrument_type="OPTION")
            assert len(result) >= 2
            assert result == sorted(result)
            assert len(result) == len(set(result))  # distinct
        finally:
            db.close()

    def test_list_expiries_unknown_symbol_empty(self, tmp_path) -> None:
        db = _build_master_with_future_expiries(tmp_path)
        try:
            assert db.list_expiries("UNKNOWNXYZ") == []
        finally:
            db.close()
