# P1 — Credential Onboarding UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Dhan credential setup and token re-auth fully usable from the browser — a 3-method setup wizard at `#/setup`, a real settings view at `#/settings`, a header credential chip, and three new backend endpoints that expose DhanPy's three auth flows (consent, direct token, PIN+TOTP) plus the data fallback token.

**Architecture:** Backend-first: 4 small changes in `auth/credential_store.py` (exp extraction + data-token validity helper) and `terminal/api/auth_router.py` (3 endpoints + status extension), each test-first in `tests/wave7/`. Then frontend: typed wrappers in `lib/api.ts`, two new components (`SetupWizard.svelte`, `SettingsView.svelte`), header chip, and route wiring in `App.svelte`. All endpoints wrap existing helpers — zero new auth logic.

**Tech Stack:** Python 3.11 + FastAPI + pytest (backend), Svelte 5 + TypeScript + Vite (frontend), Fernet credential store.

**Spec:** `docs/superpowers/specs/2026-08-02-terminal-remediation-design.md` §3.

## Global Constraints

- Test command (ALWAYS this exact form): `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave7/test_auth_router.py -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider` (use `tests/wave7/test_credential_store.py` for store tasks).
- Frontend gates: `npm run check` → 0 errors; `npm run build` → bundle lands in `src/shettyxtreme/terminal/static/` and MUST be committed (served from there).
- Full suite must stay green (732 baseline): `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider`
- No `openalgo` imports; no file > 500 lines; `core/` no external imports.
- Existing routes/contracts frozen: `/auth/*` is canonical (NOT `/api/auth`); OAuth callback redirect target `#/setup?connected=true` / `?error=...` unchanged.
- Design tokens: red `#f6525c` = up, green `#2ebd85` = down; numerals in mono; Indian price convention is law.
- Credentials stay Fernet-encrypted at `~/.shettyxtreme/credentials.enc`; never log secrets.

## File Structure

- `src/shettyxtreme/auth/credential_store.py` — modify: add `_extract_exp_from_token` static, `is_data_token_valid` method.
- `src/shettyxtreme/terminal/api/auth_router.py` — modify: 3 new endpoints + `CredentialStatusResponse` extension + `TokenBody`/`PinTotpBody`/`DataTokenBody` models.
- `tests/wave7/test_credential_store.py` — modify: exp extraction + data-token validity tests.
- `tests/wave7/test_auth_router.py` — modify: 4 new test groups (token paste, pin-totp, data-token, status extension).
- `src/shettyxtreme/terminal/web/src/lib/api.ts` — modify: auth types + typed wrappers.
- `src/shettyxtreme/terminal/web/src/components/SetupWizard.svelte` — create.
- `src/shettyxtreme/terminal/web/src/components/SettingsView.svelte` — create.
- `src/shettyxtreme/terminal/web/src/components/Header.svelte` — modify: credential chip.
- `src/shettyxtreme/terminal/web/src/App.svelte` — modify: render new components, fix `/api/auth` text.

---

### Task 1: CredentialStore — exp extraction + data-token validity

**Files:**
- Modify: `src/shettyxtreme/auth/credential_store.py` (after `_extract_client_id_from_token` block, ~line 89; after `is_token_valid`, ~line 103)
- Test: `tests/wave7/test_credential_store.py`

**Interfaces:**
- Consumes: nothing (pure additions)
- Produces: `CredentialStore._extract_exp_from_token(access_token: str | None) -> str` (ISO-8601 string or ""), `CredentialStore.is_data_token_valid() -> bool`

- [ ] **Step 1: Write the failing tests** — append to `tests/wave7/test_credential_store.py`:

```python
def test_extract_exp_from_token() -> None:
    import base64, json
    payload = {"dhanClientId": "DHAN123", "exp": 1780000000}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    token = f"header.{body}.signature"
    expiry = CredentialStore._extract_exp_from_token(token)
    assert expiry.startswith("2026-")  # 1780000000 = 2026-05-28T...
    assert CredentialStore._extract_exp_from_token(None) == ""
    assert CredentialStore._extract_exp_from_token("not.a.jwt") == ""


def test_data_token_validity() -> None:
    store = CredentialStore()
    assert store.is_data_token_valid() is False
    store.data_access_token = "tok"
    store.data_access_token_expiry = "2026-12-31T23:59:59"
    assert store.is_data_token_valid() is True
    store.data_access_token_expiry = "2020-01-01T00:00:00"
    assert store.is_data_token_valid() is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave7/test_credential_store.py -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider`
Expected: FAIL — `AttributeError: type object 'CredentialStore' has no attribute '_extract_exp_from_token'`

