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
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet

_SHETTY_DIR = Path.home() / ".shettyxtreme"
_CRED_PATH = _SHETTY_DIR / "credentials.enc"


@dataclass
class CredentialStore:
    """Encrypted credential storage for Dhan Trading and Data APIs."""

    trading_api_key: str = ""
    trading_api_secret: str = ""
    trading_access_token: str | None = None
    trading_token_expiry: str | None = None
    trading_client_id: str | None = None
    data_api_key: str = ""
    data_api_secret: str = ""
    data_access_token: str | None = None
    data_token_expiry: str | None = None
    data_client_id: str | None = None

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
        return CredentialStore(**data)

    def is_complete(self) -> bool:
        """True when both trading and data credentials are present."""
        trading_ok = bool(self.trading_api_key and self.trading_api_secret)
        data_ok = bool(self.data_api_key and self.data_api_secret)
        return trading_ok and data_ok

    def is_trading_valid(self) -> bool:
        """True when trading token exists and has not expired."""
        if not self.trading_access_token or not self.trading_token_expiry:
            return False
        expiry = datetime.fromisoformat(self.trading_token_expiry)
        return expiry > datetime.now(timezone.utc)

    def is_data_valid(self) -> bool:
        """True when data token exists and has not expired."""
        if not self.data_access_token or not self.data_token_expiry:
            return False
        expiry = datetime.fromisoformat(self.data_token_expiry)
        return expiry > datetime.now(timezone.utc)

    def update_trading_token(
        self, access_token: str, expiry: str, client_id: str
    ) -> None:
        """Update trading access token, expiry, and client ID."""
        self.trading_access_token = access_token
        self.trading_token_expiry = expiry
        self.trading_client_id = client_id

    def update_data_token(
        self, access_token: str, expiry: str, client_id: str
    ) -> None:
        """Update data access token, expiry, and client ID."""
        self.data_access_token = access_token
        self.data_token_expiry = expiry
        self.data_client_id = client_id

    def get_masked(self) -> dict:
        """Return credentials with secrets masked (last 4 chars visible)."""
        def _mask(val: str | None) -> str:
            if val is None:
                return ""
            if len(val) <= 4:
                return "***"
            return "***" + val[-4:]

        return {
            "trading_api_key": _mask(self.trading_api_key),
            "trading_api_secret": _mask(self.trading_api_secret),
            "trading_access_token": _mask(self.trading_access_token),
            "trading_token_expiry": self.trading_token_expiry or "",
            "trading_client_id": self.trading_client_id or "",
            "data_api_key": _mask(self.data_api_key),
            "data_api_secret": _mask(self.data_api_secret),
            "data_access_token": _mask(self.data_access_token),
            "data_token_expiry": self.data_token_expiry or "",
            "data_client_id": self.data_client_id or "",
        }
