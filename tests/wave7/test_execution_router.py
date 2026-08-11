"""Tests for ExecutionRouter — risk honesty (no fabricated margin, fix #2)."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from shettyxtreme.terminal.api.execution_router import router
from shettyxtreme.terminal.projections import PositionProjection, RiskProjection


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    app.state.risk_projection = RiskProjection()
    app.state.position_projection = PositionProjection()
    return app


def test_execution_router_margin_none() -> None:
    """/api/execution/risk reports null margin when no broker data is available."""
    client = TestClient(_make_app())
    resp = client.get("/api/execution/risk")
    assert resp.status_code == 200
    body = resp.json()
    assert "margin_available" in body
    assert body["margin_available"] is None


def test_execution_router_margin_reports_real_value() -> None:
    """Once a RISK_DECISION reports real margin, the endpoint surfaces it."""
    app = _make_app()
    proj = app.state.risk_projection
    proj._state["margin_available"] = 123450.0
    client = TestClient(app)
    resp = client.get("/api/execution/risk")
    assert resp.status_code == 200
    assert resp.json()["margin_available"] == 123450.0