- [ ] **Step 3: Implement** — add to `credential_store.py` after `_extract_client_id_from_token` (reuse the same JWT-decode pattern) and after `is_token_valid`:

```python
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

    def is_data_token_valid(self) -> bool:
        """True when the data-access token exists and has not expired."""
        if not self.data_access_token or not self.data_access_token_expiry:
            return False
        expiry = datetime.fromisoformat(self.data_access_token_expiry)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        return expiry > datetime.now(UTC)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: same command as Step 2. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/shettyxtreme/auth/credential_store.py tests/wave7/test_credential_store.py
git commit -m "feat(auth): add JWT exp extraction and data-token validity to CredentialStore"
```

---

### Task 2: auth_router — `POST /auth/token` (direct token paste)

**Files:**
- Modify: `src/shettyxtreme/terminal/api/auth_router.py` (models after `CredentialBody` ~line 56; endpoint after `save_credentials` ~line 110)
- Test: `tests/wave7/test_auth_router.py`

**Interfaces:**
- Consumes: `CredentialStore._extract_client_id_from_token` (exists), `CredentialStore._extract_exp_from_token` (Task 1)
- Produces: `POST /auth/token` with body `{"access_token": str}` → `SaveResult`; 400 + `{"detail": ...}` on undecodable token

- [ ] **Step 1: Write the failing test** — append to `tests/wave7/test_auth_router.py`:

```python
def test_post_direct_token() -> None:
    import base64, json
    payload = {"dhanClientId": "DHAN123", "exp": 1780000000}
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    token = f"header.{body}.signature"
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/auth/token", json={"access_token": token})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert _get_store().client_id == "DHAN123"
    assert _get_store().access_token == token
    assert _get_store().token_expiry.startswith("2026-")


def test_post_direct_token_invalid() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/auth/token", json={"access_token": "garbage"})
    assert resp.status_code == 400
```

Note: `_get_store()` returns the module-global store (already imported in the test file). If the test file doesn't import it, add `from shettyxtreme.terminal.api.auth_router import _get_store` at the top.

- [ ] **Step 2: Run test to verify it fails**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave7/test_auth_router.py::test_post_direct_token -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider`
Expected: FAIL — 404/405 (route doesn't exist).

- [ ] **Step 3: Implement** — add model + endpoint:

```python
class TokenBody(BaseModel):
    access_token: str


@router.post("/token", response_model=SaveResult)
async def save_direct_token(body: TokenBody) -> SaveResult:
    store = _get_store()
    client_id = CredentialStore._extract_client_id_from_token(body.access_token)
    expiry = CredentialStore._extract_exp_from_token(body.access_token)
    if not client_id:
        raise HTTPException(
            status_code=400,
            detail="Invalid access token: could not extract client ID (expected a Dhan JWT).",
        )
    store.update_token(
        access_token=body.access_token,
        expiry=expiry,
        client_id=client_id,
    )
    store.save()
    return SaveResult(success=True, message="Access token saved")
```

- [ ] **Step 4: Run test to verify it passes**

Run: same as Step 2, plus the invalid-token test:
`$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave7/test_auth_router.py -k "direct_token" -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/shettyxtreme/terminal/api/auth_router.py tests/wave7/test_auth_router.py
git commit -m "feat(auth): POST /auth/token — save a pasted access token with JWT client/exp extraction"
```

---

### Task 3: auth_router — `POST /auth/token/pin-totp` (expose existing helper)

**Files:**
- Modify: `src/shettyxtreme/terminal/api/auth_router.py` (after Task 2's endpoint)
- Test: `tests/wave7/test_auth_router.py`

**Interfaces:**
- Consumes: `DhanOAuthHelper.generate_access_token(client_id, pin, totp) -> ConsumeResult` (exists, dhan_oauth.py:120)
- Produces: `POST /auth/token/pin-totp` with body `{"client_id", "pin", "totp"}` → `SaveResult`; 400 on auth failure, 502 on connection error

- [ ] **Step 1: Write the failing tests** — append:

```python
def test_pin_totp_success() -> None:
    from shettyxtreme.terminal.api.auth_router import _oauth
    assert _oauth is not None
    _oauth.generate_access_token = AsyncMock(
        return_value=ConsumeResult(
            consent=ConsentResult(
                access_token="tok_pintotp",
                expiry_time="2026-12-31T23:59:59",
                client_id="DHAN123",
                client_name="PIN User",
                ddpi_status=True,
            )
        )
    )
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/auth/token/pin-totp", json={"client_id": "DHAN123", "pin": "1234", "totp": "567890"})
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert _get_store().access_token == "tok_pintotp"
    assert _get_store().client_id == "DHAN123"


