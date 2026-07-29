# Credential Consolidation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse dual trading/data Dhan credentials into a single credential set

**Architecture:** 7 files changed across auth/, core/config/, terminal/api/, terminal/static/ layers. Foundation change in credential_store.py propagates upward. Migration path for old credentials.enc format preserved.

**Tech Stack:** Python 3.11+, FastAPI, Fernet encryption, DhanHQ-py

## Global Constraints

- No file > 500 lines
- core/ imports nothing external (stdlib allowed)
- All tests must pass after each task
- Old credentials.enc must migrate silently

---

### Task 1: CredentialStore - Merge dual fields to single

**Files:**
- Modify: `src/shettyxtreme/auth/credential_store.py`

**Interfaces:**
- Consumes: none (foundation)
- Produces: `CredentialStore` with `api_key`, `api_secret`, `access_token`, `token_expiry`, `client_id`, `client_name`

- [ ] **Step 1: Open credential_store.py and replace the entire file**

Read the current file first, then write the merged version:

```python
"""Encrypted local credential store for Dhan API keys and tokens."""
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

    @staticmethod
    def _fernet() -> Fernet:
        raw = (socket.gethostname() + getpass.getuser()).encode()
        key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
        return Fernet(key)

    def save(self) -> None:
        _SHETTY_DIR.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.__dict__).encode()
        encrypted = self._fernet().encrypt(payload)
        _CRED_PATH.write_bytes(encrypted)

    @staticmethod
    def load() -> CredentialStore | None:
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
            store.client_id = data.get("trading_client_id")
            store.client_name = data.get("client_name")
            store.save()
            return store
        return CredentialStore(**data)

    def is_complete(self) -> bool:
        return bool(self.api_key and self.api_secret)

    def is_token_valid(self) -> bool:
        if not self.access_token or not self.token_expiry:
            return False
        expiry = datetime.fromisoformat(self.token_expiry)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return expiry > datetime.now(UTC)

    def update_token(self, access_token: str, expiry: str, client_id: str) -> None:
        self.access_token = access_token
        self.token_expiry = expiry
        self.client_id = client_id

    def get_masked(self) -> dict:
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
        }
```

- [ ] **Step 2: Run existing cred tests to confirm they now fail**

Run: `PYTHONPATH="" python -m pytest tests/wave7/test_credential_store.py -v --tb=short`
Expected: Some FAIL (old tests reference removed fields)

---

### Task 2: Update credential store tests

**Files:**
- Modify: `tests/wave7/test_credential_store.py`

- [ ] **Step 1: Replace test_credential_store.py**

Read the current file first, then write:

```python
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
        _CRED_PATH.write_bytes(
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
```

- [ ] **Step 2: Run tests**

