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
