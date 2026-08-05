<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "../lib/api";
  import { selectedSymbol } from "../lib/selection";
  import { onMessage } from "../lib/ws";
  import { Input } from "$lib/components/ui/input";
  import { cn } from "$lib/utils.js";
  import CandleChart from "./CandleChart.svelte";
  import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
  } from "$lib/components/ui/table";

  type Contract = {
    strike: number;
    option_type: string;
    ltp: number;
    iv: number;
    delta: number;
    gamma: number;
    theta: number;
    vega: number;
    oi: number;
    volume: number;
    bid: number;
    ask: number;
  };

  type OptionsResponse = {
    underlying: string;
    expiry: string;
    contracts: Contract[];
  };

  type ChainRow = { strike: number; ce?: Contract; pe?: Contract };
  type Side = "ce" | "pe";
  type Dir = "up" | "down";

  // IV/OI are not carried by the WS tick payload (the backend broadcasts
  // {symbol, ltp, change_pct, volume} only), so a quiet REST poll keeps those
  // columns live between loads. LTP of watchlisted contracts ticks in real
  // time via WS and flashes on each move.
  const REFRESH_MS = 15_000;
  const FLASH_MS = 150;
  const LIVE_MS = 60_000;

  let symbol = $state("NIFTY");
  let exchange = $state("NSE_FNO");
  let expiry = $state("");
  let expiries = $state<string[]>([]);
  let contracts = $state<Contract[]>([]);
  let loading = $state(false);
  let error = $state("");
  let selectedStrike = $state<number | null>(null);
  let live = $state(false);
  let now = $state(Date.now());
  // Committed request — the pair the grid is loaded for. The display `symbol`
  // / `expiry` bind to the inputs and change on every keystroke, but the grid
  // reloads only when this pair changes (blur / Enter / select / selection
  // change), never mid-typing.
  let snapshot = $state({ symbol: "NIFTY", expiry: "" });
  // Reactive flash record keyed by `${strike}|${side}`. $state so the 150ms
  // removal re-renders and the CSS animation restarts on the next tick.
  let flashes = $state<Record<string, Dir>>({});
  const flashTimers = new Map<string, number>();
  // Per-contract last-tick direction (persistent LTP cell color) and last LTP.
  const dirMap = new Map<string, Dir>();
  const prevLtp = new Map<string, number>();
  let lastTickAt: number | null = null;

  let reqId = 0;
  let refreshTimer: number | undefined;
  let nowTimer: number | undefined;
  let wrapEl: HTMLDivElement | undefined;

  let rows = $derived(buildRows(contracts));
  let matchIndex = $derived(buildMatchIndex(contracts));

  // Auto-load: runs on mount and whenever a committed request differs from
  // what the grid currently holds. The reqId guard drops stale responses so
  // a newer request always wins.
  $effect(() => {
    const req = snapshot; // reactive dependency
    const id = ++reqId;
    void load(req.symbol, req.expiry, id);
  });

  onMount(() => {
    const unsubTick = onMessage("tick", applyTick);
    const unsubSel = selectedSymbol.subscribe((v) => {
      if (v && v !== symbol) {
        symbol = v;
        snapshot = { symbol: v, expiry: snapshot.expiry };
      }
    });
    refreshTimer = window.setInterval(() => {
      void refreshSilently();
    }, REFRESH_MS);
    nowTimer = window.setInterval(() => {
      now = Date.now();
    }, 5000);
    return () => {
      unsubTick();
      unsubSel();
      if (refreshTimer !== undefined) window.clearInterval(refreshTimer);
      if (nowTimer !== undefined) window.clearInterval(nowTimer);
      for (const id of flashTimers.values()) window.clearTimeout(id);
      flashTimers.clear();
    };
  });

  function buildRows(list: Contract[]): ChainRow[] {
    const byStrike = new Map<number, ChainRow>();
    for (const c of list) {
      const entry = byStrike.get(c.strike) ?? { strike: c.strike };
      if (String(c.option_type).toUpperCase() === "PE") {
        entry.pe = c;
      } else {
        entry.ce = c;
      }
      byStrike.set(c.strike, entry);
    }
    return [...byStrike.values()].sort((a, b) => a.strike - b.strike);
  }

  function strikeKey(strike: number): number {
    return Number(strike.toFixed(2));
  }

  function contractKey(strike: number, side: Side): string {
    return `${strikeKey(strike)}|${side}`;
  }

  function buildMatchIndex(list: Contract[]): Map<string, { rowIdx: number; side: Side }> {
    const idx = new Map<string, { rowIdx: number; side: Side }>();
    list.forEach((c, i) => {
      const side: Side = String(c.option_type).toUpperCase() === "PE" ? "pe" : "ce";
      idx.set(contractKey(c.strike, side), { rowIdx: i, side });
    });
    return idx;
  }

  // Parse a contract symbol into (strike, side). Handles Fyers-style
  // "NIFTY24AUG24500CE" and spaced "NIFTY 24500 CE". Returns null for plain
  // underlying symbols (e.g. "NIFTY") which carry no strike.
  function parseTickKey(raw: string): { strike: number; side: Side } | null {
    const s = raw.trim().toUpperCase();
    const m = /^(.*?)(\d+(?:\.\d+)?)[A-Z]*\s*(CE|PE)$/.exec(s);
    if (!m) return null;
    const strike = Number(m[2]);
    if (!isFinite(strike) || strike <= 0) return null;
    return { strike, side: m[3] === "PE" ? "pe" : "ce" };
  }

  function sideOf(optionType: string): Side {
    return String(optionType).toUpperCase() === "PE" ? "pe" : "ce";
  }

  function applyTick(data: unknown): void {
    const t = data as Partial<Contract> & { symbol?: unknown };
    if (!t || typeof t.symbol !== "string" || t.symbol === "") return;
    // Prefer explicit strike/option_type fields (future payload), else parse
    // the contract symbol.
    let strike: number | null = typeof t.strike === "number" && isFinite(t.strike) ? t.strike : null;
    let side: Side | null = typeof t.option_type === "string" ? sideOf(t.option_type) : null;
    if (strike === null || side === null) {
      const parsed = parseTickKey(t.symbol);
      if (!parsed) return;
      if (strike === null) strike = parsed.strike;
      if (side === null) side = parsed.side;
    }
    const key = contractKey(strike, side);
    const entry = matchIndex.get(key);
    if (!entry) return;
    const c = contracts[entry.rowIdx];
    if (!c) return;

    const ltp = typeof t.ltp === "number" ? t.ltp : undefined;
    if (ltp !== undefined) {
      const prev = prevLtp.get(key) ?? c.ltp;
      if (ltp !== prev) {
        // Indian price law: red = up, green = down. Direction is the
        // tick-vs-previous-tick move.
        const dir: Dir = ltp > prev ? "up" : "down";
        dirMap.set(key, dir);
        scheduleFlash(key, dir);
      }
      prevLtp.set(key, ltp);
      c.ltp = ltp;
    }
    if (typeof t.iv === "number") c.iv = t.iv;
    if (typeof t.oi === "number") c.oi = t.oi;
    if (typeof t.bid === "number") c.bid = t.bid;
    if (typeof t.ask === "number") c.ask = t.ask;
    lastTickAt = Date.now();
    live = now - lastTickAt <= LIVE_MS;
  }

  function scheduleFlash(key: string, dir: Dir): void {
    flashes[key] = dir;
    const prev = flashTimers.get(key);
    if (prev !== undefined) window.clearTimeout(prev);
    const id = window.setTimeout(() => {
      const next = { ...flashes };
      delete next[key];
      flashes = next;
      flashTimers.delete(key);
    }, FLASH_MS);
    flashTimers.set(key, id);
  }

  async function load(sym: string, exp: string, id: number): Promise<void> {
    loading = true;
    if (id === reqId) error = "";
    try {
      const q = `?symbol=${encodeURIComponent(sym)}&expiry=${encodeURIComponent(exp)}`;
      const resp = await get<OptionsResponse>(`/api/intelligence/options${q}`);
      if (id !== reqId) return; // superseded by a newer request
      applyResponse(resp);
    } catch (err) {
      if (id !== reqId) return;
      error = err instanceof Error ? err.message : String(err);
    } finally {
      if (id === reqId) loading = false;
    }
  }

  function applyResponse(resp: OptionsResponse): void {
    contracts = resp.contracts ?? [];
    if (resp.expiry) {
      if (!expiries.includes(resp.expiry)) expiries = [...expiries, resp.expiry].sort();
      expiry = resp.expiry;
      // Align the committed request with the expiry the server resolved
      // (e.g. nearest expiry when none was requested). Converges after one
      // reload — never loops, because the next response matches.
      if (resp.expiry !== snapshot.expiry) {
        snapshot = { symbol: snapshot.symbol, expiry: resp.expiry };
      }
    }
  }

  // Quiet 15s poll: refreshes LTP/IV/OI numbers without flashing or touching
  // per-tick direction colors (a flash storm across 100 rows every poll would
  // be noise, not signal).
  async function refreshSilently(): Promise<void> {
    if (loading) return; // never pile on an in-flight committed load
    try {
      const q = `?symbol=${encodeURIComponent(snapshot.symbol)}&expiry=${encodeURIComponent(snapshot.expiry)}`;
      const resp = await get<OptionsResponse>(`/api/intelligence/options${q}`);
      if (resp.contracts) contracts = resp.contracts;
      if (resp.expiry && !expiries.includes(resp.expiry)) {
        expiries = [...expiries, resp.expiry].sort();
      }
    } catch {
      /* silent — the committed load path surfaces errors */
    }
  }

  function commit(): void {
    snapshot = { symbol: symbol.trim().toUpperCase() || "NIFTY", expiry: expiry.trim() };
  }

  function fmtNum(value: number | undefined, digits = 2): string {
    if (value === undefined || !isFinite(value)) return "—";
    return value.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  function fmtOi(value: number | undefined): string {
    if (value === undefined) return "—";
    return Math.round(value).toLocaleString("en-IN");
  }

  function ltpCellClass(row: ChainRow, side: Side): string {
    const c = side === "ce" ? row.ce : row.pe;
    if (!c) return "";
    const key = contractKey(c.strike, side);
    const dir = dirMap.get(key);
    const flash = flashes[key];
    return cn(
      dir === "up" ? "price-up" : dir === "down" ? "price-down" : "",
      flash ? (flash === "up" ? "flash-up" : "flash-down") : "",
    );
  }

  // Arrow-key navigation over the chain. Handled per strike cell (the
  // focusable gridcells) so no non-interactive container carries the handler.
  // ArrowDown with no row focused picks the first row; ArrowUp the last.
  function onStrikeKeydown(event: KeyboardEvent, strike: number): void {
    if (rows.length === 0) return;
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const idx = rows.findIndex((r) => r.strike === strike);
    let next: number;
    if (event.key === "ArrowDown") {
      next = idx < 0 ? 0 : Math.min(idx + 1, rows.length - 1);
    } else {
      next = idx < 0 ? rows.length - 1 : Math.max(idx - 1, 0);
    }
    event.preventDefault();
    const s = rows[next].strike;
    selectedStrike = s;
    focusStrike(s);
  }

  function focusStrike(strike: number): void {
    const el = wrapEl?.querySelector<HTMLElement>(`[data-strike="${strike}"]`);
    el?.scrollIntoView({ block: "nearest" });
    el?.focus();
  }
</script>

<section class="panel chain">
  <header class="panel-head">
    <h2>Option Chain</h2>
    <div class="controls">
      <Input
        class="mono h-7 w-[110px]"
        bind:value={symbol}
        placeholder="SYMBOL"
        onchange={commit}
        onkeydown={(e) => e.key === "Enter" && commit()}
      />
      {#if expiries.length > 0}
        <select class="expiry-select mono" bind:value={expiry} onchange={commit}>
          {#each expiries as e (e)}
            <option value={e}>{e}</option>
          {/each}
        </select>
      {:else}
        <Input
          class="mono h-7 w-[130px]"
          bind:value={expiry}
          placeholder="EXPIRY (optional)"
          onchange={commit}
          onkeydown={(e) => e.key === "Enter" && commit()}
        />
      {/if}
      <span class="live-chip" class:on={live} title={live ? "Live: watchlisted contracts tick in; chain refreshes every 15s" : "Synchronizing — no recent ticks"}>
        <span class="live-dot" aria-hidden="true"></span>
        <span class="live-label">{live ? "LIVE" : "SYNC"}</span>
      </span>
    </div>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <CandleChart {symbol} {exchange} />

  <div class="table-wrap" bind:this={wrapEl}>
    <Table class="text-[12px]">
      <TableHeader>
        <TableRow class="hover:bg-transparent">
          <TableHead class="text-center font-semibold text-ink">Strike</TableHead>
          <TableHead class="text-right" colspan={3}>Call (CE)</TableHead>
          <TableHead class="text-right" colspan={3}>Put (PE)</TableHead>
        </TableRow>
        <TableRow class="hover:bg-transparent">
          <TableHead class="text-center text-faint"></TableHead>
          <TableHead class="text-right">LTP</TableHead>
          <TableHead class="text-right">IV</TableHead>
          <TableHead class="text-right">OI</TableHead>
          <TableHead class="text-right">LTP</TableHead>
          <TableHead class="text-right">IV</TableHead>
          <TableHead class="text-right">OI</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {#each rows as row (row.strike)}
          <TableRow
            class={cn(
              "chain-row h-6",
              selectedStrike === row.strike ? "border-l-2 border-l-accent bg-row-selected" : "",
            )}
          >
            <TableCell
              class="strike-cell"
              data-strike={String(row.strike)}
              tabindex={0}
              role="gridcell"
              aria-selected={selectedStrike === row.strike}
              onfocus={() => (selectedStrike = row.strike)}
              onclick={() => (selectedStrike = row.strike)}
              onkeydown={(e) => onStrikeKeydown(e, row.strike)}
            >
              {fmtNum(row.strike, 0)}
            </TableCell>
            <TableCell class={cn("mono-num px-1.5", ltpCellClass(row, "ce"))}>{fmtNum(row.ce?.ltp)}</TableCell>
            <TableCell class="mono-num px-1.5">{fmtNum(row.ce?.iv, 1)}</TableCell>
            <TableCell class="mono-num px-1.5">{fmtOi(row.ce?.oi)}</TableCell>
            <TableCell class={cn("mono-num px-1.5", ltpCellClass(row, "pe"))}>{fmtNum(row.pe?.ltp)}</TableCell>
            <TableCell class="mono-num px-1.5">{fmtNum(row.pe?.iv, 1)}</TableCell>
            <TableCell class="mono-num px-1.5">{fmtOi(row.pe?.oi)}</TableCell>
          </TableRow>
        {/each}
      </TableBody>
    </Table>
    {#if rows.length === 0 && !loading}
      <p class="empty">No chain data. {error ? "" : "Check the symbol or start the data pipeline."}</p>
    {/if}
  </div>
</section>

<style>
  .chain {
    display: flex;
    flex-direction: column;
    min-width: 720px;
    height: 100%;
  }
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
    flex-wrap: wrap;
  }
  .panel-head h2 {
    margin: 0;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-transform: uppercase;
    white-space: nowrap;
  }
  .controls {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .expiry-select {
    background: var(--canvas-raised);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    color: var(--body);
    padding: 5px 6px;
    font-size: 12px;
    max-width: 150px;
  }
  /* LIVE / SYNC chip replaces the removed manual Load button — the grid now
     streams ticks and auto-refreshes, so the affordance is a status, not an
     action. */
  .live-chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--faint);
    white-space: nowrap;
    text-transform: uppercase;
    padding: 2px 6px;
    border: 1px solid var(--hairline);
    border-radius: 2px;
    background: var(--canvas-raised);
  }
  .live-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: var(--faint);
    flex: none;
  }
  .live-chip.on {
    color: var(--accent);
    border-color: color-mix(in srgb, var(--accent) 35%, transparent);
  }
  .live-chip.on .live-dot {
    background: var(--accent);
    animation: live-pulse 1.2s ease-in-out infinite;
  }
  @keyframes live-pulse {
    0%,
    100% {
      opacity: 1;
    }
    50% {
      opacity: 0.35;
    }
  }
  @media (prefers-reduced-motion: reduce) {
    .live-chip.on .live-dot {
      animation: none;
    }
  }
  .table-wrap {
    flex: 1;
    overflow: auto;
  }
  /* 24px chain rows (DESIGN §4). These classes are applied to <td> / <tr>
     rendered by the table primitives (child components), so they must be
     :global — Svelte scoped CSS cannot target elements owned by a child.
     Numerals mono + tabular, right-aligned, never wrapping. Color is left to
     the global .price-up/.price-down tokens so tick direction wins. */
  :global(.mono-num) {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-size: 12px;
    text-align: right;
    white-space: nowrap;
  }
  /* Strike column centered in ticker mono (DESIGN prompt 3). */
  :global(.strike-cell) {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-size: 12px;
    font-weight: 600;
    color: var(--ink);
    text-align: center;
    white-space: nowrap;
    cursor: pointer;
    outline: none;
  }
  :global(.strike-cell:focus-visible) {
    box-shadow: inset 0 0 0 2px var(--focus-ring);
  }
  .empty {
    color: var(--faint);
    font-size: 12px;
    padding: 16px 10px;
    margin: 0;
  }
  .error {
    color: var(--danger);
    font-size: 11px;
    padding: 4px 10px;
    margin: 0;
  }
</style>
