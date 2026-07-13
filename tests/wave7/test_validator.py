"""Tests for CredentialValidator (read-only credential validation)."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx

import pytest

from shettyxtreme.auth.validator import CredentialValidator, ValidationResult


def test_validate_trading_valid() -> None:
    """Mock httpx.post returning success, verify valid=True."""
    import asyncio

    async def _run() -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "tok_abc123"}

        with patch("shettyxtreme.auth.validator.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            validator = CredentialValidator()
            result = await validator.validate_trading(
                api_key="test_key", api_secret="test_secret", client_id="123"
            )
            assert result.valid is True
            assert "Trading credentials valid" in result.message

    asyncio.run(_run())


def test_validate_trading_invalid() -> None:
    """Mock httpx.post returning error, verify valid=False."""
    import asyncio

    async def _run() -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": "invalid_key"}
        mock_resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
            "401", request=MagicMock(), response=mock_resp
        ))

        with patch("shettyxtreme.auth.validator.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            validator = CredentialValidator()
            result = await validator.validate_trading(
                api_key="bad_key", api_secret="bad_secret", client_id="123"
            )
            assert result.valid is False
            assert "Trading credentials invalid" in result.message

    asyncio.run(_run())


def test_validate_data_valid() -> None:
    """Mock httpx.post returning success for data API, verify valid=True."""
    import asyncio

    async def _run() -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "tok_abc123"}

        with patch("shettyxtreme.auth.validator.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            validator = CredentialValidator()
            result = await validator.validate_data(
                api_key="test_key", api_secret="test_secret", client_id="123"
            )
            assert result.valid is True
            assert "Data credentials valid" in result.message

    asyncio.run(_run())


def test_validate_data_invalid() -> None:
    """Mock httpx.post returning error for data API, verify valid=False."""
    import asyncio

    async def _run() -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.json.return_value = {"error": "invalid_key"}
        mock_resp.raise_for_status = MagicMock(side_effect=httpx.HTTPStatusError(
            "401", request=MagicMock(), response=mock_resp
        ))

        with patch("shettyxtreme.auth.validator.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            validator = CredentialValidator()
            result = await validator.validate_data(
                api_key="bad_key", api_secret="bad_secret", client_id="123"
            )
            assert result.valid is False
            assert "Data credentials invalid" in result.message

    asyncio.run(_run())


def test_validate_access_token_trading_valid() -> None:
    """Mock httpx.get returning 200 for trading token, verify valid=True."""
    import asyncio

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
            result = await validator.validate_access_token(
                access_token="valid_token", is_trading=True
            )
            assert result.valid is True

    asyncio.run(_run())


def test_validate_access_token_trading_expired() -> None:
    """Mock httpx.get returning 401 for trading token, verify valid=False."""
    import asyncio

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
            result = await validator.validate_access_token(
                access_token="expired_token", is_trading=True
            )
            assert result.valid is False

    asyncio.run(_run())


def test_validate_access_token_data_valid() -> None:
    """Mock httpx.get returning 200 for data token, verify valid=True."""
    import asyncio

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
            result = await validator.validate_access_token(
                access_token="valid_token", is_trading=False
            )
            assert result.valid is True

    asyncio.run(_run())


def test_validate_access_token_data_expired() -> None:
    """Mock httpx.get returning 401 for data token, verify valid=False."""
    import asyncio

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
            result = await validator.validate_access_token(
                access_token="expired_token", is_trading=False
            )
            assert result.valid is False

    asyncio.run(_run())


def test_validate_handles_network_error() -> None:
    """Mock httpx raising exception, verify valid=False with error message."""
    import asyncio

    async def _run() -> None:
        with patch("shettyxtreme.auth.validator.httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("Connection refused"))
            mock_client_cls.return_value = mock_client

            validator = CredentialValidator()
            result = await validator.validate_access_token(
                access_token="token", is_trading=True
            )
            assert result.valid is False
            assert "error" in result.message.lower() or "invalid" in result.message.lower()

    asyncio.run(_run())
