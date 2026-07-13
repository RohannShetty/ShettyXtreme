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
