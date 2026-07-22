"""Read-only credential validator for Dhan API.

Validates credentials by making harmless API calls.
Never places orders or modifies anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


AUTH_BASE = "https://auth.dhan.co"
TRADING_BASE = "https://api.dhan.co/v2"
DATA_BASE = "https://api.dhan.co/v2"
# Dhan has no client_credentials token endpoint. API key/secret validity is
# proven by triggering the first step of the OAuth consent flow.
_TRADING_CONSENT_URL = f"{AUTH_BASE}/app/generate-consent"
_DATA_CONSENT_URL = f"{AUTH_BASE}/app/generate-consent"
_TRADING_FUND_LIMITS_URL = f"{TRADING_BASE}/fundlimit"
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
                    _TRADING_CONSENT_URL,
                    params={"client_id": client_id},
                    headers={"app_id": api_key, "app_secret": api_secret},
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") != "success" or not data.get("consentAppId"):
                    return ValidationResult(
                        valid=False,
                        message="Trading credentials invalid: consent not granted",
                    )
                return ValidationResult(
                    valid=True,
                    message="Trading credentials valid",
                    details=data,
                )
        except (OSError, httpx.ConnectError, httpx.TimeoutException) as exc:
            return ValidationResult(
                valid=False,
                message=f"Network error — cannot reach Dhan API: {exc}",
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
                    _DATA_CONSENT_URL,
                    params={"client_id": client_id},
                    headers={"app_id": api_key, "app_secret": api_secret},
                )
                resp.raise_for_status()
                data = resp.json()
                if data.get("status") != "success" or not data.get("consentAppId"):
                    return ValidationResult(
                        valid=False,
                        message="Data credentials invalid: consent not granted",
                    )
                return ValidationResult(
                    valid=True,
                    message="Data credentials valid",
                    details=data,
                )
        except (OSError, httpx.ConnectError, httpx.TimeoutException) as exc:
            return ValidationResult(
                valid=False,
                message=f"Network error — cannot reach Dhan API: {exc}",
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
        except (OSError, httpx.ConnectError, httpx.TimeoutException) as exc:
            return ValidationResult(
                valid=False,
                message=f"Network error — cannot reach Dhan API: {exc}",
            )
        except Exception as exc:
            return ValidationResult(
                valid=False,
                message=f"Access token invalid: {exc}",
            )