def test_pin_totp_bad_credentials() -> None:
    from shettyxtreme.terminal.api.auth_router import _oauth
    assert _oauth is not None
    _oauth.generate_access_token = AsyncMock(
        return_value=ConsumeResult(error="Dhan API 401: Invalid client id. Re-enter credentials in Step 1.")
    )
    app = _make_app()
    client = TestClient(app)
    resp = client.post("/auth/token/pin-totp", json={"client_id": "X", "pin": "0", "totp": "0"})
    assert resp.status_code == 400
    assert "401" in resp.json()["detail"]
```

Note: the autouse `_reset_auth` fixture rebuilds `_oauth` as `MagicMock(spec=DhanOAuthHelper)` each test; `generate_access_token` exists on the spec so `AsyncMock` assignment works.

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave7/test_auth_router.py -k "pin_totp" -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider`
Expected: FAIL — 404/405.

- [ ] **Step 3: Implement** — add model + endpoint:

```python
class PinTotpBody(BaseModel):
    client_id: str
    pin: str
    totp: str


@router.post("/token/pin-totp", response_model=SaveResult)
async def save_pin_totp(body: PinTotpBody) -> SaveResult:
    store = _get_store()
    assert _oauth is not None
    result = await _oauth.generate_access_token(
        client_id=body.client_id,
        pin=body.pin,
        totp=body.totp,
    )
    if not result.ok:
        error = result.error or "Failed to generate access token"
        if "Connection error" in error:
            raise HTTPException(status_code=502, detail=error)
        raise HTTPException(status_code=400, detail=error)
    consent = result.consent
    assert consent is not None
    store.update_token(
        access_token=consent.access_token,
        expiry=consent.expiry_time,
        client_id=consent.client_id,
    )
    store.save()
    return SaveResult(success=True, message="Access token generated and saved")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: same as Step 2. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/shettyxtreme/terminal/api/auth_router.py tests/wave7/test_auth_router.py
git commit -m "feat(auth): POST /auth/token/pin-totp — expose the PIN+TOTP generateAccessToken flow"
```

---

### Task 4: auth_router — `POST /auth/data-token` + status extension

