"""Dhan OAuth consent flow helper.

Implements the 3-step OAuth consent flow.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_consent_flows: set[str] = set()


@dataclass(frozen=True)
class ConsentResult:
    access_token: str
    expiry_time: str
    client_id: str
    client_name: str
    ddpi_status: bool


@dataclass(frozen=True)
class ConsumeResult:
    """Result of consume_consent — either success or descriptive error."""
    consent: ConsentResult | None = None
    error: str | None = None

    @property
    def ok(self) -> bool:
        return self.consent is not None


class DhanOAuthHelper:

    AUTH_BASE_URL: str = "https://auth.dhan.co"

    async def generate_consent(
        self, api_key: str, api_secret: str, client_id: str,
    ) -> str | None:
        url = f"{self.AUTH_BASE_URL}/app/generate-consent?client_id={client_id}"
        headers = {"app_id": api_key, "app_secret": api_secret}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                consent_app_id = data.get("consentAppId")
                if consent_app_id:
                    _consent_flows.add(consent_app_id)
                    logger.info(
                        "Consent generated, consentAppId=%s",
                        consent_app_id[:4] + "****" if len(consent_app_id) > 4 else consent_app_id,
                    )
                return consent_app_id
        except Exception:
            logger.exception("generate_consent failed")
            return None

    def get_login_url(self, consent_app_id: str) -> str:
        return (
            f"{self.AUTH_BASE_URL}/login/consentApp-login"
            f"?consentAppId={consent_app_id}"
        )

    def pop_consent_flow(self, consent_app_id: str) -> bool:
        if consent_app_id in _consent_flows:
            _consent_flows.discard(consent_app_id)
            return True
        return False

    async def consume_consent(
        self, api_key: str, api_secret: str, token_id: str,
    ) -> ConsumeResult:
        url = f"{self.AUTH_BASE_URL}/app/consumeApp-consent"
        headers = {"app_id": api_key, "app_secret": api_secret}
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, headers=headers, params={"tokenId": token_id})
                if resp.status_code == 401:
                    msg = "Dhan API 401: Invalid app_id or app_secret. Re-enter credentials in Step 1."
                    logger.error("consume_consent: %s Response: %s", msg, resp.text[:200])
                    return ConsumeResult(error=msg)
                if resp.status_code == 400:
                    msg = "Dhan API 400: Token expired or already consumed. Restart the consent flow."
                    logger.error("consume_consent: %s Response: %s", msg, resp.text[:200])
                    return ConsumeResult(error=msg)
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
                return ConsumeResult(consent=result)
        except httpx.HTTPStatusError as exc:
            msg = f"Dhan API error {exc.response.status_code}: {exc.response.text[:200]}"
            logger.error("consume_consent: %s", msg)
            return ConsumeResult(error=msg)
        except Exception as exc:
            msg = f"Connection error: {exc}"
            logger.exception("consume_consent failed")
            return ConsumeResult(error=msg)
