"""Tests for AuthRouter (onboarding and OAuth callback)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.auth.dhan_oauth import ConsentResult, ConsumeResult, DhanOAuthHelper
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
    oauth = MagicMock(spec=DhanOAuthHelper)
    oauth.generate_consent = AsyncMock(return_value="consent_abc123")
    oauth.get_login_url = MagicMock(
        return_value="https://auth.dhan.co/login/consentApp-login?consentAppId=consent_abc123"
    )
    oauth.consume_consent = AsyncMock(
        return_value=ConsumeResult(
            consent=ConsentResult(
                access_token="tok_abcdef123456",
                expiry_time="2026-12-31T23:59:59",
                client_id="DHAN123",
                client_name="Test User",
                ddpi_status=True,
            )
        )
    )
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


def test_dhan_callback_success() -> None:
    app = _make_app()
    client = TestClient(app, follow_redirects=False)

    client.post(
        "/auth/credentials",
        json={"api_key": "trading_key", "api_secret": "trading_secret"},
    )

    resp = client.get("/auth/dhan/callback?tokenId=tok_trade_123")
    assert resp.status_code == 307
    assert "connected=true" in resp.headers["location"]

    status = client.get("/auth/status").json()
    assert status["has_token"] is True


def test_dhan_callback_triggers_bootstrap(monkeypatch) -> None:
    calls: list[str] = []

    async def _record_bootstrap() -> bool:
        calls.append("boot")
        return True

    monkeypatch.setattr(_auth_router, "run_terminal_init", _record_bootstrap)
    app = _make_app()
    client = TestClient(app, follow_redirects=False)

    client.post(
        "/auth/credentials",
        json={"api_key": "trading_key", "api_secret": "trading_secret"},
    )

    resp = client.get("/auth/dhan/callback?tokenId=tok_trade_123")
    assert resp.status_code == 307
    assert "connected=true" in resp.headers["location"]
    assert calls == ["boot", "boot"]


def test_dhan_callback_bootstrap_raises_still_connects(monkeypatch) -> None:
    async def _boom() -> bool:
        raise RuntimeError("pipeline init exploded")

    monkeypatch.setattr(_auth_router, "run_terminal_init", _boom)
    app = _make_app()
    client = TestClient(app, follow_redirects=False)

    client.post(
        "/auth/credentials",
        json={"api_key": "trading_key", "api_secret": "trading_secret"},
    )

    resp = client.get("/auth/dhan/callback?tokenId=tok_trade_123")
    assert resp.status_code == 307
    assert "connected=true" in resp.headers["location"]


def test_dhan_callback_failure_redirects_fixed_error() -> None:
    raw_error = "Dhan API 500: some secret material must never leak"
    _auth_router._oauth.consume_consent = AsyncMock(
        return_value=ConsumeResult(error=raw_error)
    )
    app = _make_app()
    client = TestClient(app, follow_redirects=False)

    client.post(
        "/auth/credentials",
        json={"api_key": "trading_key", "api_secret": "trading_secret"},
    )

    resp = client.get("/auth/dhan/callback?tokenId=tok_trade_123")
    assert resp.status_code == 307
    location = resp.headers["location"]
    assert "error=Authentication+failed" in location
    assert "secret material" not in location


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


def test_post_direct_token() -> None:
    import base64
    import json as _json

    payload = {"dhanClientId": "DHAN123", "exp": 1780000000}
    body = base64.urlsafe_b64encode(_json.dumps(payload).encode()).decode().rstrip("=")
    token = f"header.{body}.signature"
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/auth/token", json={"access_token": token})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert _get_store().client_id == "DHAN123"
    assert _get_store().access_token == token
    assert _get_store().token_expiry.startswith("2026-")


def test_post_direct_token_invalid() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/auth/token", json={"access_token": "garbage"})
    assert resp.status_code == 400


def test_pin_totp_success() -> None:
    _auth_router._oauth.generate_access_token = AsyncMock(
        return_value=ConsumeResult(
            consent=ConsentResult(
                access_token="tok_pintotp",
                expiry_time="2026-12-31T23:59:59",
                client_id="DHAN123",
                client_name="PIN User",
                ddpi_status=True,
            )
        )
    )
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/auth/token/pin-totp",
        json={"client_id": "DHAN123", "pin": "1234", "totp": "567890"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert _get_store().access_token == "tok_pintotp"
    assert _get_store().client_id == "DHAN123"


def test_pin_totp_bad_credentials() -> None:
    _auth_router._oauth.generate_access_token = AsyncMock(
        return_value=ConsumeResult(
            error="Dhan API 401: Invalid client id. Re-enter credentials in Step 1."
        )
    )
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/auth/token/pin-totp",
        json={"client_id": "X", "pin": "0", "totp": "0"},
    )
    assert resp.status_code == 400
    assert "401" in resp.json()["detail"]


def test_save_data_token() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/auth/data-token",
        json={"access_token": "data_tok_1", "expiry": "2026-12-31T23:59:59"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert _get_store().data_access_token == "data_tok_1"
    assert _get_store().data_access_token_expiry == "2026-12-31T23:59:59"


def test_status_data_token_fields() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/auth/status")
    data = resp.json()
    assert "data_token_valid" in data
    assert "data_token_expiry" in data
    assert data["data_token_valid"] is False
    assert data["data_token_expiry"] is None


@pytest.mark.parametrize(
    "path, body, expected_message",
    [
        (
            "/auth/credentials",
            {"api_key": "cid:::key", "api_secret": "secret"},
            "Credentials saved",
        ),
        (
            "/auth/token",
            {"access_token": "eyJhbGciOiJIUzI1NiJ9.eyJkaGFuQ2xpZW50SWQiOiIxMjMifQ.sig"},
            "Access token saved",
        ),
        (
            "/auth/data-token",
            {"access_token": "tok", "expiry": None},
            "Data access token saved",
        ),
        (
            "/auth/token/pin-totp",
            {"client_id": "123", "pin": "1234", "totp": "123456"},
            "Access token generated and saved",
        ),
    ],
)
def test_save_endpoints_trigger_bootstrap(
    monkeypatch, path: str, body: dict, expected_message: str
) -> None:
    calls: list[str] = []

    async def _record_bootstrap() -> bool:
        calls.append("boot")
        return True

    if path == "/auth/token/pin-totp":
        _auth_router._oauth.generate_access_token = AsyncMock(
            return_value=ConsumeResult(
                consent=ConsentResult(
                    access_token="tok_pintotp",
                    expiry_time="2026-12-31T23:59:59",
                    client_id="123",
                    client_name="PIN User",
                    ddpi_status=True,
                )
            )
        )
    monkeypatch.setattr(_auth_router, "run_terminal_init", _record_bootstrap)
    app = _make_app()
    client = TestClient(app)

    resp = client.post(path, json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"success": True, "message": expected_message}
    assert calls == ["boot"]


def test_save_credentials_bootstrap_raises_still_saves(monkeypatch) -> None:
    async def _boom() -> bool:
        raise RuntimeError("pipeline init exploded")

    monkeypatch.setattr(_auth_router, "run_terminal_init", _boom)
    app = _make_app()
    client = TestClient(app)

    resp = client.post(
        "/auth/credentials",
        json={"api_key": "cid:::key", "api_secret": "secret"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"success": True, "message": "Credentials saved"}
    assert _get_store().api_key == "key"
