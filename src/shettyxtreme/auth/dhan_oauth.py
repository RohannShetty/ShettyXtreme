"""Dhan OAuth consent flow helper.

Implements the 3-step OAuth consent flow for both Trading and Data APIs.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ConsentResult:
    """Result of a successful consent consumption."""

    access_token: str
    expiry_time: str
    client_id: str
    client_name: str
    ddpi_status: bool


class DhanOAuthHelper:
    """Helper for Dhan OAuth consent flow (3-step process)."""

    AUTH_BASE_URL: str = "https://auth.dhan.co"

    async def generate_consent(
        self, api_key: str, api_secret: str, client_id: str,
    ) -> str | None:
        """Generate a consent request and return the consentAppId.

        Step 1 of the OAuth consent flow.
        """
        url = f"{self.AUTH_BASE_URL}/app/generate-consent?client_id={client_id}"
        headers = {"app_id": api_key, "app_secret": api_secret}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                consent_app_id = data.get("consentAppId")
                if consent_app_id:
                    logger.info(
                        "Consent generated, consentAppId=%s",
                        consent_app_id[:4] + "****" if len(consent_app_id) > 4 else consent_app_id,
                    )
                return consent_app_id
        except Exception:
            logger.exception("generate_consent failed")
            return None

    def get_login_url(self, consent_app_id: str) -> str:
        """Return the URL the user must visit to approve consent.

        Step 2 of the OAuth consent flow. Pure function, no HTTP.
        """
        return (
            f"{self.AUTH_BASE_URL}/login/consentApp-login"
            f"?consentAppId={consent_app_id}"
        )

    async def consume_consent(
        self, api_key: str, api_secret: str, token_id: str,
    ) -> ConsentResult | None:
        """Consume a consent token and return access credentials.

        Step 3 of the OAuth consent flow.
        """
        url = f"{self.AUTH_BASE_URL}/app/consumeApp-consent"
        headers = {"app_id": api_key, "app_secret": api_secret}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, headers=headers, params={"tokenId": token_id})
                resp.raise_for_status()
                data = resp.json()
                result = ConsentResult(
                    access_token=data.get("accessToken", ""),
                    expiry_time=data.get("expiryTime", ""),
                    client_id=data.get("clientId", ""),
                    client_name=data.get("clientName", ""),
                    ddpi_status=data.get("ddpiStatus", False),
                )
                masked_token = (
                    result.access_token[:4] + "****"
                    if len(result.access_token) > 4
                    else result.access_token
                )
                logger.info(
                    "Consent consumed, accessToken=%s clientId=%s",
                    masked_token,
                    result.client_id,
                )
                return result
        except Exception:
            logger.exception("consume_consent failed")
            return None
