"""Tests for scanner threshold settings (Phase 3A.1)."""
from __future__ import annotations

from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from shettyxtreme.core.settings import (
    SettingsError,
    SettingsStore,
    get_settings_store,
    init_settings_store,
    reset_settings_store,
)
from shettyxtreme.terminal.api.settings_router import router


@pytest_asyncio.fixture
async def client(tmp_path) -> AsyncIterator[AsyncClient]:
    init_settings_store(tmp_path / "settings.db")
    app = FastAPI()
    app.include_router(router)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
def _restore_store():
    yield
    reset_settings_store()


class TestSettingsStoreThresholds:
    """SettingsStore persists scanner_thresholds with shape validation."""

    def test_default_empty(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        assert store.scanner_thresholds() == {}

    def test_update_persists_and_reads_back(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        store.update({
            "scanner_thresholds": {
                "iv_crush": {"iv_rank_threshold": 60.0, "dte_threshold": 5},
                "pcr_extremes": {"pcr_low": 0.4},
            },
        })
        got = store.scanner_thresholds()
        assert got["iv_crush"]["iv_rank_threshold"] == 60.0
        assert got["iv_crush"]["dte_threshold"] == 5
        assert got["pcr_extremes"]["pcr_low"] == 0.4
        # Persisted: a fresh store instance over the same file sees it.
        again = SettingsStore(tmp_path / "settings.db")
        assert again.scanner_thresholds()["iv_crush"]["iv_rank_threshold"] == 60.0

    def test_non_numeric_value_rejected(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        with pytest.raises(SettingsError):
            store.update({"scanner_thresholds": {"iv_crush": {"iv_rank_threshold": "hot"}}})

    def test_non_mapping_rejected(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        with pytest.raises(SettingsError):
            store.update({"scanner_thresholds": [1, 2, 3]})
        with pytest.raises(SettingsError):
            store.update({"scanner_thresholds": {"iv_crush": 42}})

    def test_empty_update_clears_thresholds(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        store.update({"scanner_thresholds": {"iv_crush": {"iv_rank_threshold": 60.0}}})
        store.update({"scanner_thresholds": {}})
        assert store.scanner_thresholds() == {}


class TestThresholdsEndpoint:
    """GET/PUT /api/settings/scanner-thresholds."""

    @pytest.mark.asyncio
    async def test_get_defaults_empty(self, client: AsyncClient) -> None:
        resp = await client.get("/api/settings/scanner-thresholds")
        assert resp.status_code == 200
        assert resp.json() == {"scanner_thresholds": {}}

    @pytest.mark.asyncio
    async def test_put_persists_and_broadcasts(self, client: AsyncClient) -> None:
        with patch("shettyxtreme.terminal.api.settings_router.ws_bridge.broadcast", new=AsyncMock()) as bcast:
            resp = await client.put(
                "/api/settings/scanner-thresholds",
                json={"scanner_thresholds": {
                    "iv_crush": {"iv_rank_threshold": 55.0, "dte_threshold": 3},
                }},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["scanner_thresholds"]["iv_crush"]["iv_rank_threshold"] == 55.0
        bcast.assert_awaited_once()
        topic, payload = bcast.await_args.args
        assert topic == "scanner-thresholds"
        assert payload["scanner_thresholds"]["iv_crush"]["iv_rank_threshold"] == 55.0
        # Persisted — a fresh GET reflects the update.
        again = await client.get("/api/settings/scanner-thresholds")
        assert again.json()["scanner_thresholds"]["iv_crush"]["iv_rank_threshold"] == 55.0

    @pytest.mark.asyncio
    async def test_put_invalid_value_422(self, client: AsyncClient) -> None:
        # Type-invalid values are rejected by pydantic (422) before the
        # handler; the store's shape validation guards direct (non-HTTP) use.
        resp = await client.put(
            "/api/settings/scanner-thresholds",
            json={"scanner_thresholds": {"iv_crush": {"iv_rank_threshold": "nope"}}},
        )
        assert resp.status_code == 422
        # Store untouched.
        got = await client.get("/api/settings/scanner-thresholds")
        assert got.json() == {"scanner_thresholds": {}}

    @pytest.mark.asyncio
    async def test_put_float_coercion(self, client: AsyncClient) -> None:
        resp = await client.put(
            "/api/settings/scanner-thresholds",
            json={"scanner_thresholds": {"max_pain_drift": {"drift_threshold": 2.5}}},
        )
        assert resp.status_code == 200
        assert resp.json()["scanner_thresholds"]["max_pain_drift"]["drift_threshold"] == 2.5

    @pytest.mark.asyncio
    async def test_put_unknown_scanner_type_allowed_by_store(self, client: AsyncClient) -> None:
        # Shape validation lives in core; param-name validation happens when
        # scanners are (re)instantiated. Store accepts unknown types without
        # crashing.
        resp = await client.put(
            "/api/settings/scanner-thresholds",
            json={"scanner_thresholds": {"some_future_scanner": {"x": 1.0}}},
        )
        assert resp.status_code == 200
