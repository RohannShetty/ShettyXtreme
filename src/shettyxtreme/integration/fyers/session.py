"""Fyers session: access-token lifecycle and liveness probing.

Fyers does not publish its access-token TTL (community "~6 AM IST" claims are
unverifiable), so the design leans on daily interactive re-auth plus a
``GET /profile`` liveness probe as the source of truth.

- :meth:`FyersSession.is_valid` is the cheap expiry check — it fails when an
  expiry is known and past, and also when the expiry is unknown (``None``):
  a token that cannot be proven live is treated as expired so the LIVE gate
  forces re-auth instead of waving an unverifiable token through. Pair it
  with :meth:`FyersSession.probe_liveness` for an authoritative answer.
- :meth:`FyersSession.probe_liveness` calls ``GET /profile``; the transport
  maps HTTP 401 / error codes -8/-15/-16/-17 to :class:`FyersTokenExpired`,
  which the probe turns into ``False``.
- :meth:`FyersSession.persist` / :meth:`FyersSession.load` round-trip the
  session through the existing encrypted credential store.
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from shettyxtreme.integration.fyers.client import FyersHTTPClient, FyersTokenExpired


class CredentialStoreLike(Protocol):
    """The credential-store surface :class:`FyersSession` depends on."""

    app_id: str
    secret_id: str
    access_token: str | None
    token_expiry: str | None

    def save(self) -> None: ...


class FyersSession:
    """Tracks a Fyers access token and its lifecycle.

    Args:
        app_id: Fyers application ID.
        secret_id: Fyers app secret (needed for re-auth flows).
        access_token: Current access token.
        token_expiry: Known expiry, or ``None`` when unknown (Fyers does not
            publish a TTL).
    """

    def __init__(
        self,
        app_id: str,
        secret_id: str,
        access_token: str,
        token_expiry: datetime | None = None,
    ) -> None:
        self.app_id = app_id
        self.secret_id = secret_id
        self.access_token = access_token
        self.token_expiry = token_expiry

    def is_valid(self) -> bool:
        """Cheap expiry check — True only when the token is provably live.

        An unknown expiry (``None``) cannot be proven valid — Fyers does not
        publish a TTL, so a session without a recorded expiry is treated as
        expired (force re-auth) rather than waved through. This is what makes
        the LIVE session-validity gate honest (F-INT-009): an unverifiable
        token never reaches the wire. The auth flow always records the
        heuristic expiry on login, so unknown expiry only arises for stale or
        legacy sessions — exactly the ones that must re-auth. Pair this check
        with :meth:`probe_liveness` for the authoritative answer.
        """
        if self.token_expiry is None:
            return False
        expiry = self.token_expiry
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return expiry > datetime.now(UTC)

    async def probe_liveness(self, client: FyersHTTPClient) -> bool:
        """Probe the token against ``GET /profile``.

        Returns True when the call succeeds and False when the transport
        classifies the response as an expired token. Any other error
        propagates to the caller.
        """
        try:
            await client.get("/profile")
        except FyersTokenExpired:
            return False
        return True

    def update_token(
        self,
        access_token: str,
        token_expiry: datetime | None = None,
    ) -> None:
        """Refresh the token and optional expiry in place."""
        self.access_token = access_token
        self.token_expiry = token_expiry

    def persist(self, credential_store: CredentialStoreLike) -> None:
        """Write the session into the encrypted store and save it to disk."""
        credential_store.app_id = self.app_id
        credential_store.secret_id = self.secret_id
        credential_store.access_token = self.access_token
        credential_store.token_expiry = (
            self.token_expiry.isoformat() if self.token_expiry else None
        )
        credential_store.save()

    @classmethod
    def load(cls, credential_store: Any) -> FyersSession | None:
        """Rehydrate a session from a credential store.

        Returns ``None`` when the store is missing or holds no token.
        """
        if credential_store is None:
            return None
        token = credential_store.access_token
        if not token:
            return None
        return cls(
            app_id=credential_store.app_id,
            secret_id=credential_store.secret_id,
            access_token=token,
            token_expiry=_parse_expiry(credential_store.token_expiry),
        )


def _parse_expiry(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None
