<script lang="ts">
  import { onMount } from "svelte";
  import { authStatus, get, type AuthStatus } from "../lib/api";
  import { applyTheme, getTheme, type Theme } from "../lib/theme";
  import { selectedSymbol } from "../lib/selection.svelte.ts";
  import { onMessage, onConnectionChange } from "../lib/ws";
  import {
    connectionStore,
    applyServerState,
    applyHealthState,
    applyLocalWsState,
  } from "../lib/connection.svelte.ts";
  import { Button } from "$lib/components/ui/button";
  import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
  } from "$lib/components/ui/tooltip";
  import { FileText, Moon, Sun } from "@lucide/svelte";
  import KillSwitch from "./KillSwitch.svelte";
  import ModeSwitcher from "./ModeSwitcher.svelte";
  import ShortcutsDialog from "./ShortcutsDialog.svelte";

  type ComponentHealth = {
    name: string;
    status: string;
    message: string;
  };

  type HealthResponse = {
    components: ComponentHealth[];
    overall: string;
    state: string;
    detail: string;
  };

  type Session = {
    status: string;
    current_time_ist: string;
    next_event: string;
  };

  type Tick = {
    symbol: string;
    ltp: number;
    change_pct: number;
    volume: number;
  };

  let {
    drawerOpen = $bindable(false),
    onDrawer = () => {},
  }: {
    drawerOpen?: boolean;
    onDrawer?: (event: { open: boolean }) => void;
  } = $props();

  let health: HealthResponse | null = $state(null);
  let session: Session | null = $state(null);
  let credStatus: AuthStatus | null = $state(null);
  let theme: Theme = $state(getTheme());
  let refreshTimer: number | undefined;

  // P1-2.4: derive pip state from the unified connection store.
  let pipState = $derived(connectionStore.state);
  let pipDetail = $derived(connectionStore.detail);

  // --- LTP hero (DESIGN §5 header anatomy, §3.1 number-xl) ---
  // The selection store carries {symbol, exchange}, so the hero reads the
  // exchange straight from the selection — no watchlist REST round-trip.
  let selection = $derived(selectedSymbol);
  let selected = $derived(selection.symbol);
  let tickBySymbol = $state<Record<string, Tick>>({});
  let flashDir = $state<"" | "up" | "down">("");
  let flashTimer: number | undefined;

  let tick = $derived(selected ? tickBySymbol[selected] : undefined);
  // Backward-compatible: a legacy/empty exchange falls back to NSE.
  let exchange = $derived(selected ? (selection.exchange || "NSE") : "");
  let changePct = $derived(tick?.change_pct ?? null);
  let ltp = $derived(tick?.ltp ?? null);
  // Price convention: green=up/red=down (international, default) or
  // red=up/green=down (indian, opt-in). Flash toggles color weight
  // (price-up-strong), never font size/weight — no jitter (DESIGN §3.2).
  let ltpColor = $derived(
    flashDir === "up"
      ? "price-up-strong"
      : flashDir === "down"
        ? "price-down-strong"
        : changePct !== null && changePct > 0
          ? "price-up"
          : changePct !== null && changePct < 0
            ? "price-down"
            : "price-flat",
  );
  let ltpFlash = $derived(
    flashDir === "up" ? "flash-up" : flashDir === "down" ? "flash-down" : "",
  );

  function toggleTheme(): void {
    theme = theme === "dark" ? "light" : "dark";
    applyTheme(theme);
  }

  onMount(() => {
    load();
    loadCreds();
    const offTick = onMessage("tick", applyTick);
    // P1-2.4: subscribe to server-pushed connection state transitions.
    const offConn = onMessage("connection", (data: unknown) => {
      const d = data as { state?: string; detail?: string };
      if (d && typeof d.state === "string") {
        applyServerState(d.state, d.detail ?? "");
      }
    });
    // P1-2.4: subscribe to browser-WS open/close events.
    const offWsChange = onConnectionChange((wsState: string) => {
      applyLocalWsState(wsState === "open");
    });
    refreshTimer = window.setInterval(() => {
      load();
      loadCreds();
    }, 30_000);
    return () => {
      offTick();
      offConn();
      offWsChange();
      if (flashTimer !== undefined) window.clearTimeout(flashTimer);
      if (refreshTimer !== undefined) window.clearInterval(refreshTimer);
    };
  });

  async function load(): Promise<void> {
    try {
      const [h, s] = await Promise.all([
        get<HealthResponse>("/api/health"),
        get<Session>("/api/health/session"),
      ]);
      health = h;
      session = s;
      // P1-2.4: feed REST health state into the connection store as fallback.
      if (h.state) {
        applyHealthState(h.state, h.detail ?? "");
      }
    } catch {
      /* header degrades silently — panels show their own errors */
    }
  }

  async function loadCreds(): Promise<void> {
    try {
      credStatus = await authStatus();
    } catch {
      credStatus = null;
    }
  }

  // Capture live ticks so the hero tracks the selected symbol in real time.
  // Direction is the tick-vs-previous-tick move; the persistent color comes
  // from change_pct (the session direction), matching the watchlist.
  function applyTick(data: unknown): void {
    const t = data as Partial<Tick>;
    if (!t || typeof t.symbol !== "string" || t.symbol === "") return;
    const prev = tickBySymbol[t.symbol];
    const ltpVal = typeof t.ltp === "number" ? t.ltp : prev?.ltp ?? 0;
    tickBySymbol[t.symbol] = {
      symbol: t.symbol,
      ltp: ltpVal,
      change_pct:
        typeof t.change_pct === "number" ? t.change_pct : prev?.change_pct ?? 0,
      volume: typeof t.volume === "number" ? t.volume : prev?.volume ?? 0,
    };
    if (prev !== undefined && ltpVal !== prev.ltp) {
      flashDir = ltpVal > prev.ltp ? "up" : "down";
      if (flashTimer !== undefined) window.clearTimeout(flashTimer);
      flashTimer = window.setTimeout(() => (flashDir = ""), 150);
    }
  }

  function fmtLtp(value: number | null): string {
    if (value === null || !isFinite(value)) return "—";
    return value.toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  // P1-2.4: pip state is now derived from the unified connection store
  // (connection.ts).  The old pipState()/statusRank()/brokerComponents()
  // local derivation has been removed — the store is the single source
  // of truth, fed by server-pushed "connection" broadcasts and the
  // /api/health REST fallback.

  function pipLabel(state: string): string {
    switch (state) {
      case "live":
        return "LIVE";
      case "stale":
        return "STALE";
      case "connecting":
        return "CONNECTING";
      case "disconnected":
        return "DISCONNECTED";
      case "expired":
        return "EXPIRED";
      default:
        return "…";
    }
  }

  function sessionText(status: string): string {
    return String(status).toUpperCase().replace("_", " ");
  }

  function entitlementMessage(): string {
    if (!health) return "";
    const adapter = health.components.find(
      (c) => c.name === "data_adapter" || c.name === "dhan_data",
    );
    const msg = adapter?.message ?? "";
    return msg.includes("entitlement") || msg.includes("(806)") ? msg : "";
  }

  function toggleDrawer(): void {
    onDrawer({ open: !drawerOpen });
  }
</script>

<header class="head">
  <!-- Two-row fallback (roadmap #7): .head-status + .head-actions are
       display:contents on wide screens (byte-identical single row, order
       pinned below), and become two stacked flex rows on <1024px so nothing
       clips. Row 1 = status cluster (logo, LTP hero, mode, connection pip,
       entitlement chip, market hours, credential chip); row 2 = action
       cluster (kill switch, theme, shortcuts, logs drawer), right-aligned. -->
  <div class="head-status">
    <div class="brand">
      <span class="logo">SX</span>
      <span class="title">SHETTYXTREME TERMINAL</span>
    </div>

    <div
      class="ltp-hero"
      class:empty={!selected}
      title={selected ? `${selected} · ${exchange} · LTP ${fmtLtp(ltp)}` : "Select a symbol in the watchlist to pin its live price here"}
      aria-label={selected ? `${selected} ${exchange}, last traded price ${fmtLtp(ltp)}` : "No symbol selected"}
    >
      <div class="ltp-id">
        <span class="ltp-symbol ticker">{selected || "—"}</span>
        <span class="ltp-exch mono">{selected ? exchange : "NO SELECTION"}</span>
      </div>
      <span class="num ltp-value {ltpColor} {ltpFlash}">{fmtLtp(ltp)}</span>
      {#if selected && changePct !== null}
        <span class="num ltp-chg {ltpColor}">
          {changePct > 0 ? "+" : ""}{changePct.toFixed(2)}%
        </span>
      {/if}
    </div>

    <span class="head-mode"><ModeSwitcher /></span>

    <div class="health">
      <span
        class="pip pip-{pipState}"
        title={pipDetail}
        aria-label="Connection status: {pipLabel(pipState)}"
      >
        <span class="pip-dot" aria-hidden="true"></span>
        <span class="pip-label">{pipLabel(pipState)}</span>
      </span>
    </div>

    {#if entitlementMessage()}
      <span class="ent-chip" title={entitlementMessage()}>{entitlementMessage()}</span>
    {/if}

    <div class="session">
      {#if session}
        <span class="session-status">{sessionText(session.status)}</span>
        <span class="mono session-time">{session.current_time_ist?.slice(11, 16) ?? ""}</span>
      {/if}
    </div>

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
        <a class="cred-chip mute" href="#/setup" title="Set up Fyers credentials">
          <span class="dot"></span>SETUP
        </a>
      {/if}
    {/if}
  </div>

  <div class="head-actions">
    <span class="head-kill"><KillSwitch /></span>

    <span class="head-action">
      <Tooltip>
        <TooltipTrigger>
          <Button
            variant="ghost"
            size="icon"
            class="text-muted-foreground hover:text-accent-active"
            onclick={toggleTheme}
            aria-label="Toggle light or dark theme"
          >
            <span class="relative inline-flex size-4" aria-hidden="true">
              <Sun
                class="size-4 transition-[opacity,filter,scale] duration-300 ease-[cubic-bezier(0.2,0,0,1)] {theme === "dark" ? "opacity-100 scale-100 blur-0" : "opacity-0 scale-[0.25] blur-[4px]"}"
              />
              <Moon
                class="absolute inset-0 size-4 transition-[opacity,filter,scale] duration-300 ease-[cubic-bezier(0.2,0,0,1)] {theme === "dark" ? "opacity-0 scale-[0.25] blur-[4px]" : "opacity-100 scale-100 blur-0"}"
              />
            </span>
          </Button>
        </TooltipTrigger>
        <TooltipContent>Toggle theme</TooltipContent>
      </Tooltip>
    </span>

    <span class="head-action">
      <ShortcutsDialog />
    </span>

    <span class="head-action">
      <Tooltip>
        <TooltipTrigger>
          <Button
            variant="ghost"
            size="icon"
            class={drawerOpen
              ? "border border-accent-disabled text-accent-active hover:text-accent-active"
              : "text-muted-foreground hover:text-accent-active"}
            onclick={toggleDrawer}
            aria-label="Toggle logs drawer"
            aria-pressed={drawerOpen}
          >
            <FileText class="size-4" />
          </Button>
        </TooltipTrigger>
        <TooltipContent>Toggle logs drawer</TooltipContent>
      </Tooltip>
    </span>
  </div>
</header>

<style>
  .head {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 4px 12px;
    background: var(--canvas-raised);
    border-bottom: 1px solid var(--hairline);
    height: 44px;
    flex: none;
    overflow: hidden;
  }
  /* Two-row fallback (roadmap #7): on wide screens both clusters collapse
     into .head's single flex row via display:contents — their children become
     .head's direct flex items, and the explicit order values below pin the
     legacy interleave (brand, hero, mode, KILL, pip, ent, session, cred,
     then the three action toggles) so the ≥1024px layout is unchanged.
     On <1024px the clusters stop being display:contents and become two
     stacked full-width flex rows (see the media query at the bottom). */
  .head-status,
  .head-actions {
    display: contents;
  }
  .brand {
    order: 1;
    display: flex;
    align-items: center;
    gap: 8px;
    margin-right: 4px;
    min-width: 0;
  }
  .ltp-hero {
    order: 2;
  }
  .head-mode {
    order: 3;
    display: inline-flex;
    align-items: center;
  }
  .head-kill {
    order: 4;
    display: inline-flex;
    align-items: center;
  }
  .health {
    order: 5;
  }
  .ent-chip {
    order: 6;
  }
  .session {
    order: 7;
  }
  .cred-chip {
    order: 8;
  }
  .head-action {
    order: 9;
    display: inline-flex;
    align-items: center;
  }
  .logo {
    background: var(--accent);
    color: var(--on-accent);
    font-weight: 800;
    font-size: 11px;
    border-radius: 4px;
    padding: 2px 5px;
    flex: none;
  }
  .title {
    color: var(--ink);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.08em;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 0 1 auto;
    min-width: 0;
  }
  /* LTP hero — selected symbol + exchange + number-xl live price (DESIGN §5). */
  .ltp-hero {
    display: flex;
    align-items: center;
    gap: 10px;
    flex: none;
    padding: 0 12px;
    margin-left: 2px;
    border-left: 1px solid var(--hairline);
    border-right: 1px solid var(--hairline);
    min-height: 0;
  }
  .ltp-id {
    display: flex;
    flex-direction: column;
    gap: 1px;
    min-width: 0;
  }
  .ltp-symbol {
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 0.02em;
    color: var(--ink);
    white-space: nowrap;
  }
  .ltp-exch {
    font-size: 10px;
    letter-spacing: 0.06em;
    color: var(--faint);
    white-space: nowrap;
  }
  .ltp-value {
    font-size: 28px;
    font-weight: 700;
    line-height: 32px;
    letter-spacing: -0.01em;
    white-space: nowrap;
  }
  .ltp-chg {
    font-size: 11px;
    font-weight: 600;
    white-space: nowrap;
  }
  .price-flat {
    color: var(--ink);
  }
  .ltp-hero .price-up-strong {
    color: var(--price-up-strong);
  }
  .ltp-hero .price-down-strong {
    color: var(--price-down-strong);
  }
  .ltp-hero.empty .ltp-symbol,
  .ltp-hero.empty .ltp-value {
    color: var(--faint);
  }
  .health {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-left: auto;
    overflow: hidden;
  }
  .pip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    white-space: nowrap;
    text-transform: uppercase;
  }
  .pip-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex: none;
  }
  .pip-live .pip-dot {
    background: var(--success);
    animation: pip-pulse 1.2s ease-in-out infinite;
  }
  .pip-live .pip-label {
    color: var(--success);
  }
  .pip-stale .pip-dot {
    background: var(--warning);
  }
  .pip-stale .pip-label {
    color: var(--warning);
  }
  .pip-connecting .pip-dot {
    background: var(--warning);
    animation: pip-pulse 1.2s ease-in-out infinite;
  }
  .pip-connecting .pip-label {
    color: var(--warning);
  }
  .pip-disconnected .pip-dot {
    background: var(--danger);
  }
  .pip-disconnected .pip-label {
    color: var(--danger);
  }
  .pip-expired .pip-dot {
    background: var(--danger);
  }
  .pip-expired .pip-label {
    color: var(--danger);
    background: color-mix(in srgb, var(--danger) 14%, transparent);
    border: 1px solid var(--danger);
    border-radius: 2px;
    padding: 1px 5px;
  }
  .pip-unknown .pip-dot {
    background: var(--faint);
  }
  .pip-unknown .pip-label {
    color: var(--faint);
  }
  @keyframes pip-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.35;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .pip-live .pip-dot {
      animation: none;
    }
  }
  .ent-chip {
    background: color-mix(in srgb, var(--danger) 14%, transparent);
    border: 1px solid var(--danger);
    border-radius: 4px;
    color: var(--danger);
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.04em;
    padding: 3px 8px;
    white-space: nowrap;
    max-width: 300px;
    overflow: hidden;
    text-overflow: ellipsis;
    flex: 0 1 auto;
  }
  .cred-chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    border-radius: 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    padding: 3px 8px;
    white-space: nowrap;
    text-decoration: none;
    flex: none;
  }
  .cred-chip .dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
  }
  .cred-chip.ok {
    background: color-mix(in srgb, var(--success) 14%, transparent);
    border: 1px solid var(--success);
    color: var(--success);
  }
  .cred-chip.ok .dot {
    background: var(--success);
  }
  .cred-chip.warn {
    background: color-mix(in srgb, var(--warning) 14%, transparent);
    border: 1px solid var(--warning);
    color: var(--warning);
  }
  .cred-chip.warn .dot {
    background: var(--warning);
  }
  .cred-chip.mute {
    background: var(--surface-card);
    border: 1px solid var(--hairline-strong);
    color: var(--muted);
  }
  .cred-chip.mute .dot {
    background: var(--faint);
  }
  .cred-chip:hover {
    color: var(--accent-active);
    border-color: var(--accent);
  }
  .session {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .session-status {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--accent);
    white-space: nowrap;
  }
  .session-time {
    font-size: 11px;
    color: var(--faint);
  }

  /* Progressive header compaction — safety items (mode, kill switch, pip,
     market-hours, cred chip, toggles) never collapse (DESIGN §8); the
     decorative/secondary chrome yields first. */
  @media (max-width: 1360px) {
    .ltp-chg {
      display: none;
    }
  }
  @media (max-width: 1240px) {
    .title {
      display: none;
    }
  }
  @media (max-width: 1080px) {
    .head {
      gap: 8px;
      padding: 4px 8px;
    }
    .session-time {
      display: none;
    }
  }

  /* Two-row fallback (roadmap #7, DESIGN §8): below 1024px the single 44px
     row cannot hold brand + LTP hero + mode + pip + market hours + cred chip
     + kill switch + toggles without clipping, so the clusters stop being
     display:contents and become two full-width rows:
       row 1 = logo + mode + connection pip + market hours (+ status chips)
       row 2 = kill switch + theme + shortcuts + logs drawer, right-aligned
     Rows are 36px tall (not 32) because DESIGN §9 floors the kill switch at
     min-height 36px — .head must never clip it (overflow:hidden is kept).
     The order values from the base rules still sequence items within each
     row, so no re-interleaving is needed. */
  @media (max-width: 1024px) {
    .head {
      flex-wrap: wrap;
      height: auto;
    }
    .head-status,
    .head-actions {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 1 1 100%;
      min-height: 36px;
    }
    .head-status {
      flex-wrap: wrap;
    }
    .head-actions {
      justify-content: flex-end;
    }
    .health {
      margin-left: 0;
    }
  }
</style>
