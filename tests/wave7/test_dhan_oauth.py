"""Tests for DhanOAuthHelper (Dhan OAuth consent flow)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from shettyxtreme.auth.dhan_oauth import ConsentResult, DhanOAuthHelper


@pytest.mark.asyncio
async def test_generate_consent_success() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "consentAppId": "test123",
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        helper = DhanOAuthHelper()
        result = await helper.generate_consent(
            api_key="key123",
            api_secret="secret456",
            client_id="C123",
        )
        assert result == "test123"


@pytest.mark.asyncio
async def test_generate_consent_failure() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.json.return_value = {"status": "error", "message": "server error"}
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "HTTP error", request=MagicMock(), response=mock_response,
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        helper = DhanOAuthHelper()
        result = await helper.generate_consent(
            api_key="key123",
            api_secret="secret456",
            client_id="C123",
        )
        assert result is None


def test_get_login_url() -> None:
    helper = DhanOAuthHelper()
    url = helper.get_login_url("consent_app_abc")
    expected = (
        "https://auth.dhan.co/login/consentApp-login"
        "?consentAppId=consent_app_abc"
    )
    assert url == expected


@pytest.mark.asyncio
async def test_consume_consent_success() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "status": "success",
        "accessToken": "tok_abc123",
        "expiryTime": "2026-12-31T23:59:59+00:00",
        "clientId": "C123",
        "clientName": "TestClient",
        "ddpiStatus": True,
    }
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        helper = DhanOAuthHelper()
        result = await helper.consume_consent(
            api_key="key123",
            api_secret="secret456",
            token_id="token_xyz",
        )
        assert result is not None
        assert result.access_token == "tok_abc123"
        assert result.expiry_time == "2026-12-31T23:59:59+00:00"
        assert result.client_id == "C123"
        assert result.client_name == "TestClient"
        assert result.ddpi_status is True


@pytest.mark.asyncio
async def test_consume_consent_failure() -> None:
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.json.return_value = {"status": "error"}
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
        "HTTP error", request=MagicMock(), response=mock_response,
    )

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        helper = DhanOAuthHelper()
        result = await helper.consume_consent(
            api_key="key123",
            api_secret="secret456",
            token_id="token_xyz",
        )
        assert result is None


@pytest.mark.asyncio
async def test_generate_consent_handles_network_error() -> None:
    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=httpx.ConnectError("connection refused"))
        mock_client_cls.return_value = mock_client

        helper = DhanOAuthHelper()
        result = await helper.generate_consent(
            api_key="key123",
            api_secret="secret456",
            client_id="C123",
        )
        assert result is None
