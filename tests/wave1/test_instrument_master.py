"""Tests for InstrumentMaster: symbol resolution and expiry calculation.

Mocks the Dhan security list fetch. Uses temp directory for SQLite DB.
"""
from __future__ import annotations

import os
import tempfile
from datetime import date
from typing import Generator
from unittest.mock import MagicMock

import pytest

from shettyxtreme.integration.instrument_master import InstrumentMaster

# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

SECURITY_LIST_RESPONSE = [
    {
        "SECURITY_ID": "11536",
        "TRADING_SYMBOL": "RELIANCE",
        "EXCHANGE": "NSE",
        "INSTRUMENT_TYPE": "EQUITY",
        "ISIN": "INE002A01018",
        "COMPANY_NAME": "Reliance Industries Ltd",
    },
    {
        "SECURITY_ID": "3456",
        "TRADING_SYMBOL": "TATAMOTORS",
        "EXCHANGE": "NSE",
        "INSTRUMENT_TYPE": "EQUITY",
        "ISIN": "INE215A01028",
        "COMPANY_NAME": "Tata Motors Ltd",
    },
    {
        "SECURITY_ID": "5254",
        "TRADING_SYMBOL": "RELIANCE",
        "EXCHANGE": "BSE",
        "INSTRUMENT_TYPE": "EQUITY",
        "ISIN": "INE002A01018",
        "COMPANY_NAME": "Reliance Industries Ltd",
    },
]


@pytest.fixture
def temp_db_path() -> Generator[str, None, None]:
    with tempfile.TemporaryDirectory(prefix="inst_master_") as td:
        yield os.path.join(td, "instruments.db")


@pytest.fixture
def instrument_master(temp_db_path: str) -> InstrumentMaster:
    mock_dhan = MagicMock()
    mock_dhan.fetch_security_list.return_value = SECURITY_LIST_RESPONSE
    im = InstrumentMaster(
        db_path=temp_db_path, dhan_client=mock_dhan,
    )
    yield im
    im.close()


@pytest.fixture
def instrument_master_holidays(temp_db_path: str) -> InstrumentMaster:
    mock_dhan = MagicMock()
    mock_dhan.fetch_security_list.return_value = []
    im = InstrumentMaster(
        db_path=temp_db_path, dhan_client=mock_dhan,
        holidays={"2024-01-18", "2024-01-25"},
    )
    yield im
    im.close()


# ---------------------------------------------------------------------------
# Symbol resolution tests
# ---------------------------------------------------------------------------

