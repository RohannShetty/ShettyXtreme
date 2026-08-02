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
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import {
    Tabs,
    TabsContent,
    TabsList,
    TabsTrigger,
  } from "$lib/components/ui/tabs";

  let { query = null }: { query?: URLSearchParams | null } = $props();

  let status: AuthStatus | null = $state(null);
  let tab = $state("creds");
  let error = $state("");
  let busy = $state(false);

  // Method 1: app credentials
  let clientId = $state("");
  let apiKey = $state("");
  let apiSecret = $state("");
  let testResult: ValidationResult | null = $state(null);

  // Method 2: direct token
  let directToken = $state("");

  // Method 3: PIN + TOTP
  let ptClientId = $state("");
  let pin = $state("");
  let totp = $state("");

  // Data token (advanced)
  let dataToken = $state("");

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

  <Tabs value={tab} onValueChange={(v) => (tab = v)}>
    <TabsList class="w-full">
      <TabsTrigger value="creds">App credentials</TabsTrigger>
      <TabsTrigger value="token">Direct token</TabsTrigger>
      <TabsTrigger value="pintotp">PIN + TOTP</TabsTrigger>
    </TabsList>

    <TabsContent value="creds">
      <div class="card">
        <p class="caption">From the Dhan Developer Portal — one app with Trading + Market Data capabilities.</p>
        <label class="field">
          <span class="caption">Client ID</span>
          <Input class="mono" bind:value={clientId} placeholder="DHANCLIENTID" />
        </label>
        <label class="field">
          <span class="caption">API Key</span>
          <Input class="mono" type="password" bind:value={apiKey} placeholder="api_key" />
        </label>
        <label class="field">
          <span class="caption">API Secret</span>
          <Input class="mono" type="password" bind:value={apiSecret} placeholder="api_secret" />
        </label>
        <div class="actions">
          <Button variant="secondary" onclick={onTest} disabled={busy || !apiKey || !apiSecret}>Test</Button>
          <Button onclick={onConnect} disabled={busy || !apiKey || !apiSecret}>Connect Dhan</Button>
        </div>
        {#if testResult}
          <p class={testResult.valid ? "ok-text" : "err-text"}>{testResult.message}</p>
        {/if}
      </div>
    </TabsContent>

    <TabsContent value="token">
      <div class="card">
        <p class="caption">Paste an existing Dhan access token (JWT). Client ID and expiry are read from it automatically.</p>
        <label class="field">
          <span class="caption">Access Token</span>
          <Input class="mono" type="password" bind:value={directToken} placeholder="eyJhbGciOi…" />
        </label>
        <div class="actions">
          <Button onclick={onSaveDirect} disabled={busy || !directToken.trim()}>Save token</Button>
        </div>
      </div>
    </TabsContent>

    <TabsContent value="pintotp">
      <div class="card">
        <p class="caption">Generate an access token from your Dhan client ID + trading PIN + TOTP.</p>
        <label class="field">
          <span class="caption">Client ID</span>
          <Input class="mono" bind:value={ptClientId} placeholder="DHANCLIENTID" />
        </label>
        <label class="field">
          <span class="caption">PIN</span>
          <Input class="mono" type="password" bind:value={pin} placeholder="4-digit trading PIN" />
        </label>
        <label class="field">
          <span class="caption">TOTP</span>
          <Input class="mono" bind:value={totp} placeholder="6-digit authenticator code" />
        </label>
        <div class="actions">
          <Button onclick={onSavePinTotp} disabled={busy || !ptClientId || !pin || !totp}>Generate & save</Button>
        </div>
      </div>
    </TabsContent>
  </Tabs>

  <details class="advanced">
    <summary class="caption">Data token (optional — only if your app lacks Market Data entitlement)</summary>
    <label class="field">
      <span class="caption">Data Access Token</span>
      <Input class="mono" type="password" bind:value={dataToken} placeholder="separate data-entitlement token" />
    </label>
    <Button variant="secondary" onclick={onSaveDataToken} disabled={busy || !dataToken.trim()}>Save data token</Button>
  </details>

  {#if error}
    <p class="err-text">{error}</p>
  {/if}

  <a href="#/">← Back to terminal</a>
</div>

<style>
  .setup {
    max-width: 560px;
    margin: 32px auto;
    padding: 0 16px;
  }
  .heading {
    font-size: 14px;
    font-weight: 600;
    color: var(--ink);
    margin-bottom: 12px;
  }
  .card {
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-radius: 6px;
    padding: 16px;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .field {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .actions {
    display: flex;
    gap: 8px;
  }
  .advanced {
    margin-top: 12px;
  }
  .advanced summary {
    cursor: pointer;
    color: var(--muted);
  }
  .advanced .field {
    margin: 8px 0;
  }
  .banner {
    padding: 8px 12px;
    border-radius: 4px;
    font-size: 12px;
    margin-bottom: 12px;
  }
  .banner-ok {
    background: color-mix(in srgb, var(--success) 14%, transparent);
    border: 1px solid var(--success);
  }
  .banner-warn {
    background: color-mix(in srgb, var(--warning) 14%, transparent);
    border: 1px solid var(--warning);
  }
  .banner-err {
    background: color-mix(in srgb, var(--danger) 14%, transparent);
    border: 1px solid var(--danger);
  }
  .ok-text {
    color: var(--success);
    font-size: 12px;
    margin: 0;
  }
  .err-text {
    color: var(--danger);
    font-size: 12px;
    margin: 0;
  }
  .caption {
    color: var(--muted);
    font-size: 12px;
    margin: 0;
  }
</style>
