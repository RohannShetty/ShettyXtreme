"""Credential validator for the Fyers API.

Validates credentials by checking format and structure locally, and probes
token liveness via the Fyers ``GET /profile`` endpoint through
:class:`~shettyxtreme.integration.fyers.client.FyersHTTPClient`.

Never places orders or modifies anything.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from shettyxtreme.integration.fyers.client import (
    FyersDataEntitlementError,
    FyersError,
    FyersHTTPClient,
    FyersTokenExpired,
)


@dataclass
class ValidationResult:
    valid: bool
    message: str
    details: dict[str, Any] | None = None


class CredentialValidator:

    def __init__(self, http_client: FyersHTTPClient | None = None) -> None:
        self._http_client = http_client

    async def validate_credentials(self, app_id: str, secret_id: str) -> ValidationResult:
        if not app_id or not secret_id:
            return ValidationResult(
                valid=False,
                message="Both App ID and Secret ID are required.",
            )
        return ValidationResult(
            valid=True,
            message="Credentials saved. Connect Fyers to obtain an access token.",
        )

    async def validate_access_token(
        self, app_id: str, access_token: str
    ) -> ValidationResult:
        """Probe Fyers ``GET /profile`` with the stored access token."""
        client = self._http_client or FyersHTTPClient(
            app_id=app_id, access_token=access_token
        )
        try:
            data = await client.get("/profile")
        except FyersTokenExpired:
            return ValidationResult(
                valid=False,
                message="Fyers access token expired — re-auth required",
            )
        except FyersDataEntitlementError as exc:
            return ValidationResult(
                valid=False,
                message=f"Fyers data entitlement missing: {exc.message}",
            )
        except FyersError as exc:
            return ValidationResult(
                valid=False,
                message=f"Fyers API rejected the token: {exc.message}",
            )
        except (OSError, httpx.ConnectError, httpx.TimeoutException) as exc:
            return ValidationResult(
                valid=False,
                message=f"Network error — cannot reach Fyers API: {exc}",
            )
        except Exception as exc:
            return ValidationResult(
                valid=False,
                message=f"Access token invalid: {exc}",
            )

        if isinstance(data, dict) and data.get("s") == "ok":
            return ValidationResult(
                valid=True,
                message="Access token valid",
                details=data,
            )
        return ValidationResult(
            valid=False,
            message="Access token rejected by Fyers",
        )
