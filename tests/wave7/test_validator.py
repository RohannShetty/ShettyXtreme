"""Tests for CredentialValidator (Fyers /profile liveness probe)."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from shettyxtreme.auth.validator import CredentialValidator, ValidationResult
from shettyxtreme.integration.fyers.client import FyersHTTPClient, FyersTokenExpired


def _mock_client(return_value=None, side_effect=None) -> MagicMock:
    client = MagicMock(spec=FyersHTTPClient)
    client.get = AsyncMock(return_value=return_value, side_effect=side_effect)
    return client


@pytest.mark.asyncio
async def test_validate_credentials_valid() -> None:
    validator = CredentialValidator()
    result = await validator.validate_credentials(app_id="APP", secret_id="SECRET")
    assert result.valid is True
    assert "Connect Fyers" in result.message


@pytest.mark.asyncio
async def test_validate_credentials_invalid_empty_app_id() -> None:
    validator = CredentialValidator()
    result = await validator.validate_credentials(app_id="", secret_id="SECRET")
    assert result.valid is False
    assert "App ID" in result.message


@pytest.mark.asyncio
async def test_validate_credentials_invalid_empty_secret() -> None:
    validator = CredentialValidator()
    result = await validator.validate_credentials(app_id="APP", secret_id="")
    assert result.valid is False


@pytest.mark.asyncio
async def test_validate_access_token_valid() -> None:
    client = _mock_client(return_value={"s": "ok", "data": {"name": "Rohan"}})
    validator = CredentialValidator(http_client=client)
    result = await validator.validate_access_token(app_id="APP", access_token="tok")
    assert result.valid is True
    assert "valid" in result.message.lower()
    client.get.assert_awaited_once_with("/profile")


@pytest.mark.asyncio
async def test_validate_access_token_401_expired() -> None:
    client = _mock_client(side_effect=FyersTokenExpired("HTTP 401"))
    validator = CredentialValidator(http_client=client)
    result = await validator.validate_access_token(app_id="APP", access_token="tok")
    assert result.valid is False
    assert "expired" in result.message.lower()


@pytest.mark.asyncio
async def test_validate_access_token_non_ok_200() -> None:
    client = _mock_client(return_value={"s": "error", "code": -99})
    validator = CredentialValidator(http_client=client)
    result = await validator.validate_access_token(app_id="APP", access_token="tok")
    assert result.valid is False
    assert "rejected" in result.message.lower()


@pytest.mark.asyncio
async def test_validate_access_token_handles_network_error() -> None:
    client = _mock_client(side_effect=httpx.ConnectError("refused"))
    validator = CredentialValidator(http_client=client)
    result = await validator.validate_access_token(app_id="APP", access_token="tok")
    assert result.valid is False
    assert "network" in result.message.lower()


@pytest.mark.asyncio
async def test_validate_access_token_handles_unexpected_error() -> None:
    client = _mock_client(side_effect=RuntimeError("boom"))
    validator = CredentialValidator(http_client=client)
    result = await validator.validate_access_token(app_id="APP", access_token="tok")
    assert result.valid is False
