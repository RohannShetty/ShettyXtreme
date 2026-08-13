"""F1 — Fyers instrument master (SQLite) tests.

Exercises download->store (refresh with an injected fetcher), lookup,
search, URL-encoded lookups, failure isolation, and the F-INT-008 staleness
gate (refresh when stale, skip when fresh).
"""
from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta

from shettyxtreme.integration.fyers.instrument_master import FyersInstrumentMaster

from .conftest import MASTER_FIXTURE, fyers_epoch, fyers_row


def _fake_master_get(url: str) -> bytes:
    """Default fetcher: serve a small one-row master for any URL."""
    if url.endswith("NSE_CM_sym_master.json"):
        return json.dumps(
            {"NSE:SBIN-EQ": fyers_row("NSE:SBIN-EQ", series="EQ")}
        ).encode("utf-8")
    return b"{}"


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


class TestInstrumentMasterStaleness:
    """F-INT-008 — the mirror refreshes when stale and skips when fresh."""

    def test_needs_refresh_when_empty(self, tmp_path) -> None:
        db = FyersInstrumentMaster(db_path=str(tmp_path / "f.db"))
        try:
            assert db.needs_refresh() is True
        finally:
            db.close()

    def test_needs_refresh_false_when_fresh(self, tmp_path) -> None:
        db = FyersInstrumentMaster(db_path=str(tmp_path / "f.db"), masters=("NSE_CM",))
        try:
            db.refresh(http_get=_fake_master_get)
            assert db.count_instruments() == 1
            assert db.last_refreshed() is not None
            assert db.needs_refresh() is False
        finally:
            db.close()

    def test_needs_refresh_true_when_stale(self, tmp_path) -> None:
        db = FyersInstrumentMaster(db_path=str(tmp_path / "f.db"), masters=("NSE_CM",))
        try:
            db.refresh(http_get=_fake_master_get)
            # Backdate the refresh stamp past the 24h default threshold.
            db._set_meta(
                "last_refreshed",
                (datetime.now(UTC) - timedelta(hours=25)).isoformat(),
            )
            assert db.needs_refresh() is True
            assert db.needs_refresh(max_age_hours=48) is False
        finally:
            db.close()

    def test_needs_refresh_true_with_zero_max_age(self, tmp_path) -> None:
        db = FyersInstrumentMaster(
            db_path=str(tmp_path / "f.db"), masters=("NSE_CM",), max_age_hours=0
        )
        try:
            db.refresh(http_get=_fake_master_get)
            # Any elapsed time > 0 makes a 0h threshold stale.
            assert db.needs_refresh() is True
        finally:
            db.close()

    def test_needs_refresh_true_when_timestamp_missing(self, tmp_path) -> None:
        """A populated pre-F-INT-008 DB (rows, no stamp) self-heals."""
        db = FyersInstrumentMaster(db_path=str(tmp_path / "f.db"))
        try:
            db._upsert_master(MASTER_FIXTURE)
            assert db.count_instruments() > 0
            assert db.last_refreshed() is None
            assert db.needs_refresh() is True
        finally:
            db.close()

    def test_failed_refresh_does_not_reset_clock(self, tmp_path) -> None:
        """A total download failure must not stamp last_refreshed — the
        mirror stays stale and the next bootstrap retries."""
        db = FyersInstrumentMaster(db_path=str(tmp_path / "f.db"), masters=("BAD",))
        try:
            def fail(url: str) -> bytes:
                raise RuntimeError("connection refused")

            counts = db.refresh(http_get=fail)
            assert counts == {"BAD": 0}
            assert db.last_refreshed() is None
            assert db.needs_refresh() is True
        finally:
            db.close()

    def test_ensure_fresh_refreshes_when_stale(self, tmp_path) -> None:
        db = FyersInstrumentMaster(db_path=str(tmp_path / "f.db"), masters=("NSE_CM",))
        try:
            db.refresh(http_get=_fake_master_get)
            db._set_meta(
                "last_refreshed",
                (datetime.now(UTC) - timedelta(hours=25)).isoformat(),
            )
            result = db.ensure_fresh(http_get=_fake_master_get)
            assert result == {"NSE_CM": 1}
            assert db.needs_refresh() is False
        finally:
            db.close()

    def test_ensure_fresh_skips_when_fresh(self, tmp_path) -> None:
        db = FyersInstrumentMaster(db_path=str(tmp_path / "f.db"), masters=("NSE_CM",))
        try:
            db.refresh(http_get=_fake_master_get)
            calls: list[str] = []

            def spy(url: str) -> bytes:
                calls.append(url)
                return _fake_master_get(url)

            assert db.ensure_fresh(http_get=spy) is None
            assert calls == []  # fresh mirror — no HTTP fetch at all
        finally:
            db.close()

    def test_ensure_fresh_populates_empty_db(self, tmp_path) -> None:
        db = FyersInstrumentMaster(db_path=str(tmp_path / "f.db"), masters=("NSE_CM",))
        try:
            result = db.ensure_fresh(http_get=_fake_master_get)
            assert result == {"NSE_CM": 1}
            assert db.count_instruments() == 1
        finally:
            db.close()


