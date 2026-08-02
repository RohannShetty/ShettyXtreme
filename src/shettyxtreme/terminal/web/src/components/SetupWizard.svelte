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
