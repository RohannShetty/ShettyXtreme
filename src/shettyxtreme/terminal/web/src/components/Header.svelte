<script lang="ts">
  import { onMount } from "svelte";
  import { authStatus, get, type AuthStatus } from "../lib/api";
  import { applyTheme, getTheme, type Theme } from "../lib/theme";
  import { selectedSymbol } from "../lib/selection";
  import { onMessage } from "../lib/ws";
  import { Button } from "$lib/components/ui/button";
  import {
    Tooltip,
    TooltipContent,
    TooltipTrigger,
  } from "$lib/components/ui/tooltip";
  import { FileText, Moon, Sun } from "@lucide/svelte";
  import KillSwitch from "./KillSwitch.svelte";
  import ModeSwitcher from "./ModeSwitcher.svelte";

  type ComponentHealth = {
    name: string;
    status: string;
    message: string;
  };

  type HealthResponse = {
    components: ComponentHealth[];
    overall: string;
  };

  type Session = {
    status: string;
    current_time_ist: string;
    next_event: string;
  };

  type WatchlistItem = { symbol: string; exchange: string };

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

  // --- LTP hero (DESIGN §5 header anatomy, §3.1 number-xl) ---
  let selected = $derived($selectedSymbol);
  let tickBySymbol = $state<Record<string, Tick>>({});
  let exchangeBySymbol = $state<Record<string, string>>({});
  let flashDir = $state<"" | "up" | "down">("");
  let flashTimer: number | undefined;

  let tick = $derived(selected ? tickBySymbol[selected] : undefined);
  let exchange = $derived(selected ? (exchangeBySymbol[selected] ?? "NSE") : "");
  let changePct = $derived(tick?.change_pct ?? null);
  let ltp = $derived(tick?.ltp ?? null);
  // Indian price law: red = up, green = down. Flash toggles color weight
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
    loadExchanges();
    const offTick = onMessage("tick", applyTick);
    refreshTimer = window.setInterval(() => {
      load();
      loadCreds();
      loadExchanges();
    }, 30_000);
    return () => {
      offTick();
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

  // Build symbol → exchange map from the watchlist so the hero can show the
  // exchange next to the selected symbol (the selection store carries the
  // symbol only).
  async function loadExchanges(): Promise<void> {
    try {
      const items = await get<WatchlistItem[]>("/api/watchlist");
      const map: Record<string, string> = {};
      for (const it of items) {
        if (it && it.symbol) map[it.symbol] = it.exchange || "NSE";
      }
      exchangeBySymbol = map;
    } catch {
      /* header degrades silently */
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

  // Broker-neutral connection pip (S0 honesty hardening).
  // Backend contract statuses: healthy / stale / disconnected / token_expired / down.
  // Legacy Dhan component names are matched too so the pip stays honest mid-migration.
  const BROKER_COMPONENTS = ["data_adapter", "trading_adapter", "dhan_data", "dhan_trading"];

  type PipState = "live" | "stale" | "disconnected" | "expired" | "unknown";

  function brokerComponents(): ComponentHealth[] {
    return (health?.components ?? []).filter((c) => BROKER_COMPONENTS.includes(c.name));
  }

  function statusRank(status: string): number {
    const s = String(status).toLowerCase();
    if (s === "token_expired") return 4;
    if (s === "down" || s === "disconnected") return 3;
    if (s === "stale" || s === "degraded") return 2;
    if (s === "healthy") return 1;
    return 0;
  }

  function pipState(): PipState {
    const comps = brokerComponents();
    if (comps.length === 0) return "unknown";
    let worst = 0;
    for (const c of comps) worst = Math.max(worst, statusRank(c.status));
    if (worst >= 4) return "expired";
    if (worst === 3) return "disconnected";
    if (worst === 2) return "stale";
    return "live";
  }

  function pipLabel(state: PipState): string {
    switch (state) {
      case "live":
        return "LIVE";
      case "stale":
        return "STALE";
      case "disconnected":
        return "DISCONNECTED";
      case "expired":
        return "EXPIRED";
      default:
        return "…";
    }
  }

  function pipDetail(): string {
    const comps = brokerComponents();
    if (comps.length === 0) return "No broker adapter status reported";
    const worst = [...comps].sort((a, b) => statusRank(b.status) - statusRank(a.status))[0];
    return worst ? `${worst.name}: ${worst.message || worst.status}` : "";
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

  <ModeSwitcher />
  <KillSwitch />

  <div class="health">
    <span
      class="pip pip-{pipState()}"
      title={pipDetail()}
      aria-label="Connection status: {pipLabel(pipState())}"
    >
      <span class="pip-dot" aria-hidden="true"></span>
      <span class="pip-label">{pipLabel(pipState())}</span>
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

  <Tooltip>
    <TooltipTrigger>
      <Button
        variant="ghost"
        size="icon"
        class="text-muted-foreground hover:text-accent-active"
        onclick={toggleTheme}
        aria-label="Toggle light or dark theme"
      >
        {#if theme === "dark"}
          <Sun class="size-4" />
        {:else}
          <Moon class="size-4" />
        {/if}
      </Button>
    </TooltipTrigger>
    <TooltipContent>Toggle theme</TooltipContent>
  </Tooltip>

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
  .brand {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-right: 4px;
    min-width: 0;
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
    font-size: 9px;
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
</style>
