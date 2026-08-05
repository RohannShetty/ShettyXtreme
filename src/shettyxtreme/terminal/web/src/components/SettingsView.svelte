<script lang="ts">
  import { onMount } from "svelte";
  import { authStatus, logoutAuth, reauth, type AuthStatus } from "../lib/api";
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent } from "$lib/components/ui/card";

  let status: AuthStatus | null = $state(null);
  let error = $state("");
  let busy = $state(false);
  let rootEl: HTMLDivElement | undefined;

  onMount(() => {
    load();
    // Enter anywhere on the surface (nothing focused) triggers the primary
    // action — the operator-grade "save" of this view. Tab naturally walks
    // the buttons.
    window.addEventListener("keydown", onGlobalKeydown);
    return () => window.removeEventListener("keydown", onGlobalKeydown);
  });

  function onGlobalKeydown(event: KeyboardEvent): void {
    if (event.key !== "Enter") return;
    const t = event.target as HTMLElement | null;
    if (t && (t.tagName === "BUTTON" || t.tagName === "A" || t.tagName === "INPUT" || t.tagName === "TEXTAREA")) {
      return;
    }
    if (t && rootEl?.contains(t)) {
      event.preventDefault();
      void onReauth();
    }
  }

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
      const auth = await reauth();
      window.location.href = auth.login_url;
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

  // Token state is a semantic status chip (DESIGN.md §4): VALID = success,
  // EXPIRED = warning, NOT SET = neutral.
  function tokenVariant(s: AuthStatus | null): "success" | "warning" | "secondary" {
    if (!s) return "secondary";
    if (s.token_valid) return "success";
    if (s.has_token) return "warning";
    return "secondary";
  }

  function tokenLabel(s: AuthStatus | null): string {
    if (!s) return "—";
    return s.token_valid ? "VALID" : s.has_token ? "EXPIRED" : "NOT SET";
  }
</script>

<div class="settings" bind:this={rootEl} aria-label="Settings">
  <h1 class="heading">Settings</h1>

  {#if status}
    <Card>
      <CardContent class="flex flex-col gap-2.5">
        <div class="row">
          <span class="label">Broker</span>
          <span class="value mono">{status.broker || "fyers"}</span>
        </div>
        <div class="row">
          <span class="label">Client</span>
          <span class="value mono">{status.client_name || status.client_id || "—"}</span>
        </div>
        <div class="row">
          <span class="label">Token</span>
          <Badge variant={tokenVariant(status)}>{tokenLabel(status)}</Badge>
        </div>
        <div class="row">
          <span class="label">Token expiry</span>
          <span class="value mono">{fmtExpiry(status.token_expiry)}</span>
        </div>
        <div class="actions">
          <Button onclick={onReauth} disabled={busy}>Re-auth (open Fyers login)</Button>
          <Button variant="danger" onclick={onLogout} disabled={busy}>Logout</Button>
        </div>
      </CardContent>
    </Card>
  {:else}
    <p class="caption">Could not load credential status — is the terminal running?</p>
  {/if}

  {#if error}
    <p class="err-text">{error}</p>
  {/if}

  <a class="back" href="#/">← Back to terminal</a>
</div>

<style>
  .settings {
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
  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 16px;
    padding: 6px 0;
    border-bottom: 1px solid var(--hairline);
  }
  .row:last-of-type {
    border-bottom: none;
  }
  .label {
    color: var(--muted);
    font-size: 12px;
  }
  .value {
    color: var(--ink);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }
  .actions {
    display: flex;
    gap: 8px;
    margin-top: 8px;
  }
  .caption {
    color: var(--muted);
    font-size: 12px;
  }
  .err-text {
    color: var(--danger);
    font-size: 12px;
  }
  .back {
    display: inline-block;
    margin-top: 12px;
    color: var(--accent);
    text-decoration: none;
    font-size: 12px;
  }
  .back:hover {
    color: var(--accent-active);
    text-decoration: underline;
  }
</style>
