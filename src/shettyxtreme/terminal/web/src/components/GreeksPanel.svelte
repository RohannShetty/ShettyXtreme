<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "../lib/api";
  import { onMessage } from "../lib/ws";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import {
    Table,
    TableBody,
    TableCell,
    TableHead,
    TableHeader,
    TableRow,
  } from "$lib/components/ui/table";

  type PositionGreek = {
    symbol: string;
    net_quantity: number;
    strike?: number | null;
    option_type?: string | null;
    expiry?: string | null;
    greeks?: {
      delta: number;
      gamma: number;
      theta: number;
      vega: number;
    } | null;
  };

  type PortfolioGreeks = {
    net_delta: number;
    net_gamma: number;
    net_theta: number;
    net_vega: number;
    positions: PositionGreek[];
  };

  const REFRESH_MS = 15_000;

  let data = $state<PortfolioGreeks | null>(null);
  let loading = $state(true);
  let error = $state("");
  let lastUpdated = $state<Date | null>(null);

  let refreshTimer: number | undefined;

  onMount(() => {
    void load();
    refreshTimer = window.setInterval(() => void load(), REFRESH_MS);
    return () => {
      if (refreshTimer !== undefined) window.clearInterval(refreshTimer);
    };
  });

  async function load(): Promise<void> {
    try {
      data = await get<PortfolioGreeks>("/api/execution/portfolio-greeks");
      lastUpdated = new Date();
      error = "";
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  function fmtNum(value: number, digits = 2): string {
    if (!isFinite(value)) return "—";
    return value.toLocaleString("en-IN", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  function fmtGreek(value: number | undefined, digits = 2): string {
    if (value === undefined || !isFinite(value) || value === 0) return "—";
    return value.toLocaleString("en-IN", {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    });
  }

  function deltaClass(value: number): string {
    return value > 0 ? "price-up" : value < 0 ? "price-down" : "";
  }

  let optionPositions = $derived(
    (data?.positions ?? []).filter((p) => p.greeks !== null && p.greeks !== undefined),
  );
</script>

<section class="panel greeks-panel">
  <header class="panel-head">
    <h2>Portfolio Greeks</h2>
    {#if lastUpdated}
      <span class="updated">
        {lastUpdated.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
      </span>
    {/if}
  </header>

  {#if error && !data}
    <p class="error">{error}</p>
  {/if}

  {#if loading && !data}
    <div class="tiles">
      {#each ["Δ", "Γ", "Θ", "V"] as label (label)}
        <div class="tile">
          <span class="tile-label">{label}</span>
          <span class="tile-value skeleton-block">—</span>
        </div>
      {/each}
    </div>
  {:else if data}
    <div class="tiles">
      <div class="tile">
        <span class="tile-label">NET Δ</span>
        <span class="tile-value {deltaClass(data.net_delta)}">{fmtNum(data.net_delta)}</span>
      </div>
      <div class="tile">
        <span class="tile-label">NET Γ</span>
        <span class="tile-value">{fmtNum(data.net_gamma, 4)}</span>
      </div>
      <div class="tile">
        <span class="tile-label">NET Θ</span>
        <span class="tile-value">{fmtNum(data.net_theta)}</span>
      </div>
      <div class="tile">
        <span class="tile-label">NET V</span>
        <span class="tile-value">{fmtNum(data.net_vega)}</span>
      </div>
    </div>

    {#if optionPositions.length > 0}
      <div class="positions-table">
        <ScrollArea class="flex-1 min-h-0">
          <Table class="text-[11px]">
            <TableHeader>
              <TableRow class="hover:bg-transparent">
                <TableHead>Symbol</TableHead>
                <TableHead class="text-right" title="Strike price">Strike</TableHead>
                <TableHead class="text-right" title="Option type">Type</TableHead>
                <TableHead class="text-right" title="Expiry">Exp</TableHead>
                <TableHead class="text-right">Qty</TableHead>
                <TableHead class="text-right">Δ</TableHead>
                <TableHead class="text-right">Γ</TableHead>
                <TableHead class="text-right">Θ</TableHead>
                <TableHead class="text-right">V</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {#each optionPositions as p (p.symbol)}
                <TableRow>
                  <TableCell class="font-mono font-semibold text-ink">{p.symbol}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums">{p.strike ?? "—"}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums {p.option_type === 'CE' ? 'text-option-call' : p.option_type === 'PE' ? 'text-option-put' : ''}">{p.option_type ?? "—"}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums text-xs">{p.expiry ?? "—"}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums">{p.net_quantity}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums {deltaClass(p.greeks?.delta ?? 0)}">{fmtGreek(p.greeks?.delta)}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums">{fmtGreek(p.greeks?.gamma, 4)}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums">{fmtGreek(p.greeks?.theta)}</TableCell>
                  <TableCell class="font-mono text-right tabular-nums">{fmtGreek(p.greeks?.vega)}</TableCell>
                </TableRow>
              {/each}
            </TableBody>
          </Table>
        </ScrollArea>
      </div>
    {:else}
      <p class="empty">No option positions with greeks.</p>
    {/if}
  {:else}
    <p class="empty">No portfolio greeks data.</p>
  {/if}
</section>

<style>
  .greeks-panel {
    display: flex;
    flex-direction: column;
    min-width: 0;
    height: 100%;
    gap: 8px;
  }
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 6px 10px;
    border-bottom: 1px solid var(--hairline);
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
  .updated {
    font-size: 10px;
    font-family: var(--font-mono);
    color: var(--faint);
  }
  /* Summary tiles — 4-column grid (Net Δ/Γ/Θ/V). */
  .tiles {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
    padding: 6px 10px;
  }
  .tile {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 6px 8px;
    background: var(--canvas-raised);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    min-width: 0;
  }
  .tile-label {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .tile-value {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-size: 13px;
    font-weight: 600;
    color: var(--ink);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .skeleton-block {
    color: var(--faint);
  }
  .positions-table {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
  .empty {
    color: var(--faint);
    font-size: 12px;
    padding: 12px 10px;
    margin: 0;
    text-align: center;
  }
  .error {
    color: var(--danger);
    font-size: 11px;
    padding: 4px 10px;
    margin: 0;
  }
</style>
