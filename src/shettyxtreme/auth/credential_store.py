"""Encrypted local credential store for Fyers app credentials and tokens.

Stores credentials at ~/.shettyxtreme/credentials.enc using Fernet encryption.
Key derived from machine-specific identifier (hostname + username).

Key-derivation audit (Oracle #5, 2026-08-05): the encryption key is NOT a
static fallback and NOT a hardware secret. It is derived per machine as
``urlsafe_b64encode(sha256(hostname + username).digest())`` — machine-bound
in practice (different host/user derive different keys, so the ciphertext is
not portable) and deterministic per machine (saves survive restarts). Two
known limitations, both accepted for a local single-workstation tool:
    * hostname+username is guessable, so an attacker holding the ciphertext
      could brute-force the key offline — no DPAPI/TPM binding;
    * two machines with identical hostname AND username would share a key.

Fyers uses a single-token model: one access token minted per OAuth
authorization-code exchange, valid for the day. There is no separate data
token and no JWT parsing — the client id comes from the OAuth redirect
(`user_id`), not from the token payload.
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import json
import logging
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_SHETTY_DIR = Path.home() / ".shettyxtreme"
_CRED_PATH = _SHETTY_DIR / "credentials.enc"

# Keys that mark a payload as legacy Dhan credentials.
_LEGACY_KEYS: tuple[str, ...] = (
    "trading_api_key",
    "trading_api_secret",
    "trading_access_token",
    "data_api_key",
    "data_access_token",
    "data_token_expiry",
    "api_key",
    "api_secret",
)


@dataclass
class CredentialStore:
    """Encrypted credential storage for the Fyers API app + access token."""

    broker: str = "fyers"
    app_id: str = ""
    secret_id: str = ""
    access_token: str | None = None
    token_expiry: str | None = None
    client_id: str | None = None
    client_name: str | None = None

    @staticmethod
    def _fernet() -> Fernet:
        raw = (socket.gethostname() + getpass.getuser()).encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
        return Fernet(key)

    def save(self) -> None:
        """Encrypt and write credentials to disk."""
        _SHETTY_DIR.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.__dict__).encode()
        encrypted = self._fernet().encrypt(payload)
        _CRED_PATH.write_bytes(encrypted)

    @staticmethod
    def _is_legacy_payload(data: dict) -> bool:
        """True when a stored payload came from the Dhan credential era."""
        if any(key in data for key in _LEGACY_KEYS):
            return True
        return data.get("broker") in (None, "dhan")

    @staticmethod
    def load() -> CredentialStore | None:
        """Decrypt and return stored credentials, or None if file missing.

        Legacy Dhan payloads are cleared and replaced with a fresh Fyers
        store — the Dhan access token is not portable and Fyers requires a
        new authorization-code flow.
        """
        if not _CRED_PATH.exists():
            return None
        encrypted = _CRED_PATH.read_bytes()
        try:
            payload = CredentialStore._fernet().decrypt(encrypted)
        except Exception:
            return None
        data = json.loads(payload)
        if CredentialStore._is_legacy_payload(data):
            logger.info(
                "Detected legacy Dhan credentials — clearing store; Fyers re-auth required"
            )
            store = CredentialStore()
            store.save()
            return store
        return CredentialStore(
            broker=data.get("broker", "fyers"),
            app_id=data.get("app_id", ""),
            secret_id=data.get("secret_id", ""),
            access_token=data.get("access_token"),
            token_expiry=data.get("token_expiry"),
            client_id=data.get("client_id"),
            client_name=data.get("client_name"),
        )

    def is_complete(self) -> bool:
        """True when Fyers app credentials (App ID + Secret ID) are present."""
        return bool(self.app_id and self.secret_id)

    def is_token_valid(self) -> bool:
        """True when the access token exists and has not expired."""
        if not self.access_token or not self.token_expiry:
            return False
        expiry = datetime.fromisoformat(self.token_expiry)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return expiry > datetime.now(UTC)

    def update_token(self, access_token: str, expiry: str, client_id: str) -> None:
        """Update the access token, its expiry, and the client id."""
        self.access_token = access_token
        self.token_expiry = expiry
        self.client_id = client_id

    def get_masked(self) -> dict:
        """Return credentials with secrets masked (last 4 chars visible)."""
        def _mask(val: str | None) -> str:
            if val is None:
                return ""
            if len(val) <= 4:
                return "***"
            return "***" + val[-4:]

        return {
            "broker": self.broker,
            "app_id": _mask(self.app_id),
            "secret_id": _mask(self.secret_id),
            "access_token": _mask(self.access_token),
            "token_expiry": self.token_expiry or "",
            "client_id": self.client_id or "",
            "client_name": self.client_name or "",
        }
