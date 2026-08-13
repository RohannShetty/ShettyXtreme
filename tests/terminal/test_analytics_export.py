"""Tests for the analytics data export endpoint (CSV + JSON) (3A.3)."""
from __future__ import annotations

import csv
import io
from typing import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import shettyxtreme.terminal.api.analytics_router as ar
from shettyxtreme.options.iv_rank import IVRankCalculator
from shettyxtreme.options.oi_tracker import OITracker
from shettyxtreme.terminal.api.analytics_router import router
from shettyxtreme.terminal.api.analytics_store import AnalyticsStore


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _populate(app: FastAPI, tmp_path, monkeypatch) -> None:
    """Wire calculators + store on app.state and point DB paths at tmp_path."""
    calc = IVRankCalculator()
    calc.record_iv_batch("NIFTY", [10.0, 12.0, 14.0, 11.0, 13.0])
    monkeypatch.setattr(app.state, "iv_rank_calculator", calc, raising=False)

    tracker = OITracker()
    tracker.update_from_chain("NIFTY", "28AUG", [
        {"strike": 24500, "option_type": "CE", "oi": 2000},
        {"strike": 24500, "option_type": "PE", "oi": 4000},
    ])
    monkeypatch.setattr(app.state, "oi_tracker", tracker, raising=False)

    store = AnalyticsStore(str(tmp_path / "analytics.db"))
    store.record_max_pain("NIFTY", "28AUG", 24500.0, 24550.0)
    store.record_regime("trending_up", 0.75, adx=28.0, di_plus=24.0, di_minus=20.0)
    monkeypatch.setattr(app.state, "analytics_store", store, raising=False)

    # Scorecard section reads these via module-level paths -> tmp sandbox.
    monkeypatch.setattr(ar, "RESEARCH_DB_PATH", str(tmp_path / "research.db"))
    monkeypatch.setattr(ar, "SESSIONS_DB_PATH", str(tmp_path / "sessions.db"))
    monkeypatch.setattr(ar, "LEARNING_DB_PATH", str(tmp_path / "learning.db"))
    monkeypatch.setattr(ar, "LEDGER_DB_PATH", str(tmp_path / "ledger.db"))


@pytest_asyncio.fixture
async def app_client(
    tmp_path, monkeypatch
) -> AsyncIterator[tuple[FastAPI, AsyncClient]]:
    app = _make_app()
    _populate(app, tmp_path, monkeypatch)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield app, ac


@pytest.mark.asyncio
async def test_export_csv_download(app_client) -> None:
    _, client = app_client
    resp = await client.get("/api/analytics/export?format=csv&days=30")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    disposition = resp.headers["content-disposition"]
    assert "attachment" in disposition
    assert "analytics_export.csv" in disposition

    text = resp.text
    # Every section header is present.
    for section in (
        "# scorecard_metrics",
        "# regime_history",
        "# iv_rank_history",
        "# pcr_history",
        "# max_pain_history",
    ):
        assert section in text
    # Recorded rows are present with their header columns.
    assert "trending_up" in text
    assert "24500.0" in text
    assert "timestamp,max_pain,spot_price" in text


@pytest.mark.asyncio
async def test_export_csv_parses_cleanly(app_client) -> None:
    _, client = app_client
    resp = await client.get("/api/analytics/export?format=csv&days=30")

    rows = list(csv.reader(io.StringIO(resp.text)))
    section_cols: dict[str, int] = {
        "# scorecard_metrics": 4,
        "# regime_history": 4,
        "# iv_rank_history": 4,
        "# pcr_history": 5,
        "# max_pain_history": 4,
    }
    current: str | None = None
    for row in rows:
        if not row:
            continue
        if row[0].startswith("#"):
            current = row[0]
            assert current in section_cols
            continue
        # Data rows must match their section's column count (no ragged CSV).
        assert current is not None
        assert len(row) == section_cols[current], f"ragged row in {current}: {row}"


@pytest.mark.asyncio
async def test_export_json(app_client) -> None:
    _, client = app_client
    resp = await client.get("/api/analytics/export?format=json&days=30")

    assert resp.status_code == 200
    assert "json" in resp.headers["content-type"]
    body = resp.json()
    assert set(body.keys()) == {
        "scorecard_metrics",
        "regime_history",
        "iv_rank_history",
        "pcr_history",
        "max_pain_history",
    }
    assert isinstance(body["scorecard_metrics"], list)
    assert len(body["regime_history"]) == 1
    assert body["regime_history"][0]["regime"] == "trending_up"
    assert len(body["max_pain_history"]) == 1
    assert body["max_pain_history"][0]["symbol"] == "NIFTY"
    assert body["max_pain_history"][0]["max_pain"] == 24500.0
    assert len(body["iv_rank_history"]) == 5
    assert len(body["pcr_history"]) == 1


@pytest.mark.asyncio
async def test_export_defaults_to_csv(app_client) -> None:
    _, client = app_client
    resp = await client.get("/api/analytics/export?days=30")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")


@pytest.mark.asyncio
async def test_export_rejects_unknown_format(app_client) -> None:
    _, client = app_client
    resp = await client.get("/api/analytics/export?format=xml")
    assert resp.status_code == 422
