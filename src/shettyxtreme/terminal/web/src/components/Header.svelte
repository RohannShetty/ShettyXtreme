<script lang="ts">
  import { onMount } from "svelte";
  import { authStatus, get, type AuthStatus } from "../lib/api";
  import { applyTheme, getTheme, type Theme } from "../lib/theme";
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

  function toggleTheme(): void {
    theme = theme === "dark" ? "light" : "dark";
    applyTheme(theme);
  }

  onMount(() => {
    load();
    loadCreds();
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

  function statusClass(status: string): string {
    const s = String(status).toLowerCase();
    return s === "healthy" ? "st-ok" : s === "degraded" ? "st-warn" : "st-down";
  }

  function sessionText(status: string): string {
    return String(status).toUpperCase().replace("_", " ");
  }

  function entitlementMessage(): string {
    if (!health) return "";
    const dhan = health.components.find((c) => c.name === "dhan_data");
    const msg = dhan?.message ?? "";
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

  <ModeSwitcher />
  <KillSwitch />

  <div class="health">
    {#if health}
      {#each health.components as c (c.name)}
        <span class="comp" title={c.message || c.name}>
          <span class="dot {statusClass(c.status)}"></span>
          <span class="comp-name">{c.name}</span>
        </span>
      {/each}
    {:else}
      <span class="comp-name muted">health…</span>
    {/if}
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
      <a class="cred-chip mute" href="#/setup" title="Set up Dhan credentials">
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
    min-height: 44px;
  }
  .brand {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-right: 4px;
  }
  .logo {
    background: var(--accent);
    color: var(--on-accent);
    font-weight: 800;
    font-size: 11px;
    border-radius: 4px;
    padding: 2px 5px;
  }
  .title {
    color: var(--ink);
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.08em;
    white-space: nowrap;
  }
  .health {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-left: auto;
    overflow: hidden;
  }
  .comp {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 10px;
    color: var(--muted);
    white-space: nowrap;
    max-width: 220px;
  }
  .comp-name {
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .dot {
    width: 7px;
    height: 7px;
    border-radius: 50%;
    flex: none;
  }
  .st-ok {
    background: var(--success);
  }
  .st-warn {
    background: var(--warning);
  }
  .st-down {
    background: var(--danger);
  }
  .muted {
    color: var(--faint);
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
    flex: none;
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
</style>
