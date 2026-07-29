"""Tests for AuthRouter (onboarding and OAuth callback)."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.auth.dhan_oauth import ConsentResult, DhanOAuthHelper
from shettyxtreme.auth.validator import CredentialValidator, ValidationResult
from shettyxtreme.terminal.api.auth_router import (
    init_auth,
    router,
)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _make_store() -> CredentialStore:
    return CredentialStore()


def _make_mock_oauth() -> MagicMock:
    oauth = MagicMock(spec=DhanOAuthHelper)
    oauth.generate_consent = AsyncMock(return_value="consent_abc123")
    oauth.get_login_url = MagicMock(
        return_value="https://auth.dhan.co/login/consentApp-login?consentAppId=consent_abc123"
    )
    oauth.consume_consent = AsyncMock(
        return_value=ConsentResult(
            access_token="tok_abcdef123456",
            expiry_time="2026-12-31T23:59:59",
            client_id="DHAN123",
            client_name="Test User",
            ddpi_status=True,
        )
    )
    oauth.pop_consent_flow = MagicMock(return_value=True)
    return oauth


def _make_mock_validator() -> MagicMock:
    validator = MagicMock(spec=CredentialValidator)
    validator.validate_credentials = AsyncMock(
        return_value=ValidationResult(valid=True, message="Credentials valid")
    )
    return validator


@pytest.fixture(autouse=True)
def _reset_auth() -> None:
    init_auth(_make_store(), _make_mock_oauth(), _make_mock_validator())
    yield
    init_auth(_make_store(), _make_mock_oauth(), _make_mock_validator())


def test_auth_status_no_creds() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_api_key"] is False
    assert data["has_token"] is False
    assert data["token_valid"] is False
    assert data["connected"] is False


def test_save_credentials() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/auth/credentials",
        json={"api_key": "test_key_123", "api_secret": "test_secret_456"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "saved" in data["message"].lower()
    status = client.get("/auth/status").json()
    assert status["has_api_key"] is True


def test_start_consent() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/auth/start-consent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["consent_app_id"] == "consent_abc123"
    assert "login_url" in data
    assert "consentAppId" in data["login_url"]


def test_dhan_callback_unknown_flow() -> None:
    from shettyxtreme.terminal.api.auth_router import _oauth
    _oauth.pop_consent_flow = MagicMock(return_value=False)
    app = _make_app()
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/auth/dhan/callback?tokenId=test_token_999")
    assert resp.status_code == 307
    assert "setup.html" in resp.headers["location"]
    assert "error=unknown_flow" in resp.headers["location"]


def test_dhan_callback_success() -> None:
    app = _make_app()
    client = TestClient(app, follow_redirects=False)

    client.post(
        "/auth/credentials",
        json={"api_key": "trading_key", "api_secret": "trading_secret"},
    )

    resp = client.get("/auth/dhan/callback?tokenId=tok_trade_123&consentAppId=consent_trading_id")
    assert resp.status_code == 307
    assert "connected=true" in resp.headers["location"]

    status = client.get("/auth/status").json()
    assert status["has_token"] is True


def test_auth_logout() -> None:
    app = _make_app()
    client = TestClient(app)
    client.post(
        "/auth/credentials",
        json={"api_key": "key1", "api_secret": "secret1"},
    )
    resp = client.post("/auth/logout")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    status = client.get("/auth/status").json()
    assert status["has_token"] is False


def test_auth_status_with_creds() -> None:
    app = _make_app()
    client = TestClient(app)
    client.post(
        "/auth/credentials",
        json={"api_key": "my_trading_key", "api_secret": "my_secret"},
    )
    resp = client.get("/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_api_key"] is True
