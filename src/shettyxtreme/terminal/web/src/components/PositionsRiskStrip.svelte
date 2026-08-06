<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "../lib/api";
  import { onMessage } from "../lib/ws";
  import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
  } from "$lib/components/ui/table";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import EmptyState from "./state/EmptyState.svelte";
  import LoadingState from "./state/LoadingState.svelte";
  import ErrorState from "./state/ErrorState.svelte";

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
    margin_available: number | null; // null = unknown, never pretend it is 0
    loss_limit: number;
    loss_limit_hit: boolean;
    max_positions: number;
    active_positions: number;
  };

  let positions = $state<Position[]>([]);
  let risk = $state<Risk | null>(null);
  let error = $state("");
  let loading = $state(true);

  onMount(() => {
    load();
    return onMessage("position", () => load());
  });

  async function load(): Promise<void> {
    error = "";
    loading = true;
    try {
      positions = await get<Position[]>("/api/execution/positions");
      risk = await get<Risk>("/api/execution/risk");
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
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

  let marginUnknown = $derived(risk !== null && risk.margin_available === null);
  let marginRatio = $derived(
    risk && risk.margin_available !== null && risk.margin_used + risk.margin_available > 0
      ? risk.margin_used / (risk.margin_used + risk.margin_available)
      : 0,
  );
  let marginBreach = $derived(
    risk !== null &&
      risk.margin_available !== null &&
      risk.margin_used > risk.margin_available,
  );
  let marginClass = $derived(marginBreach ? "ratio-breach" : marginRatio > 0.8 ? "ratio-warn" : "");
</script>

<section class="strip">
  <div class="pos-table">
    <h2>Positions</h2>
    <ScrollArea class="flex-1 min-h-0">
      {#if loading && positions.length === 0}
        <LoadingState label="Loading positions…" rows={3} />
      {:else if positions.length === 0}
        <EmptyState message="No open positions." />
      {:else}
        <Table>
          <TableHeader>
            <TableRow class="hover:bg-transparent">
              <TableHead>Symbol</TableHead>
              <TableHead class="text-right">Qty</TableHead>
              <TableHead class="text-right">Avg</TableHead>
              <TableHead class="text-right">M2M</TableHead>
              <TableHead class="text-right">P&L</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {#each positions as p (p.symbol)}
              <TableRow>
                <TableCell class="font-mono font-semibold text-ink">{p.symbol}</TableCell>
                <TableCell class="font-mono text-right tabular-nums">{p.net_quantity}</TableCell>
                <TableCell class="font-mono text-right tabular-nums">{p.buy_avg ? fmtAvg(p.buy_avg) : "—"}</TableCell>
                <TableCell class="font-mono text-right tabular-nums {pnlClass(p.m2m)}">{fmtMoney(p.m2m)}</TableCell>
                <TableCell class="font-mono text-right tabular-nums {pnlClass(p.pnl)}">{fmtMoney(p.pnl)}</TableCell>
              </TableRow>
            {/each}
          </TableBody>
        </Table>
      {/if}
    </ScrollArea>
  </div>

  <div class="risk-block">
    <h2>Risk</h2>
    {#if error}
      <ErrorState message={error} onRetry={load} />
    {:else if loading && risk === null}
      <LoadingState label="Loading risk…" rows={2} />
    {:else if risk}
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
              style="width: {marginUnknown ? 0 : Math.min(marginRatio * 100, 100)}%"
            ></div>
          </div>
          <span class="num">
            {fmtMoney(risk.margin_used)} / {marginUnknown ? "—" : fmtMoney(risk.margin_available ?? 0)}
          </span>
        </div>
      </div>
      <div class="row chips">
        {#if risk.loss_limit_hit}
          <span class="chip chip-danger">LOSS LIMIT HIT</span>
        {/if}
        {#if marginUnknown}
          <span class="chip chip-mute">MARGIN UNKNOWN</span>
        {:else if marginBreach}
          <span class="chip chip-danger">MARGIN BREACH</span>
        {:else if marginRatio > 0.8}
          <span class="chip chip-warn">MARGIN > 80%</span>
        {/if}
        <span class="chip chip-info">{risk.active_positions}/{risk.max_positions} POSITIONS</span>
      </div>
    {:else}
      <EmptyState message="No risk data." />
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
    /* Level-1 hairline card on the canvas (DESIGN §2.2/§6): the strip is a
       panel, not a bare surface. */
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-radius: 6px;
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
  .chip-mute {
    color: var(--faint);
    border: 1px solid var(--hairline-strong);
  }
</style>
