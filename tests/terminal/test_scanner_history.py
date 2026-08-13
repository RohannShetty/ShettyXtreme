"""Tests for the scanner findings SQLite store + history endpoint (Phase 3A.1)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from shettyxtreme.terminal.api.scanner_router import init_scanner_store, router
from shettyxtreme.terminal.api.scanner_store import ScannerStore


def _finding(
    scanner_type: str = "gamma_spike",
    symbol: str = "NIFTY",
    severity: str = "HIGH",
    detail: dict[str, Any] | None = None,
    ts: str | None = None,
) -> dict[str, Any]:
    return {
        "scanner_type": scanner_type,
        "symbol": symbol,
        "severity": severity,
        "detail": detail or {"strike": 25000},
        "timestamp": ts or datetime.now(UTC).isoformat(),
    }


@pytest.fixture(autouse=True)
def _reset_store_globals():
    yield
    init_scanner_store(None)


class TestScannerStore:
    """ScannerStore records and lists findings with filters."""

    def test_record_and_list_roundtrip(self, tmp_path) -> None:
        store = ScannerStore(tmp_path / "scanner.db")
        finding_id = store.record(_finding(detail={"strike": 25000, "gamma": 0.005}))
        rows = store.list()
        assert len(rows) == 1
        assert rows[0]["id"] == finding_id
        assert rows[0]["scanner_type"] == "gamma_spike"
        assert rows[0]["symbol"] == "NIFTY"
        assert rows[0]["severity"] == "HIGH"
        assert rows[0]["detail"] == {"strike": 25000, "gamma": 0.005}
        assert rows[0]["timestamp"]
        store.close()

    def test_persists_across_instances(self, tmp_path) -> None:
        db = tmp_path / "scanner.db"
        first = ScannerStore(db)
        first.record(_finding())
        first.close()
        second = ScannerStore(db)
        assert len(second.list()) == 1
        second.close()

    def test_filter_by_scanner_type(self, tmp_path) -> None:
        store = ScannerStore(tmp_path / "scanner.db")
        store.record(_finding(scanner_type="gamma_spike"))
        store.record(_finding(scanner_type="iv_crush", symbol="BANKNIFTY", severity="MEDIUM"))
        store.record(_finding(scanner_type="gamma_spike", symbol="SENSEX", severity="LOW"))
        rows = store.list(scanner_type="gamma_spike")
        assert len(rows) == 2
        assert all(r["scanner_type"] == "gamma_spike" for r in rows)
        assert store.list(scanner_type="pcr_extremes") == []
        store.close()

    def test_limit(self, tmp_path) -> None:
        store = ScannerStore(tmp_path / "scanner.db")
        for i in range(10):
            store.record(_finding(symbol=f"S{i}"))
        assert len(store.list(limit=3)) == 3
        store.close()

    def test_since_filters_by_timestamp(self, tmp_path) -> None:
        store = ScannerStore(tmp_path / "scanner.db")
        store.record(_finding(symbol="OLD", ts="2026-08-10T09:00:00+00:00"))
        store.record(_finding(symbol="NEW", ts="2026-08-13T09:00:00+00:00"))
        rows = store.list(since="2026-08-12T00:00:00+00:00")
        assert [r["symbol"] for r in rows] == ["NEW"]
        store.close()

    def test_newest_first_ordering(self, tmp_path) -> None:
        store = ScannerStore(tmp_path / "scanner.db")
        store.record(_finding(symbol="FIRST", ts="2026-08-10T09:00:00+00:00"))
        store.record(_finding(symbol="SECOND", ts="2026-08-13T09:00:00+00:00"))
        rows = store.list()
        assert [r["symbol"] for r in rows] == ["SECOND", "FIRST"]
        store.close()

    def test_close_idempotent(self, tmp_path) -> None:
        store = ScannerStore(tmp_path / "scanner.db")
        store.close()
        store.close()  # must not raise


@pytest_asyncio.fixture
async def history_client(tmp_path) -> AsyncIterator[AsyncClient]:
    store = ScannerStore(tmp_path / "scanner.db")
    init_scanner_store(store)
    app = FastAPI()
    app.include_router(router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    store.close()


class TestHistoryEndpoint:
    """GET /api/scanner/findings/history."""

    @pytest.mark.asyncio
    async def test_empty_history(self, tmp_path) -> None:
        init_scanner_store(None)
        app = FastAPI()
        app.include_router(router)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/scanner/findings/history")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_history_returns_recorded_findings(self, history_client: AsyncClient) -> None:
        resp = await history_client.get("/api/scanner/findings/history")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_history_with_data(self, tmp_path) -> None:
        store = ScannerStore(tmp_path / "scanner.db")
        store.record(_finding(scanner_type="gamma_spike", severity="HIGH"))
        store.record(_finding(scanner_type="iv_crush", symbol="BANKNIFTY", severity="MEDIUM"))
        init_scanner_store(store)
        app = FastAPI()
        app.include_router(router)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.get("/api/scanner/findings/history")
        store.close()
        assert resp.status_code == 200
        rows = resp.json()
        assert len(rows) == 2
        assert {r["scanner_type"] for r in rows} == {"gamma_spike", "iv_crush"}
        assert rows[0]["detail"] == {"strike": 25000}

    @pytest.mark.asyncio
    async def test_history_filter_by_type_and_limit(self, tmp_path) -> None:
        store = ScannerStore(tmp_path / "scanner.db")
        store.record(_finding(scanner_type="gamma_spike", symbol="A"))
        store.record(_finding(scanner_type="gamma_spike", symbol="B"))
        store.record(_finding(scanner_type="iv_crush", symbol="C"))
        init_scanner_store(store)
        app = FastAPI()
        app.include_router(router)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            filtered = await ac.get("/api/scanner/findings/history?scanner_type=gamma_spike&limit=1")
            none = await ac.get("/api/scanner/findings/history?scanner_type=pcr_extremes")
        store.close()
        assert len(filtered.json()) == 1
        assert filtered.json()[0]["scanner_type"] == "gamma_spike"
        assert none.json() == []
