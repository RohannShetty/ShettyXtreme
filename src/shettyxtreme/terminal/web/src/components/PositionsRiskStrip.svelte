<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "../lib/api";
  import { onMessage } from "../lib/ws";

  type Position = {
    symbol: string;
    exchange: string;
    quantity: number;
    net_quantity: number;
    buy_avg: number | null;
    m2m: number;
    pnl: number;
    product: string;
  };

  type Risk = {
    daily_pnl: number;
    margin_used: number;
    margin_available: number;
    loss_limit: number;
    loss_limit_hit: boolean;
    max_positions: number;
    active_positions: number;
  };

  let positions: Position[] = [];
  let risk: Risk | null = null;
  let error = "";

  onMount(() => {
    load();
    return onMessage("position", () => load());
  });

  async function load(): Promise<void> {
    error = "";
    try {
      positions = await get<Position[]>("/api/execution/positions");
      risk = await get<Risk>("/api/execution/risk");
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  function pnlClass(value: number): string {
    return value > 0 ? "price-up" : value < 0 ? "price-down" : "";
  }

  function fmtMoney(value: number): string {
    const sign = value > 0 ? "+" : "";
    return `${sign}${value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  function fmtAvg(value: number): string {
    return value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  $: marginRatio =
    risk && risk.margin_used + risk.margin_available > 0
      ? risk.margin_used / (risk.margin_used + risk.margin_available)
      : 0;
  $: marginBreach = risk !== null && risk.margin_used > risk.margin_available;
  $: marginClass = marginBreach ? "ratio-breach" : marginRatio > 0.8 ? "ratio-warn" : "";
</script>

<section class="strip">
  <div class="pos-table">
    <h2>Positions</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>SYMBOL</th>
            <th>QTY</th>
            <th>AVG</th>
            <th>M2M</th>
            <th>P&L</th>
          </tr>
        </thead>
        <tbody>
          {#each positions as p (p.symbol)}
            <tr>
              <td class="ticker">{p.symbol}</td>
              <td class="num">{p.net_quantity}</td>
              <td class="num">{p.buy_avg ? fmtAvg(p.buy_avg) : "—"}</td>
              <td class="num {pnlClass(p.m2m)}">{fmtMoney(p.m2m)}</td>
              <td class="num {pnlClass(p.pnl)}">{fmtMoney(p.pnl)}</td>
            </tr>
          {/each}
          {#if positions.length === 0}
            <tr><td colspan="5" class="empty">No open positions.</td></tr>
          {/if}
        </tbody>
      </table>
    </div>
  </div>

  <div class="risk-block">
    <h2>Risk</h2>
    {#if risk}
      <div class="row">
        <span class="label">DAILY P&L</span>
        <span class="num value {pnlClass(risk.daily_pnl)}">{fmtMoney(risk.daily_pnl)}</span>
      </div>
      <div class="row">
        <span class="label">MARGIN</span>
        <div class="margin">
          <div class="bar">
            <div
              class="fill {marginClass}"
              style="width: {Math.min(marginRatio * 100, 100)}%"
            ></div>
          </div>
          <span class="num">{fmtMoney(risk.margin_used)} / {fmtMoney(risk.margin_available)}</span>
        </div>
      </div>
      <div class="row chips">
        {#if risk.loss_limit_hit}
          <span class="chip chip-danger">LOSS LIMIT HIT</span>
        {/if}
        {#if marginBreach}
          <span class="chip chip-danger">MARGIN BREACH</span>
        {:else if marginRatio > 0.8}
          <span class="chip chip-warn">MARGIN > 80%</span>
        {/if}
        <span class="chip chip-info">{risk.active_positions}/{risk.max_positions} POSITIONS</span>
      </div>
    {:else}
      <p class="empty">Loading risk…</p>
    {/if}
    {#if error}
      <p class="error">{error}</p>
    {/if}
  </div>
</section>

<style>
  .strip {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(300px, 360px);
    gap: 12px;
    min-height: 240px;
    padding: 10px;
    height: 100%;
  }
  .pos-table,
  .risk-block {
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  h2 {
    margin: 0 0 6px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .table-wrap {
    flex: 1;
    overflow-y: auto;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
  }
  thead {
    position: sticky;
    top: 0;
    background: var(--surface-elevated);
  }
  th {
    color: var(--muted);
    font-size: 10px;
    font-weight: 600;
    text-align: right;
    padding: 3px 8px;
    border-bottom: 1px solid var(--hairline-strong);
  }
  th:first-child {
    text-align: left;
  }
  td {
    padding: 3px 8px;
    text-align: right;
    border-bottom: 1px solid var(--hairline);
  }
  td:first-child {
    text-align: left;
  }
  td:last-child {
    text-align: right;
  }
  .num {
    font-size: 12px;
  }
  .ticker {
    color: var(--ink);
    font-weight: 600;
  }
  .empty {
    color: var(--faint);
    font-size: 12px;
    padding: 8px 0;
  }
  .risk-block {
    gap: 8px;
    border-left: 1px solid var(--hairline);
    padding-left: 12px;
  }
  .row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .label {
    color: var(--muted);
    font-size: 10px;
    letter-spacing: 0.06em;
    white-space: nowrap;
  }
  .value {
    font-size: 13px;
    font-weight: 600;
  }
  .margin {
    display: flex;
    flex-direction: column;
    gap: 4px;
    flex: 1;
    align-items: flex-end;
  }
  .bar {
    width: 100%;
    height: 5px;
    background: var(--canvas-raised);
    border-radius: 3px;
    overflow: hidden;
  }
  .fill {
    height: 100%;
    background: var(--accent);
    transition: width 120ms ease-out;
  }
  .fill.ratio-warn {
    background: var(--warning);
  }
  .fill.ratio-breach {
    background: var(--danger);
  }
  .chips {
    flex-wrap: wrap;
  }
  .chip {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.05em;
    border-radius: 4px;
    padding: 2px 6px;
    white-space: nowrap;
  }
  .chip-danger {
    color: var(--danger);
    border: 1px solid var(--danger);
  }
  .chip-warn {
    color: var(--warning);
    border: 1px solid var(--warning);
  }
  .chip-info {
    color: var(--info);
    border: 1px solid var(--info);
  }
  .error {
    color: var(--danger);
    font-size: 11px;
    margin: 0;
  }
</style>
