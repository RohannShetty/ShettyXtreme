<script lang="ts">
  import { onMount } from "svelte";
  import { del, get, post } from "../lib/api";
  import { selectedSymbol } from "../lib/selection";
  import { onMessage } from "../lib/ws";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import { Select, SelectContent, SelectItem, SelectTrigger } from "$lib/components/ui/select";
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
  const FLASH_MS = 150;

  let items: WatchItem[] = $state([]);
  let selected = $state("");
  let newSymbol = $state("");
  let newExchange = $state("NSE");
  let error = $state("");
  let loading = $state(true);
  let now = $state(Date.now());
  // Reactive flash record (keyed by symbol). Must be $state so the 150ms
  // removal re-renders and the CSS animation can restart on the next tick.
  let flashes = $state<Record<string, "up" | "down">>({});
  const flashTimers = new Map<string, number>();
  // symbol -> epoch ms of the last tick we actually saw for that symbol
  const lastSeenMs = new Map<string, number>();
  // symbol -> last LTP seen in the tick stream (flash direction = tick move)
  const prevLtp = new Map<string, number>();
  let staleTimer: number | undefined;
  let rowEls: (HTMLDivElement | undefined)[] = [];

  onMount(() => {
    load();
    const unsub = onMessage("tick", applyTick);
    staleTimer = window.setInterval(() => (now = Date.now()), 5000);
    return () => {
      unsub();
      if (staleTimer !== undefined) window.clearInterval(staleTimer);
      for (const id of flashTimers.values()) window.clearTimeout(id);
      flashTimers.clear();
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
      if (typeof tick.ltp === "number") {
        // Flash direction is the tick-vs-previous-tick move (DESIGN §3.2);
        // the persistent LTP color stays on change_pct (session direction),
        // matching the header hero. Red = rise, green = fall — Indian law.
        const prev = prevLtp.get(tick.symbol) ?? existing.ltp;
        if (tick.ltp !== prev) {
          scheduleFlash(tick.symbol, tick.ltp > prev ? "up" : "down");
        }
        prevLtp.set(tick.symbol, tick.ltp);
        existing.ltp = tick.ltp;
      }
      if (typeof tick.change_pct === "number") existing.change_pct = tick.change_pct;
      if (typeof tick.volume === "number") existing.volume = tick.volume;
      lastSeenMs.set(tick.symbol, Date.now());
      items = items.slice();
    }
  }

  function scheduleFlash(symbol: string, dir: "up" | "down"): void {
    flashes[symbol] = dir;
    const prev = flashTimers.get(symbol);
    if (prev !== undefined) window.clearTimeout(prev);
    const id = window.setTimeout(() => {
      const next = { ...flashes };
      delete next[symbol];
      flashes = next;
      flashTimers.delete(symbol);
    }, FLASH_MS);
    flashTimers.set(symbol, id);
  }

  function isStale(item: WatchItem): boolean {
    const last = lastSeenMs.get(item.symbol);
    if (last === undefined) return true; // never ticked in this session → no live data
    return now - last > STALE_MS;
  }

  function flashClass(symbol: string): string {
    const dir = flashes[symbol];
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
      prevLtp.delete(symbol);
      const next = { ...flashes };
      delete next[symbol];
      flashes = next;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  function fmtLtp(value: number): string {
    return value > 0 ? value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";
  }

  // Per-row keyboard: Enter/Space selects; ArrowUp/ArrowDown moves the
  // selection and the focus ring together. Handled on the interactive row so
  // no non-interactive container carries a keydown listener.
  function onRowKeydown(event: KeyboardEvent, idx: number): void {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      selectRow(items[idx].symbol);
      return;
    }
    if (items.length === 0) return;
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    let next: number;
    if (event.key === "ArrowDown") {
      next = Math.min(idx + 1, items.length - 1);
    } else {
      next = Math.max(idx - 1, 0);
    }
    event.preventDefault();
    selectRow(items[next].symbol);
    rowEls[next]?.focus();
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
    <Select type="single" value={newExchange} onValueChange={(v) => (newExchange = v)}>
      <SelectTrigger class="mono h-7 w-[64px] text-[11px]" aria-label="Exchange">
        <span>{newExchange}</span>
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="NSE" label="NSE" class="font-mono text-[11px]">NSE</SelectItem>
        <SelectItem value="NSE_FNO" label="NFO" class="font-mono text-[11px]">NFO</SelectItem>
        <SelectItem value="BSE" label="BSE" class="font-mono text-[11px]">BSE</SelectItem>
      </SelectContent>
    </Select>
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
      <ScrollArea class="list-scroll flex-1">
        <div class="list">
          {#each items as item, i (item.symbol)}
            <div
              class={flashClass(item.symbol) ? `row ${flashClass(item.symbol)}` : "row"}
              class:selected={selected === item.symbol}
              bind:this={rowEls[i]}
              onclick={() => selectRow(item.symbol)}
              onkeydown={(e) => onRowKeydown(e, i)}
              role="button"
              tabindex="0"
              title={isStale(item) ? "No tick in the last 60s" : ""}
            >
              <div class="sym-cell">
                <span class="ticker">{item.symbol}</span>
                <span class="meta">
                  <span class="exch">{item.exchange}</span>
                  {#if isStale(item)}
                    <span class="stale-chip">STALE</span>
                  {/if}
                </span>
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
      </ScrollArea>
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
  .list-scroll {
    min-height: 0;
  }
  .list {
    padding-bottom: 6px;
  }
  /* 28px rows (DESIGN §4 table contract). Content is two-line (symbol/exch +
     STALE chip); tight line-heights keep it inside the fixed row height. */
  .row {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto auto 20px;
    gap: 8px;
    align-items: center;
    height: 28px;
    padding: 0 10px;
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
  .row:focus-visible {
    outline: none;
    box-shadow: inset 0 0 0 2px var(--focus-ring);
  }
  .sym-cell {
    display: flex;
    flex-direction: column;
    justify-content: center;
    min-width: 0;
  }
  .ticker {
    font-size: 12px;
    line-height: 14px;
    color: var(--ink);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .meta {
    display: flex;
    align-items: center;
    gap: 4px;
    line-height: 14px;
    min-width: 0;
  }
  .exch {
    font-size: 9px;
    color: var(--faint);
    white-space: nowrap;
  }
  /* STALE chip — DESIGN §4: {colors.warning} micro (11px) uppercase chip in
     the cell corner. Replaces the old opacity-fade staleness (a stale terminal
     must not look fresh — DESIGN §7). */
  .stale-chip {
    flex: none;
    font-size: 11px;
    font-weight: 600;
    line-height: 14px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--warning);
    background: color-mix(in srgb, var(--warning) 12%, transparent);
    border: 1px solid color-mix(in srgb, var(--warning) 35%, transparent);
    border-radius: 2px;
    padding: 0 3px;
    white-space: nowrap;
  }
  .ltp {
    font-size: 13px;
    white-space: nowrap;
  }
  .chg {
    font-size: 11px;
    min-width: 58px;
    text-align: right;
    white-space: nowrap;
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
