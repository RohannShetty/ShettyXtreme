"""Tests for greeks history recording + endpoint (Phase 3A.4).

Verifies:
- GreeksStore: record / get_history round-trip, days filter, close
- GET /api/execution/greeks-history endpoint (with and without a store)
- PositionProjection recording hook fires on position updates
"""
from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shettyxtreme.terminal.api.execution_router import _iv_cache, router
from shettyxtreme.terminal.api.greeks_store import GreeksStore
from shettyxtreme.terminal.projections import PositionProjection, set_greeks_store


@pytest.fixture
def store(tmp_path):
    """A GreeksStore on a temp db path."""
    db = tmp_path / "greeks.db"
    s = GreeksStore(db)
    yield s
    s.close()


class TestGreeksStore:
    """SQLite store round-trip and filtering."""

    def test_record_and_get_history_round_trip(self, store: GreeksStore) -> None:
        store.record(12.5, -0.3, -250.0, 80.0, 2)
        store.record(-4.0, 0.1, -100.0, 30.0, 1)

        rows = store.get_history(days=7)
        assert len(rows) == 2
        first, second = rows
        assert first["net_delta"] == 12.5
        assert first["net_gamma"] == -0.3
        assert first["net_theta"] == -250.0
        assert first["net_vega"] == 80.0
        assert first["position_count"] == 2
        assert first["timestamp"]
        assert second["net_delta"] == -4.0
        assert second["position_count"] == 1

    def test_get_history_oldest_first(self, store: GreeksStore) -> None:
        store.record(1.0, 0.0, 0.0, 0.0, 1)
        store.record(2.0, 0.0, 0.0, 0.0, 1)
        rows = store.get_history(days=7)
        assert [r["net_delta"] for r in rows] == [1.0, 2.0]

    def test_get_history_days_filter(self, store: GreeksStore, tmp_path) -> None:
        """Rows older than the window are excluded."""
        store.record(5.0, 0.0, 0.0, 0.0, 1)
        # Backdate a second row directly (raw sqlite) to 10 days ago.
        old_ts = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        conn = sqlite3.connect(str(tmp_path / "greeks.db"), timeout=5.0)
        try:
            conn.execute(
                "INSERT INTO greeks_history "
                "(net_delta, net_gamma, net_theta, net_vega, position_count, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (99.0, 0.0, 0.0, 0.0, 3, old_ts),
            )
            conn.commit()
        finally:
            conn.close()

        rows_7 = store.get_history(days=7)
        assert len(rows_7) == 1
        assert rows_7[0]["net_delta"] == 5.0

        rows_30 = store.get_history(days=30)
        assert len(rows_30) == 2

    def test_get_history_clamps_days_to_at_least_one(self, store: GreeksStore) -> None:
        store.record(5.0, 0.0, 0.0, 0.0, 1)
        # A row just inserted is always inside even a 1-day window.
        assert len(store.get_history(days=0)) == 1
        assert len(store.get_history(days=-1)) == 1

    def test_record_creates_parent_directory(self, tmp_path) -> None:
        db = tmp_path / "nested" / "dir" / "greeks.db"
        s = GreeksStore(db)
        try:
            s.record(1.0, 0.0, 0.0, 0.0, 1)
            assert db.exists()
        finally:
            s.close()

    def test_close_is_idempotent(self, store: GreeksStore) -> None:
        store.close()
        store.close()  # must not raise


def _make_app(store: GreeksStore | None) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.position_projection = PositionProjection()
    if store is not None:
        app.state.greeks_store = store
    return app


