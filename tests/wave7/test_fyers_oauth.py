"""Tests for FyersOAuthHelper (Fyers OAuth2 authorization-code flow)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from shettyxtreme.auth.fyers_oauth import (
    AUTH_BASE_URL,
    GENERATE_AUTHCODE_URL,
    VALIDATE_AUTHCODE_URL,
    FyersAuthError,
    FyersOAuthHelper,
)


def test_generate_auth_url_structure() -> None:
    helper = FyersOAuthHelper()
    url = helper.generate_auth_url(
        app_id="ABC123",
        redirect_uri="http://localhost:8000/auth/fyers/callback",
        state="state_token",
    )
    assert url.startswith(f"{GENERATE_AUTHCODE_URL}?")
    assert "client_id=ABC123" in url
    assert "redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fauth%2Ffyers%2Fcallback" in url
    assert "response_type=code" in url
    assert "state=state_token" in url
    assert "scope=openid" in url
    assert "nonce=" in url


def test_generate_auth_url_generates_state_when_missing() -> None:
    helper = FyersOAuthHelper()
    url = helper.generate_auth_url(app_id="ABC123", redirect_uri="http://localhost/cb")
    assert "state=" in url
    # Two calls produce different states (fresh CSRF token each time).
    url2 = helper.generate_auth_url(app_id="ABC123", redirect_uri="http://localhost/cb")
    state1 = url.split("state=")[1].split("&")[0]
    state2 = url2.split("state=")[1].split("&")[0]
    assert state1 != state2


def test_compute_app_id_hash_sha256() -> None:
    digest = FyersOAuthHelper.compute_app_id_hash("APP", "SECRET")
    assert len(digest) == 64  # sha256 hex
    # Deterministic, and matches the documented appIdHash construction.
    assert digest == FyersOAuthHelper.compute_app_id_hash("APP", "SECRET")
    assert digest != FyersOAuthHelper.compute_app_id_hash("APP", "OTHER")


@pytest.mark.asyncio
async def test_exchange_auth_code_success() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "s": "ok",
        "code": 200,
        "access_token": "tok_abc123",
        "refresh_token": "rf_xyz",
        "fy_id": "FY12345",
    }

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        helper = FyersOAuthHelper()
        result = await helper.exchange_auth_code(
            app_id="APP", secret_id="SECRET", auth_code="code_jwt"
        )
        assert result.access_token == "tok_abc123"
        assert result.refresh_token == "rf_xyz"
        assert result.client_id == "FY12345"
        assert result.token_expiry  # ISO-8601 expiry always present

        # appIdHash must be the sha256 of "APP:SECRET".
        sent = mock_client.post.call_args.kwargs["json"]
        assert sent["grant_type"] == "authorization_code"
        assert sent["code"] == "code_jwt"
        assert sent["appIdHash"] == FyersOAuthHelper.compute_app_id_hash("APP", "SECRET")


@pytest.mark.asyncio
async def test_exchange_auth_code_user_id_takes_precedence() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "s": "ok",
        "code": 200,
        "access_token": "tok_1",
        "fy_id": "FROM_RESPONSE",
    }

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        helper = FyersOAuthHelper()
        result = await helper.exchange_auth_code(
            app_id="APP", secret_id="SECRET", auth_code="code", user_id="FROM_REDIRECT"
        )
        assert result.client_id == "FROM_REDIRECT"


@pytest.mark.asyncio
async def test_exchange_auth_code_raises_on_http_error_status() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.json.return_value = {"s": "error", "code": -2}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        helper = FyersOAuthHelper()
        with pytest.raises(FyersAuthError):
            await helper.exchange_auth_code("APP", "SECRET", "bad_code")


@pytest.mark.asyncio
async def test_exchange_auth_code_raises_on_error_body() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"s": "error", "code": -15}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        helper = FyersOAuthHelper()
        with pytest.raises(FyersAuthError):
            await helper.exchange_auth_code("APP", "SECRET", "bad_code")


@pytest.mark.asyncio
async def test_exchange_auth_code_raises_on_network_error() -> None:
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mock_client_cls.return_value = mock_client

        helper = FyersOAuthHelper()
        with pytest.raises(FyersAuthError):
            await helper.exchange_auth_code("APP", "SECRET", "code")


@pytest.mark.asyncio
async def test_exchange_auth_code_client_id_from_auth_code_jwt_fallback() -> None:
    """When the response carries no client id and no user_id is passed, the
    fy_id is decoded from the auth-code JWT payload."""
    import base64
    import json as _json

    payload = {"fy_id": "FY_JWT_99"}
    body = base64.urlsafe_b64encode(_json.dumps(payload).encode()).decode().rstrip("=")
    auth_code = f"header.{body}.signature"

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "s": "ok",
        "code": 200,
        "access_token": "tok_1",
    }

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        helper = FyersOAuthHelper()
        result = await helper.exchange_auth_code("APP", "SECRET", auth_code)
        assert result.client_id == "FY_JWT_99"


def test_auth_endpoint_constants() -> None:
    assert AUTH_BASE_URL == "https://api-t1.fyers.in/api/v3"
    assert GENERATE_AUTHCODE_URL.endswith("/generate-authcode")
    assert VALIDATE_AUTHCODE_URL.endswith("/validate-authcode")