**Files:**
- Modify: `src/shettyxtreme/terminal/api/auth_router.py` (response model ~line 35, `get_status` ~line 84, new endpoint after Task 3's)
- Test: `tests/wave7/test_auth_router.py`

**Interfaces:**
- Consumes: `CredentialStore.update_data_token(token, expiry)` (exists, credential_store.py:110), `is_data_token_valid()` (Task 1)
- Produces: `POST /auth/data-token` body `{"access_token": str, "expiry": str | None}` → `SaveResult`; `CredentialStatusResponse` gains `data_token_valid: bool`, `data_token_expiry: str | None`

- [ ] **Step 1: Write the failing tests** — append:

```python
def test_save_data_token() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.post(
        "/auth/data-token",
        json={"access_token": "data_tok_1", "expiry": "2026-12-31T23:59:59"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    assert _get_store().data_access_token == "data_tok_1"


def test_status_data_token_fields() -> None:
    app = _make_app()
    client = TestClient(app)
    resp = client.get("/auth/status")
    data = resp.json()
    assert "data_token_valid" in data
    assert "data_token_expiry" in data
    assert data["data_token_valid"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave7/test_auth_router.py -k "data_token" -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider`
Expected: FAIL — 404/405 and missing response fields.

- [ ] **Step 3: Implement**

Extend the response model:

```python
class CredentialStatusResponse(BaseModel):
    has_api_key: bool = False
    has_token: bool = False
    token_valid: bool = False
    token_expiry: str | None = None
    connected: bool = False
    setup_complete: bool = False
    client_name: str | None = None
    client_id: str | None = None
    data_token_valid: bool = False
    data_token_expiry: str | None = None
```

Extend `get_status` (add before the return):

```python
    data_token_valid = store.is_data_token_valid() if store.data_access_token else False
```

and add to the `CredentialStatusResponse(...)` constructor:

```python
        data_token_valid=data_token_valid,
        data_token_expiry=store.data_access_token_expiry,
```

Add model + endpoint:

```python
class DataTokenBody(BaseModel):
    access_token: str
    expiry: str | None = None


@router.post("/data-token", response_model=SaveResult)
async def save_data_token(body: DataTokenBody) -> SaveResult:
    store = _get_store()
    store.update_data_token(token=body.access_token, expiry=body.expiry)
    store.save()
    return SaveResult(success=True, message="Data access token saved")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave7/test_auth_router.py -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider`
Expected: whole file PASS.

- [ ] **Step 5: Run the full suite**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider`
Expected: 736+ passed, 0 failed (732 baseline + new tests).

- [ ] **Step 6: Commit**

```bash
git add src/shettyxtreme/terminal/api/auth_router.py tests/wave7/test_auth_router.py
git commit -m "feat(auth): POST /auth/data-token and data-token fields in /auth/status"
```

---

### Task 5: api.ts — typed auth wrappers

**Files:**
- Modify: `src/shettyxtreme/terminal/web/src/lib/api.ts` (append after `SessionsResponse` at line 214)

**Interfaces:**
- Consumes: existing `get`/`post`/`postBody` helpers
- Produces: types + functions consumed by Tasks 6–8 (exact names below)

- [ ] **Step 1: Implement** — append to `api.ts`:

```ts
// --- Auth / credential onboarding (P1) ---

export type AuthStatus = {
  has_api_key: boolean;
  has_token: boolean;
  token_valid: boolean;
  token_expiry: string | null;
  connected: boolean;
  setup_complete: boolean;
  client_name: string | null;
  client_id: string | null;
  data_token_valid: boolean;
  data_token_expiry: string | null;
};

export type ConsentStart = { consent_app_id: string; login_url: string };
export type SaveResult = { success: boolean; message: string };
export type ValidationResult = { valid: boolean; message: string };

export async function authStatus(): Promise<AuthStatus> {
  return get<AuthStatus>("/auth/status");
}

export async function saveCredentials(apiKey: string, apiSecret: string): Promise<SaveResult> {
  return postBody<SaveResult>("/auth/credentials", { api_key: apiKey, api_secret: apiSecret });
}

export async function testCredentials(apiKey: string, apiSecret: string): Promise<ValidationResult> {
  return postBody<ValidationResult>("/auth/test", { api_key: apiKey, api_secret: apiSecret });
}

export async function startConsent(): Promise<ConsentStart> {
  return post<ConsentStart>("/auth/start-consent");
}

export async function saveDirectToken(accessToken: string): Promise<SaveResult> {
  return postBody<SaveResult>("/auth/token", { access_token: accessToken });
}

export async function savePinTotp(clientId: string, pin: string, totp: string): Promise<SaveResult> {
  return postBody<SaveResult>("/auth/token/pin-totp", { client_id: clientId, pin, totp });
}

export async function saveDataToken(accessToken: string, expiry: string | null = null): Promise<SaveResult> {
  return postBody<SaveResult>("/auth/data-token", { access_token: accessToken, expiry });
}

export async function reauth(): Promise<ConsentStart> {
  return post<ConsentStart>("/api/settings/reauth");
}

export async function logoutAuth(): Promise<SaveResult> {
  return post<SaveResult>("/auth/logout");
}
```

- [ ] **Step 2: Verify with svelte-check**

Run (in `src/shettyxtreme/terminal/web`): `npm run check`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add src/shettyxtreme/terminal/web/src/lib/api.ts
git commit -m "feat(web): typed auth API wrappers (status, credentials, consent, token, pin-totp, data-token)"
```

---

### Task 6: SetupWizard.svelte — 3-method setup view

**Files:**
- Create: `src/shettyxtreme/terminal/web/src/components/SetupWizard.svelte`

**Interfaces:**
- Consumes: `authStatus`, `saveCredentials`, `testCredentials`, `startConsent`, `saveDirectToken`, `savePinTotp`, `saveDataToken` (Task 5)
- Produces: component rendered by App.svelte at route `/setup` (Task 8); respects `?connected=true` / `?error=` query params passed via props

- [ ] **Step 1: Implement** — create the component (follows Header.svelte patterns: `onMount` fetch, local `error`, CSS via `design.css` tokens; tabs per DESIGN.md spec):

```svelte
<script lang="ts">
  import { onMount } from "svelte";
  import {
    authStatus,
    saveCredentials,
    saveDirectToken,
    saveDataToken,
    savePinTotp,
    startConsent,
    testCredentials,
    type AuthStatus,
    type SaveResult,
    type ValidationResult,
  } from "../lib/api";

  export let query: URLSearchParams | null = null;

  let status: AuthStatus | null = null;
  let tab = "creds";
  let error = "";
  let busy = false;

  // Method 1: app credentials
  let clientId = "";
  let apiKey = "";
  let apiSecret = "";
  let testResult: ValidationResult | null = null;

  // Method 2: direct token
  let directToken = "";

  // Method 3: PIN + TOTP
  let ptClientId = "";
  let pin = "";
  let totp = "";

  // Data token (advanced)
  let dataToken = "";
  let showDataToken = false;

  onMount(load);

  async function load(): Promise<void> {
    try {
      status = await authStatus();
    } catch {
      status = null;
    }
  }

  async function run(fn: () => Promise<unknown>): Promise<void> {
    error = "";
    busy = true;
    try {
      await fn();
      await load();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }

  function onTest(): void {
    void run(async () => {
      testResult = await testCredentials(clientId ? `${clientId}:::${apiKey}` : apiKey, apiSecret);
    });
  }

  function onConnect(): void {
    void run(async () => {
      await saveCredentials(clientId ? `${clientId}:::${apiKey}` : apiKey, apiSecret);
      const consent = await startConsent();
      window.location.href = consent.login_url;
    });
  }

  function onSaveDirect(): void {
    void run(async () => saveDirectToken(directToken.trim()));
  }

  function onSavePinTotp(): void {
    void run(async () => savePinTotp(ptClientId.trim(), pin.trim(), totp.trim()));
  }

  function onSaveDataToken(): void {
    void run(async () => saveDataToken(dataToken.trim()));
  }

  function tabClass(t: string): string {
    return t === tab ? "tab active" : "tab";
  }
</script>

<div class="setup">
  <h1 class="heading">Setup</h1>

  {#if query && query.get("connected") === "true"}
    <div class="banner banner-ok" role="status">Connected — credentials saved. Close this tab and return to the terminal.</div>
  {:else if query && query.get("error")}
    <div class="banner banner-err" role="alert">{query.get("error")} <a href="#/settings">Retry</a></div>
  {/if}

  {#if status?.connected}
    <div class="banner banner-ok" role="status">
      Connected as {status.client_name || status.client_id}. Token valid until {status.token_expiry?.slice(0, 10)}.
      <a href="#/">← Back to terminal</a>
    </div>
  {/if}

  {#if status && !status.connected && status.has_token && !status.token_valid}
    <div class="banner banner-warn" role="alert">Saved token has expired — re-connect to refresh it.</div>
  {/if}

  <div class="tabs" role="tablist">
    <button class={tabClass("creds")} on:click={() => (tab = "creds")}>App credentials</button>
    <button class={tabClass("token")} on:click={() => (tab = "token")}>Direct token</button>
    <button class={tabClass("pintotp")} on:click={() => (tab = "pintotp")}>PIN + TOTP</button>
  </div>

  {#if tab === "creds"}
    <div class="card">
      <p class="caption">From the Dhan Developer Portal — one app with Trading + Market Data capabilities.</p>
      <label class="field">
        <span class="caption">Client ID</span>
        <input class="mono" bind:value={clientId} placeholder="DHANCLIENTID" />
      </label>
      <label class="field">
        <span class="caption">API Key</span>
        <input class="mono" type="password" bind:value={apiKey} placeholder="api_key" />
      </label>
      <label class="field">
        <span class="caption">API Secret</span>
        <input class="mono" type="password" bind:value={apiSecret} placeholder="api_secret" />
      </label>
      <div class="actions">
        <button class="btn-secondary" on:click={onTest} disabled={busy || !apiKey || !apiSecret}>Test</button>
        <button class="btn-primary" on:click={onConnect} disabled={busy || !apiKey || !apiSecret}>Connect Dhan</button>
      </div>
      {#if testResult}
        <p class={testResult.valid ? "ok-text" : "err-text"}>{testResult.message}</p>
      {/if}
    </div>
  {:else if tab === "token"}
    <div class="card">
      <p class="caption">Paste an existing Dhan access token (JWT). Client ID and expiry are read from it automatically.</p>
      <label class="field">
        <span class="caption">Access Token</span>
        <input class="mono" type="password" bind:value={directToken} placeholder="eyJhbGciOi…" />
      </label>
      <div class="actions">
        <button class="btn-primary" on:click={onSaveDirect} disabled={busy || !directToken.trim()}>Save token</button>
      </div>
    </div>
  {:else}
    <div class="card">
      <p class="caption">Generate an access token from your Dhan client ID + trading PIN + TOTP.</p>
      <label class="field">
        <span class="caption">Client ID</span>
        <input class="mono" bind:value={ptClientId} placeholder="DHANCLIENTID" />
      </label>
      <label class="field">
        <span class="caption">PIN</span>
        <input class="mono" type="password" bind:value={pin} placeholder="4-digit trading PIN" />
      </label>
      <label class="field">
        <span class="caption">TOTP</span>
        <input class="mono" bind:value={totp} placeholder="6-digit authenticator code" />
      </label>
      <div class="actions">
        <button class="btn-primary" on:click={onSavePinTotp} disabled={busy || !ptClientId || !pin || !totp}>Generate & save</button>
      </div>
    </div>
  {/if}

  <details class="advanced">
    <summary class="caption">Data token (optional — only if your app lacks Market Data entitlement)</summary>
    <label class="field">
      <span class="caption">Data Access Token</span>
      <input class="mono" type="password" bind:value={dataToken} placeholder="separate data-entitlement token" />
    </label>
    <button class="btn-secondary" on:click={onSaveDataToken} disabled={busy || !dataToken.trim()}>Save data token</button>
  </details>

  {#if error}
    <p class="err-text">{error}</p>
  {/if}

  <a href="#/">← Back to terminal</a>
</div>

<style>
  .setup { max-width: 560px; margin: 32px auto; padding: 0 16px; }
  .heading { font-size: 14px; font-weight: 600; color: var(--ink); margin-bottom: 12px; }
  .tabs { display: flex; gap: 4px; border-bottom: 2px solid var(--hairline); margin-bottom: 12px; }
  .tab {
    background: none; border: none; padding: 8px 12px; font-size: 12px; color: var(--muted);
    cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -2px;
  }
  .tab:hover { color: var(--body); }
  .tab.active { color: var(--ink); border-bottom-color: var(--accent); }
  .card {
    background: var(--surface-card); border: 1px solid var(--hairline); border-radius: 6px;
    padding: 16px; display: flex; flex-direction: column; gap: 12px;
  }
  .field { display: flex; flex-direction: column; gap: 4px; }
  .field input {
    background: var(--canvas-raised); border: 1px solid var(--hairline); border-radius: 4px;
    color: var(--ink); padding: 6px 10px; font-size: 12px;
  }
  .field input:focus { outline: none; border-color: var(--focus-ring); }
  .actions { display: flex; gap: 8px; }
  .btn-primary {
    background: var(--accent); border: 1px solid var(--accent); border-radius: 4px;
    color: var(--on-accent); font-size: 13px; font-weight: 600; padding: 8px 24px; cursor: pointer;
  }
  .btn-primary:disabled { background: var(--accent-disabled); color: var(--faint); cursor: default; }
  .btn-secondary {
    background: var(--surface-elevated); border: 1px solid var(--hairline-strong); border-radius: 4px;
    color: var(--body); font-size: 13px; font-weight: 600; padding: 8px 24px; cursor: pointer;
  }
  .btn-secondary:disabled { color: var(--faint); border-color: var(--hairline); cursor: default; }
  .advanced { margin-top: 12px; }
  .advanced summary { cursor: pointer; color: var(--muted); }
  .advanced .field { margin: 8px 0; }
  .banner { padding: 8px 12px; border-radius: 4px; font-size: 12px; margin-bottom: 12px; }
  .banner-ok { background: color-mix(in srgb, var(--success) 14%, transparent); border: 1px solid var(--success); }
  .banner-warn { background: color-mix(in srgb, var(--warning) 14%, transparent); border: 1px solid var(--warning); }
  .banner-err { background: color-mix(in srgb, var(--danger) 14%, transparent); border: 1px solid var(--danger); }
  .ok-text { color: var(--success); font-size: 12px; margin: 0; }
  .err-text { color: var(--danger); font-size: 12px; margin: 0; }
  .caption { color: var(--muted); font-size: 12px; margin: 0; }
</style>
```

- [ ] **Step 2: Verify with svelte-check**

Run (in `src/shettyxtreme/terminal/web`): `npm run check`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add src/shettyxtreme/terminal/web/src/components/SetupWizard.svelte
git commit -m "feat(web): 3-method SetupWizard (credentials / direct token / PIN+TOTP) + data token slot"
```

---

### Task 7: SettingsView.svelte — status, re-auth, logout

**Files:**
- Create: `src/shettyxtreme/terminal/web/src/components/SettingsView.svelte`

**Interfaces:**
- Consumes: `authStatus`, `reauth`, `logoutAuth` (Task 5)
- Produces: component rendered by App.svelte at route `/settings` (Task 8)

- [ ] **Step 1: Implement** — create the component:

```svelte
<script lang="ts">
  import { onMount } from "svelte";
  import { authStatus, logoutAuth, reauth, type AuthStatus } from "../lib/api";

  let status: AuthStatus | null = null;
  let error = "";
  let busy = false;

  onMount(load);

  async function load(): Promise<void> {
    try {
      status = await authStatus();
    } catch {
      status = null;
    }
  }

  async function onReauth(): Promise<void> {
    error = "";
    busy = true;
    try {
      const consent = await reauth();
      window.location.href = consent.login_url;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
      busy = false;
    }
  }

  async function onLogout(): Promise<void> {
    error = "";
    busy = true;
    try {
      await logoutAuth();
      status = null;
      await load();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      busy = false;
    }
  }

  function fmtExpiry(v: string | null): string {
    if (!v) return "—";
    const d = new Date(v);
    return Number.isNaN(d.getTime()) ? v : d.toLocaleString("en-IN");
  }
</script>

<div class="settings">
  <h1 class="heading">Settings</h1>

  {#if status}
    <div class="card">
      <div class="row"><span class="label">Client</span><span class="value mono">{status.client_name || status.client_id || "—"}</span></div>
      <div class="row"><span class="label">Token</span><span class="value mono">{status.token_valid ? "VALID" : status.has_token ? "EXPIRED" : "NOT SET"}</span></div>
      <div class="row"><span class="label">Token expiry</span><span class="value mono">{fmtExpiry(status.token_expiry)}</span></div>
      <div class="row"><span class="label">Data token</span><span class="value mono">{status.data_token_valid ? "VALID" : "NOT SET"}</span></div>
      <div class="row"><span class="label">Data token expiry</span><span class="value mono">{fmtExpiry(status.data_token_expiry)}</span></div>
      <div class="actions">
        <button class="btn-primary" on:click={onReauth} disabled={busy}>Re-auth (open Dhan login)</button>
        <button class="btn-danger" on:click={onLogout} disabled={busy}>Logout</button>
      </div>
    </div>
  {:else}
    <p class="caption">Could not load credential status — is the terminal running?</p>
  {/if}

  {#if error}
    <p class="err-text">{error}</p>
  {/if}

  <a href="#/">← Back to terminal</a>
</div>

<style>
  .settings { max-width: 560px; margin: 32px auto; padding: 0 16px; }
  .heading { font-size: 14px; font-weight: 600; color: var(--ink); margin-bottom: 12px; }
  .card {
    background: var(--surface-card); border: 1px solid var(--hairline); border-radius: 6px;
    padding: 16px; display: flex; flex-direction: column; gap: 10px; margin-bottom: 12px;
  }
  .row { display: flex; justify-content: space-between; gap: 16px; }
  .label { color: var(--muted); font-size: 12px; }
  .value { color: var(--ink); font-size: 12px; }
  .actions { display: flex; gap: 8px; margin-top: 8px; }
  .btn-primary {
    background: var(--accent); border: 1px solid var(--accent); border-radius: 4px;
    color: var(--on-accent); font-size: 13px; font-weight: 600; padding: 8px 24px; cursor: pointer;
  }
  .btn-primary:disabled { background: var(--accent-disabled); color: var(--faint); cursor: default; }
  .btn-danger {
    background: var(--danger); border: 1px solid var(--danger); border-radius: 4px;
    color: #fff; font-size: 13px; font-weight: 600; padding: 8px 24px; cursor: pointer;
  }
  .btn-danger:disabled { background: #7a2a2e; color: #ffb9bb; cursor: default; }
  .caption { color: var(--muted); font-size: 12px; }
  .err-text { color: var(--danger); font-size: 12px; }
</style>
```

- [ ] **Step 2: Verify with svelte-check**

Run (in `src/shettyxtreme/terminal/web`): `npm run check`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add src/shettyxtreme/terminal/web/src/components/SettingsView.svelte
git commit -m "feat(web): SettingsView with credential status, re-auth and logout"
```

---

### Task 8: Header chip + App.svelte route wiring

**Files:**
- Modify: `src/shettyxtreme/terminal/web/src/components/Header.svelte`
- Modify: `src/shettyxtreme/terminal/web/src/App.svelte`

**Interfaces:**
- Consumes: `authStatus` (Task 5), `SetupWizard` (Task 6), `SettingsView` (Task 7)
- Produces: navigable credential chip; `/setup` and `/settings` routes render the real views

- [ ] **Step 1: Header chip** — modify `Header.svelte`:

In the `<script>` block, after the existing `load()`:
```ts
  import { authStatus, type AuthStatus } from "../lib/api";
  // add state:
  let credStatus: AuthStatus | null = null;
  // in onMount: call loadCreds() alongside load()
  async function loadCreds(): Promise<void> {
    try {
      credStatus = await authStatus();
    } catch {
      credStatus = null;
    }
  }
```

After the `session` block and before the LOGS button, add:
```svelte
  {#if credStatus}
    {#if credStatus.connected}
      <a class="cred-chip ok" href="#/settings" title="Credentials connected — manage in settings">
        <span class="dot"></span>CONNECTED
      </a>
    {:else if credStatus.has_token && !credStatus.token_valid}
      <a class="cred-chip warn" href="#/settings" title="Token expired — re-authenticate in settings">
        <span class="dot"></span>REAUTH
      </a>
    {:else}
      <a class="cred-chip mute" href="#/setup" title="Set up Dhan credentials">
        <span class="dot"></span>SETUP
      </a>
    {/if}
  {/if}
```

Add styles (mirroring `.ent-chip`):
```css
  .cred-chip {
    display: inline-flex; align-items: center; gap: 6px;
    border-radius: 4px; font-size: 10px; font-weight: 700;
    letter-spacing: 0.06em; padding: 3px 8px; white-space: nowrap; text-decoration: none;
  }
  .cred-chip .dot { width: 6px; height: 6px; border-radius: 50%; }
  .cred-chip.ok { background: color-mix(in srgb, var(--success) 14%, transparent); border: 1px solid var(--success); color: var(--success); }
  .cred-chip.ok .dot { background: var(--success); }
  .cred-chip.warn { background: color-mix(in srgb, var(--warning) 14%, transparent); border: 1px solid var(--warning); color: var(--warning); }
  .cred-chip.warn .dot { background: var(--warning); }
  .cred-chip.mute { background: var(--surface-card); border: 1px solid var(--hairline-strong); color: var(--muted); }
  .cred-chip.mute .dot { background: var(--faint); }
  .cred-chip:hover { color: var(--accent-active); border-color: var(--accent); }
```

- [ ] **Step 2: App.svelte wiring** — modify `App.svelte`:

Add imports:
```ts
  import SetupWizard from "./components/SetupWizard.svelte";
  import SettingsView from "./components/SettingsView.svelte";
```

Replace the `/settings` branch (lines 73-78):
```svelte
  {:else if route === "/settings"}
    <SettingsView />
```

Replace the `/setup` branch (lines 79-92):
```svelte
  {:else if route === "/setup"}
    <SetupWizard {query} />
```

- [ ] **Step 3: Verify with svelte-check**

Run (in `src/shettyxtreme/terminal/web`): `npm run check`
Expected: 0 errors.

- [ ] **Step 4: Build and commit the bundle**

```powershell
npm run build
```
Then commit BOTH source and bundle:
```bash
git add src/shettyxtreme/terminal/web/src/components/Header.svelte src/shettyxtreme/terminal/web/src/App.svelte src/shettyxtreme/terminal/static/
git commit -m "feat(web): header credential chip + wire /setup and /settings to real views (bundle)"
```

- [ ] **Step 5: Full-suite regression**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\pytest-phase2 -p no:cacheprovider`
Expected: all pass (frontend-only change; verifies nothing regressed).

---

### Task 9: Manual verification of the live flow

**Files:** none (verification only)

- [ ] **Step 1: Start the terminal**

Run: `.venv\Scripts\python.exe run.py --mode OBSERVER`
Expected: starts without the port-8000 bind error (stop any previous instance first: `Stop-Process -Id <pid> -Force` if needed).

- [ ] **Step 2: Check the header chip**

Open `http://127.0.0.1:8000/#/`. Expected: header shows SETUP chip (or CONNECTED/REAUTH matching stored state).

- [ ] **Step 3: Exercise the wizard**

Open `http://127.0.0.1:8000/#/setup`. Expected: 3 tabs render; `?connected=true` banner logic intact (visit `http://127.0.0.1:8000/?connected=true#/setup` to confirm).

- [ ] **Step 4: Exercise settings**

Open `http://127.0.0.1:8000/#/settings`. Expected: status rows render; Re-auth navigates to Dhan login (if credentials stored); Logout clears token and flips chip to SETUP.

- [ ] **Step 5: Commit any manual-verification fixes**

If verification surfaced issues, fix, re-run `npm run check` + `npm run build`, and commit:
```bash
git add -A
git commit -m "fix(web): manual-verification fixes for credential onboarding flow"
```

---

## Self-Review Notes

- **Spec coverage:** §3.1 (3 endpoints + status extension) → Tasks 1-4; §3.2 (wizard, settings, header chip, api.ts, App.svelte) → Tasks 5-8; §3.3 (DhanPy flows covered: consent, PIN+TOTP, direct token, data token) → Tasks 2,3,4,6; non-negotiables enforced per task via Global Constraints. No gaps.
- **Type consistency:** `_extract_exp_from_token` / `is_data_token_valid` defined Task 1, consumed Tasks 2/4; `AuthStatus`/`SaveResult`/`ConsentStart`/`ValidationResult` defined Task 5, consumed Tasks 6-8 with identical names; `setup_complete` field retained in status model (used by nothing frontend-side, kept for contract stability).
- **Placeholder scan:** no TBD/TODO; every code step contains full code; test names match run commands.
- **Dependency order:** Task 1 → 2/3/4 (backend); 5 → 6/7 → 8 → 9 (frontend). Tasks 2-4 can run after Task 1 in any order.
