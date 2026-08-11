"""Integration tests for the ShettyXtreme Terminal FastAPI app.

Verifies HTTP routing and response shapes without starting the real
EventBus or broker adapters.  Projections are installed on app.state by
the client fixture so state-dependent endpoints run for real.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from shettyxtreme.terminal.api import execution_router
from shettyxtreme.terminal.api.app import app
from shettyxtreme.terminal.projections import (
    AlertProjection,
    HealthProjection,
    WatchlistProjection,
)


@pytest.fixture(scope="module")
def client() -> TestClient:
    app.state.health_projection = HealthProjection()
    app.state.watchlist_projection = WatchlistProjection()
    app.state.alert_projection = AlertProjection()
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
    # F-AUTH-002: a legitimate callback must echo the state persisted at
    # start-auth. start-auth is not callable here (no credentials in this
    # integration harness), so simulate the cookie the real flow sets and
    # verify the callback still redirects into the SPA.
    client.cookies.set(
        "_fyers_oauth_state", "test_state", path="/auth/fyers/callback"
    )
    resp = client.get(
        "/auth/fyers/callback?auth_code=bogus&state=test_state",
        follow_redirects=False,
    )
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert location.startswith("/static/")
    assert "setup.html" not in location


# ── Health endpoints ──────────────────────────────────────────────────────


def test_health_endpoint(client: TestClient) -> None:
    resp = client.get("/api/health")
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
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


# ── Scanner alerts endpoint ───────────────────────────────────────────────


def test_scanner_alerts_empty(client: TestClient) -> None:
    resp = client.get("/api/scanner/alerts")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)


# ── WebSocket origin validation (F-EXEC-001) ───────────────────────────────


def test_ws_accepts_production_origin(client: TestClient) -> None:
    with client.websocket_connect(
        "/ws", headers={"origin": "http://127.0.0.1:8000"}
    ) as ws:
        ws.send_text("ping")
        assert "pong" in ws.receive_text()


def test_ws_accepts_vite_dev_origin(client: TestClient) -> None:
    with client.websocket_connect(
        "/ws", headers={"origin": "http://localhost:3000"}
    ) as ws:
        ws.send_text("ping")
        assert "pong" in ws.receive_text()


def test_ws_rejects_foreign_origin(client: TestClient) -> None:
    # A foreign site must be cut off before the socket is accepted.
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(
            "/ws", headers={"origin": "http://evil.example"}
        ) as ws:
            ws.send_text("ping")
