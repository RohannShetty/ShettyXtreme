"""F1 — Fyers symbol resolution tests.

Covers internal <-> Fyers ticker conversion: weekly/monthly encoding, month
codes (1-9/O/N/D), special-char URL encoding, master validation, and the
watchlist round-trip gate.

NOTE on the weekly day padding: Fyers zero-pads weekly days to two digits for
all months — verified live on the published master (e.g. ``EURINR26O01104CE``
= 26-Oct-01). ``NIFTY 2024-10-08 25000 CE`` therefore encodes as
``NSE:NIFTY24O0825000CE`` (the ``NSE:NIFTY24O80825000CE`` form seen in older
documents carries a spurious digit).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest

from shettyxtreme.integration.fyers.instrument_master import FyersInstrumentMaster
from shettyxtreme.integration.fyers.symbols import (
    FyersSymbolResolver,
    SymbolNotFoundError,
    from_fyers,
    is_monthly_expiry,
    to_fyers,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# to_fyers — encoding
# ---------------------------------------------------------------------------


class TestToFyers:
    def test_index_nifty(self) -> None:
        assert to_fyers("NIFTY", "NSE_FNO", "INDEX") == "NSE:NIFTY50-INDEX"

    def test_index_banknifty(self) -> None:
        assert to_fyers("BANKNIFTY", "NSE_FNO", "INDEX") == "NSE:NIFTYBANK-INDEX"

    def test_index_finnifty(self) -> None:
        assert to_fyers("FINNIFTY", "NSE", "INDEX") == "NSE:FINNIFTY-INDEX"

    def test_equity(self) -> None:
        assert to_fyers("SBIN", "NSE", "EQUITY") == "NSE:SBIN-EQ"

    def test_equity_series_be(self) -> None:
        assert to_fyers("SBIN", "NSE", "EQUITY", series="BE") == "NSE:SBIN-BE"

    def test_special_characters_url_encoded(self) -> None:
        """M&M must come out URL-encoded: NSE:M%26M-EQ."""
        assert to_fyers("M&M", "NSE", "EQUITY") == "NSE:M%26M-EQ"

    def test_monthly_option(self) -> None:
        """Last Thursday of Oct 2024 -> monthly AUG/OCT-style encoding."""
        assert (
            to_fyers("NIFTY", "NSE_FNO", "OPTION", expiry=date(2024, 10, 31),
                     strike=25000, option_type="CE")
            == "NSE:NIFTY24OCT25000CE"
        )

    def test_weekly_option(self) -> None:
        """Mid-month Tuesday -> weekly encoding with zero-padded day."""
        assert (
            to_fyers("NIFTY", "NSE_FNO", "OPTION", expiry=date(2024, 10, 8),
                     strike=25000, option_type="CE")
            == "NSE:NIFTY24O0825000CE"
        )

    def test_weekly_option_november_code(self) -> None:
        assert (
            to_fyers("NIFTY", "NSE_FNO", "OPTION", expiry=date(2024, 11, 8),
                     strike=25000, option_type="CE")
            == "NSE:NIFTY24N0825000CE"
        )

    def test_weekly_option_december_code(self) -> None:
        assert (
            to_fyers("NIFTY", "NSE_FNO", "OPTION", expiry=date(2024, 12, 8),
                     strike=25000, option_type="PE")
            == "NSE:NIFTY24D0825000PE"
        )

    def test_weekly_option_expiry_as_iso_string(self) -> None:
        assert (
            to_fyers("NIFTY", "NSE_FNO", "OPTION", expiry="2024-10-08",
                     strike=25000, option_type="CE")
            == "NSE:NIFTY24O0825000CE"
        )

    def test_weekly_option_float_strike(self) -> None:
        """25000.0 must format as an integer strike (no decimals)."""
        assert (
            to_fyers("NIFTY", "NSE_FNO", "OPTION", expiry=date(2024, 10, 8),
                     strike=25000.0, option_type="CE")
            == "NSE:NIFTY24O0825000CE"
        )

    def test_monthly_future(self) -> None:
        assert (
            to_fyers("NIFTY", "NFO", "FUTURES", expiry=date(2024, 10, 31))
            == "NSE:NIFTY24OCTFUT"
        )

    def test_weekly_future(self) -> None:
        assert (
            to_fyers("NIFTY", "NFO", "FUTURES", expiry=date(2024, 10, 8))
            == "NSE:NIFTY24O08FUT"
        )

    def test_unsupported_instrument_type(self) -> None:
        with pytest.raises(ValueError):
            to_fyers("NIFTY", "NSE", "BOGUS")

    def test_option_requires_expiry(self) -> None:
        with pytest.raises(ValueError):
            to_fyers("NIFTY", "NSE_FNO", "OPTION", strike=25000, option_type="CE")

    def test_option_requires_strike(self) -> None:
        with pytest.raises(ValueError):
            to_fyers("NIFTY", "NSE_FNO", "OPTION", expiry=date(2024, 10, 8),
                     option_type="CE")

    def test_option_requires_valid_option_type(self) -> None:
        with pytest.raises(ValueError):
            to_fyers("NIFTY", "NSE_FNO", "OPTION", expiry=date(2024, 10, 8),
                     strike=25000, option_type="XX")

    def test_bad_exchange_raises(self) -> None:
        with pytest.raises(ValueError):
            to_fyers("NIFTY", "NYSE", "INDEX")


# ---------------------------------------------------------------------------
# from_fyers — parsing
# ---------------------------------------------------------------------------


class TestFromFyers:
    def test_parse_index(self) -> None:
        assert from_fyers("NSE:NIFTY50-INDEX") == {
            "internal_symbol": "NIFTY",
            "exchange": "NSE_FNO",
            "instrument_type": "INDEX",
            "expiry": None,
            "strike": None,
            "option_type": None,
        }

    def test_parse_banknifty_index(self) -> None:
        assert from_fyers("NSE:NIFTYBANK-INDEX")["internal_symbol"] == "BANKNIFTY"

    def test_parse_equity(self) -> None:
        parsed = from_fyers("NSE:SBIN-EQ")
        assert parsed["internal_symbol"] == "SBIN"
        assert parsed["exchange"] == "NSE"
        assert parsed["instrument_type"] == "EQUITY"

    def test_parse_url_encoded_special_chars(self) -> None:
        parsed = from_fyers("NSE:M%26M-EQ")
        assert parsed["internal_symbol"] == "M&M"
        assert parsed["instrument_type"] == "EQUITY"

    def test_parse_raw_special_chars(self) -> None:
        assert from_fyers("NSE:M&M-EQ")["internal_symbol"] == "M&M"

    def test_parse_monthly_option(self) -> None:
        parsed = from_fyers("NSE:NIFTY24OCT25000CE")
        assert parsed["internal_symbol"] == "NIFTY"
        assert parsed["instrument_type"] == "OPTION"
        assert parsed["option_type"] == "CE"
        assert parsed["strike"] == 25000
        assert parsed["expiry"].year == 2024 and parsed["expiry"].month == 10

    def test_parse_weekly_option(self) -> None:
        parsed = from_fyers("NSE:NIFTY24O0825000CE")
        assert parsed["internal_symbol"] == "NIFTY"
        assert parsed["expiry"] == date(2024, 10, 8)
        assert parsed["strike"] == 25000
        assert parsed["option_type"] == "CE"

    def test_parse_weekly_option_letter_codes(self) -> None:
        assert from_fyers("NSE:NIFTY24N0825000CE")["expiry"] == date(2024, 11, 8)
        assert from_fyers("NSE:NIFTY24D0825000PE")["expiry"] == date(2024, 12, 8)

    def test_parse_monthly_future(self) -> None:
        parsed = from_fyers("NSE:NIFTY24OCTFUT")
        assert parsed["internal_symbol"] == "NIFTY"
        assert parsed["instrument_type"] == "FUTURES"
        assert parsed["expiry"].month == 10

    def test_parse_weekly_future(self) -> None:
        parsed = from_fyers("NSE:NIFTY24O08FUT")
        assert parsed["internal_symbol"] == "NIFTY"
        assert parsed["instrument_type"] == "FUTURES"
        assert parsed["expiry"] == date(2024, 10, 8)

    def test_unknown_symbol_raises(self) -> None:
        with pytest.raises(ValueError):
            from_fyers("NSE:FOOBAR")

    def test_invalid_string_raises(self) -> None:
        with pytest.raises(ValueError):
            from_fyers("not-a-fyers-symbol")


# ---------------------------------------------------------------------------
# Round trips
# ---------------------------------------------------------------------------


class TestRoundTrip:
    @pytest.mark.parametrize(
        "internal,exchange,inst_type,fyers",
        [
            ("NIFTY", "NSE_FNO", "INDEX", "NSE:NIFTY50-INDEX"),
            ("BANKNIFTY", "NSE_FNO", "INDEX", "NSE:NIFTYBANK-INDEX"),
            ("FINNIFTY", "NSE_FNO", "INDEX", "NSE:FINNIFTY-INDEX"),
            ("SBIN", "NSE", "EQUITY", "NSE:SBIN-EQ"),
            ("M&M", "NSE", "EQUITY", "NSE:M%26M-EQ"),
            ("NIFTY", "NSE_FNO", "FUTURES", "NSE:NIFTY24OCTFUT"),
            ("NIFTY", "NSE_FNO", "FUTURES", "NSE:NIFTY24O08FUT"),
            ("NIFTY", "NSE_FNO", "OPTION", "NSE:NIFTY24OCT25000CE"),
            ("NIFTY", "NSE_FNO", "OPTION", "NSE:NIFTY24O0825000CE"),
        ],
    )
    def test_parse_recovers_fields(
        self, internal: str, exchange: str, inst_type: str, fyers: str
    ) -> None:
        """A Fyers ticker parses back to its internal identity."""
        parsed = from_fyers(fyers)
        assert parsed["internal_symbol"] == internal
        assert parsed["exchange"] == exchange
        assert parsed["instrument_type"] == inst_type

    @pytest.mark.parametrize(
        "internal,exchange,inst_type,fyers",
        [
            # Index/equity/weekly forms encode their full identity, so
            # from_fyers -> to_fyers is an exact re-encode.
            ("NIFTY", "NSE_FNO", "INDEX", "NSE:NIFTY50-INDEX"),
            ("BANKNIFTY", "NSE_FNO", "INDEX", "NSE:NIFTYBANK-INDEX"),
            ("FINNIFTY", "NSE_FNO", "INDEX", "NSE:FINNIFTY-INDEX"),
            ("SBIN", "NSE", "EQUITY", "NSE:SBIN-EQ"),
            ("M&M", "NSE", "EQUITY", "NSE:M%26M-EQ"),
            ("NIFTY", "NSE_FNO", "FUTURES", "NSE:NIFTY24O08FUT"),
            ("NIFTY", "NSE_FNO", "OPTION", "NSE:NIFTY24O0825000CE"),
        ],
    )
    def test_reencode_identity(
        self, internal: str, exchange: str, inst_type: str, fyers: str
    ) -> None:
        """from_fyers -> to_fyers reproduces the ticker (modulo URL encoding)."""
        decoded = from_fyers(fyers)
        reencoded = to_fyers(
            decoded["internal_symbol"], decoded["exchange"],
            decoded["instrument_type"], expiry=decoded["expiry"],
            strike=decoded["strike"], option_type=decoded["option_type"],
        )
        reparsed = from_fyers(reencoded)
        assert reparsed["internal_symbol"] == internal
        assert reparsed["exchange"] == exchange
        assert reparsed["instrument_type"] == inst_type
        if inst_type != "EQUITY" or "M&M" not in internal:
            # URL-encoding only differs for special characters.
            assert reencoded == fyers

    def test_round_trip_full_derivative(self) -> None:
        """Full weekly option round-trip recovers every field."""
        original = {
            "internal_symbol": "NIFTY",
            "exchange": "NSE_FNO",
            "instrument_type": "OPTION",
            "expiry": date(2024, 10, 8),
            "strike": 25000,
            "option_type": "CE",
        }
        fyers = to_fyers(
            original["internal_symbol"], original["exchange"],
            original["instrument_type"], expiry=original["expiry"],
            strike=original["strike"], option_type=original["option_type"],
        )
        assert fyers == "NSE:NIFTY24O0825000CE"
        parsed = from_fyers(fyers)
        assert parsed["internal_symbol"] == original["internal_symbol"]
        assert parsed["exchange"] == original["exchange"]
        assert parsed["instrument_type"] == original["instrument_type"]
        assert parsed["expiry"] == original["expiry"]
        assert parsed["strike"] == original["strike"]
        assert parsed["option_type"] == original["option_type"]


class TestRoundTripWatchlist:
    """Every index in configs/default_watchlist.yaml resolves internal→Fyers→internal."""

    def _watchlist(self) -> list[dict[str, Any]]:
        path = REPO_ROOT / "configs" / "default_watchlist.yaml"
        assert path.exists(), f"watchlist missing at {path}"
        import yaml

        with open(path, "r") as fh:
            data = yaml.safe_load(fh)
        return data["default_watchlist"]["indices"]

    def test_watchlist_resolves(self) -> None:
        for entry in self._watchlist():
            name = str(entry["name"])
            exchange = str(entry["exchange"])
            # Watchlist stores internal symbols, not Dhan security IDs.
            assert str(entry["security_id"]) == name
            fyers = to_fyers(name, exchange, "INDEX")
            assert fyers.startswith("NSE:") and fyers.endswith("-INDEX")
            parsed = from_fyers(fyers)
            assert parsed["internal_symbol"] == name
            assert parsed["exchange"] == exchange
            assert parsed["instrument_type"] == "INDEX"

    def test_watchlist_resolves_with_master(self, resolver: FyersSymbolResolver) -> None:
        for entry in self._watchlist():
            name = str(entry["name"])
            exchange = str(entry["exchange"])
            fyers = resolver.to_fyers(name, exchange, "INDEX")
            assert resolver.from_fyers(fyers)["internal_symbol"] == name


# ---------------------------------------------------------------------------
# Master validation gate (the -300 gotcha guard)
# ---------------------------------------------------------------------------


class TestMasterValidation:
    def test_known_symbol_passes(self, resolver: FyersSymbolResolver) -> None:
        assert resolver.to_fyers("SBIN", "NSE", "EQUITY") == "NSE:SBIN-EQ"

    def test_known_derivative_passes(self, resolver: FyersSymbolResolver) -> None:
        assert (
            resolver.to_fyers("NIFTY", "NSE_FNO", "OPTION", expiry=date(2024, 10, 8),
                              strike=25000, option_type="CE")
            == "NSE:NIFTY24O0825000CE"
        )

    def test_unknown_symbol_raises(self, resolver: FyersSymbolResolver) -> None:
        with pytest.raises(SymbolNotFoundError):
            resolver.to_fyers("NONEXISTENT", "NSE", "EQUITY")

    def test_strike_missing_from_master_raises(self, resolver: FyersSymbolResolver) -> None:
        """A weekly option the master does not list must not silently pass."""
        with pytest.raises(SymbolNotFoundError):
            # Weekly expiry + a strike that is not in the fixture master.
            resolver.to_fyers("NIFTY", "NSE_FNO", "OPTION", expiry=date(2024, 11, 8),
                              strike=26000, option_type="CE")

    def test_module_to_fyers_accepts_master_kwarg(self, master: FyersInstrumentMaster) -> None:
        assert to_fyers("SBIN", "NSE", "EQUITY", master=master) == "NSE:SBIN-EQ"
        with pytest.raises(SymbolNotFoundError):
            to_fyers("NONEXISTENT", "NSE", "EQUITY", master=master)


# ---------------------------------------------------------------------------
# Monthly vs weekly detection
# ---------------------------------------------------------------------------


class TestIsMonthlyExpiry:
    def test_last_thursday_of_month_is_monthly(self) -> None:
        assert is_monthly_expiry(date(2024, 10, 31)) is True

    def test_mid_month_tuesday_is_weekly(self) -> None:
        assert is_monthly_expiry(date(2024, 10, 8)) is False

    def test_last_tuesday_of_month_is_monthly(self) -> None:
        """Post-2025 SEBI convention: index expiries moved to Tuesday."""
        assert is_monthly_expiry(date(2026, 8, 25)) is True

    def test_mid_month_tuesday_2026_is_weekly(self) -> None:
        assert is_monthly_expiry(date(2026, 8, 4)) is False

    def test_accepts_iso_string(self) -> None:
        assert is_monthly_expiry("2024-10-31") is True
        assert is_monthly_expiry("2024-10-08") is False
