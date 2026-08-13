"""Tests for the IV rank history endpoint + IVRankCalculator.get_history (3A.3)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import AsyncIterator

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from shettyxtreme.options.iv_rank import IVRankCalculator, IVSnapshot
from shettyxtreme.terminal.api.analytics_router import router


def _populated_calculator() -> IVRankCalculator:
    calc = IVRankCalculator()
    calc.record_iv_batch("NIFTY", [10.0, 12.0, 14.0, 11.0, 13.0])
    return calc


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest_asyncio.fixture
async def app_client() -> AsyncIterator[tuple[FastAPI, AsyncClient]]:
    app = _make_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield app, ac


# ── Calculator-level ─────────────────────────────────────────────────────────


def test_get_history_returns_timestamped_entries() -> None:
    calc = _populated_calculator()
    history = calc.get_history("NIFTY", days=30)

    assert len(history) == 5
    entry = history[0]
    assert set(entry.keys()) == {"timestamp", "iv_rank_percent", "iv_classification"}
    # ISO-8601 timestamp parses and carries a tz.
    parsed = datetime.fromisoformat(entry["timestamp"])
    assert parsed.tzinfo is not None
    assert 0.0 <= entry["iv_rank_percent"] <= 100.0
    assert entry["iv_classification"] in ("LOW", "NORMAL", "HIGH")
    # Oldest first.
    stamps = [datetime.fromisoformat(h["timestamp"]) for h in history]
    assert stamps == sorted(stamps)


def test_get_history_empty_for_unknown_symbol() -> None:
    calc = _populated_calculator()
    assert calc.get_history("BANKNIFTY", days=30) == []


def test_get_history_days_filter_excludes_old_snapshots() -> None:
    calc = _populated_calculator()
    old = datetime.now(UTC) - timedelta(days=60)
    calc._snapshots["NIFTY"].append(IVSnapshot(symbol="NIFTY", iv=9.0, timestamp=old))

    history = calc.get_history("NIFTY", days=30)
    assert len(history) == 5  # the 60-day-old snapshot is filtered out


# ── Endpoint-level ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_iv_rank_history_endpoint(app_client, monkeypatch) -> None:
    app, client = app_client
    monkeypatch.setattr(app.state, "iv_rank_calculator", _populated_calculator(), raising=False)

    resp = await client.get("/api/analytics/iv-rank-history?symbol=NIFTY&days=30")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 5
    assert set(body[0].keys()) == {"timestamp", "iv_rank_percent", "iv_classification"}


@pytest.mark.asyncio
async def test_iv_rank_history_endpoint_degrades_without_calculator(
    app_client,
) -> None:
    _, client = app_client
    resp = await client.get("/api/analytics/iv-rank-history?symbol=NIFTY&days=30")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_iv_rank_history_days_query_validation(app_client) -> None:
    _, client = app_client
    resp = await client.get("/api/analytics/iv-rank-history?symbol=NIFTY&days=0")
    assert resp.status_code == 422
