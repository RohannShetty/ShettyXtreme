"""Tests for POST /api/intelligence/propose-from-hint (Phase 3, task 3A.2).

Verifies one-click proposal generation from a hint payload: a PENDING
proposal is queued on the ExecutionEngine (OBSERVER-first, D10), the
response reuses the ProposalResponse shape with source="manual_hint",
neutral/unknown directions are rejected, and a missing execution engine
surfaces as 503.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shettyxtreme.execution.execution_engine import ExecutionEngine
from shettyxtreme.intelligence.risk.risk_engine import RiskEngine
from shettyxtreme.terminal.api.hint_store import HintStore
from shettyxtreme.terminal.api.intelligence_router import router

_BULLISH_PAYLOAD = {
    "symbol": "NIFTY",
    "direction": "bullish",
    "strike": 25000.0,
    "premium": 150.0,
    "expiry": "27AUG2026",
    "option_type": "CE",
    "lot_size": 75,
    "lots": 1,
    "stop_loss": 75.0,
    "target": 300.0,
    "rationale": "test hint proposal",
    "confidence": 0.8,
}


def _make_app(tmp_path, with_engine: bool = True) -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    if with_engine:
        app.state.execution_engine = ExecutionEngine(
            executor=MagicMock(),
            risk_engine=RiskEngine(),
            db_path=None,
        )
    return app


@pytest.fixture()
def client(tmp_path):
    return TestClient(_make_app(tmp_path))


class TestProposeFromHint:
    def test_creates_pending_proposal(self, client) -> None:
        resp = client.post("/api/intelligence/propose-from-hint", json=_BULLISH_PAYLOAD)
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"]
        assert data["symbol"] == "NIFTY"
        assert data["side"] == "BUY"
        assert data["quantity"] == 75
        assert data["lots"] == 1
        assert data["lot_size"] == 75
        assert data["strike"] == 25000.0
        assert data["price"] == 150.0
        assert data["entry_premium"] == 150.0
        assert data["expiry"] == "27AUG2026"
        assert data["option_type"] == "CE"
        assert data["stop_loss"] == 75.0
        assert data["target"] == 300.0
        assert data["rationale"] == "test hint proposal"
        assert data["source"] == "manual_hint"
        assert data["hint_kind"] == "manual_hint"
        assert data["strategy"] == "Long Call"
        assert data["status"] == "PENDING"
        assert data["conviction"] == 0.8

    def test_bearish_creates_sell_proposal(self, client) -> None:
        payload = {**_BULLISH_PAYLOAD, "direction": "bearish"}
        resp = client.post("/api/intelligence/propose-from-hint", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["side"] == "SELL"
        assert data["option_type"] == "CE"  # explicit CE preserved
        assert data["strategy"] == "Long Put"

    def test_option_type_derived_from_direction(self, client) -> None:
        payload = {**_BULLISH_PAYLOAD}
        payload.pop("option_type")
        resp = client.post("/api/intelligence/propose-from-hint", json=payload)
        assert resp.status_code == 200
        assert resp.json()["option_type"] == "CE"
        payload = {**_BULLISH_PAYLOAD, "direction": "bearish"}
        payload.pop("option_type")
        resp = client.post("/api/intelligence/propose-from-hint", json=payload)
        assert resp.status_code == 200
        assert resp.json()["option_type"] == "PE"

    def test_quantity_from_lot_size_when_lots_absent(self, client) -> None:
        payload = {**_BULLISH_PAYLOAD}
        payload.pop("lots")
        resp = client.post("/api/intelligence/propose-from-hint", json=payload)
        assert resp.status_code == 200
        assert resp.json()["quantity"] == 75

    def test_up_down_direction_aliases(self, client) -> None:
        resp = client.post(
            "/api/intelligence/propose-from-hint",
            json={**_BULLISH_PAYLOAD, "direction": "UP"},
        )
        assert resp.status_code == 200
        assert resp.json()["side"] == "BUY"
        resp = client.post(
            "/api/intelligence/propose-from-hint",
            json={**_BULLISH_PAYLOAD, "direction": "DOWN"},
        )
        assert resp.status_code == 200
        assert resp.json()["side"] == "SELL"

    def test_neutral_direction_rejected(self, client) -> None:
        resp = client.post(
            "/api/intelligence/propose-from-hint",
            json={**_BULLISH_PAYLOAD, "direction": "neutral"},
        )
        assert resp.status_code == 422
        assert "neutral" in resp.json()["detail"]

    def test_unknown_direction_rejected(self, client) -> None:
        resp = client.post(
            "/api/intelligence/propose-from-hint",
            json={**_BULLISH_PAYLOAD, "direction": "sideways"},
        )
        assert resp.status_code == 422

    def test_missing_engine_returns_503(self, tmp_path) -> None:
        client = TestClient(_make_app(tmp_path, with_engine=False))
        resp = client.post("/api/intelligence/propose-from-hint", json=_BULLISH_PAYLOAD)
        assert resp.status_code == 503

    def test_proposal_is_approvable_later(self, client) -> None:
        """The queued proposal must be a real PendingApproval (not a stub)."""
        resp = client.post("/api/intelligence/propose-from-hint", json=_BULLISH_PAYLOAD)
        approval_id = resp.json()["id"]
        engine = client.app.state.execution_engine
        approval = engine.get_approval(approval_id)
        assert approval is not None
        assert approval.status == "PENDING"
        assert approval.signal.direction.name == "UP"
        assert approval.strategy_hint["symbol"] == "NIFTY"


class TestProposeFromHintRecordsHint:
    """The endpoint also records the hint for accuracy tracking (3A.2)."""

    @pytest.fixture()
    def client_with_store(self, tmp_path):
        app = _make_app(tmp_path)
        app.state.hint_store = HintStore(db_path=str(tmp_path / "hints.db"))
        return TestClient(app)

    def test_hint_recorded_on_proposal(self, client_with_store) -> None:
        resp = client_with_store.post(
            "/api/intelligence/propose-from-hint", json=_BULLISH_PAYLOAD
        )
        assert resp.status_code == 200
        stats = client_with_store.app.state.hint_store.get_stats()
        assert stats["total_hints"] == 1
        assert stats["sample_size"] == 0  # unresolved so far

    def test_hint_missing_store_is_best_effort(self, client) -> None:
        """No hint store wired → the proposal still succeeds."""
        resp = client.post("/api/intelligence/propose-from-hint", json=_BULLISH_PAYLOAD)
        assert resp.status_code == 200
