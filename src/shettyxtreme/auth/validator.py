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


@dataclass
class ValidationResult:
    valid: bool
    message: str
    details: dict[str, Any] | None = None


class CredentialValidator:

    async def validate_credentials(
        self, api_key: str, api_secret: str, client_id: str
    ) -> ValidationResult:
        if not api_key or not api_secret:
            return ValidationResult(
                valid=False,
                message="Both API key and secret are required.",
            )
        return ValidationResult(
            valid=True,
            message="Credentials saved. Actual validation occurs during OAuth consent.",
        )

    async def validate_access_token(self, access_token: str) -> ValidationResult:
        try:
            headers = {"access-token": access_token}
            async with httpx.AsyncClient() as client:
                resp = await client.get(_FUND_LIMITS_URL, headers=headers)
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
