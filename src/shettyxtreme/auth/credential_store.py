"""Encrypted local credential store for Dhan API keys and tokens.

Stores credentials at ~/.shettyxtreme/credentials.enc using Fernet encryption.
Key derived from machine-specific identifier (hostname + username).
"""
from __future__ import annotations

import base64
import getpass
import hashlib
import json
import socket
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from cryptography.fernet import Fernet

_SHETTY_DIR = Path.home() / ".shettyxtreme"
_CRED_PATH = _SHETTY_DIR / "credentials.enc"


@dataclass
class CredentialStore:
    """Encrypted credential storage for single Dhan API credential."""

    api_key: str = ""
    api_secret: str = ""
    access_token: str | None = None
    token_expiry: str | None = None
    client_id: str | None = None
    client_name: str | None = None
    data_access_token: str | None = None
    data_access_token_expiry: str | None = None

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
    def load() -> CredentialStore | None:
        """Decrypt and return stored credentials, or None if file missing."""
        if not _CRED_PATH.exists():
            return None
        encrypted = _CRED_PATH.read_bytes()
        try:
            payload = CredentialStore._fernet().decrypt(encrypted)
        except Exception:
            return None
        data = json.loads(payload)
        if "trading_api_key" in data:
            store = CredentialStore()
            store.api_key = data.get("trading_api_key", "")
            store.api_secret = data.get("trading_api_secret", "")
            store.access_token = data.get("trading_access_token")
            store.token_expiry = data.get("trading_token_expiry")
            store.client_id = data.get("trading_client_id") or CredentialStore._extract_client_id_from_token(store.access_token)
            store.client_name = data.get("client_name")
            store.save()
            return store
        store = CredentialStore(**data)
        # Auto-extract client_id from JWT if missing
        if not store.client_id and store.access_token:
            store.client_id = CredentialStore._extract_client_id_from_token(store.access_token)
        return store

    @staticmethod
    def _extract_client_id_from_token(access_token: str | None) -> str:
        """Extract dhanClientId from JWT access token."""
        if not access_token:
            return ""
        try:
            parts = access_token.split(".")
            if len(parts) < 2:
                return ""
            payload = parts[1] + "=="
            decoded = json.loads(base64.urlsafe_b64decode(payload))
            return decoded.get("dhanClientId", "")
        except Exception:
            return ""

    @staticmethod
    def _extract_exp_from_token(access_token: str | None) -> str:
        """Extract the `exp` claim (epoch seconds) from a JWT access token as ISO-8601."""
        if not access_token:
            return ""
        try:
            parts = access_token.split(".")
            if len(parts) < 2:
                return ""
            payload = parts[1] + "=="
            decoded = json.loads(base64.urlsafe_b64decode(payload))
            exp = decoded.get("exp")
            if not exp:
                return ""
            return datetime.fromtimestamp(int(exp), tz=UTC).isoformat()
        except Exception:
            return ""

    def is_complete(self) -> bool:
        """True when API key and secret are present."""
        return bool(self.api_key and self.api_secret)

    def is_token_valid(self) -> bool:
        """True when token exists and has not expired."""
        if not self.access_token or not self.token_expiry:
            return False
        expiry = datetime.fromisoformat(self.token_expiry)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return expiry > datetime.now(UTC)

    def is_data_token_valid(self) -> bool:
        """True when the data-access token exists and has not expired."""
        if not self.data_access_token or not self.data_access_token_expiry:
            return False
        expiry = datetime.fromisoformat(self.data_access_token_expiry)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return expiry > datetime.now(UTC)

    def update_token(self, access_token: str, expiry: str, client_id: str) -> None:
        """Update access token, expiry, and client ID."""
        self.access_token = access_token
        self.token_expiry = expiry
        self.client_id = client_id

    def update_data_token(self, token: str, expiry: str | None) -> None:
        """Update the data-access token (fallback used by the Dhan data adapter)."""
        self.data_access_token = token
        self.data_access_token_expiry = expiry

    def get_masked(self) -> dict:
        """Return credentials with secrets masked (last 4 chars visible)."""
        def _mask(val: str | None) -> str:
            if val is None:
                return ""
            if len(val) <= 4:
                return "***"
            return "***" + val[-4:]

        return {
            "api_key": _mask(self.api_key),
            "api_secret": _mask(self.api_secret),
            "access_token": _mask(self.access_token),
            "token_expiry": self.token_expiry or "",
            "client_id": self.client_id or "",
            "client_name": self.client_name or "",
            "data_access_token": _mask(self.data_access_token),
        }
