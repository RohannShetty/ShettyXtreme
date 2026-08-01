<script lang="ts">
  import { onMount } from "svelte";
  import { del, get, post } from "../lib/api";
  import { onMessage } from "../lib/ws";

  type WatchItem = {
    symbol: string;
    exchange: string;
    ltp: number;
    change_pct: number;
    volume: number;
  };

  let items: WatchItem[] = [];
  let selected = "";
  let newSymbol = "";
  let newExchange = "NSE";
  let error = "";
  const flashMap = new Map<string, "up" | "down">();

  onMount(() => {
    load();
    return onMessage("tick", applyTick);
  });

  async function load(): Promise<void> {
    try {
      items = await get<WatchItem[]>("/api/watchlist");
      if (selected && !items.some((i) => i.symbol === selected)) selected = "";
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
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
      flashMap.set(tick.symbol, (tick.change_pct ?? existing.change_pct) >= 0 ? "up" : "down");
      window.setTimeout(() => flashMap.delete(tick.symbol ?? ""), 160);
      items = items.slice();
    }
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
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  function fmtLtp(value: number): string {
    return value > 0 ? value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—";
  }
</script>

<section class="panel watchlist">
  <header class="panel-head">
    <h2>Watchlist</h2>
    <span class="count mono">{items.length}</span>
  </header>

  <div class="add-row">
    <input
      class="sym-input mono"
      placeholder="SYMBOL"
      bind:value={newSymbol}
      on:keydown={(e) => e.key === "Enter" && add()}
    />
    <select class="exch-select mono" bind:value={newExchange}>
      <option value="NSE">NSE</option>
      <option value="NSE_FNO">NFO</option>
      <option value="BSE">BSE</option>
    </select>
    <button class="add-btn" on:click={add}>+</button>
  </div>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <div class="list">
    {#each items as item (item.symbol)}
      <div
        class="row"
        class:selected={selected === item.symbol}
        class:flash-up={flashClass(item.symbol) === "flash-up"}
        class:flash-down={flashClass(item.symbol) === "flash-down"}
        on:click={() => (selected = item.symbol)}
        on:keydown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            selected = item.symbol;
          }
        }}
        role="button"
        tabindex="0"
      >
        <div class="sym-cell">
          <span class="ticker">{item.symbol}</span>
          <span class="exch">{item.exchange}</span>
        </div>
        <span class="num ltp {pnlClass(item.change_pct)}">{fmtLtp(item.ltp)}</span>
        <span class="num chg {pnlClass(item.change_pct)}">{item.change_pct > 0 ? "+" : ""}{item.change_pct.toFixed(2)}%</span>
        <button class="rm" on:click|stopPropagation={() => remove(item.symbol)} title="Remove">×</button>
      </div>
    {/each}
    {#if items.length === 0}
      <p class="empty">No instruments. Add one above.</p>
    {/if}
  </div>
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
  .sym-input {
    flex: 1;
    min-width: 0;
    background: var(--canvas-raised);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    color: var(--ink);
    padding: 5px 8px;
    font-size: 12px;
  }
  .sym-input:focus {
    outline: none;
    border-color: var(--focus-ring);
  }
  .exch-select {
    background: var(--canvas-raised);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    color: var(--body);
    padding: 5px 4px;
    font-size: 11px;
  }
  .add-btn {
    background: var(--accent);
    border: 1px solid var(--accent);
    border-radius: 4px;
    color: var(--on-accent);
    font-weight: 700;
    width: 28px;
    cursor: pointer;
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
    font-size: 14px;
    cursor: pointer;
    padding: 0;
  }
  .rm:hover {
    color: var(--danger);
  }
  .empty {
    color: var(--faint);
    font-size: 11px;
    padding: 12px 10px;
    margin: 0;
  }
  .error {
    color: var(--danger);
    font-size: 11px;
    padding: 4px 10px;
    margin: 0;
  }
</style>
