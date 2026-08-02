"""Tests for CredentialStore (encrypted credential storage)."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

import shettyxtreme.auth.credential_store as _cred_mod
from shettyxtreme.auth.credential_store import CredentialStore


def test_save_and_load(tmp_path: Path) -> None:
    monkeypatch_dir = tmp_path / "creds"
    monkeypatch_dir.mkdir()
    creds_file = monkeypatch_dir / "credentials.enc"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(_cred_mod, "_CRED_PATH", creds_file)
    try:
        store = CredentialStore(
            api_key="client1:::apikey1",
            api_secret="secret1",
        )
        store.save()
        loaded = CredentialStore.load()
        assert loaded is not None
        assert loaded.api_key == "client1:::apikey1"
        assert loaded.api_secret == "secret1"
    finally:
        monkeypatch.undo()


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
    store = CredentialStore(api_key="key", api_secret="secret")
    assert store.is_complete() is True
    store2 = CredentialStore()
    assert store2.is_complete() is False
    store3 = CredentialStore(api_key="key")
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
        api_key="client:::abcdef123456",
        api_secret="supersecretvalue",
        access_token="tok_abcdef123456",
    )
    masked = store.get_masked()
    assert "3456" in masked["api_key"]
    assert masked["api_secret"] != "supersecretvalue"
    assert masked["access_token"] != "tok_abcdef123456"


def test_update_token() -> None:
    store = CredentialStore()
    store.update_token("new_token", "2026-12-31T23:59:59+00:00", "C123")
    assert store.access_token == "new_token"
    assert store.token_expiry == "2026-12-31T23:59:59+00:00"
    assert store.client_id == "C123"


def test_migration_from_dual_format(tmp_path: Path) -> None:
    monkeypatch_dir = tmp_path / "creds"
    monkeypatch_dir.mkdir()
    creds_file = monkeypatch_dir / "credentials.enc"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(_cred_mod, "_CRED_PATH", creds_file)
    try:
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
        creds_file.write_bytes(
            CredentialStore._fernet().encrypt(json.dumps(old).encode())
        )
        loaded = CredentialStore.load()
        assert loaded is not None
        assert loaded.api_key == "old_key"
        assert loaded.api_secret == "old_secret"
        assert loaded.access_token == "old_token"
        assert loaded.client_id == "OLD123"
        assert loaded.client_name == "Old User"
    finally:
        monkeypatch.undo()


def test_data_token_roundtrip(tmp_path: Path) -> None:
    monkeypatch_dir = tmp_path / "creds"
    monkeypatch_dir.mkdir()
    creds_file = monkeypatch_dir / "credentials.enc"
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(_cred_mod, "_CRED_PATH", creds_file)
    try:
        store = CredentialStore(api_key="key", api_secret="secret")
        store.update_data_token("data_abc", "2026-12-31T00:00:00Z")
        store.save()
        reloaded = CredentialStore.load()
        assert reloaded is not None
        assert reloaded.data_access_token == "data_abc"
        assert reloaded.data_access_token_expiry == "2026-12-31T00:00:00Z"
    finally:
        monkeypatch.undo()


def test_extract_exp_from_token() -> None:
    import base64

    payload = {"dhanClientId": "DHAN123", "exp": 1780000000}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    token = f"header.{body}.signature"
    expiry = CredentialStore._extract_exp_from_token(token)
    assert expiry.startswith("2026-")  # 1780000000 = 2026-05-28T...
    assert CredentialStore._extract_exp_from_token(None) == ""
    assert CredentialStore._extract_exp_from_token("not.a.jwt") == ""
    assert CredentialStore._extract_exp_from_token("onlyone") == ""


def test_data_token_validity() -> None:
    store = CredentialStore()
    assert store.is_data_token_valid() is False
    store.data_access_token = "tok"
    store.data_access_token_expiry = "2026-12-31T23:59:59"
    assert store.is_data_token_valid() is True
    store.data_access_token_expiry = "2020-01-01T00:00:00"
    assert store.is_data_token_valid() is False
