<script lang="ts">
  import { onMount } from "svelte";
  import {
    authStatus,
    saveCredentials,
    startAuth,
    testCredentials,
    type AuthStatus,
    type ValidationResult,
  } from "../lib/api";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";

  let { query = null }: { query?: URLSearchParams | null } = $props();

  let status: AuthStatus | null = $state(null);
  let error = $state("");
  let busy = $state(false);

  // Fyers app credentials
  let appId = $state("");
  let secretId = $state("");
  let testResult: ValidationResult | null = $state(null);

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
      testResult = await testCredentials(appId.trim(), secretId.trim());
    });
  }

  function onConnect(): void {
    void run(async () => {
      await saveCredentials(appId.trim(), secretId.trim());
      const auth = await startAuth();
      window.location.href = auth.login_url;
    });
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

  <div class="card">
    <p class="caption">
      From the Fyers Developer Portal — create an app with Trading API enabled and set the
      redirect URL to <code>{location.origin}/auth/fyers/callback</code>.
    </p>
    <label class="field">
      <span class="caption">App ID</span>
      <Input class="mono" bind:value={appId} placeholder="APP_ID" />
    </label>
    <label class="field">
      <span class="caption">Secret ID</span>
      <Input class="mono" type="password" bind:value={secretId} placeholder="secret_id" />
    </label>
    <div class="actions">
      <Button variant="secondary" onclick={onTest} disabled={busy || !appId.trim() || !secretId.trim()}>Test</Button>
      <Button onclick={onConnect} disabled={busy || !appId.trim() || !secretId.trim()}>Connect Fyers</Button>
    </div>
    {#if testResult}
      <p class={testResult.valid ? "ok-text" : "err-text"}>{testResult.message}</p>
    {/if}
  </div>

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
  .caption code {
    font-size: 11px;
  }
</style>
