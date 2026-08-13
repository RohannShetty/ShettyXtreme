<script lang="ts">
  import { onMount } from "svelte";
  import { toast } from "svelte-sonner";
  import {
    authStatus,
    logoutAuth,
    reauth,
    getSettings,
    updateSettings,
    setTheme,
    setColorConvention,
    getScheduler,
    updateScheduler,
    type AuthStatus,
    type SettingsResponse,
    type SettingsScheduler,
  } from "../lib/api";
  import { applyTheme, type Theme } from "../lib/theme";
  import { applyColorConvention, type ColorConvention } from "../lib/color-convention";
  import { Badge } from "$lib/components/ui/badge";
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardHeader, CardTitle } from "$lib/components/ui/card";
  import { Input } from "$lib/components/ui/input";

  // ── Auth / credentials ──────────────────────────────────────────────────
  let status: AuthStatus | null = $state(null);
  let authError = $state("");
  let authBusy = $state(false);

  // ── Settings load ───────────────────────────────────────────────────────
  let settingsLoaded = $state(false);
  let loadError = $state("");

  // ── Risk limits form (strings: number inputs stay raw until saved) ─────
  let lossLimitStr = $state("");
  let maxPositionsStr = $state("");
  let riskError = $state("");
  let riskSaving = $state(false);

  // ── Theme ───────────────────────────────────────────────────────────────
  let theme: Theme = $state("dark");
  let themeError = $state("");
  let themeSaving = $state(false);

  // ── Color convention ───────────────────────────────────────────────────
  let colorConvention: ColorConvention = $state("international");
  let conventionError = $state("");
  let conventionSaving = $state(false);

  // ── Research scheduler form + live status ───────────────────────────────
  let schedEnabled = $state(false);
  let schedIntervalStr = $state("");
  let schedLenses = $state("");
  let schedTools = $state("");
  let schedStatus: SettingsScheduler | null = $state(null);
  let schedError = $state("");
  let schedSaving = $state(false);

  const LOSS_LIMIT_MAX = 10_000_000;
  const INTERVAL_MAX = 1440;
  const STATUS_POLL_MS = 15_000;

  let pollTimer: number | undefined;

  onMount(() => {
    void loadAll();
    // Live scheduler state (running / next_run_at / …) ticks on its own —
    // poll so the status block stays honest without a manual refresh.
    pollTimer = window.setInterval(() => void refreshScheduler(), STATUS_POLL_MS);
    return () => {
      if (pollTimer !== undefined) window.clearInterval(pollTimer);
    };
  });

  async function loadAll(): Promise<void> {
    try {
      status = await authStatus();
    } catch {
      status = null;
    }
    try {
      const s = await getSettings();
      applySettings(s);
      settingsLoaded = true;
    } catch (err) {
      loadError = err instanceof Error ? err.message : String(err);
    }
    await refreshScheduler();
  }

  /** Seed every form field from a full settings snapshot (GET / PUT /api/settings). */
  function applySettings(s: SettingsResponse): void {
    lossLimitStr = String(Math.abs(s.loss_limit));
    maxPositionsStr = String(s.max_positions);
    theme = s.theme;
    colorConvention = s.color_convention;
    const sch = s.scheduler;
    schedEnabled = sch.enabled;
    schedIntervalStr = String(sch.interval_minutes);
    schedLenses = (sch.lenses ?? []).join(", ");
    schedTools = (sch.tools ?? []).join(", ");
    schedStatus = sch;
  }

  async function refreshScheduler(): Promise<void> {
    try {
      schedStatus = await getScheduler();
    } catch {
      /* best-effort poll — keep the last known status */
    }
  }

  // ── Auth actions ────────────────────────────────────────────────────────
  async function onReauth(): Promise<void> {
    authError = "";
    authBusy = true;
    try {
      const auth = await reauth();
      window.location.href = auth.login_url;
    } catch (err) {
      authError = err instanceof Error ? err.message : String(err);
      authBusy = false;
    }
  }

  async function onLogout(): Promise<void> {
    authError = "";
    authBusy = true;
    try {
      await logoutAuth();
      status = null;
      await load();
    } catch (err) {
      authError = err instanceof Error ? err.message : String(err);
    } finally {
      authBusy = false;
    }
  }

  async function load(): Promise<void> {
    try {
      status = await authStatus();
    } catch {
      status = null;
    }
  }

  // ── Risk limits ─────────────────────────────────────────────────────────
  /** Client-side guard mirroring the backend spec; server 400s still surface. */
  function validateRisk(): string {
    const l = lossLimitStr.trim();
    const m = maxPositionsStr.trim();
    if (l === "") return "Daily loss limit is required";
    const loss = Number(l);
    if (!Number.isFinite(loss) || loss < 0) {
      return "Daily loss limit must be a positive amount";
    }
    if (loss > LOSS_LIMIT_MAX) {
      return "Daily loss limit cannot exceed ₹1,00,00,000";
    }
    if (m === "") return "Max positions is required";
    const pos = Number(m);
    if (!Number.isInteger(pos) || pos < 1 || pos > 100) {
      return "Max positions must be a whole number between 1 and 100";
    }
    return "";
  }

  async function onSaveRisk(): Promise<void> {
    riskError = "";
    const msg = validateRisk();
    if (msg) {
      riskError = msg;
      return;
    }
    riskSaving = true;
    try {
      const s = await updateSettings({
        loss_limit: -Math.abs(Number(lossLimitStr.trim())),
        max_positions: Math.trunc(Number(maxPositionsStr.trim())),
      });
      applySettings(s);
      toast.success("Risk limits saved — live in the risk engine");
    } catch (err) {
      riskError = err instanceof Error ? err.message : String(err);
    } finally {
      riskSaving = false;
    }
  }

  // ── Theme ───────────────────────────────────────────────────────────────
  async function onChangeTheme(next: Theme): Promise<void> {
    if (next === theme || themeSaving) return;
    const prev = theme;
    themeError = "";
    themeSaving = true;
    // Apply immediately locally (sx-theme in localStorage), then reconcile
    // with the server, which persists and broadcasts to WS clients.
    theme = next;
    applyTheme(next);
    try {
      const r = await setTheme(next);
      theme = r.theme;
      applyTheme(r.theme);
      toast.success(`Theme set to ${r.theme}`);
    } catch (err) {
      themeError = err instanceof Error ? err.message : String(err);
      theme = prev;
      applyTheme(prev);
    } finally {
      themeSaving = false;
    }
  }

  // ── Color convention ───────────────────────────────────────────────────
  async function onChangeConvention(next: ColorConvention): Promise<void> {
    if (next === colorConvention || conventionSaving) return;
    const prev = colorConvention;
    conventionError = "";
    conventionSaving = true;
    colorConvention = next;
    applyColorConvention(next);
    try {
      const r = await setColorConvention(next);
      colorConvention = r.color_convention;
      applyColorConvention(r.color_convention);
      toast.success(`Price colors set to ${r.color_convention}`);
    } catch (err) {
      conventionError = err instanceof Error ? err.message : String(err);
      colorConvention = prev;
      applyColorConvention(prev);
    } finally {
      conventionSaving = false;
    }
  }

  // ── Research scheduler ──────────────────────────────────────────────────
  function parseList(raw: string): string[] {
    return raw
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean);
  }

  function validateScheduler(): string {
    if (!schedEnabled) return ""; // a disabled scheduler is always saveable
    const i = schedIntervalStr.trim();
    if (i === "") return "Interval is required";
    const iv = Number(i);
    if (!Number.isFinite(iv) || iv <= 0) return "Interval must be a positive number";
    if (iv > INTERVAL_MAX) return "Interval cannot exceed 1440 minutes (24 h)";
    return "";
  }

  async function onSaveScheduler(): Promise<void> {
    schedError = "";
    const msg = validateScheduler();
    if (msg) {
      schedError = msg;
      return;
    }
    schedSaving = true;
    try {
      const sch = await updateScheduler({
        enabled: schedEnabled,
        interval_minutes: Number(schedIntervalStr.trim()),
        lenses: parseList(schedLenses),
        tools: parseList(schedTools),
      });
      // Re-seed from the server snapshot so persisted values are canonical.
      schedEnabled = sch.enabled;
      schedIntervalStr = String(sch.interval_minutes);
      schedLenses = (sch.lenses ?? []).join(", ");
      schedTools = (sch.tools ?? []).join(", ");
      schedStatus = sch;
      if (sch.enabled && !sch.running) {
        toast.warning("Scheduler saved — not running (DEEPSEEK_API_KEY not set)");
      } else {
        toast.success(sch.running ? "Scheduler is running" : "Scheduler config saved");
      }
    } catch (err) {
      schedError = err instanceof Error ? err.message : String(err);
    } finally {
      schedSaving = false;
    }
  }

  // ── Display helpers ─────────────────────────────────────────────────────
  function fmtTs(v: string | null): string {
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

  // Scheduler live state is a status chip: RUNNING = success, enabled-but-idle
  // = warning (honest: intent without a running loop), disabled = neutral.
  function schedVariant(): "success" | "warning" | "secondary" {
    const s = schedStatus;
    if (!s) return "secondary";
    if (s.running) return "success";
    if (s.enabled) return "warning";
    return "secondary";
  }

  function schedLabel(): string {
    const s = schedStatus;
    if (!s) return "—";
    if (s.running) return "RUNNING";
    if (s.enabled) return "NOT RUNNING";
    return "DISABLED";
  }
</script>

<div class="settings" aria-label="Settings">
  <h1 class="heading">Settings</h1>

  <Card>
    <CardHeader>
      <CardTitle>Broker credentials</CardTitle>
    </CardHeader>
    <CardContent class="flex flex-col gap-2.5">
      {#if status}
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
          <span class="value mono">{fmtTs(status.token_expiry)}</span>
        </div>
        <div class="actions">
          <Button onclick={onReauth} disabled={authBusy}>Re-auth (open Fyers login)</Button>
          <Button variant="danger" onclick={onLogout} disabled={authBusy}>Logout</Button>
        </div>
      {:else}
        <p class="caption">Could not load credential status — is the terminal running?</p>
      {/if}
      {#if authError}
        <p class="err-text" role="alert">{authError}</p>
      {/if}
    </CardContent>
  </Card>

  {#if loadError}
    <p class="err-text" role="alert">Could not load settings: {loadError}</p>
  {:else if !settingsLoaded}
    <p class="caption">Loading settings…</p>
  {:else}
    <!-- Risk limits — caps are consumed live by the risk engine (no restart). -->
    <Card>
      <CardHeader>
        <CardTitle>Risk limits</CardTitle>
        <p class="card-desc">Applied live by the risk engine — no restart needed.</p>
      </CardHeader>
      <CardContent>
        <form
          onsubmit={(e) => {
            e.preventDefault();
            void onSaveRisk();
          }}
        >
          <div class="field">
            <label class="flabel" for="loss-limit">Daily loss limit</label>
            <div class="prefix-wrap">
              <span class="prefix mono" aria-hidden="true">−</span>
              <Input
                id="loss-limit"
                class="mono pl-6"
                type="number"
                min="0"
                max={String(LOSS_LIMIT_MAX)}
                step="500"
                bind:value={lossLimitStr}
                placeholder="5000"
              />
            </div>
            <p class="hint">Positive amount — stored as a negative cap (max ₹1,00,00,000).</p>
          </div>
          <div class="field">
            <label class="flabel" for="max-positions">Max concurrent positions</label>
            <Input
              id="max-positions"
              class="mono"
              type="number"
              min="1"
              max="100"
              step="1"
              bind:value={maxPositionsStr}
              placeholder="5"
            />
            <p class="hint">1–100. The engine rejects new positions beyond this cap.</p>
          </div>
          {#if riskError}
            <p class="err-text" role="alert">{riskError}</p>
          {/if}
          <div class="actions">
            <Button type="submit" disabled={riskSaving}>
              {riskSaving ? "Saving…" : "Save risk limits"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>

    <!-- Theme — persisted on the terminal, broadcast to WS clients. -->
    <Card>
      <CardHeader>
        <CardTitle>Theme</CardTitle>
        <p class="card-desc">Persisted on the terminal and broadcast to connected clients.</p>
      </CardHeader>
      <CardContent>
        <div class="seg" role="radiogroup" aria-label="Theme">
          <button
            type="button"
            class="seg-btn"
            class:active={theme === "dark"}
            role="radio"
            aria-checked={theme === "dark"}
            onclick={() => void onChangeTheme("dark")}
            disabled={themeSaving}
          >
            Dark
          </button>
          <button
            type="button"
            class="seg-btn"
            class:active={theme === "light"}
            role="radio"
            aria-checked={theme === "light"}
            onclick={() => void onChangeTheme("light")}
            disabled={themeSaving}
          >
            Light
          </button>
        </div>
        {#if themeError}
          <p class="err-text" role="alert">{themeError}</p>
        {/if}
      </CardContent>
    </Card>

    <!-- Price colors — convention toggle (Indian / International). -->
    <Card>
      <CardHeader>
        <CardTitle>Price colors</CardTitle>
        <p class="card-desc">Indian (red=up, green=down) or International (green=up, red=down).</p>
      </CardHeader>
      <CardContent>
        <div class="seg" role="radiogroup" aria-label="Price color convention">
          <button
            type="button"
            class="seg-btn"
            class:active={colorConvention === "international"}
            role="radio"
            aria-checked={colorConvention === "international"}
            onclick={() => void onChangeConvention("international")}
            disabled={conventionSaving}
          >
            International
          </button>
          <button
            type="button"
            class="seg-btn"
            class:active={colorConvention === "indian"}
            role="radio"
            aria-checked={colorConvention === "indian"}
            onclick={() => void onChangeConvention("indian")}
            disabled={conventionSaving}
          >
            Indian
          </button>
        </div>
        {#if conventionError}
          <p class="err-text" role="alert">{conventionError}</p>
        {/if}
      </CardContent>
    </Card>

    <!-- Research scheduler — config + honest live status. -->
    <Card>
      <CardHeader>
        <CardTitle>Research scheduler</CardTitle>
        <p class="card-desc">Runs periodic research briefs over the configured lenses and tools.</p>
      </CardHeader>
      <CardContent>
        <form
          onsubmit={(e) => {
            e.preventDefault();
            void onSaveScheduler();
          }}
        >
          <div class="row">
            <span class="label">Enabled</span>
            <button
              type="button"
              role="switch"
              aria-checked={schedEnabled}
              aria-label="Research scheduler enabled"
              class="switch"
              class:on={schedEnabled}
              onclick={() => (schedEnabled = !schedEnabled)}
            >
              <span class="switch-knob"></span>
            </button>
          </div>

          {#if schedEnabled}
            <div class="field">
              <label class="flabel" for="sched-interval">Interval (minutes)</label>
              <Input
                id="sched-interval"
                class="mono"
                type="number"
                min="1"
                max="1440"
                step="5"
                bind:value={schedIntervalStr}
                placeholder="60"
              />
              <p class="hint">1–1440 minutes (24 h).</p>
            </div>
            <div class="field">
              <label class="flabel" for="sched-lenses">Lenses</label>
              <Input
                id="sched-lenses"
                class="mono"
                type="text"
                bind:value={schedLenses}
                placeholder="macro, news, technical"
              />
              <p class="hint">Comma-separated lens names.</p>
            </div>
            <div class="field">
              <label class="flabel" for="sched-tools">Tools</label>
              <Input
                id="sched-tools"
                class="mono"
                type="text"
                bind:value={schedTools}
                placeholder="search, fetch_page"
              />
              <p class="hint">Comma-separated tool names.</p>
            </div>
          {/if}

          {#if schedError}
            <p class="err-text" role="alert">{schedError}</p>
          {/if}
          <div class="actions">
            <Button type="submit" disabled={schedSaving}>
              {schedSaving ? "Saving…" : "Save scheduler"}
            </Button>
          </div>

          {#if schedStatus}
            <div class="divider"></div>
            <div class="status-block">
              <div class="row">
                <span class="label">Status</span>
                <Badge variant={schedVariant()}>{schedLabel()}</Badge>
              </div>
              <div class="row">
                <span class="label">Next run</span>
                <span class="value mono">{fmtTs(schedStatus.next_run_at)}</span>
              </div>
              <div class="row">
                <span class="label">Last run</span>
                <span class="value mono">{fmtTs(schedStatus.last_run_at)}</span>
              </div>
              {#if schedStatus.last_result}
                <div class="row result-row">
                  <span class="label">Last result</span>
                  <span class="value mono result-text">{schedStatus.last_result}</span>
                </div>
              {/if}
            </div>
          {/if}

          {#if schedStatus && schedStatus.enabled && !schedStatus.running}
            <p class="notice warn">
              Enabled but not running — set <span class="mono">DEEPSEEK_API_KEY</span> on the
              terminal process to activate.
            </p>
          {/if}
        </form>
      </CardContent>
    </Card>
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
  .card-desc {
    color: var(--muted);
    font-size: 12px;
    margin: 2px 0 0;
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
  .field {
    margin-bottom: 12px;
  }
  .flabel {
    display: block;
    color: var(--muted);
    font-size: 11px;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 6px;
  }
  .hint {
    color: var(--faint);
    font-size: 11px;
    margin-top: 4px;
  }
  /* Daily-loss-limit field: fixed "−" adornment, operator types a magnitude. */
  .prefix-wrap {
    position: relative;
  }
  .prefix {
    position: absolute;
    left: 10px;
    top: 50%;
    transform: translateY(-50%);
    color: var(--muted);
    font-size: 13px;
    pointer-events: none;
  }
  /* Segmented theme control — active segment carries the single accent. */
  .seg {
    display: inline-flex;
    border: 1px solid var(--hairline);
    border-radius: 4px;
    overflow: hidden;
  }
  .seg-btn {
    padding: 6px 20px;
    font-size: 12px;
    font-weight: 600;
    color: var(--muted);
    background: transparent;
    border: none;
    border-right: 1px solid var(--hairline);
    cursor: pointer;
    transition:
      background-color 100ms,
      color 100ms;
  }
  .seg-btn:last-child {
    border-right: none;
  }
  .seg-btn:hover {
    color: var(--ink);
    background: var(--row-hover);
  }
  .seg-btn.active {
    color: var(--accent);
    background: var(--surface-elevated);
  }
  .seg-btn:disabled {
    cursor: default;
    opacity: 0.5;
  }
  .seg-btn:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: -2px;
  }
  /* Toggle / switch per DESIGN §4: off = hairline track + muted knob,
     on = accent track + white knob; transitions ≤ 120ms. */
  .switch {
    position: relative;
    width: 36px;
    height: 20px;
    border-radius: 10px;
    background: var(--hairline-strong);
    border: none;
    padding: 0;
    cursor: pointer;
    flex: none;
    transition: background-color 100ms;
  }
  .switch-knob {
    position: absolute;
    top: 2px;
    left: 2px;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    background: var(--muted);
    transition:
      transform 100ms,
      background-color 100ms;
  }
  .switch.on {
    background: var(--accent);
  }
  .switch.on .switch-knob {
    background: #fff;
    transform: translateX(16px);
  }
  .switch:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  .divider {
    height: 1px;
    background: var(--hairline);
    margin: 16px 0 8px;
  }
  .result-row {
    align-items: flex-start;
  }
  .result-text {
    text-align: right;
    white-space: normal;
    word-break: break-word;
    max-width: 62%;
  }
  /* Alert-bar treatment (DESIGN §4): status token at ~10% on the card. */
  .notice {
    margin-top: 12px;
    font-size: 12px;
    line-height: 18px;
    padding: 6px 10px;
    border: 1px solid;
    border-radius: 4px;
  }
  .notice.warn {
    color: var(--warning);
    border-color: var(--warning);
    background: color-mix(in srgb, var(--warning) 10%, transparent);
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
