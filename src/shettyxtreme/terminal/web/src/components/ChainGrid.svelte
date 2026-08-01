<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "../lib/api";

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

  let symbol = "NIFTY";
  let expiry = "";
  let expiries: string[] = [];
  let contracts: Contract[] = [];
  let loading = false;
  let error = "";

  $: rows = buildRows(contracts);

  onMount(() => {
    load();
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
      <input class="sym-input mono" bind:value={symbol} placeholder="SYMBOL" />
      {#if expiries.length > 0}
        <select class="expiry-select mono" bind:value={expiry}>
          {#each expiries as e (e)}
            <option value={e}>{e}</option>
          {/each}
        </select>
      {:else}
        <input class="sym-input mono" bind:value={expiry} placeholder="EXPIRY (optional)" />
      {/if}
      <button class="load-btn" on:click={load} disabled={loading}>{loading ? "…" : "LOAD"}</button>
    </div>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th class="strike-col">STRIKE</th>
          <th colspan="3">CALL (CE)</th>
          <th colspan="3">PUT (PE)</th>
        </tr>
        <tr>
          <th></th>
          <th>LTP</th>
          <th>IV</th>
          <th>OI</th>
          <th>LTP</th>
          <th>IV</th>
          <th>OI</th>
        </tr>
      </thead>
      <tbody>
        {#each rows as row (row.strike)}
          <tr>
            <td class="num strike-col">{fmtNum(row.strike, 0)}</td>
            <td class="num">{fmtNum(row.ce?.ltp)}</td>
            <td class="num">{fmtNum(row.ce?.iv, 1)}</td>
            <td class="num">{fmtOi(row.ce?.oi)}</td>
            <td class="num">{fmtNum(row.pe?.ltp)}</td>
            <td class="num">{fmtNum(row.pe?.iv, 1)}</td>
            <td class="num">{fmtOi(row.pe?.oi)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
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
  .sym-input {
    width: 110px;
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
  .expiry-select {
    background: var(--canvas-raised);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    color: var(--body);
    padding: 5px 6px;
    font-size: 12px;
    max-width: 150px;
  }
  .load-btn {
    background: var(--accent);
    border: 1px solid var(--accent);
    border-radius: 4px;
    color: var(--on-accent);
    font-weight: 700;
    font-size: 11px;
    padding: 5px 12px;
    cursor: pointer;
  }
  .load-btn:disabled {
    background: var(--accent-disabled);
    border-color: var(--accent-disabled);
    color: var(--muted);
    cursor: default;
  }
  .table-wrap {
    flex: 1;
    overflow: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  thead {
    position: sticky;
    top: 0;
    z-index: 1;
    background: var(--surface-elevated);
  }
  th {
    color: var(--muted);
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.05em;
    padding: 4px 6px;
    border-bottom: 1px solid var(--hairline-strong);
    text-align: right;
    white-space: nowrap;
  }
  th:nth-child(1),
  th:nth-child(2) {
    text-align: left;
  }
  td {
    padding: 3px 6px;
    text-align: right;
    border-bottom: 1px solid var(--hairline);
    height: 28px;
    white-space: nowrap;
  }
  td:last-child {
    text-align: right;
  }
  tbody tr:hover {
    background: var(--row-hover);
  }
  .strike-col {
    text-align: left !important;
    color: var(--ink);
    font-weight: 600;
  }
  .num {
    font-size: 12px;
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
