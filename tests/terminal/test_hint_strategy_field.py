"""Tests for the strategy field on the strategy-hint response (Phase 3, 3A.2).

The StrategyHintResponse model gains ``strategy`` (populated from
``StrategyHint.strategy``) so the hints panel can label the proposed
structure. Verifies the model default and that the endpoint includes the
computed strategy name for both actionable and stand-aside hints.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shettyxtreme.terminal.api.intelligence_router import router
from shettyxtreme.terminal.api.models import StrategyHintResponse


class TestStrategyHintResponseModel:
    def test_strategy_field_round_trips(self) -> None:
        model = StrategyHintResponse(direction="bullish", strategy="Long Call")
        assert model.strategy == "Long Call"
        assert model.model_dump()["strategy"] == "Long Call"

    def test_strategy_defaults_none(self) -> None:
        model = StrategyHintResponse(direction="bullish")
        assert model.strategy is None


def _make_app(signal: dict) -> FastAPI:
    """App with a fake adapter chain + projection signal for strategy-hint."""
    app = FastAPI()
    app.include_router(router)

    class FakeAdapter:
        async def get_option_chain(
            self, underlying: str, expiry: str, strike_count: int,
        ) -> dict:
            return {
                "s": "ok",
                "underlying_ltp": 25000.0,
                "option_chain": [
                    {"strike": 24900.0, "option_type": "CE", "premium": 260.0, "iv": 0.15},
                    {"strike": 25000.0, "option_type": "CE", "premium": 120.0, "iv": 0.15},
                    {"strike": 25100.0, "option_type": "CE", "premium": 55.0, "iv": 0.15},
                    {"strike": 25000.0, "option_type": "PE", "premium": 110.0, "iv": 0.15},
                ],
            }

    proj = MagicMock()
    proj.get_signal.return_value = signal
    app.state.intelligence_projection = proj
    app.state.data_adapter = FakeAdapter()
    return app


@pytest.fixture()
def client():
    return TestClient(_make_app({
        "direction": "UP", "conviction": 0.8, "P": 0.9,
    }))


class TestStrategyHintEndpoint:
    def test_bullish_hint_carries_strategy(self, client) -> None:
        resp = client.get("/api/intelligence/strategy-hint")
        assert resp.status_code == 200
        data = resp.json()
        assert data["direction"] == "bullish"
        assert data["strategy"] == "Long Call"

    def test_bearish_hint_carries_long_put(self) -> None:
        client = TestClient(_make_app({
            "direction": "DOWN", "conviction": 0.8, "P": 0.9,
        }))
        data = client.get("/api/intelligence/strategy-hint").json()
        assert data["direction"] == "bearish"
        assert data["strategy"] == "Long Put"

    def test_neutral_signal_strategy_stand_aside(self) -> None:
        client = TestClient(_make_app({
            "direction": "NEUTRAL", "conviction": 0.0, "P": 1.0,
        }))
        data = client.get("/api/intelligence/strategy-hint").json()
        assert data["direction"] == "neutral"
        assert data["strategy"] == "stand_aside"

    def test_low_conviction_strategy_stand_aside(self) -> None:
        client = TestClient(_make_app({
            "direction": "UP", "conviction": 0.1, "P": 0.9,
        }))
        data = client.get("/api/intelligence/strategy-hint").json()
        assert data["strategy"] == "stand_aside"