Run: `PYTHONPATH="" python -m pytest tests/wave7/test_credential_store.py -v --tb=short`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/shettyxtreme/auth/credential_store.py tests/wave7/test_credential_store.py
git commit -m "feat: consolidate CredentialStore to single credential + migration"
```

---

### Task 3: Validator - Remove dual methods

**Files:**
- Modify: `src/shettyxtreme/auth/validator.py`

- [ ] **Step 1: Replace validator.py**

Read the current file first, then write:

```python
"""Credential validator for Dhan API."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

_FUND_LIMITS_URL = "https://api.dhan.co/v2/fundlimit"


@dataclass
class ValidationResult:
    valid: bool
    message: str
    details: dict[str, Any] | None = None


class CredentialValidator:

    async def validate_credentials(
        self, api_key: str, api_secret: str, client_id: str
    ) -> ValidationResult:
        if not api_key or not api_secret:
            return ValidationResult(
                valid=False,
                message="Both API key and secret are required.",
            )
        return ValidationResult(
            valid=True,
            message="Credentials saved. Actual validation occurs during OAuth consent.",
        )

    async def validate_access_token(self, access_token: str) -> ValidationResult:
        try:
            headers = {"access-token": access_token}
            async with httpx.AsyncClient() as client:
                resp = await client.get(_FUND_LIMITS_URL, headers=headers)
                resp.raise_for_status()
                return ValidationResult(
                    valid=True,
                    message="Access token valid",
                    details=resp.json(),
                )
        except (OSError, httpx.ConnectError, httpx.TimeoutException) as exc:
            return ValidationResult(
                valid=False,
                message=f"Network error — cannot reach Dhan API: {exc}",
            )
        except Exception as exc:
            return ValidationResult(
                valid=False,
                message=f"Access token invalid: {exc}",
            )
```

- [ ] **Step 2: Run tests to confirm no regressions**

Run: `PYTHONPATH="" python -m pytest tests/ -v --tb=short`
Expected: Existing tests that touch validator may need updates (handled in Task 6)

---

### Task 4: ConfigManager - Remove dual env fields

**Files:**
- Modify: `src/shettyxtreme/core/config/config_manager.py`

- [ ] **Step 1: Edit config_manager.py**

Read the current file, then make these edits:

In the Config dataclass, replace the dual credential fields with just:
```python
    # Broker credentials (loaded from env)
    dhan_client_id: str | None = None
    dhan_access_token: str | None = None
```

Remove these fields:
```python
    # Dhan dual-path credentials (trading + data, separate to avoid error 806)
    dhan_trading_client_id: str | None = None
    dhan_trading_access_token: str | None = None
    dhan_data_api_key: str | None = None
    dhan_data_client_id: str | None = None
```

Remove env overrides for dual fields from `_load_env_overrides`:
```python
            "DHAN_TRADING_CLIENT_ID": "dhan_trading_client_id",
            "DHAN_TRADING_ACCESS_TOKEN": "dhan_trading_access_token",
            "DHAN_DATA_API_KEY": "dhan_data_api_key",
            "DHAN_DATA_CLIENT_ID": "dhan_data_client_id",
```

Change the dual-path comment to: `# Single Dhan credential (one app with both Trading + Market Data capabilities)`

- [ ] **Step 2: Run config tests**

Run: `PYTHONPATH="" python -m pytest tests/ -v --tb=short`
Expected: PASS (config tests don't reference removed fields)

---

### Task 5: AuthRouter - Collapse endpoints

**Files:**
- Modify: `src/shettyxtreme/terminal/api/auth_router.py`

- [ ] **Step 1: Replace auth_router.py**

Read the current file, then write the collapsed version:

```python
"""Auth router for onboarding wizard and Dhan OAuth callback."""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.auth.dhan_oauth import DhanOAuthHelper
from shettyxtreme.auth.validator import CredentialValidator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_store: CredentialStore | None = None
_oauth: DhanOAuthHelper | None = None
_validator: CredentialValidator | None = None


def init_auth(
    store: CredentialStore,
    oauth: DhanOAuthHelper,
    validator: CredentialValidator,
) -> None:
    global _store, _oauth, _validator
    _store = store
    _oauth = oauth
    _validator = validator


class CredentialStatusResponse(BaseModel):
    has_api_key: bool = False
    has_token: bool = False
    token_valid: bool = False
    token_expiry: str | None = None
    connected: bool = False
    setup_complete: bool = False
    client_name: str | None = None
    client_id: str | None = None


class ConsentStartResponse(BaseModel):
    consent_app_id: str
    login_url: str


class SaveResult(BaseModel):
    success: bool
    message: str


class CredentialBody(BaseModel):
    api_key: str
    api_secret: str


def _split_combined_key(api_key: str) -> tuple[str, str]:
    if ":::" in api_key:
        client_id, _, key = api_key.partition(":::")
        return client_id.strip(), key.strip()
    return "", api_key.strip()


class ValidationResultResponse(BaseModel):
    valid: bool
    message: str


def _get_store() -> CredentialStore:
    if _store is None:
        return CredentialStore()
    return _store


@router.get("/status", response_model=CredentialStatusResponse)
async def get_status() -> CredentialStatusResponse:
    store = _get_store()
    token_valid = store.is_token_valid() if store.access_token else False
    connected = token_valid and bool(store.access_token)
    return CredentialStatusResponse(
        has_api_key=bool(store.api_key),
        has_token=bool(store.access_token),
        token_valid=token_valid,
        token_expiry=store.token_expiry,
        connected=connected,
        setup_complete=connected,
        client_name=store.client_name,
        client_id=store.client_id,
    )


@router.post("/credentials", response_model=SaveResult)
async def save_credentials(body: CredentialBody) -> SaveResult:
    store = _get_store()
    client_id, api_key = _split_combined_key(body.api_key)
    store.api_key = api_key
    store.api_secret = body.api_secret
    if client_id:
        store.client_id = client_id
    store.save()
    return SaveResult(success=True, message="Credentials saved")


@router.post("/start-consent", response_model=ConsentStartResponse)
async def start_consent() -> ConsentStartResponse:
    store = _get_store()
    assert _oauth is not None
    consent_app_id = await _oauth.generate_consent(
        api_key=store.api_key,
        api_secret=store.api_secret,
        client_id=store.client_id or "",
    )
    if not consent_app_id:
        raise HTTPException(
            status_code=502,
            detail="Failed to generate consent. Check your API credentials and ensure the OAuth redirect URL is set correctly in the Dhan Developer Portal.",
        )
    login_url = _oauth.get_login_url(consent_app_id)
    return ConsentStartResponse(
        consent_app_id=consent_app_id,
        login_url=login_url,
    )


@router.get("/dhan/callback", response_model=None)
async def dhan_callback(tokenId: str, consentAppId: str = "") -> RedirectResponse:
    try:
        flow_type = _oauth.pop_consent_flow(consentAppId)
        if flow_type is None:
            logger.warning("Unknown consent flow for %s", consentAppId)
            return RedirectResponse(url="/static/setup.html?error=unknown_flow")

        store = _get_store()
        result = await _oauth.consume_consent(
            api_key=store.api_key,
            api_secret=store.api_secret,
            token_id=tokenId,
        )
        if result:
            store.update_token(
                access_token=result.access_token,
                expiry=result.expiry_time,
                client_id=result.client_id,
            )
            store.client_name = result.client_name
            store.save()
            return RedirectResponse(url="/static/setup.html?connected=true")
        return RedirectResponse(url="/static/setup.html?error=consent_failed")

    except Exception:
        logger.exception("OAuth callback failed")
        return RedirectResponse(url="/static/setup.html?error=server_error")


@router.post("/test", response_model=ValidationResultResponse)
async def test_credentials(body: CredentialBody | None = None) -> ValidationResultResponse:
    store = _get_store()
    assert _validator is not None
    if body:
        client_id, api_key = _split_combined_key(body.api_key)
        api_secret = body.api_secret
    else:
        client_id = store.client_id or ""
        api_key = store.api_key
        api_secret = store.api_secret
    result = await _validator.validate_credentials(
        api_key=api_key,
        api_secret=api_secret,
        client_id=client_id,
    )
    return ValidationResultResponse(valid=result.valid, message=result.message)


@router.post("/logout", response_model=SaveResult)
async def logout() -> SaveResult:
    store = _get_store()
    store.access_token = None
    store.save()
    return SaveResult(success=True, message="Access tokens cleared")
```

---

### Task 6: Update auth router tests

**Files:**
- Modify: `tests/wave7/test_auth_router.py`

- [ ] **Step 1: Replace test_auth_router.py**

Read the current file, then write:

```python
"""Tests for AuthRouter (onboarding and OAuth callback)."""
from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shettyxtreme.auth.credential_store import CredentialStore
from shettyxtreme.auth.dhan_oauth import ConsentResult, DhanOAuthHelper
from shettyxtreme.auth.validator import CredentialValidator, ValidationResult
from shettyxtreme.terminal.api.auth_router import (
    init_auth,
    router,
)


def _make_app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


def _make_store() -> CredentialStore:
    return CredentialStore()


def _make_mock_oauth() -> MagicMock:
    oauth = MagicMock(spec=DhanOAuthHelper)
    oauth.generate_consent = AsyncMock(return_value="consent_abc123")
    oauth.get_login_url = MagicMock(
        return_value="https://auth.dhan.co/login/consentApp-login?consentAppId=consent_abc123"
    )
    oauth.consume_consent = AsyncMock(
        return_value=ConsentResult(
            access_token="tok_abcdef123456",
            expiry_time="2026-12-31T23:59:59",
            client_id="DHAN123",
            client_name="Test User",
            ddpi_status=True,
        )
    )
    oauth.pop_consent_flow = MagicMock(return_value="dhan")
    return oauth


def _make_mock_validator() -> MagicMock:
    validator = MagicMock(spec=CredentialValidator)
    validator.validate_credentials = AsyncMock(
        return_value=ValidationResult(valid=True, message="Credentials valid")
    )
    return validator


@pytest.fixture(autouse=True)
def _reset_auth() -> None:
    init_auth(_make_store(), _make_mock_oauth(), _make_mock_validator())
    yield
    init_auth(_make_store(), _make_mock_oauth(), _make_mock_validator())


def test_auth_status_no_creds() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_api_key"] is False
    assert data["has_token"] is False
    assert data["token_valid"] is False


def test_save_credentials() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/auth/credentials",
        json={"api_key": "test_key_123", "api_secret": "test_secret_456"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert "saved" in data["message"].lower()


def test_start_consent() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/auth/start-consent")
    assert resp.status_code == 200
    data = resp.json()
    assert data["consent_app_id"] == "consent_abc123"
    assert "login_url" in data
    assert "consentAppId" in data["login_url"]


def test_dhan_callback_unknown_flow() -> None:
    from shettyxtreme.terminal.api.auth_router import _oauth
    _oauth.pop_consent_flow = MagicMock(return_value=None)
    app = _make_app()
    client = TestClient(app, follow_redirects=False)
    resp = client.get("/auth/dhan/callback?tokenId=test_token_999")
    assert resp.status_code == 307
    assert "setup.html" in resp.headers["location"]
    assert "error=unknown_flow" in resp.headers["location"]


def test_dhan_callback_success() -> None:
    app = _make_app()
    client = TestClient(app, follow_redirects=False)

    client.post(
        "/auth/credentials",
        json={"api_key": "test_key", "api_secret": "test_secret"},
    )

    from shettyxtreme.terminal.api.auth_router import _oauth
    _oauth.pop_consent_flow = MagicMock(return_value="dhan")

    resp = client.get("/auth/dhan/callback?tokenId=tok_123&consentAppId=consent_id")
    assert resp.status_code == 307
    assert "connected=true" in resp.headers["location"]

    status = client.get("/auth/status").json()
    assert status["has_token"] is True


def test_auth_logout() -> None:
    app = _make_app()
    client = TestClient(app)
    client.post(
        "/auth/credentials",
        json={"api_key": "key1", "api_secret": "secret1"},
    )
    resp = client.post("/auth/logout")
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    status = client.get("/auth/status").json()
    assert status["has_token"] is False


def test_auth_status_with_creds() -> None:
    app = _make_app()
    client = TestClient(app)
    client.post(
        "/auth/credentials",
        json={"api_key": "my_key", "api_secret": "my_secret"},
    )
    resp = client.get("/auth/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["has_api_key"] is True
```

- [ ] **Step 2: Run auth router tests**

Run: `PYTHONPATH="" python -m pytest tests/wave7/test_auth_router.py -v --tb=short`
Expected: ALL PASS

---

### Task 7: Setup HTML - 4-step to 3-step wizard

**Files:**
- Modify: `src/shettyxtreme/terminal/static/setup.html`

- [ ] **Step 1: Edit setup.html**

Key changes:
1. `STEPS = 4` → `STEPS = 3`, `STEP_TITLES = ['Trading API', 'Data API', 'Connect', 'Done']` → `STEP_TITLES = ['API Key', 'Connect', 'Done']`
2. Remove step 2 (Data API credentials) HTML block
3. Renumber remaining steps: step 3 → step 2, step 4 → step 3
4. Update `checkUrlParams()`: `params.get('connected') === 'trading'` → `params.get('connected') === 'true'`, remove data check
5. Update `checkStatus()`: single `connected` check instead of both
6. Update step navigation: `showStep(2)` for back/next instead of 3
7. Update OAuth connect button: single button, single `/auth/start-consent` call
8. Update help instructions: "Create ONE app with both Trading + Market Data capabilities"
9. Update progress bar renders to 3 steps
10. Remove all `dataApiKey`, `dataApiSecret`, `dataTested`, `btnConnectData`, `dataDot`, `dataConnLabel` references

- [ ] **Step 2: Manual review of setup.html**

Check that no invalid DOM IDs remain referenced in JS.

---

### Task 8: Full test sweep + verification

- [ ] **Step 1: Run full test suite**

Run: `PYTHONPATH="" python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 2: Check import rules**

Run: `Select-String -Path "src\shettyxtreme\**\*.py" -Pattern "import openalgo|from openalgo"`
Expected: No matches

- [ ] **Step 3: Check file length rule**

Run: `Get-ChildItem -Path "src\shettyxtreme" -Recurse -Filter "*.py" | ForEach-Object { if ((Get-Content $_).Count -gt 500) { $_ } }`
Expected: No output (no files > 500 lines)

- [ ] **Step 4: Check for stale dual-credential references**

Run: `Select-String -Path "src\shettyxtreme\**\*.py" -Pattern "trading_api_key|data_api_key|trading_api_secret|data_api_secret"`
Expected: No matches (except possibly in migration code within credential_store.py)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat: consolidate dual credentials to single Dhan credential

- CredentialStore: merge trading/data fields, add old-format migration
- ConfigManager: remove dual credential env overrides
- Validator: collapse validate_trading/validate_data to validate_credentials
- AuthRouter: collapse 9 endpoints to 6
- Setup HTML: 4-step wizard to 3-step
- Tests: update to match single-credential architecture"
```
