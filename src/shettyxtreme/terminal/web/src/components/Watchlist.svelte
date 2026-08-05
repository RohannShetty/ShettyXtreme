<script lang="ts">
  import { onMount } from "svelte";
  import { del, get, post } from "../lib/api";
  import { selectedSymbol } from "../lib/selection";
  import { onMessage } from "../lib/ws";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Plus, X } from "@lucide/svelte";
  import EmptyState from "./state/EmptyState.svelte";
  import LoadingState from "./state/LoadingState.svelte";
  import ErrorState from "./state/ErrorState.svelte";

  type WatchItem = {
    symbol: string;
    exchange: string;
    ltp: number;
    change_pct: number;
    volume: number;
    timestamp: string | null;
  };

  const STALE_MS = 60_000;

  let items: WatchItem[] = $state([]);
  let selected = $state("");
  let newSymbol = $state("");
  let newExchange = $state("NSE");
  let error = $state("");
  let loading = $state(true);
  let now = $state(Date.now());
  const flashMap = new Map<string, "up" | "down">();
  // symbol -> epoch ms of the last tick we actually saw for that symbol
  const lastSeenMs = new Map<string, number>();
  let staleTimer: number | undefined;

  onMount(() => {
    load();
    const unsub = onMessage("tick", applyTick);
    staleTimer = window.setInterval(() => (now = Date.now()), 5000);
    return () => {
      unsub();
      if (staleTimer !== undefined) window.clearInterval(staleTimer);
    };
  });

  async function load(): Promise<void> {
    loading = true;
    error = "";
    try {
      items = await get<WatchItem[]>("/api/watchlist");
      for (const it of items) {
        if (it.timestamp) {
          const ts = Date.parse(it.timestamp);
          if (!Number.isNaN(ts)) lastSeenMs.set(it.symbol, ts);
        }
      }
      if (selected && !items.some((i) => i.symbol === selected)) selected = "";
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  function applyTick(data: unknown): void {
    const tick = data as Partial<WatchItem>;
    if (!tick || typeof tick.symbol !== "string") return;
    const existing = items.find((i) => i.symbol === tick.symbol);
    if (existing) {
      if (typeof tick.ltp === "number") existing.ltp = tick.ltp;
      if (typeof tick.change_pct === "number") existing.change_pct = tick.change_pct;
      if (typeof tick.volume === "number") existing.volume = tick.volume;
      lastSeenMs.set(tick.symbol, Date.now());
      flashMap.set(tick.symbol, (tick.change_pct ?? existing.change_pct) >= 0 ? "up" : "down");
      window.setTimeout(() => flashMap.delete(tick.symbol ?? ""), 160);
      items = items.slice();
    }
  }

  function isStale(item: WatchItem): boolean {
    const last = lastSeenMs.get(item.symbol);
    if (last === undefined) return true; // never ticked in this session → no live data
    return now - last > STALE_MS;
  }

  function flashClass(symbol: string): string {
    const dir = flashMap.get(symbol);
    return dir ? (dir === "up" ? "flash-up" : "flash-down") : "";
  }

  function pnlClass(changePct: number): string {
    return changePct > 0 ? "price-up" : changePct < 0 ? "price-down" : "";
  }

  async function add(): Promise<void> {
    const symbol = newSymbol.trim().toUpperCase();
    if (!symbol) return;
    error = "";
    try {
      await post<WatchItem>(`/api/watchlist/${encodeURIComponent(symbol)}?exchange=${encodeURIComponent(newExchange)}`);
      newSymbol = "";
      await load();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function remove(symbol: string): Promise<void> {
    try {
      await del(`/api/watchlist/${encodeURIComponent(symbol)}`);
      if (selected === symbol) selected = "";
      items = items.filter((i) => i.symbol !== symbol);
      lastSeenMs.delete(symbol);
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  function fmtLtp(value: number): string {
    return value > 0 ? value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";
  }

  function onRowKeydown(event: KeyboardEvent, symbol: string): void {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectRow(symbol);
    }
  }

  function selectRow(symbol: string): void {
    selected = symbol;
    selectedSymbol.set(symbol);
  }
</script>

<section class="panel watchlist">
  <header class="panel-head">
    <h2>Watchlist</h2>
    <span class="count mono">{items.length}</span>
  </header>

  <div class="add-row">
    <Input
      class="mono h-7"
      placeholder="SYMBOL"
      bind:value={newSymbol}
      onkeydown={(e) => e.key === "Enter" && add()}
    />
    <select class="exch-select mono" bind:value={newExchange}>
      <option value="NSE">NSE</option>
      <option value="NSE_FNO">NFO</option>
      <option value="BSE">BSE</option>
    </select>
    <Button size="icon" class="size-7" onclick={add} aria-label="Add symbol">
      <Plus class="size-3.5" />
    </Button>
  </div>

  {#if error && items.length === 0}
    <ErrorState message={error} onRetry={load} />
  {:else}
    {#if error}
      <ErrorState message={error} onRetry={load} />
    {/if}

    {#if loading && items.length === 0}
      <LoadingState label="Loading watchlist…" rows={4} />
    {:else}
      <div class="list">
        {#each items as item (item.symbol)}
          <div
            class={flashClass(item.symbol) ? `row ${flashClass(item.symbol)}` : "row"}
            class:selected={selected === item.symbol}
            class:stale={isStale(item)}
            onclick={() => selectRow(item.symbol)}
            onkeydown={(e) => onRowKeydown(e, item.symbol)}
            role="button"
            tabindex="0"
            title={isStale(item) ? "No tick in the last 60s" : ""}
          >
            <div class="sym-cell">
              <span class="ticker">{item.symbol}</span>
              <span class="exch">{item.exchange}</span>
            </div>
            <span class="num ltp {pnlClass(item.change_pct)}">{fmtLtp(item.ltp)}</span>
            <span class="num chg {pnlClass(item.change_pct)}">{item.change_pct > 0 ? "+" : ""}{item.change_pct.toFixed(2)}%</span>
            <button
              class="rm"
              onclick={(e) => {
                e.stopPropagation();
                remove(item.symbol);
              }}
              title="Remove"
              aria-label={`Remove ${item.symbol}`}
            >
              <X class="size-3.5" />
            </button>
          </div>
        {/each}
        {#if items.length === 0}
          <EmptyState message="No instruments. Add one above." />
        {/if}
      </div>
    {/if}
  {/if}
</section>

<style>
  .watchlist {
    display: flex;
    flex-direction: column;
    min-width: 260px;
    height: 100%;
  }
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
  }
  .panel-head h2 {
    margin: 0;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .count {
    color: var(--faint);
    font-size: 11px;
  }
  .add-row {
    display: flex;
    gap: 4px;
    padding: 8px 10px;
  }
  .exch-select {
    background: var(--canvas-raised);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    color: var(--body);
    padding: 5px 4px;
    font-size: 11px;
  }
  .list {
    flex: 1;
    overflow-y: auto;
    padding-bottom: 6px;
  }
  .row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto 20px;
    gap: 8px;
    align-items: center;
    padding: 5px 10px;
    cursor: pointer;
    border-left: 2px solid transparent;
  }
  .row:hover {
    background: var(--row-hover);
  }
  .row.selected {
    background: var(--row-selected);
    border-left-color: var(--accent);
  }
  .row.stale {
    opacity: 0.5;
    transition: opacity 300ms ease;
  }
  .sym-cell {
    display: flex;
    flex-direction: column;
    min-width: 0;
  }
  .ticker {
    font-size: 12px;
    color: var(--ink);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .exch {
    font-size: 9px;
    color: var(--faint);
  }
  .ltp {
    font-size: 12px;
  }
  .chg {
    font-size: 11px;
    min-width: 58px;
    text-align: right;
  }
  .rm {
    background: none;
    border: none;
    color: var(--faint);
    cursor: pointer;
    padding: 2px;
    display: inline-flex;
  }
  .rm:hover {
    color: var(--danger);
  }
</style>
