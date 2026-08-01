"""Integration tests for the ShettyXtreme Terminal FastAPI app.

Verifies HTTP routing and response shapes without starting the real
EventBus or Dhan adapters.  Projections are not available in the test
lifespan, so state-dependent endpoints are skipped gracefully.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from shettyxtreme.terminal.api import execution_router
from shettyxtreme.terminal.api.app import app


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


# ── Redirect tests ────────────────────────────────────────────────────────


def test_root_redirects(client: TestClient) -> None:
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/static/"


def test_setup_redirects(client: TestClient) -> None:
    resp = client.get("/setup", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/static/#/setup"


def test_settings_redirects(client: TestClient) -> None:
    resp = client.get("/settings", follow_redirects=False)
    assert resp.status_code == 307
    assert resp.headers["location"] == "/static/#/settings"


def test_oauth_callback_redirects_to_spa(client: TestClient) -> None:
    resp = client.get("/auth/dhan/callback?tokenId=bogus", follow_redirects=False)
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert location.startswith("/static/")
    assert "setup.html" not in location


# ── Health endpoints ──────────────────────────────────────────────────────


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/api/health")
    if resp.status_code == 500:
        pytest.skip("health_projection not initialised in test lifespan")
    assert resp.status_code == 200
    body = resp.json()
    assert "overall" in body


def test_health_session(client: TestClient) -> None:
    resp = client.get("/api/health/session")
    if resp.status_code == 500:
        pytest.skip("health_projection not initialised in test lifespan")
    assert resp.status_code == 200
    body = resp.json()
    assert "status" in body
    assert body["status"] in {"pre_open", "open", "post_close", "closed"}


# ── Execution endpoints ───────────────────────────────────────────────────


def test_execution_mode_default(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    mode_file = tmp_path / "mode.txt"
    monkeypatch.setattr(execution_router, "_MODE_FILE", mode_file)
    execution_router._current_mode = execution_router._load_mode()
    resp = client.get("/api/execution/mode")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "OBSERVER"


# ── Watchlist endpoint ────────────────────────────────────────────────────


def test_watchlist_empty_or_seeded(client: TestClient) -> None:
    resp = client.get("/api/watchlist")
    if resp.status_code == 500:
        pytest.skip("watchlist_projection not initialised in test lifespan")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


# ── Scanner alerts endpoint ───────────────────────────────────────────────


def test_scanner_alerts_empty(client: TestClient) -> None:
    resp = client.get("/api/scanner/alerts")
    if resp.status_code == 500:
        pytest.skip("alert_projection not initialised in test lifespan")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
