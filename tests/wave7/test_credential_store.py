"""Tests for CredentialStore (encrypted credential storage)."""
from __future__ import annotations

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
            trading_api_key="client1:::apikey1",
            trading_api_secret="secret1",
            data_api_key="datakey1",
            data_api_secret="datasecret1",
        )
        store.save()
        loaded = CredentialStore.load()
        assert loaded is not None
        assert loaded.trading_api_key == "client1:::apikey1"
        assert loaded.trading_api_secret == "secret1"
        assert loaded.data_api_key == "datakey1"
        assert loaded.data_api_secret == "datasecret1"
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


def test_is_complete_requires_both() -> None:
    store = CredentialStore(
        trading_api_key="client1:::key",
        trading_api_secret="secret",
    )
    assert store.is_complete() is False

    store2 = CredentialStore(
        data_api_key="key",
        data_api_secret="secret",
    )
    assert store2.is_complete() is False

    store3 = CredentialStore(
        trading_api_key="client1:::key",
        trading_api_secret="secret",
        data_api_key="key",
        data_api_secret="secret",
    )
    assert store3.is_complete() is True


def test_is_trading_valid_with_expired_token() -> None:
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    store = CredentialStore(
        trading_access_token="token123",
        trading_token_expiry=past,
    )
    assert store.is_trading_valid() is False


def test_is_trading_valid_with_future_token() -> None:
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    store = CredentialStore(
        trading_access_token="token123",
        trading_token_expiry=future,
    )
    assert store.is_trading_valid() is True


def test_is_data_valid_same_as_trading() -> None:
    past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    store_expired = CredentialStore(
        data_access_token="token123",
        data_token_expiry=past,
    )
    assert store_expired.is_data_valid() is False

    store_valid = CredentialStore(
        data_access_token="token123",
        data_token_expiry=future,
    )
    assert store_valid.is_data_valid() is True


def test_get_masked_hides_secrets() -> None:
    store = CredentialStore(
        trading_api_key="client:::abcdef123456",
        trading_api_secret="supersecretvalue",
        trading_access_token="tok_abcdef123456",
        data_api_key="datakey_long",
        data_api_secret="datasecret_long",
        data_access_token="data_token_long",
    )
    masked = store.get_masked()
    assert "3456" in masked["trading_api_key"]
    assert "ef12" not in masked["trading_api_key"] or masked["trading_api_key"].endswith("3456")
    assert masked["trading_api_secret"] != "supersecretvalue"
    assert masked["trading_access_token"] != "tok_abcdef123456"
    assert masked["data_api_key"] != "datakey_long"
    assert masked["data_api_secret"] != "datasecret_long"
    assert masked["data_access_token"] != "data_token_long"


def test_update_trading_token() -> None:
    store = CredentialStore()
    store.update_trading_token("new_token", "2026-12-31T23:59:59+00:00", "C123")
    assert store.trading_access_token == "new_token"
    assert store.trading_token_expiry == "2026-12-31T23:59:59+00:00"
    assert store.trading_client_id == "C123"


def test_update_data_token() -> None:
    store = CredentialStore()
    store.update_data_token("new_data_token", "2026-12-31T23:59:59+00:00", "D456")
    assert store.data_access_token == "new_data_token"
    assert store.data_token_expiry == "2026-12-31T23:59:59+00:00"
    assert store.data_client_id == "D456"