class TestSymbolResolution:
    """Tests for fetch_security_list and resolve_symbol."""

    def test_fetch_security_list_populates_db(
        self, instrument_master: InstrumentMaster
    ) -> None:
        """fetch_security_list should insert all instruments."""
        count = instrument_master.fetch_security_list()
        assert count == 3

    def test_resolve_symbol_nse(self, instrument_master: InstrumentMaster) -> None:
        """resolve_symbol should return correct security_id for NSE."""
        instrument_master.fetch_security_list()
        result = instrument_master.resolve_symbol("RELIANCE", "NSE")
        assert result == "11536"

    def test_resolve_symbol_bse(self, instrument_master: InstrumentMaster) -> None:
        """resolve_symbol should return correct security_id for BSE."""
        instrument_master.fetch_security_list()
        result = instrument_master.resolve_symbol("RELIANCE", "BSE")
        assert result == "5254"

    def test_resolve_symbol_tatamotors(self, instrument_master: InstrumentMaster) -> None:
        """resolve_symbol should work for other symbols."""
        instrument_master.fetch_security_list()
        result = instrument_master.resolve_symbol("TATAMOTORS", "NSE")
        assert result == "3456"

    def test_resolve_symbol_not_found(self, instrument_master: InstrumentMaster) -> None:
        """resolve_symbol should return None for unknown symbol."""
        instrument_master.fetch_security_list()
        result = instrument_master.resolve_symbol("NONEXISTENT", "NSE")
        assert result is None

    def test_resolve_symbol_case_insensitive(
        self, instrument_master: InstrumentMaster
    ) -> None:
        """resolve_symbol should handle lowercase symbols."""
        instrument_master.fetch_security_list()
        result = instrument_master.resolve_symbol("reliance", "NSE")
        assert result == "11536"

    def test_fetch_no_dhan_client(self, temp_db_path: str) -> None:
        """fetch_security_list should return 0 when no Dhan client."""
        im = InstrumentMaster(db_path=temp_db_path, dhan_client=None)
        count = im.fetch_security_list()
        assert count == 0
        im.close()

    def test_fetch_handles_exception(self, temp_db_path: str) -> None:
        """fetch_security_list should return 0 on API exception."""
        mock_dhan = MagicMock()
        mock_dhan.fetch_security_list.side_effect = RuntimeError("API error")
        im = InstrumentMaster(db_path=temp_db_path, dhan_client=mock_dhan)
        count = im.fetch_security_list()
        assert count == 0
        im.close()

    def test_resolve_security_id_reverse_lookup(self, instrument_master: InstrumentMaster) -> None:
        """resolve_security_id should return the trading symbol for an ID."""
        instrument_master.fetch_security_list()
        assert instrument_master.resolve_security_id("11536") == "RELIANCE"
        assert instrument_master.resolve_security_id("3456") == "TATAMOTORS"

    def test_resolve_security_id_unknown(self, instrument_master: InstrumentMaster) -> None:
        """resolve_security_id should return None for an unknown ID."""
        instrument_master.fetch_security_list()
        assert instrument_master.resolve_security_id("999999") is None

    def test_resolve_symbol_exchange_alias(self, instrument_master: InstrumentMaster) -> None:
        """resolve_symbol should accept feed-segment names (NSE_EQ) as aliases."""
        instrument_master.fetch_security_list()
        assert instrument_master.resolve_symbol("RELIANCE", "NSE_EQ") == "11536"

    def test_fetch_security_list_dataframe(self, temp_db_path: str) -> None:
        """fetch_security_list should read the real SDK CSV columns (SEM_*)."""
        mock_dhan = MagicMock()
        import pandas as pd

        mock_dhan.fetch_security_list.return_value = pd.DataFrame(
            [
                {
                    "SEM_EXM_EXCH_ID": "NSE", "SEM_SEGMENT": "I",
                    "SEM_SMST_SECURITY_ID": "13", "SEM_INSTRUMENT_NAME": "INDEX",
                    "SEM_EXPIRY_CODE": "0", "SEM_TRADING_SYMBOL": "NIFTY",
                    "SEM_EXCH_INSTRUMENT_TYPE": "INDEX", "SEM_SERIES": "INDEX",
                    "SM_SYMBOL_NAME": "NIFTY 50",
                },
                {
                    "SEM_EXM_EXCH_ID": "NSE", "SEM_SEGMENT": "E",
                    "SEM_SMST_SECURITY_ID": "2885", "SEM_INSTRUMENT_NAME": "EQUITY",
                    "SEM_EXPIRY_CODE": "0", "SEM_TRADING_SYMBOL": "RELIANCE",
                    "SEM_EXCH_INSTRUMENT_TYPE": "EQUITY", "SEM_SERIES": "EQ",
                    "SM_SYMBOL_NAME": "Reliance Industries",
                },
            ]
        )
        im = InstrumentMaster(db_path=temp_db_path, dhan_client=mock_dhan)
        assert im.fetch_security_list() == 2
        # Segment I maps to the NSE_FNO feed; segment E to NSE_EQ.
        assert im.resolve_symbol("NIFTY", "NSE_FNO") == "13"
        assert im.resolve_symbol("RELIANCE", "NSE_EQ") == "2885"
        assert im.resolve_security_id("2885", "NSE_EQ") == "RELIANCE"
        im.close()

    def test_fetch_security_list_wrong_keys_returns_zero(self, temp_db_path: str) -> None:
        """A DataFrame without any recognized key must not poison the DB (C1 guard)."""
        mock_dhan = MagicMock()
        import pandas as pd

        mock_dhan.fetch_security_list.return_value = pd.DataFrame(
            [{"FOO": "1", "BAR": "2"}, {"FOO": "3", "BAR": "4"}]
        )
        im = InstrumentMaster(db_path=temp_db_path, dhan_client=mock_dhan)
        assert im.fetch_security_list() == 0
        assert im.count_instruments() == 0
        im.close()

    def test_security_id_collision_across_segments(self, temp_db_path: str) -> None:
        """The same security ID on different segments must both survive (13 = ABB + NIFTY)."""
        mock_dhan = MagicMock()
        import pandas as pd

        mock_dhan.fetch_security_list.return_value = pd.DataFrame(
            [
                {
                    "SEM_EXM_EXCH_ID": "NSE", "SEM_SEGMENT": "E",
                    "SEM_SMST_SECURITY_ID": "13", "SEM_TRADING_SYMBOL": "ABB",
                    "SEM_EXCH_INSTRUMENT_TYPE": "EQUITY", "SM_SYMBOL_NAME": "ABB Ltd",
                },
                {
                    "SEM_EXM_EXCH_ID": "NSE", "SEM_SEGMENT": "I",
                    "SEM_SMST_SECURITY_ID": "13", "SEM_TRADING_SYMBOL": "NIFTY",
                    "SEM_EXCH_INSTRUMENT_TYPE": "INDEX", "SM_SYMBOL_NAME": "NIFTY 50",
                },
            ]
        )
        im = InstrumentMaster(db_path=temp_db_path, dhan_client=mock_dhan)
        assert im.fetch_security_list() == 2
        assert im.count_instruments() == 2
        assert im.resolve_symbol("NIFTY", "NSE_FNO") == "13"
        assert im.resolve_symbol("ABB", "NSE_EQ") == "13"
        assert im.resolve_security_id("13", "NSE_FNO") == "NIFTY"
        assert im.resolve_security_id("13", "NSE_EQ") == "ABB"
        im.close()

    def test_resolve_symbol_fallback_is_deterministic(self, temp_db_path: str) -> None:
        """Exchange-less fallback returns the ORDER BY exchange row, not insertion order."""
        mock_dhan = MagicMock()
        import pandas as pd

        # NSE row inserted first; BSE_EQ sorts before NSE_EQ.
        mock_dhan.fetch_security_list.return_value = pd.DataFrame(
            [
                {
                    "SEM_EXM_EXCH_ID": "NSE", "SEM_SEGMENT": "E",
                    "SEM_SMST_SECURITY_ID": "11536", "SEM_TRADING_SYMBOL": "RELIANCE",
                },
                {
                    "SEM_EXM_EXCH_ID": "BSE", "SEM_SEGMENT": "E",
                    "SEM_SMST_SECURITY_ID": "5254", "SEM_TRADING_SYMBOL": "RELIANCE",
                },
            ]
        )
        im = InstrumentMaster(db_path=temp_db_path, dhan_client=mock_dhan)
        assert im.fetch_security_list() == 2
        # No exchange aliases match MCX, so the fallback runs.
        assert im.resolve_symbol("RELIANCE", "MCX") == "5254"
        im.close()

    def test_legacy_schema_dropped_and_recreated(self, temp_db_path: str) -> None:
        """A pre-v2 instruments table (security_id PRIMARY KEY) must be replaced."""
        import sqlite3

        db = temp_db_path
        conn = sqlite3.connect(db)
        try:
            conn.execute(
                """
                CREATE TABLE instruments (
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
            conn.execute(
                "INSERT INTO instruments VALUES ('13', 'NIFTY', 'NSE_FNO', 'INDEX', '', '')"
            )
            conn.commit()
        finally:
            conn.close()

        im = InstrumentMaster(db_path=db, dhan_client=MagicMock())
        try:
            assert im.count_instruments() == 0  # legacy table dropped
        finally:
            im.close()


# ---------------------------------------------------------------------------
# Weekly expiry tests
# ---------------------------------------------------------------------------

class TestWeeklyExpiry:
    """Tests for get_next_weekly_expiry (Thursday-based)."""

    def test_weekly_from_monday(self, instrument_master: InstrumentMaster) -> None:
        """From Monday Jan 15 2024, expiry should be Thursday Jan 18."""
        result = instrument_master.get_next_weekly_expiry(date(2024, 1, 15))
        assert result == date(2024, 1, 18)
        assert result.weekday() == 3

    def test_weekly_from_thursday_same_day(
        self, instrument_master: InstrumentMaster
    ) -> None:
        """From Thursday (expiry day), should return same Thursday."""
        result = instrument_master.get_next_weekly_expiry(date(2024, 1, 18))
        assert result == date(2024, 1, 18)

    def test_weekly_from_friday(self, instrument_master: InstrumentMaster) -> None:
        """From Friday, expiry should be next Thursday."""
        result = instrument_master.get_next_weekly_expiry(date(2024, 1, 19))
        assert result == date(2024, 1, 25)

    def test_weekly_thursday_is_holiday_to_friday(
        self, instrument_master_holidays: InstrumentMaster
    ) -> None:
        """When Thursday is a holiday, expiry should move to Friday."""
        # 2024-01-18 is Thursday and is in holiday set
        result = instrument_master_holidays.get_next_weekly_expiry(
            date(2024, 1, 15)
        )
        assert result == date(2024, 1, 19)
        assert result.weekday() == 4  # Friday

    def test_weekly_crosses_month_boundary(
        self, instrument_master: InstrumentMaster
    ) -> None:
        """Weekly expiry near end of month should cross into next month."""
        # Jan 31, 2024 is Wednesday. Next Thursday is Feb 1.
        result = instrument_master.get_next_weekly_expiry(date(2024, 1, 31))
        assert result == date(2024, 2, 1)

    def test_weekly_from_tuesday(self, instrument_master: InstrumentMaster) -> None:
        """From Tuesday, expiry should be Thursday of same week."""
        result = instrument_master.get_next_weekly_expiry(date(2024, 1, 16))
        assert result == date(2024, 1, 18)

    def test_weekly_returns_date_type(
        self, instrument_master: InstrumentMaster
    ) -> None:
        """get_next_weekly_expiry should return a date object."""
        result = instrument_master.get_next_weekly_expiry(date(2024, 1, 15))
        assert isinstance(result, date)


# ---------------------------------------------------------------------------
# Monthly expiry tests
# ---------------------------------------------------------------------------

class TestMonthlyExpiry:
    """Tests for get_next_monthly_expiry (last Thursday of month)."""

    def test_monthly_january_2024(self, instrument_master: InstrumentMaster) -> None:
        """Last Thursday of Jan 2024 should be Jan 25."""
        result = instrument_master.get_next_monthly_expiry(date(2024, 1, 1))
        assert result == date(2024, 1, 25)
        assert result.weekday() == 3

    def test_monthly_february_2024(self, instrument_master: InstrumentMaster) -> None:
        """Last Thursday of Feb 2024 (leap year) should be Feb 29."""
        result = instrument_master.get_next_monthly_expiry(date(2024, 2, 1))
        assert result == date(2024, 2, 29)
        assert result.weekday() == 3

    def test_monthly_after_expiry_goes_next_month(
        self, instrument_master: InstrumentMaster
    ) -> None:
        """When current month expiry has passed, use next month."""
        # Jan 26 is after Jan 25 expiry
        result = instrument_master.get_next_monthly_expiry(date(2024, 1, 26))
        assert result == date(2024, 2, 29)

    def test_monthly_expiry_holiday_to_previous_day(
        self, instrument_master_holidays: InstrumentMaster
    ) -> None:
        """When last Thursday is a holiday, expiry should move to Wednesday."""
        # Jan 25 is Thursday and is in holiday set
        result = instrument_master_holidays.get_next_monthly_expiry(
            date(2024, 1, 1)
        )
        assert result == date(2024, 1, 24)
        assert result.weekday() == 2  # Wednesday

    def test_monthly_december_rolls_to_january(
        self, instrument_master: InstrumentMaster
    ) -> None:
        """Monthly expiry in December should roll to January next year."""
        # Dec last Thursday is Dec 26, 2024
        result = instrument_master.get_next_monthly_expiry(date(2024, 12, 1))
        assert result == date(2024, 12, 26)
        assert result.weekday() == 3

    def test_monthly_dec_after_expiry(self, instrument_master: InstrumentMaster) -> None:
        """After Dec expiry, should go to Jan next year."""
        # Dec 27 is after Dec 26 expiry
        result = instrument_master.get_next_monthly_expiry(date(2024, 12, 27))
        # Last Thursday of Jan 2025: Jan 31 is Friday, last Thursday is Jan 30
        assert result.year == 2025
        assert result.month == 1
        assert result.weekday() == 3

    def test_monthly_returns_date_type(
        self, instrument_master: InstrumentMaster
    ) -> None:
        """get_next_monthly_expiry should return a date object."""
        result = instrument_master.get_next_monthly_expiry(date(2024, 1, 1))
        assert isinstance(result, date)
