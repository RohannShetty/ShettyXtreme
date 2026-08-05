"""Fyers OAuth2 authorization-code flow helper.

Flow (primary-source verified 2026-08-04):

1. ``GET /api/v3/generate-authcode`` builds the login URL; the user
   authenticates in the browser and Fyers redirects to the callback with
   ``?auth_code=<JWT>&user_id=<fy_id>&state=...``.
2. ``POST /api/v3/validate-authcode`` exchanges the single-use auth code
   for an ``access_token`` (and a ``refresh_token`` whose refresh endpoint
   is undocumented / possibly discontinued).

Fyers tokens expire daily with no silent refresh — the design treats the
authorization-code exchange as the only reliable re-auth path.
"""
from __future__ import annotations

import hashlib
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

AUTH_BASE_URL = "https://api-t1.fyers.in/api/v3"
GENERATE_AUTHCODE_URL = f"{AUTH_BASE_URL}/generate-authcode"
VALIDATE_AUTHCODE_URL = f"{AUTH_BASE_URL}/validate-authcode"

# Community-observed daily expiry (~6 AM IST); the exact TTL is unpublished.
# The stored expiry is a heuristic — the pre-market /profile probe is the gate.
_DEFAULT_TOKEN_TTL_HOURS = 24
_IST = None  # resolved lazily to keep imports light


class FyersAuthError(Exception):
    """Raised when the Fyers OAuth flow fails (network, bad creds, exchange)."""


@dataclass(frozen=True)
class FyersTokenResult:
    """Outcome of a successful validate-authcode exchange."""

    access_token: str
    token_expiry: str
    client_id: str
    refresh_token: str | None = None


class FyersOAuthHelper:
    """Generates the Fyers auth URL and exchanges the callback auth code."""

    def generate_auth_url(
        self,
        app_id: str,
        redirect_uri: str,
        state: str | None = None,
    ) -> str:
        """Build the Fyers login URL for the authorization-code flow."""
        params = {
            "client_id": app_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "state": state or secrets.token_urlsafe(16),
            "scope": "openid",
            "nonce": secrets.token_urlsafe(8),
        }
        return f"{GENERATE_AUTHCODE_URL}?{urlencode(params)}"

    @staticmethod
    def compute_app_id_hash(app_id: str, secret_id: str) -> str:
        """SHA-256 hex digest of ``app_id:secret_id`` (the appIdHash)."""
        return hashlib.sha256(f"{app_id}:{secret_id}".encode()).hexdigest()

    async def exchange_auth_code(
        self,
        app_id: str,
        secret_id: str,
        auth_code: str,
        user_id: str | None = None,
    ) -> FyersTokenResult:
        """Exchange the single-use auth code for an access token.

        Raises :class:`FyersAuthError` on any failure — the caller must never
        see a partially-parsed result.
        """
        payload = {
            "grant_type": "authorization_code",
            "appIdHash": self.compute_app_id_hash(app_id, secret_id),
            "code": auth_code,
        }
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(VALIDATE_AUTHCODE_URL, json=payload)
        except httpx.HTTPError as exc:
            raise FyersAuthError(f"Network error reaching Fyers API: {exc}") from exc

        if resp.status_code != 200:
            raise FyersAuthError(
                f"Fyers validate-authcode failed (HTTP {resp.status_code})"
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise FyersAuthError("Fyers returned a non-JSON response") from exc

        if data.get("s") != "ok" or not data.get("access_token"):
            code = data.get("code")
            raise FyersAuthError(
                f"Fyers rejected the auth code (code={code or 'unknown'})"
            )

        client_id = (
            user_id
            or data.get("fy_id")
            or data.get("client_id")
            or self._fy_id_from_auth_code(auth_code)
        )
        logger.info("Fyers auth-code exchange succeeded for client %s", client_id)
        return FyersTokenResult(
            access_token=data["access_token"],
            token_expiry=_default_token_expiry(),
            client_id=client_id or "",
            refresh_token=data.get("refresh_token"),
        )

    @staticmethod
    def _fy_id_from_auth_code(auth_code: str) -> str:
        """Last-resort client id: decode ``fy_id`` from the auth-code JWT payload."""
        try:
            parts = auth_code.split(".")
            if len(parts) < 2:
                return ""
            payload = parts[1] + "=="
            import base64
            import json

            decoded = json.loads(base64.urlsafe_b64decode(payload))
            return str(decoded.get("fy_id", ""))
        except Exception:
            return ""


def _default_token_expiry() -> str:
    """Heuristic expiry: next ~6 AM IST (community daily-expiry time).

    The liveness probe (/profile) is authoritative; this is a conservative
    schedule so the health monitor flags re-auth before the market day.
    """
    from zoneinfo import ZoneInfo

    ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    expiry = (ist + timedelta(days=1)).replace(
        hour=6, minute=0, second=0, microsecond=0
    )
    return expiry.astimezone(UTC).isoformat()
