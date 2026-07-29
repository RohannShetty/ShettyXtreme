"""Tests for CredentialValidator."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

import pytest

from shettyxtreme.auth.validator import CredentialValidator, ValidationResult


def test_validate_credentials_valid() -> None:
    async def _run() -> None:
        validator = CredentialValidator()
        result = await validator.validate_credentials(
            api_key="test_key", api_secret="test_secret", client_id="123"
        )
        assert result.valid is True
        assert "OAuth consent" in result.message
    asyncio.run(_run())


def test_validate_credentials_invalid_empty_key() -> None:
    async def _run() -> None:
        validator = CredentialValidator()
        result = await validator.validate_credentials(
            api_key="", api_secret="test_secret", client_id="123"
        )
        assert result.valid is False
    asyncio.run(_run())


def test_validate_credentials_invalid_empty_secret() -> None:
    async def _run() -> None:
        validator = CredentialValidator()
        result = await validator.validate_credentials(
            api_key="test_key", api_secret="", client_id="123"
        )
        assert result.valid is False
    asyncio.run(_run())


def test_validate_access_token_valid() -> None:
    async def _run() -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        with patch("shettyxtreme.auth.validator.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client
            validator = CredentialValidator()
            result = await validator.validate_access_token(access_token="valid_token")
            assert result.valid is True
    asyncio.run(_run())


def test_validate_access_token_expired() -> None:
    async def _run() -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
            "401", request=MagicMock(), response=mock_resp
        ))
        with patch("shettyxtreme.auth.validator.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client
            validator = CredentialValidator()
            result = await validator.validate_access_token(access_token="expired_token")
            assert result.valid is False
    asyncio.run(_run())


def test_validate_handles_network_error() -> None:
    async def _run() -> None:
        with patch("shettyxtreme.auth.validator.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client_cls.return_value = mock_client
            validator = CredentialValidator()
            result = await validator.validate_access_token(access_token="token")
            assert result.valid is False
            assert "error" in result.message.lower() or "invalid" in result.message.lower()
    asyncio.run(_run())