class TestListExpiries:
    """list_expiries() returns distinct sorted future expiries."""

    def test_list_expiries_distinct_sorted(self, master: FyersInstrumentMaster) -> None:
        # The fixture has 2024-10-08, 2024-10-31, 2024-11-08, 2024-12-08
        # but only future dates (>= today) are returned. Since these are
        # in the past, the list will be empty in production. We test with
        # a fresh DB containing future dates.
        from datetime import UTC, datetime

        db = FyersInstrumentMaster(
            db_path=str(master._db_path).replace(".db", "_future.db"),
            masters=("NSE_FO",),
        )

        # Create a fixture with future expiries
        future1 = (datetime.now(UTC).date().replace(day=1) + __import__("datetime").timedelta(days=45)).isoformat()
        future2 = (datetime.now(UTC).date().replace(day=1) + __import__("datetime").timedelta(days=75)).isoformat()

        import json
        from tests.integration.conftest import fyers_epoch, fyers_row

        def fake_get(url: str) -> bytes:
            d1 = date.fromisoformat(future1)
            d2 = date.fromisoformat(future2)
            return json.dumps({
                f"NSE:NIFTY{d1.year % 100:02d}O{d1.month:01d}{d1.day:02d}25000CE": fyers_row(
                    f"NSE:NIFTY{d1.year % 100:02d}O{d1.month:01d}{d1.day:02d}25000CE",
                    expiry=fyers_epoch(d1.year, d1.month, d1.day),
                    opt_type="CE", strike=25000.0, lot=75,
                ),
                f"NSE:NIFTY{d2.year % 100:02d}O{d2.month:01d}{d2.day:02d}25000CE": fyers_row(
                    f"NSE:NIFTY{d2.year % 100:02d}O{d2.month:01d}{d2.day:02d}25000CE",
                    expiry=fyers_epoch(d2.year, d2.month, d2.day),
                    opt_type="CE", strike=25000.0, lot=75,
                ),
            }).encode()

        db.refresh(http_get=fake_get)
        result = db.list_expiries("NIFTY", exchange="NSE", instrument_type="OPTION")
        assert len(result) == 2
        assert result == sorted(result)  # sorted ascending
        assert result[0] == future1
        assert result[1] == future2
        # Distinct check: adding same date again shouldn't duplicate
        db.close()

    def test_list_expiries_empty_for_unknown_symbol(self, master: FyersInstrumentMaster) -> None:
        result = master.list_expiries("NONEXISTENT")
        assert result == []

    def test_list_expiries_empty_for_equity_type(self, master: FyersInstrumentMaster) -> None:
        result = master.list_expiries("NIFTY", instrument_type="EQUITY")
        assert result == []
