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

  const MAX_LOGS = 200;

  onMount(() => {
    refresh();
    timer = window.setInterval(refresh, 3000);
    const offAlert = onMessage("alert", (data) => appendBroadcast("alert", data));
    const offRisk = onMessage("risk", (data) => appendBroadcast("risk", data));
    return () => {
      if (timer !== undefined) window.clearInterval(timer);
      offAlert();
      offRisk();
    };
  });

  onDestroy(() => {
    if (timer !== undefined) window.clearInterval(timer);
  });

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

<aside class="drawer" class:open>
  <header class="drawer-head">
    <h2>Logs</h2>
    <Button variant="ghost" size="icon" class="size-7 text-faint hover:text-ink" onclick={() => (open = false)} aria-label="Close logs drawer">
      <X class="size-4" />
    </Button>
  </header>
  <div class="log-list">
    {#each logs as log (log.timestamp + log.message)}
      <div class="line mono {levelClass(log.level)}">
        <span class="time">{fmtTime(log.timestamp)}</span>
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
  .drawer {
    display: flex;
    flex-direction: column;
    min-width: 320px;
    min-height: 0;
    flex: 1 1 0;
    background: var(--canvas-raised);
    border-left: 1px solid var(--hairline);
    border-radius: 0 0 6px 0;
  }
  .drawer:not(.open) {
    display: none;
  }

  @media (max-width: 1439px) {
    .drawer {
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      z-index: 30;
      width: min(380px, 88vw);
      border-left: 1px solid var(--hairline-strong);
      /* Level-3 overlay: surface-overlay + scrim, no drop shadow (DESIGN.md §6) */
      background: var(--surface-overlay);
      transform: translateX(100%);
      transition: transform 120ms ease-out;
      display: flex;
      border-radius: 0;
    }
    .drawer.open {
      transform: translateX(0);
    }
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
    padding: 6px 0;
  }
  .line {
    display: flex;
    gap: 10px;
    padding: 3px 10px;
    font-size: 11px;
    border-bottom: 1px solid var(--hairline);
    align-items: baseline;
  }
  .time {
    color: var(--faint);
    white-space: nowrap;
  }
  .msg {
    flex: 1;
    min-width: 0;
    word-break: break-word;
    line-height: 1.45;
  }
  .lv-info {
    color: var(--muted);
  }
  .lv-warn {
    color: var(--warning);
  }
  .lv-error {
    color: var(--danger);
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
