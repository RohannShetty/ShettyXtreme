"""F-INT-008 — instrument-master bootstrap refreshes when stale, skips when fresh.

The bootstrap previously refreshed only when the DB was empty; a populated but
stale mirror (missing new expiries / changed lot sizes) was never refreshed.
The bootstrap now delegates to ``FyersInstrumentMaster.ensure_fresh`` with the
configured ``max_age_hours`` threshold.
"""
from __future__ import annotations

from unittest.mock import patch

from shettyxtreme.terminal.api.instrument_init import init_instrument_master


class _FakeMaster:
    def __init__(self, db_path: str, max_age_hours: float = 24.0) -> None:
        self.db_path = db_path
        self.max_age_hours = max_age_hours
        self.ensure_fresh_calls: list[dict] = []

    def ensure_fresh(self, max_age_hours=None, http_get=None, timeout=120.0):
        self.ensure_fresh_calls.append({"max_age_hours": max_age_hours})
        return {"NSE_CM": 1}


def test_init_refreshes_stale_master(tmp_path) -> None:
    """A stale master triggers a refresh via ensure_fresh."""
    with patch(
        "shettyxtreme.terminal.api.instrument_init.FyersInstrumentMaster", _FakeMaster
    ):
        master = init_instrument_master(
            db_path=str(tmp_path / "f.db"), max_age_hours=12
        )
    assert master is not None
    assert master.db_path == str(tmp_path / "f.db")
    assert master.max_age_hours == 12
    assert master.ensure_fresh_calls == [{"max_age_hours": 12}]


def test_init_skips_refresh_when_fresh(tmp_path) -> None:
    """A fresh master (ensure_fresh returns None) is used as-is — no fetch."""
    class _FreshMaster(_FakeMaster):
        def ensure_fresh(self, max_age_hours=None, http_get=None, timeout=120.0):
            self.ensure_fresh_calls.append({"max_age_hours": max_age_hours})
            return None  # already fresh

    with patch(
        "shettyxtreme.terminal.api.instrument_init.FyersInstrumentMaster", _FreshMaster
    ):
        master = init_instrument_master(db_path=str(tmp_path / "f.db"))
    assert master is not None
    assert master.ensure_fresh_calls == [{"max_age_hours": 24}]


def test_init_failure_returns_none(tmp_path) -> None:
    """A constructor failure degrades gracefully to None (no crash at boot)."""
    class _BoomMaster(_FakeMaster):
        def __init__(self, db_path: str, max_age_hours: float = 24.0) -> None:
            raise RuntimeError("boom")

    with patch(
        "shettyxtreme.terminal.api.instrument_init.FyersInstrumentMaster", _BoomMaster
    ):
        assert init_instrument_master(db_path=str(tmp_path / "f.db")) is None
