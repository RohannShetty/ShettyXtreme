"""Tests for AuthRouter (Fyers onboarding and OAuth callback)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.auth.fyers_oauth import FyersAuthError, FyersOAuthHelper, FyersTokenResult
from shettyxtreme.auth.validator import CredentialValidator, ValidationResult
import shettyxtreme.terminal.api.auth_router as _auth_router
from shettyxtreme.terminal.api.auth_router import (
    _get_store,
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
    oauth = MagicMock(spec=FyersOAuthHelper)
    oauth.generate_auth_url = MagicMock(
        return_value=(
            "https://api-t1.fyers.in/api/v3/generate-authcode"
            "?client_id=APP123&redirect_uri=http%3A%2F%2Ftestserver%2Fauth%2Ffyers%2Fcallback"
            "&response_type=code&state=state123&scope=openid&nonce=nonce123"
        )
    )
    oauth.exchange_auth_code = AsyncMock(
        return_value=FyersTokenResult(
            access_token="tok_fyers_123456",
            token_expiry="2026-12-31T23:59:59+00:00",
            client_id="FY123",
            refresh_token="rf_1",
        )
    )
    return oauth


def _make_mock_validator() -> MagicMock:
    validator = MagicMock(spec=CredentialValidator)
    validator.validate_credentials = AsyncMock(
        return_value=ValidationResult(valid=True, message="Credentials valid. Connect Fyers to obtain an access token.")
    )
    validator.validate_access_token = AsyncMock(
        return_value=ValidationResult(valid=True, message="Access token valid")
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
    assert data["broker"] == "fyers"


def test_save_credentials() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/auth/credentials",
        json={"app_id": "APP123", "secret_id": "SECRET456"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "saved" in data["message"].lower()
    status = client.get("/auth/status").json()
    assert status["has_api_key"] is True
    assert _get_store().app_id == "APP123"
    assert _get_store().secret_id == "SECRET456"
    assert _get_store().broker == "fyers"


def test_save_credentials_trims_whitespace() -> None:
    app = _make_app()
    client = TestClient(app)
    client.post(
        "/auth/credentials",
        json={"app_id": "  APP123  ", "secret_id": "  SECRET456  "},
    )
    assert _get_store().app_id == "APP123"
    assert _get_store().secret_id == "SECRET456"


def test_start_auth_returns_auth_url() -> None:
    app = _make_app()
    client = TestClient(app)
    client.post(
        "/auth/credentials",
        json={"app_id": "APP123", "secret_id": "SECRET456"},
    )
    resp = client.post("/auth/start-auth")
    assert resp.status_code == 200
    data = resp.json()
    assert "generate-authcode" in data["login_url"]
    assert "client_id=APP123" in data["login_url"]
    assert "state" in data
    # Callback redirect_uri is derived from the request base URL.
    assert "auth%2Ffyers%2Fcallback" in data["login_url"]


def test_start_auth_requires_saved_app_id() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/auth/start-auth")
    assert resp.status_code == 400
    assert "App ID" in resp.json()["detail"]


def test_fyers_callback_success() -> None:
    app = _make_app()
    client = TestClient(app, follow_redirects=False)

    client.post(
        "/auth/credentials",
        json={"app_id": "APP123", "secret_id": "SECRET456"},
    )

    resp = client.get(
        "/auth/fyers/callback?auth_code=code_jwt&user_id=FY123&state=state123"
    )
    assert resp.status_code == 307
    assert "connected=true" in resp.headers["location"]

    store = _get_store()
    assert store.access_token == "tok_fyers_123456"
    assert store.client_id == "FY123"
    assert store.token_expiry == "2026-12-31T23:59:59+00:00"
    assert store.is_token_valid() is True


def test_fyers_callback_triggers_bootstrap(monkeypatch) -> None:
    calls: list[str] = []

    async def _record_bootstrap() -> bool:
        calls.append("boot")
        return True

    monkeypatch.setattr(_auth_router, "run_terminal_init", _record_bootstrap)
    app = _make_app()
    client = TestClient(app, follow_redirects=False)

    client.post(
        "/auth/credentials",
        json={"app_id": "APP123", "secret_id": "SECRET456"},
    )

    resp = client.get("/auth/fyers/callback?auth_code=code_jwt&user_id=FY123")
    assert resp.status_code == 307
    assert "connected=true" in resp.headers["location"]
    assert calls == ["boot", "boot"]  # credentials save + callback


def test_fyers_callback_bootstrap_raises_still_connects(monkeypatch) -> None:
    async def _boom() -> bool:
        raise RuntimeError("pipeline init exploded")

    monkeypatch.setattr(_auth_router, "run_terminal_init", _boom)
    app = _make_app()
    client = TestClient(app, follow_redirects=False)

    client.post(
        "/auth/credentials",
        json={"app_id": "APP123", "secret_id": "SECRET456"},
    )

    resp = client.get("/auth/fyers/callback?auth_code=code_jwt&user_id=FY123")
    assert resp.status_code == 307
    assert "connected=true" in resp.headers["location"]


def test_fyers_callback_failure_redirects_fixed_error() -> None:
    raw_error = "Fyers API 500: some secret material must never leak"
    _auth_router._oauth.exchange_auth_code = AsyncMock(
        side_effect=FyersAuthError(raw_error)
    )
    app = _make_app()
    client = TestClient(app, follow_redirects=False)

    client.post(
        "/auth/credentials",
        json={"app_id": "APP123", "secret_id": "SECRET456"},
    )

    resp = client.get("/auth/fyers/callback?auth_code=bad_code&user_id=FY123")
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert "error=Authentication+failed" in location
    assert "secret material" not in location


def test_fyers_callback_missing_auth_code_redirects_error() -> None:
    app = _make_app()
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/auth/fyers/callback?user_id=FY123")
    assert resp.status_code == 307
    assert "error=Authentication+failed" in resp.headers["location"]


def test_auth_logout() -> None:
    app = _make_app()
    client = TestClient(app)
    client.post(
        "/auth/credentials",
        json={"app_id": "APP123", "secret_id": "SECRET456"},
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
        json={"app_id": "APP123", "secret_id": "SECRET456"},
    )
    resp = client.get("/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_api_key"] is True


def test_auth_test_validates_format_without_token() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/auth/test",
        json={"app_id": "APP123", "secret_id": "SECRET456"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert "Connect Fyers" in data["message"]


def test_auth_test_probes_fyers_token() -> None:
    """With a stored token, /auth/test runs the Fyers /profile probe."""
    store = _get_store()
    store.app_id = "APP123"
    store.secret_id = "SECRET456"
    store.access_token = "tok_probe"
    store.token_expiry = "2099-12-31T23:59:59+00:00"

    app = _make_app()
    client = TestClient(app)
    resp = client.post("/auth/test")  # no body — uses the stored credentials
    assert resp.status_code == 200
    data = resp.json()
    assert data["valid"] is True
    assert data["message"] == "Access token valid"
    _auth_router._validator.validate_access_token.assert_awaited_once_with(
        app_id="APP123", access_token="tok_probe"
    )


@pytest.mark.parametrize(
    "path",
    [
        "/auth/token",
        "/auth/token/pin-totp",
        "/auth/data-token",
        "/auth/start-consent",
        "/auth/dhan/callback",
    ],
)
def test_dhan_only_endpoints_removed(path: str) -> None:
    """Fyers has a single-token model — Dhan-only endpoints are gone."""
    app = _make_app()
    client = TestClient(app)
    resp = client.get(path, follow_redirects=False)
    assert resp.status_code == 404


def test_save_credentials_trigger_bootstrap(monkeypatch) -> None:
    calls: list[str] = []

    async def _record_bootstrap() -> bool:
        calls.append("boot")
        return True

    monkeypatch.setattr(_auth_router, "run_terminal_init", _record_bootstrap)
    app = _make_app()
    client = TestClient(app)

    resp = client.post(
        "/auth/credentials",
        json={"app_id": "APP123", "secret_id": "SECRET456"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "message": "Credentials saved"}
    assert calls == ["boot"]


def test_save_credentials_bootstrap_raises_still_saves(monkeypatch) -> None:
    async def _boom() -> bool:
        raise RuntimeError("pipeline init exploded")

    monkeypatch.setattr(_auth_router, "run_terminal_init", _boom)
    app = _make_app()
    client = TestClient(app)

    resp = client.post(
        "/auth/credentials",
        json={"app_id": "APP123", "secret_id": "SECRET456"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "message": "Credentials saved"}
    assert _get_store().app_id == "APP123"
