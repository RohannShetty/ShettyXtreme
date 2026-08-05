"""F1 — Fyers instrument master (SQLite) tests.

Exercises download->store (refresh with an injected fetcher), lookup,
search, URL-encoded lookups, and failure isolation.
"""
from __future__ import annotations

import json
from datetime import date

from shettyxtreme.integration.fyers.instrument_master import FyersInstrumentMaster

from .conftest import MASTER_FIXTURE, fyers_epoch, fyers_row


class TestInstrumentMaster:
    def test_refresh_populates_from_http(self, tmp_path) -> None:
        db = FyersInstrumentMaster(db_path=str(tmp_path / "f.db"), masters=("NSE_CM", "NSE_FO"))

        def fake_get(url: str) -> bytes:
            if url.endswith("NSE_CM_sym_master.json"):
                return json.dumps(MASTER_FIXTURE).encode("utf-8")
            if url.endswith("NSE_FO_sym_master.json"):
                return json.dumps(
                    {
                        "NSE:BANKNIFTY24OCTFUT": fyers_row(
                            "NSE:BANKNIFTY24OCTFUT", expiry=fyers_epoch(2024, 10, 31), lot=30
                        )
                    }
                ).encode("utf-8")
            return b"{}"

        counts = db.refresh(http_get=fake_get)
        assert counts == {"NSE_CM": 11, "NSE_FO": 1}
        assert db.count_instruments() == 12
        db.close()

    def test_refresh_failure_is_isolated(self, tmp_path) -> None:
        db = FyersInstrumentMaster(db_path=str(tmp_path / "f.db"), masters=("BAD", "NSE_CM"))

        def fake_get(url: str) -> bytes:
            if url.endswith("NSE_CM_sym_master.json"):
                return json.dumps({"NSE:SBIN-EQ": fyers_row("NSE:SBIN-EQ", series="EQ")}).encode()
            raise RuntimeError("connection refused")

        counts = db.refresh(http_get=fake_get)
        assert counts["BAD"] == 0
        assert counts["NSE_CM"] == 1
        db.close()

    def test_refresh_rejects_non_dict(self, tmp_path) -> None:
        db = FyersInstrumentMaster(db_path=str(tmp_path / "f.db"))
        counts = db.refresh(masters=("NSE_CM",), http_get=lambda url: b"[1,2,3]")
        assert counts["NSE_CM"] == 0
        db.close()

    def test_lookup_exact(self, master: FyersInstrumentMaster) -> None:
        row = master.lookup("NSE:NIFTY24O0825000CE")
        assert row is not None
        assert row["internal_symbol"] == "NIFTY"
        assert row["instrument_type"] == "OPTION"
        assert row["option_type"] == "CE"
        assert row["strike"] == 25000.0
        assert row["expiry"] == "2024-10-08"
        assert row["lot_size"] == 75
        assert row["tick_size"] == 0.05
        assert row["isin"] == "INE000000000"

    def test_lookup_url_encoded(self, master: FyersInstrumentMaster) -> None:
        assert master.lookup("NSE:M%26M-EQ") is not None
        assert master.lookup("NSE:M%26M-EQ")["internal_symbol"] == "M&M"

    def test_lookup_missing_returns_none(self, master: FyersInstrumentMaster) -> None:
        assert master.lookup("NSE:NONEXISTENT-EQ") is None

    def test_lookup_index_row(self, master: FyersInstrumentMaster) -> None:
        row = master.lookup("NSE:NIFTY50-INDEX")
        assert row["internal_symbol"] == "NIFTY"
        assert row["instrument_type"] == "INDEX"
        assert row["expiry"] is None

    def test_search_by_symbol_and_type(self, master: FyersInstrumentMaster) -> None:
        rows = master.search("NIFTY", exchange="NSE", instrument_type="OPTION")
        assert len(rows) == 4  # O/N/D weekly + monthly fixtures
        assert all(r["instrument_type"] == "OPTION" for r in rows)

    def test_search_with_expiry_strike_option_type(
        self, master: FyersInstrumentMaster
    ) -> None:
        rows = master.search(
            "NIFTY", exchange="NSE", instrument_type="OPTION",
            expiry=date(2024, 10, 8), strike=25000.0, option_type="CE",
        )
        assert len(rows) == 1
        assert rows[0]["fyers_symbol"] == "NSE:NIFTY24O0825000CE"

    def test_search_no_match(self, master: FyersInstrumentMaster) -> None:
        assert master.search("RELIANCE", exchange="NSE", instrument_type="EQUITY") == []

    def test_search_equity_with_special_chars(self, master: FyersInstrumentMaster) -> None:
        rows = master.search("M&M", exchange="NSE", instrument_type="EQUITY")
        assert len(rows) == 1
        assert rows[0]["fyers_symbol"] == "NSE:M&M-EQ"

    def test_default_db_path_has_fyers_dir(self, tmp_path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = FyersInstrumentMaster(db_path="data/fyers_instruments.db")
        try:
            assert (tmp_path / "data" / "fyers_instruments.db").exists()
            assert db.count_instruments() == 0
        finally:
            db.close()
