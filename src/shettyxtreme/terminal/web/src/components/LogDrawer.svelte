<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { get } from "../lib/api";
  import { onMessage } from "../lib/ws";
  import { Button } from "$lib/components/ui/button";
  import { X } from "@lucide/svelte";

  type LogEntry = {
    log_type: string;
    message: string;
    level: string;
    timestamp: string | null;
  };

  let { open = $bindable(false) }: { open?: boolean } = $props();

  let logs: LogEntry[] = $state([]);
  let error = $state("");
  let timer: number | undefined;
  let drawerEl: HTMLElement | undefined;

  const MAX_LOGS = 200;

  onMount(() => {
    refresh();
    timer = window.setInterval(refresh, 3000);
    const offAlert = onMessage("alert", (data) => appendBroadcast("alert", data));
    const offRisk = onMessage("risk", (data) => appendBroadcast("risk", data));
    // Esc closes the drawer whenever the drawer (or a control inside it) has
    // focus. The drawer takes focus on open so the shortcut is always live.
    window.addEventListener("keydown", onKeydown);
    return () => {
      if (timer !== undefined) window.clearInterval(timer);
      offAlert();
      offRisk();
      window.removeEventListener("keydown", onKeydown);
    };
  });

  onDestroy(() => {
    if (timer !== undefined) window.clearInterval(timer);
  });

  // Keyboard: Esc closes the drawer whenever it (or a control inside it) has
  // focus. The drawer takes focus on open so the shortcut is always live.
  $effect(() => {
    if (open) drawerEl?.focus();
  });

  function onKeydown(event: KeyboardEvent): void {
    if (event.key !== "Escape") return;
    const t = event.target as HTMLElement | null;
    if (drawerEl && t && drawerEl.contains(t)) {
      event.preventDefault();
      open = false;
    }
  }

  async function refresh(): Promise<void> {
    try {
      const fresh = await get<LogEntry[]>("/api/scanner/logs?limit=100");
      logs = fresh.slice(-MAX_LOGS);
      error = "";
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  function appendBroadcast(kind: string, data: unknown): void {
    const d = data as Partial<LogEntry>;
    const entry: LogEntry = {
      log_type: kind,
      message: typeof d.message === "string" ? d.message : JSON.stringify(d),
      level: typeof d.level === "string" ? d.level : "WARN",
      timestamp: new Date().toISOString(),
    };
    logs = [...logs, entry].slice(-MAX_LOGS);
  }

  function levelClass(level: string): string {
    const l = String(level).toUpperCase();
    return l === "ERROR" ? "lv-error" : l === "WARN" ? "lv-warn" : "lv-info";
  }

  function fmtTime(ts: string | null): string {
    if (!ts) return "—";
    const d = new Date(ts);
    if (isNaN(d.getTime())) return ts;
    return d.toLocaleTimeString("en-IN", { hour12: false });
  }
</script>

<aside
  class="drawer"
  class:open
  tabindex="-1"
  bind:this={drawerEl}
  aria-label="Logs drawer"
>
  <header class="drawer-head">
    <h2>Logs</h2>
    <Button variant="ghost" size="icon" class="size-7 text-faint hover:text-ink" onclick={() => (open = false)} aria-label="Close logs drawer">
      <X class="size-4" />
    </Button>
  </header>
  <div class="log-list">
    {#each logs as log (log.timestamp + log.message)}
      <div class="line">
        <span class="time">{fmtTime(log.timestamp)}</span>
        <span class="level {levelClass(log.level)}">{log.level}</span>
        <span class="msg">{log.message}</span>
      </div>
    {/each}
    {#if logs.length === 0}
      <p class="empty">No log entries yet.</p>
    {/if}
    {#if error}
      <p class="error">{error}</p>
    {/if}
  </div>
</aside>

<style>
  /* Docked panel — level-1 hairline card inside the right dock. The internal
     overlay mode (<1440px) was removed in Phase 3 S6: the right-col overlay
     drawer in App.svelte is the single overlay affordance now. */
  .drawer {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    flex: 1 1 0;
    background: var(--canvas-raised);
    border: 1px solid var(--hairline);
    border-radius: 6px;
    overflow: hidden;
  }
  .drawer:not(.open) {
    display: none;
  }
  .drawer-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
  }
  .drawer-head h2 {
    margin: 0;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .log-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  /* Log rows — surface-card cards, micro timestamps, body message text. */
  .line {
    display: flex;
    gap: 8px;
    padding: 5px 8px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    align-items: baseline;
  }
  .time {
    color: var(--faint);
    font-family: var(--font-mono);
    font-size: 10px;
    font-variant-numeric: tabular-nums;
    white-space: nowrap;
    flex: none;
  }
  /* Level carries the status color (info / warning / danger) as a labeled
     chip — color is never the only indicator (DESIGN.md §2.4, a11y). */
  .level {
    font-family: var(--font-mono);
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    flex: none;
  }
  .lv-info {
    color: var(--info);
  }
  .lv-warn {
    color: var(--warning);
  }
  .lv-error {
    color: var(--danger);
  }
  .msg {
    flex: 1;
    min-width: 0;
    word-break: break-word;
    line-height: 1.45;
    font-size: 12px;
    color: var(--body);
  }
  .empty {
    color: var(--faint);
    font-size: 12px;
    padding: 12px 10px;
    margin: 0;
  }
  .error {
    color: var(--danger);
    font-size: 11px;
    padding: 8px 10px;
    margin: 0;
  }
</style>
