"""F2 — Fyers session lifecycle tests.

Covers the expiry check, the ``/profile`` liveness probe, token refresh, and
persist/load round-tripping through the encrypted credential store.
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.integration.fyers.client import FyersTokenExpired
from shettyxtreme.integration.fyers.session import FyersSession

APP = "APP123"
SECRET = "SECRET1"
TOKEN = "TOK_LIVE"


class TestIsValid:
    def test_expired_token_is_invalid(self) -> None:
        session = FyersSession(
            APP, SECRET, TOKEN, token_expiry=datetime(2020, 1, 1, tzinfo=UTC)
        )
        assert session.is_valid() is False

    def test_future_token_is_valid(self) -> None:
        session = FyersSession(
            APP, SECRET, TOKEN, token_expiry=datetime(2099, 1, 1, tzinfo=UTC)
        )
        assert session.is_valid() is True

    def test_naive_expiry_assumed_utc(self) -> None:
        session = FyersSession(APP, SECRET, TOKEN, token_expiry=datetime(2099, 1, 1))
        assert session.is_valid() is True

    def test_unknown_expiry_is_treated_as_expired(self) -> None:
        """F-INT-009 regression: an unknown expiry cannot be proven valid.

        Fyers does not publish a TTL; a session without a recorded expiry is
        treated as expired so the LIVE session-validity gate forces re-auth
        instead of waving an unverifiable token through.
        """
        session = FyersSession(APP, SECRET, TOKEN)
        assert session.token_expiry is None
        assert session.is_valid() is False


class TestProbeLiveness:
    @pytest.mark.asyncio
    async def test_profile_200_returns_true(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(return_value={"s": "ok"})
        session = FyersSession(APP, SECRET, TOKEN)
        assert await session.probe_liveness(client) is True
        client.get.assert_awaited_once_with("/profile")

    @pytest.mark.asyncio
    async def test_token_expired_returns_false(self) -> None:
        client = AsyncMock()
        client.get = AsyncMock(side_effect=FyersTokenExpired("expired"))
        session = FyersSession(APP, SECRET, TOKEN)
        assert await session.probe_liveness(client) is False
        client.get.assert_awaited_once_with("/profile")


class TestUpdateToken:
    def test_update_token_refreshes_state(self) -> None:
        session = FyersSession(APP, SECRET, "OLD")
        expiry = datetime(2099, 6, 1, 9, 15, tzinfo=UTC)
        session.update_token("NEW_TOKEN", expiry)
        assert session.access_token == "NEW_TOKEN"
        assert session.token_expiry == expiry


class TestPersistLoad:
    def test_round_trip_through_credential_store(self, monkeypatch) -> None:
        store = CredentialStore()
        monkeypatch.setattr(store, "save", lambda: None)  # never touch disk
        expiry = datetime(2099, 6, 1, 9, 15, tzinfo=UTC)
        session = FyersSession(APP, SECRET, TOKEN, token_expiry=expiry)
        session.persist(store)

        assert store.app_id == APP
        assert store.secret_id == SECRET
        assert store.access_token == TOKEN
        assert store.token_expiry == "2099-06-01T09:15:00+00:00"

        loaded = FyersSession.load(store)
        assert loaded is not None
        assert loaded.app_id == APP
        assert loaded.secret_id == SECRET
        assert loaded.access_token == TOKEN
        assert loaded.token_expiry == expiry

    def test_load_missing_store_returns_none(self) -> None:
        assert FyersSession.load(None) is None

    def test_load_empty_store_returns_none(self, monkeypatch) -> None:
        store = CredentialStore()
        monkeypatch.setattr(store, "save", lambda: None)
        assert FyersSession.load(store) is None

    def test_round_trip_without_expiry(self, monkeypatch) -> None:
        store = CredentialStore()
        monkeypatch.setattr(store, "save", lambda: None)
        FyersSession(APP, SECRET, TOKEN).persist(store)
        loaded = FyersSession.load(store)
        assert loaded is not None
        assert loaded.token_expiry is None
        # Unknown expiry = cannot be proven live = treated as expired (F-INT-009).
        assert loaded.is_valid() is False

    def test_persist_load_round_trip_with_fyers_fields(self) -> None:
        """Regression (F2 x F5): persist/load must round-trip the Fyers
        field names (app_id/secret_id) through the credential store — never
        the dropped Dhan-era api_key/api_secret/data_access_token."""
        store = SimpleNamespace(
            app_id="",
            secret_id="",
            access_token=None,
            token_expiry=None,
            save=lambda: None,  # never touch disk
        )
        expiry = datetime(2099, 6, 1, 9, 15, tzinfo=UTC)
        session = FyersSession(APP, SECRET, TOKEN, token_expiry=expiry)
        session.persist(store)

        # Written under the Fyers field names, not Dhan-era ones.
        assert store.app_id == APP
        assert store.secret_id == SECRET
        assert store.access_token == TOKEN
        assert store.token_expiry == "2099-06-01T09:15:00+00:00"
        assert not hasattr(store, "api_key")
        assert not hasattr(store, "api_secret")
        assert not hasattr(store, "data_access_token")

        loaded = FyersSession.load(store)
        assert loaded is not None
        assert loaded.app_id == APP
        assert loaded.secret_id == SECRET
        assert loaded.access_token == TOKEN
        assert loaded.token_expiry == expiry
