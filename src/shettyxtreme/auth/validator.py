"""Read-only credential validator for Dhan API.

Validates credentials by making harmless API calls.
Never places orders or modifies anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


TRADING_BASE = "https://api.dhan.co/v2"
DATA_BASE = "https://api.dhan.co/v2"
_TRADING_TOKEN_URL = f"{TRADING_BASE}/oauth2/token"
_DATA_TOKEN_URL = f"{DATA_BASE}/oauth2/token"
_TRADING_FUND_LIMITS_URL = f"{TRADING_BASE}/fund_limits"
_DATA_LTP_URL = f"{DATA_BASE}/marketdata/ltp"


@dataclass
class ValidationResult:
    valid: bool
    message: str
    details: dict[str, Any] | None = None


class CredentialValidator:

    async def validate_trading(
        self, api_key: str, api_secret: str, client_id: str
    ) -> ValidationResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _TRADING_TOKEN_URL,
                    data={
                        "client_id": client_id,
                        "grant_type": "client_credentials",
                        "secret": api_secret,
                    },
                    headers={"api-key": api_key},
                )
                resp.raise_for_status()
                data = resp.json()
                return ValidationResult(
                    valid=True,
                    message="Trading credentials valid",
                    details=data,
                )
        except Exception as exc:
            return ValidationResult(
                valid=False,
                message=f"Trading credentials invalid: {exc}",
            )

    async def validate_data(
        self, api_key: str, api_secret: str, client_id: str
    ) -> ValidationResult:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    _DATA_TOKEN_URL,
                    data={
                        "client_id": client_id,
                        "grant_type": "client_credentials",
                        "secret": api_secret,
                    },
                    headers={"api-key": api_key},
                )
                resp.raise_for_status()
                data = resp.json()
                return ValidationResult(
                    valid=True,
                    message="Data credentials valid",
                    details=data,
                )
        except Exception as exc:
            return ValidationResult(
                valid=False,
                message=f"Data credentials invalid: {exc}",
            )

    async def validate_access_token(
        self, access_token: str, is_trading: bool
    ) -> ValidationResult:
        try:
            headers = {"access-token": access_token}
            if is_trading:
                url = _TRADING_FUND_LIMITS_URL
            else:
                url = _DATA_LTP_URL
                params = {"symbol": "NIFTY", "exchange": "NSE", "security-type": "INDEX"}
            async with httpx.AsyncClient() as client:
                if is_trading:
                    resp = await client.get(url, headers=headers)
                else:
                    resp = await client.get(url, headers=headers, params=params)
                resp.raise_for_status()
                return ValidationResult(
                    valid=True,
                    message="Access token valid",
                    details=resp.json(),
                )
        except Exception as exc:
            return ValidationResult(
                valid=False,
                message=f"Access token invalid: {exc}",
            )
