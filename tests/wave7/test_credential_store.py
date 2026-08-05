"""Tests for CredentialStore (encrypted Fyers credential storage)."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

import shettyxtreme.auth.credential_store as _cred_mod
from shettyxtreme.auth.credential_store import CredentialStore


@pytest.fixture
def creds_file(tmp_path: Path) -> Path:
    monkeypatch_dir = tmp_path / "creds"
    monkeypatch_dir.mkdir()
    path = monkeypatch_dir / "credentials.enc"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(_cred_mod, "_CRED_PATH", path)
    yield path
    monkeypatch.undo()


def test_save_and_load(creds_file: Path) -> None:
    store = CredentialStore(app_id="APP123", secret_id="SECRET456")
    store.save()
    loaded = CredentialStore.load()
    assert loaded is not None
    assert loaded.broker == "fyers"
    assert loaded.app_id == "APP123"
    assert loaded.secret_id == "SECRET456"


def test_load_returns_none_when_no_file(tmp_path: Path) -> None:
    creds_file = tmp_path / "nonexistent" / "credentials.enc"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(_cred_mod, "_CRED_PATH", creds_file)
    try:
        result = CredentialStore.load()
        assert result is None
    finally:
        monkeypatch.undo()


def test_is_complete() -> None:
    store = CredentialStore(app_id="APP", secret_id="SECRET")
    assert store.is_complete() is True
    store2 = CredentialStore()
    assert store2.is_complete() is False
    store3 = CredentialStore(app_id="APP")
    assert store3.is_complete() is False


def test_is_token_valid_expired() -> None:
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    store = CredentialStore(access_token="token123", token_expiry=past)
    assert store.is_token_valid() is False


def test_is_token_valid_future() -> None:
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    store = CredentialStore(access_token="token123", token_expiry=future)
    assert store.is_token_valid() is True


def test_get_masked_hides_secrets() -> None:
    store = CredentialStore(
        app_id="APPabcdef123456",
        secret_id="supersecretvalue",
        access_token="tok_abcdef123456",
    )
    masked = store.get_masked()
    assert "3456" in masked["app_id"]
    assert masked["secret_id"] != "supersecretvalue"
    assert masked["access_token"] != "tok_abcdef123456"
    assert masked["broker"] == "fyers"


def test_update_token() -> None:
    store = CredentialStore()
    store.update_token("new_token", "2026-12-31T23:59:59+00:00", "FY123")
    assert store.access_token == "new_token"
    assert store.token_expiry == "2026-12-31T23:59:59+00:00"
    assert store.client_id == "FY123"


def test_migration_clears_legacy_dhan_credentials(creds_file: Path) -> None:
    """Old Dhan payloads are cleared and replaced with a fresh Fyers store."""
    old = {
        "trading_api_key": "old_key",
        "trading_api_secret": "old_secret",
        "trading_access_token": "old_token",
        "trading_token_expiry": "2026-12-31T23:59:59+00:00",
        "trading_client_id": "OLD123",
        "client_name": "Old User",
        "data_api_key": "",
        "data_api_secret": "",
        "data_access_token": None,
        "data_token_expiry": None,
        "data_client_id": None,
    }
    creds_file.write_bytes(CredentialStore._fernet().encrypt(json.dumps(old).encode()))
    loaded = CredentialStore.load()
    assert loaded is not None
    assert loaded.app_id == ""
    assert loaded.secret_id == ""
    assert loaded.access_token is None
    assert loaded.client_id is None
    assert loaded.broker == "fyers"


def test_migration_clears_dhan_broker_payload(creds_file: Path) -> None:
    """A payload stamped broker=dhan is treated as legacy and cleared."""
    old = {"broker": "dhan", "access_token": "tok", "token_expiry": "2099-01-01T00:00:00"}
    creds_file.write_bytes(CredentialStore._fernet().encrypt(json.dumps(old).encode()))
    loaded = CredentialStore.load()
    assert loaded is not None
    assert loaded.broker == "fyers"
    assert loaded.access_token is None


def test_fyers_payload_roundtrip_with_token(creds_file: Path) -> None:
    store = CredentialStore(
        broker="fyers",
        app_id="APP123",
        secret_id="SECRET456",
        access_token="tok_abc",
        token_expiry="2026-12-31T00:00:00+00:00",
        client_id="FY123",
        client_name="Test User",
    )
    store.save()
    reloaded = CredentialStore.load()
    assert reloaded is not None
    assert reloaded.access_token == "tok_abc"
    assert reloaded.client_id == "FY123"
    assert reloaded.client_name == "Test User"
    assert reloaded.token_expiry == "2026-12-31T00:00:00+00:00"


def test_is_legacy_payload_detects_data_token() -> None:
    assert CredentialStore._is_legacy_payload({"data_access_token": "x"}) is True
    assert CredentialStore._is_legacy_payload({"api_key": "x"}) is True
    assert CredentialStore._is_legacy_payload({"broker": "dhan"}) is True
    assert CredentialStore._is_legacy_payload({}) is True  # no broker key = legacy
    assert CredentialStore._is_legacy_payload({"broker": "fyers"}) is False
    assert CredentialStore._is_legacy_payload(
        {"broker": "fyers", "app_id": "A", "secret_id": "S"}
    ) is False


# ── Oracle #5: encryption key derivation audit ──────────────────────────────

def test_fernet_key_derivation_is_machine_bound(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The Fernet key derives from hostname+username, so different machines
    derive different keys — credentials are NOT portable."""
    monkeypatch.setattr(_cred_mod.socket, "gethostname", lambda: "host-alpha")
    monkeypatch.setattr(_cred_mod.getpass, "getuser", lambda: "user-one")
    key_a = CredentialStore._fernet()

    monkeypatch.setattr(_cred_mod.socket, "gethostname", lambda: "host-beta")
    key_b = CredentialStore._fernet()

    assert key_a != key_b


def test_fernet_key_derivation_is_deterministic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same machine identity (hostname+user) always yields the same key, so
    saves survive restarts on the same machine: a payload encrypted with one
    derivation decrypts with the next."""
    monkeypatch.setattr(_cred_mod.socket, "gethostname", lambda: "host-alpha")
    monkeypatch.setattr(_cred_mod.getpass, "getuser", lambda: "user-one")

    k1 = CredentialStore._fernet()
    k2 = CredentialStore._fernet()
    assert k2.decrypt(k1.encrypt(b"secret")) == b"secret"


def test_credentials_not_portable_across_machines(
    creds_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A store written on one machine cannot be decrypted on another: the
    different hostname/user derives a different key, so load() returns None
    rather than leaking the plaintext."""
    monkeypatch.setattr(_cred_mod.socket, "gethostname", lambda: "machine-a")
    monkeypatch.setattr(_cred_mod.getpass, "getuser", lambda: "user-a")
    CredentialStore(app_id="APP123", secret_id="SECRET456").save()

    monkeypatch.setattr(_cred_mod.socket, "gethostname", lambda: "machine-b")
    monkeypatch.setattr(_cred_mod.getpass, "getuser", lambda: "user-b")
    assert CredentialStore.load() is None
