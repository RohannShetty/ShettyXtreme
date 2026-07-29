"""Credential validator for Dhan API.

Validates credentials by checking format and structure locally.
The actual OAuth-based credential verification happens naturally
during the consent flow in Step 3 of the setup wizard — calling
generate-consent for validation creates wasted consents on Dhan's side.

Never places orders or modifies anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

_FUND_LIMITS_URL = "https://api.dhan.co/v2/fundlimit"
_LTP_URL = "https://api.dhan.co/v2/marketdata/ltp"


@dataclass
class ValidationResult:
    valid: bool
    message: str
    details: dict[str, Any] | None = None


class CredentialValidator:

    async def validate_trading(
        self, api_key: str, api_secret: str, client_id: str
    ) -> ValidationResult:
        if not api_key or not api_secret:
            return ValidationResult(
                valid=False,
                message="Both API key and secret are required.",
            )
        return ValidationResult(
            valid=True,
            message="Trading credentials saved. Actual validation occurs during OAuth consent.",
        )

    async def validate_data(
        self, api_key: str, api_secret: str, client_id: str
    ) -> ValidationResult:
        if not api_key or not api_secret:
            return ValidationResult(
                valid=False,
                message="Both API key and secret are required.",
            )
        return ValidationResult(
            valid=True,
            message="Data credentials saved. Actual validation occurs during OAuth consent.",
        )

    async def validate_access_token(
        self, access_token: str, is_trading: bool
    ) -> ValidationResult:
        try:
            headers = {"access-token": access_token}
            if is_trading:
                url = _FUND_LIMITS_URL
            else:
                url = _LTP_URL
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