class TestGreeksHistoryEndpoint:
    """GET /api/execution/greeks-history."""

    def test_returns_recorded_snapshots(self, store: GreeksStore) -> None:
        store.record(12.5, -0.3, -250.0, 80.0, 2)
        client = TestClient(_make_app(store))
        resp = client.get("/api/execution/greeks-history?days=7")
        assert resp.status_code == 200
        rows = resp.json()
        assert isinstance(rows, list)
        assert len(rows) == 1
        assert rows[0]["net_delta"] == 12.5
        assert rows[0]["net_gamma"] == -0.3
        assert rows[0]["net_theta"] == -250.0
        assert rows[0]["net_vega"] == 80.0
        assert rows[0]["position_count"] == 2
        assert rows[0]["timestamp"]

    def test_default_days_is_7(self, store: GreeksStore) -> None:
        store.record(1.0, 0.0, 0.0, 0.0, 1)
        client = TestClient(_make_app(store))
        resp = client.get("/api/execution/greeks-history")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_days_param_filters(self, store: GreeksStore, tmp_path) -> None:
        store.record(5.0, 0.0, 0.0, 0.0, 1)
        old_ts = (datetime.now(UTC) - timedelta(days=10)).isoformat()
        conn = sqlite3.connect(str(tmp_path / "greeks.db"), timeout=5.0)
        try:
            conn.execute(
                "INSERT INTO greeks_history "
                "(net_delta, net_gamma, net_theta, net_vega, position_count, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (99.0, 0.0, 0.0, 0.0, 3, old_ts),
            )
            conn.commit()
        finally:
            conn.close()

        client = TestClient(_make_app(store))
        assert len(client.get("/api/execution/greeks-history?days=7").json()) == 1
        assert len(client.get("/api/execution/greeks-history?days=30").json()) == 2

    def test_invalid_days_rejected(self, store: GreeksStore) -> None:
        client = TestClient(_make_app(store))
        assert client.get("/api/execution/greeks-history?days=0").status_code == 422
        assert client.get("/api/execution/greeks-history?days=9999").status_code == 422

    def test_returns_empty_list_without_store(self) -> None:
        client = TestClient(_make_app(None))
        resp = client.get("/api/execution/greeks-history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_filter_by_regime(self, store: GreeksStore, tmp_path) -> None:
        """Phase 3C.1: greeks history can be filtered by active regime."""
        from shettyxtreme.terminal.api.analytics_store import AnalyticsStore

        analytics_store = AnalyticsStore(str(tmp_path / "analytics.db"))
        app = _make_app(store)
        app.state.analytics_store = analytics_store
        client = TestClient(app)

        from datetime import UTC, datetime, timedelta

        now = datetime.now(UTC)
        # Two regime periods: trending_up yesterday, range_bound today.
        # trending_up started 24h ago, range_bound started 12h ago.
        trending_up_ts = (now - timedelta(hours=24)).isoformat()
        range_bound_ts = (now - timedelta(hours=12)).isoformat()
        
        with sqlite3.connect(str(tmp_path / "analytics.db")) as conn:
            conn.execute(
                "INSERT INTO regime_history (regime, confidence, timestamp) VALUES (?, ?, ?)",
                ("trending_up", 0.8, trending_up_ts),
            )
            conn.execute(
                "INSERT INTO regime_history (regime, confidence, timestamp) VALUES (?, ?, ?)",
                ("range_bound", 0.6, range_bound_ts),
            )
            conn.commit()

        # Two greeks snapshots backdated to fall under each regime.
        with sqlite3.connect(str(tmp_path / "greeks.db")) as conn:
            for ts, delta in ((now - timedelta(hours=18), 10.0), (now - timedelta(hours=1), 99.0)):
                conn.execute(
                    "INSERT INTO greeks_history "
                    "(net_delta, net_gamma, net_theta, net_vega, position_count, timestamp) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (delta, 0.0, 0.0, 0.0, 1, ts.isoformat()),
                )
            conn.commit()

        try:
            trending = client.get("/api/execution/greeks-history?days=7&regime=trending_up").json()
            assert len(trending) == 1
            assert trending[0]["net_delta"] == 10.0

            ranging = client.get("/api/execution/greeks-history?days=7&regime=range_bound").json()
            assert len(ranging) == 1
            assert ranging[0]["net_delta"] == 99.0

            all_rows = client.get("/api/execution/greeks-history?days=7").json()
            assert len(all_rows) == 2
        finally:
            analytics_store.close()


_OPTION_SYMBOL = "NSE:NIFTY26AUG25000CE"


class TestPositionProjectionHook:
    """PositionProjection records a greeks snapshot on position updates."""

    def setup_method(self) -> None:
        import shettyxtreme.terminal.api.execution_router as mod

        _iv_cache.clear()
        _iv_cache[(25000, "CE")] = 15.0
        mod._last_spot = 24950.0
        set_greeks_store(None)

    def teardown_method(self) -> None:
        import shettyxtreme.terminal.api.execution_router as mod

        _iv_cache.clear()
        mod._last_spot = None
        set_greeks_store(None)

    @pytest.mark.asyncio
    @patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
    async def test_on_position_update_records_greeks(self, mock_broadcast, tmp_path) -> None:
        from shettyxtreme.core.event_bus.event_bus import Event, Topic

        store = GreeksStore(tmp_path / "greeks.db")
        set_greeks_store(store)
        proj = PositionProjection()
        try:
            await proj.on_position_update(Event(
                topic=Topic.POSITION_CHANGED,
                data={"symbol": _OPTION_SYMBOL, "quantity": 50, "net_quantity": 50,
                      "m2m": 1000.0, "pnl": 500.0},
                source="test",
            ))
            rows = store.get_history(days=7)
        finally:
            store.close()

        assert len(rows) == 1
        assert rows[0]["position_count"] == 1
        # Long call → positive net delta, non-zero greeks.
        assert rows[0]["net_delta"] > 0
        assert rows[0]["net_gamma"] >= 0

    @pytest.mark.asyncio
    @patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
    async def test_no_store_means_no_recording(self, mock_broadcast) -> None:
        from shettyxtreme.core.event_bus.event_bus import Event, Topic

        proj = PositionProjection()
        await proj.on_position_update(Event(
            topic=Topic.POSITION_CHANGED,
            data={"symbol": _OPTION_SYMBOL, "quantity": 50, "net_quantity": 50},
            source="test",
        ))
        # Position still updated; recording silently skipped.
        assert len(proj.get()) == 1

    @pytest.mark.asyncio
    @patch("shettyxtreme.terminal.projections.ws_bridge.broadcast", new_callable=AsyncMock)
    async def test_unknown_greeks_skipped_not_fabricated(self, mock_broadcast, tmp_path) -> None:
        """No IV for the position → no snapshot (never zeros/None recorded)."""
        from shettyxtreme.core.event_bus.event_bus import Event, Topic

        _iv_cache.clear()  # strip IV so greeks are unknown
        store = GreeksStore(tmp_path / "greeks.db")
        set_greeks_store(store)
        proj = PositionProjection()
        try:
            await proj.on_position_update(Event(
                topic=Topic.POSITION_CHANGED,
                data={"symbol": _OPTION_SYMBOL, "quantity": 50, "net_quantity": 50},
                source="test",
            ))
            rows = store.get_history(days=7)
        finally:
            store.close()

        assert rows == []

    def test_empty_book_records_zero_snapshot(self, tmp_path) -> None:
        store = GreeksStore(tmp_path / "greeks.db")
        set_greeks_store(store)
        try:
            proj = PositionProjection()
            proj._positions = []  # flat book
            proj._record_greeks_snapshot()
            rows = store.get_history(days=7)
        finally:
            store.close()

        assert len(rows) == 1
        assert rows[0]["position_count"] == 0
        assert rows[0]["net_delta"] == 0.0

    def test_recording_hook_isolated_from_other_position_changes(self, tmp_path) -> None:
        """Non-option position updates don't fabricate greeks snapshots."""
        from shettyxtreme.core.event_bus.event_bus import Event, Topic

        store = GreeksStore(tmp_path / "greeks.db")
        set_greeks_store(store)
        proj = PositionProjection()
        try:
            import asyncio

            asyncio.run(proj.on_position_update(Event(
                topic=Topic.POSITION_CHANGED,
                data={"symbol": "NSE:NIFTY50-INDEX", "quantity": 0, "net_quantity": 0},
                source="test",
            )))
            rows = store.get_history(days=7)
        finally:
            store.close()

        assert rows == []
