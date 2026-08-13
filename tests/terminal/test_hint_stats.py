"""Tests for hint accuracy tracking (Phase 3, task 3A.2).

Unit tests for HintStore (record_hint / record_outcome / find_hint /
get_stats) plus the GET /api/intelligence/hint-stats endpoint, and the
PositionProjection close hook that records outcomes.
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shettyxtreme.core.event_bus.event_bus import Event, Topic
from shettyxtreme.terminal.api.hint_store import HintStore
from shettyxtreme.terminal.api.intelligence_router import router
from shettyxtreme.terminal.projections import PositionProjection


@pytest.fixture()
def store(tmp_path) -> HintStore:
    return HintStore(db_path=str(tmp_path / "hints.db"))


def _hint(symbol: str = "NIFTY", direction: str = "bullish", strike: float = 25000.0) -> dict:
    return {"symbol": symbol, "direction": direction, "strike": strike}


class TestRecordHint:
    def test_returns_id_and_persists(self, store) -> None:
        hint_id = store.record_hint(_hint())
        assert hint_id
        row = store.get_hint(hint_id)
        assert row is not None
        assert row["symbol"] == "NIFTY"
        assert row["direction"] == "bullish"
        assert row["strike"] == 25000.0
        assert row["outcome"] is None
        assert row["actual_pnl"] is None

    def test_direction_normalized(self, store) -> None:
        hint_id = store.record_hint(_hint(direction="UP"))
        assert store.get_hint(hint_id)["direction"] == "bullish"

    def test_db_file_created_with_schema(self, tmp_path) -> None:
        db_path = str(tmp_path / "nested" / "hints.db")
        store = HintStore(db_path=db_path)
        store.record_hint(_hint())
        with sqlite3.connect(db_path) as conn:
            cols = {r[1] for r in conn.execute("PRAGMA table_info(hint_outcomes)")}
        assert {
            "hint_id", "symbol", "direction", "strike", "suggested_at",
            "outcome", "actual_pnl", "recorded_at",
        } <= cols


class TestRecordOutcome:
    def test_updates_row(self, store) -> None:
        hint_id = store.record_hint(_hint())
        assert store.record_outcome(hint_id, "win", 450.0) is True
        row = store.get_hint(hint_id)
        assert row["outcome"] == "win"
        assert row["actual_pnl"] == 450.0
        assert row["recorded_at"] is not None

    def test_first_outcome_wins(self, store) -> None:
        hint_id = store.record_hint(_hint())
        assert store.record_outcome(hint_id, "win", 450.0) is True
        assert store.record_outcome(hint_id, "loss", -100.0) is False
        row = store.get_hint(hint_id)
        assert row["outcome"] == "win"
        assert row["actual_pnl"] == 450.0

    def test_unknown_hint_returns_false(self, store) -> None:
        assert store.record_outcome("nope", "win", 1.0) is False


class TestFindHint:
    def test_most_recent_unresolved_matches(self, store) -> None:
        old_id = store.record_hint(_hint())
        store.record_outcome(old_id, "win", 100.0)  # resolved → skipped
        new_id = store.record_hint(_hint(strike=25100.0))
        assert store.find_hint("NIFTY", "bullish") == new_id

    def test_direction_mismatch_returns_none(self, store) -> None:
        store.record_hint(_hint(direction="bearish"))
        assert store.find_hint("NIFTY", "bullish") is None

    def test_position_ticker_prefix_matches_hint_symbol(self, store) -> None:
        """Position symbols may be Fyers tickers — prefix match both ways."""
        hint_id = store.record_hint(_hint())
        assert store.find_hint("NIFTY27AUG25000CE", "bullish") == hint_id
        assert store.find_hint("NIFTY", "bullish") == hint_id


class TestGetStats:
    def test_empty(self, store) -> None:
        stats = store.get_stats(days=30)
        assert stats == {
            "win_rate": None, "avg_pnl": None,
            "sample_size": 0, "total_hints": 0, "days": 30,
        }

    def test_win_rate_and_avg_pnl(self, store) -> None:
        for pnl in (400.0, 250.0, -150.0):
            hint_id = store.record_hint(_hint())
            store.record_outcome(hint_id, "win" if pnl > 0 else "loss", pnl)
        stats = store.get_stats()
        assert stats["sample_size"] == 3
        assert stats["total_hints"] == 3
        assert stats["win_rate"] == pytest.approx(2 / 3, abs=0.001)
        assert stats["avg_pnl"] == pytest.approx((400.0 + 250.0 - 150.0) / 3, abs=0.01)

    def test_unresolved_hints_not_in_sample(self, store) -> None:
        store.record_hint(_hint())  # never resolved
        stats = store.get_stats()
        assert stats["total_hints"] == 1
        assert stats["sample_size"] == 0
        assert stats["win_rate"] is None
        assert stats["avg_pnl"] is None

    def test_days_window_filters_old_hints(self, store, tmp_path) -> None:
        old_id = store.record_hint(_hint())
        # Backdate the hint + outcome beyond the 30-day window.
        old_ts = (datetime.now(UTC) - timedelta(days=45)).isoformat()
        with sqlite3.connect(str(tmp_path / "hints.db")) as conn:
            conn.execute(
                "UPDATE hint_outcomes SET suggested_at = ?, recorded_at = ?, "
                "outcome = 'win', actual_pnl = 100.0 WHERE hint_id = ?",
                (old_ts, old_ts, old_id),
            )
            conn.commit()
        stats = store.get_stats(days=30)
        assert stats["total_hints"] == 0
        assert stats["sample_size"] == 0
        stats_wide = store.get_stats(days=60)
        assert stats_wide["total_hints"] == 1
        assert stats_wide["sample_size"] == 1


class TestHintStatsEndpoint:
    @pytest.fixture()
    def client(self, tmp_path):
        app = FastAPI()
        app.include_router(router)
        app.state.hint_store = HintStore(db_path=str(tmp_path / "hints.db"))
        return TestClient(app)

    def test_returns_stats_shape(self, client) -> None:
        resp = client.get("/api/intelligence/hint-stats")
        assert resp.status_code == 200
        data = resp.json()
        assert set(data) == {"win_rate", "avg_pnl", "sample_size", "total_hints", "days"}
        assert data["sample_size"] == 0
        assert data["total_hints"] == 0
        assert data["days"] == 30

    def test_days_query_param(self, client) -> None:
        resp = client.get("/api/intelligence/hint-stats?days=7")
        assert resp.status_code == 200
        assert resp.json()["days"] == 7

    def test_days_bounds_validated(self, client) -> None:
        assert client.get("/api/intelligence/hint-stats?days=0").status_code == 422
        assert client.get("/api/intelligence/hint-stats?days=9999").status_code == 422

    def test_reflects_recorded_data(self, client) -> None:
        store = client.app.state.hint_store
        for pnl in (100.0, -50.0):
            hint_id = store.record_hint(_hint())
            store.record_outcome(hint_id, "win" if pnl > 0 else "loss", pnl)
        data = client.get("/api/intelligence/hint-stats").json()
        assert data["sample_size"] == 2
        assert data["win_rate"] == 0.5
        assert data["avg_pnl"] == 25.0

    def test_missing_store_returns_503(self, tmp_path) -> None:
        app = FastAPI()
        app.include_router(router)
        resp = TestClient(app).get("/api/intelligence/hint-stats")
        assert resp.status_code == 503


class TestPositionProjectionOutcomeHook:
    """PositionProjection records hint outcomes when positions close (3A.2)."""

    @pytest.fixture()
    def projection(self, store) -> PositionProjection:
        proj = PositionProjection()
        proj.set_hint_store(store)
        return proj

    @staticmethod
    def _event(data: dict) -> Event:
        return Event(topic=Topic.POSITION_CHANGED, data=data, source="test")

    @pytest.mark.asyncio
    async def test_closed_position_records_win(self, projection, store) -> None:
        hint_id = store.record_hint(_hint())
        await projection.on_position_update(self._event({
            "symbol": "NIFTY", "status": "CLOSED",
            "quantity": 0, "net_quantity": 0, "pnl": 520.0,
        }))
        assert store.get_hint(hint_id)["outcome"] == "win"
        assert store.get_hint(hint_id)["actual_pnl"] == 520.0

    @pytest.mark.asyncio
    async def test_closed_position_records_loss(self, projection, store) -> None:
        hint_id = store.record_hint(_hint())
        await projection.on_position_update(self._event({
            "symbol": "NIFTY", "status": "CLOSED",
            "quantity": 0, "net_quantity": 0, "pnl": -240.0,
        }))
        row = store.get_hint(hint_id)
        assert row["outcome"] == "loss"
        assert row["actual_pnl"] == -240.0

    @pytest.mark.asyncio
    async def test_open_position_does_not_record(self, projection, store) -> None:
        hint_id = store.record_hint(_hint())
        await projection.on_position_update(self._event({
            "symbol": "NIFTY", "quantity": 75, "net_quantity": 75, "pnl": 10.0,
        }))
        assert store.get_hint(hint_id)["outcome"] is None

    @pytest.mark.asyncio
    async def test_close_with_side_infers_long_direction(self, projection, store) -> None:
        """SELL close of a long → bullish hint (side is opposite of position)."""
        hint_id = store.record_hint(_hint())
        await projection.on_position_update(self._event({
            "symbol": "NIFTY", "side": "SELL", "quantity": 0, "pnl": 100.0,
        }))
        assert store.get_hint(hint_id)["outcome"] == "win"

    @pytest.mark.asyncio
    async def test_no_matching_hint_is_noop(self, projection, store) -> None:
        await projection.on_position_update(self._event({
            "symbol": "RELIANCE", "status": "CLOSED", "pnl": 100.0,
        }))
        assert store.get_stats()["total_hints"] == 0

    @pytest.mark.asyncio
    async def test_no_store_attached_is_noop(self, store, tmp_path) -> None:
        hint_id = store.record_hint(_hint())
        proj = PositionProjection()  # no store attached
        await proj.on_position_update(self._event({
            "symbol": "NIFTY", "status": "CLOSED", "pnl": 100.0,
        }))
        assert store.get_hint(hint_id)["outcome"] is None
