<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "../lib/api";
  import { selectedSymbol } from "../lib/selection";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
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

  let symbol = $state("NIFTY");
  let exchange = $state("NSE_FNO");
  let expiry = $state("");
  let expiries = $state<string[]>([]);
  let contracts = $state<Contract[]>([]);
  let loading = $state(false);
  let error = $state("");

  let rows = $derived(buildRows(contracts));

  onMount(() => {
    load();
    return selectedSymbol.subscribe((v) => {
      if (v && v !== symbol) {
        symbol = v;
        load();
      }
    });
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

  async function load(): Promise<void> {
    loading = true;
    error = "";
    try {
      const q = `?symbol=${encodeURIComponent(symbol)}&expiry=${encodeURIComponent(expiry)}`;
      const resp = await get<OptionsResponse>(`/api/intelligence/options${q}`);
      contracts = resp.contracts ?? [];
      if (resp.expiry && !expiries.includes(resp.expiry)) {
        expiries = [...expiries, resp.expiry].sort();
      }
      if (resp.expiry) expiry = resp.expiry;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
    loading = false;
  }

  function fmtNum(value: number | undefined, digits = 2): string {
    if (value === undefined || !isFinite(value)) return "—";
    return value.toLocaleString("en-IN", { minimumFractionDigits: digits, maximumFractionDigits: digits });
  }

  function fmtOi(value: number | undefined): string {
    if (value === undefined) return "—";
    return Math.round(value).toLocaleString("en-IN");
  }
</script>

<section class="panel chain">
  <header class="panel-head">
    <h2>Option Chain</h2>
    <div class="controls">
      <Input class="mono h-7 w-[110px]" bind:value={symbol} placeholder="SYMBOL" />
      {#if expiries.length > 0}
        <select class="expiry-select mono" bind:value={expiry}>
          {#each expiries as e (e)}
            <option value={e}>{e}</option>
          {/each}
        </select>
      {:else}
        <Input class="mono h-7 w-[130px]" bind:value={expiry} placeholder="EXPIRY (optional)" />
      {/if}
      <Button size="sm" onclick={load} disabled={loading}>{loading ? "Loading…" : "Load"}</Button>
    </div>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <CandleChart {symbol} {exchange} />

  <div class="table-wrap">
    <Table class="text-[12px]">
      <TableHeader>
        <TableRow class="hover:bg-transparent">
          <TableHead class="font-semibold text-ink">Strike</TableHead>
          <TableHead class="text-right" colspan={3}>Call (CE)</TableHead>
          <TableHead class="text-right" colspan={3}>Put (PE)</TableHead>
        </TableRow>
        <TableRow class="hover:bg-transparent">
          <TableHead class="font-semibold text-ink"></TableHead>
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
          <TableRow class="h-6">
            <TableCell class="font-mono text-right text-[12px] font-semibold text-ink tabular-nums">{fmtNum(row.strike, 0)}</TableCell>
            <TableCell class="font-mono text-right text-[12px] tabular-nums">{fmtNum(row.ce?.ltp)}</TableCell>
            <TableCell class="font-mono text-right text-[12px] tabular-nums">{fmtNum(row.ce?.iv, 1)}</TableCell>
            <TableCell class="font-mono text-right text-[12px] tabular-nums">{fmtOi(row.ce?.oi)}</TableCell>
            <TableCell class="font-mono text-right text-[12px] tabular-nums">{fmtNum(row.pe?.ltp)}</TableCell>
            <TableCell class="font-mono text-right text-[12px] tabular-nums">{fmtNum(row.pe?.iv, 1)}</TableCell>
            <TableCell class="font-mono text-right text-[12px] tabular-nums">{fmtOi(row.pe?.oi)}</TableCell>
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
  .table-wrap {
    flex: 1;
    overflow: auto;
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
