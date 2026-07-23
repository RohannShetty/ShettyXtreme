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
    oauth.pop_consent_flow = MagicMock(return_value="trading")
    return oauth


def _make_mock_validator() -> MagicMock:
    validator = MagicMock(spec=CredentialValidator)
    validator.validate_trading = AsyncMock(
        return_value=ValidationResult(valid=True, message="Trading credentials valid")
    )
    validator.validate_data = AsyncMock(
        return_value=ValidationResult(valid=True, message="Data credentials valid")
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
    assert data["trading_has_api_key"] is False
    assert data["trading_has_token"] is False
    assert data["trading_valid"] is False
    assert data["data_has_api_key"] is False
    assert data["data_has_token"] is False
    assert data["data_valid"] is False


def test_save_trading_credentials() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/auth/credentials/trading",
        json={"api_key": "test_key_123", "api_secret": "test_secret_456"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "saved" in data["message"].lower() or "trading" in data["message"].lower()


def test_save_data_credentials() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/auth/credentials/data",
        json={"api_key": "data_key_789", "api_secret": "data_secret_012"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "saved" in data["message"].lower() or "data" in data["message"].lower()


def test_start_consent_trading() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/auth/start-consent/trading",
        json={"client_id": "DHAN123"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["consent_app_id"] == "consent_abc123"
    assert "login_url" in data
    assert "consentAppId" in data["login_url"]


def test_dhan_callback() -> None:
    from shettyxtreme.terminal.api.auth_router import _oauth
    _oauth.pop_consent_flow = MagicMock(return_value=None)
    app = _make_app()
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/auth/dhan/callback?tokenId=test_token_999")
    assert resp.status_code == 307
    assert "setup.html" in resp.headers["location"]
    assert "error=unknown_flow" in resp.headers["location"]


def test_dhan_callback_trading() -> None:
    app = _make_app()
    client = TestClient(app, follow_redirects=False)

    # Save credentials first
    client.post(
        "/auth/credentials/trading",
        json={"api_key": "trading_key", "api_secret": "trading_secret"},
    )

    resp = client.get("/auth/dhan/callback?tokenId=tok_trade_123&consentAppId=consent_trading_id")
    assert resp.status_code == 307
    assert "connected=trading" in resp.headers["location"]

    status = client.get("/auth/status").json()
    assert status["trading_has_token"] is True
    assert status["data_has_token"] is False


def test_dhan_callback_data() -> None:
    app = _make_app()
    client = TestClient(app, follow_redirects=False)

    # Save data credentials
    client.post(
        "/auth/credentials/data",
        json={"api_key": "data_key", "api_secret": "data_secret"},
    )

    # Configure mock to return "data" for this consent ID
    from shettyxtreme.terminal.api.auth_router import _oauth
    _oauth.pop_consent_flow = MagicMock(return_value="data")

    resp = client.get("/auth/dhan/callback?tokenId=tok_data_456&consentAppId=consent_data_id")
    assert resp.status_code == 307
    assert "connected=data" in resp.headers["location"]

    status = client.get("/auth/status").json()
    assert status["data_has_token"] is True
    assert status["trading_has_token"] is False


def test_auth_logout() -> None:
    app = _make_app()
    client = TestClient(app)
    # First save some trading credentials
    client.post(
        "/auth/credentials/trading",
        json={"api_key": "key1", "api_secret": "secret1"},
    )
    # Then logout
    resp = client.post("/auth/logout")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    # Verify tokens cleared by checking status
    status = client.get("/auth/status").json()
    assert status["trading_has_token"] is False
    assert status["data_has_token"] is False


def test_auth_status_with_creds() -> None:
    app = _make_app()
    client = TestClient(app)
    client.post(
        "/auth/credentials/trading",
        json={"api_key": "my_trading_key", "api_secret": "my_secret"},
    )
    client.post(
        "/auth/credentials/data",
        json={"api_key": "my_data_key", "api_secret": "my_data_secret"},
    )
    resp = client.get("/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["trading_has_api_key"] is True
    assert data["data_has_api_key"] is True
