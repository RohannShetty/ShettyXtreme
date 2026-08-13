<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "../lib/api";
  import { onMessage } from "../lib/ws";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import EmptyState from "./state/EmptyState.svelte";
  import LoadingState from "./state/LoadingState.svelte";
  import ErrorState from "./state/ErrorState.svelte";

  type SectorItem = {
    sector: string;
    notional: number;
    pnl: number;
    share_pct: number;
  };

  type GreeksBreakdown = {
    long_val: number;
    short_val: number;
    net: number;
  };

  type GreeksConc = {
    delta: GreeksBreakdown;
    gamma: GreeksBreakdown;
    theta: GreeksBreakdown;
    vega: GreeksBreakdown;
    lopsided_warning: string | null;
  };

  type ScenarioPnl = {
    shift_pct: number;
    total_pnl: number;
  };

  type Stress = {
    scenarios: ScenarioPnl[];
    worst_case_pnl: number;
    worst_case_shift: number;
  };

  type MarginUtil = {
    margin_used: number | null;
    margin_available: number | null;
    total: number | null;
    utilization_pct: number | null;
    breach: boolean;
  };

  type HeatmapData = {
    sector_exposure: SectorItem[];
    greeks: GreeksConc;
    stress: Stress;
    margin: MarginUtil;
    position_count: number;
    enriched_count: number;
  };

  const REFRESH_MS = 15_000;

  let data = $state<HeatmapData | null>(null);
  let loading = $state(true);
  let error = $state("");
  let refreshTimer: number | undefined;

  onMount(() => {
    void load();
    refreshTimer = window.setInterval(() => void load(), REFRESH_MS);
    const offRisk = onMessage("risk", () => void load());
    return () => {
      offRisk();
      if (refreshTimer !== undefined) clearInterval(refreshTimer);
    };
  });

  async function load(): Promise<void> {
    try {
      data = await get<HeatmapData>("/api/execution/risk/heatmap");
      error = "";
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  function fmtMoney(value: number): string {
    const sign = value > 0 ? "+" : "";
    return `${sign}${value.toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
  }

  function fmtNum(value: number, decimals = 2): string {
    if (!isFinite(value) || value === 0) return "—";
    return value.toLocaleString("en-IN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  }

  function fmtPct(value: number): string {
    return `${value.toFixed(1)}%`;
  }

  function pnlClass(value: number): string {
    return value > 0 ? "price-up" : value < 0 ? "price-down" : "";
  }

  function heatOpacity(sharePct: number, maxShare: number): number {
    if (maxShare <= 0) return 0.15;
    return 0.15 + (sharePct / maxShare) * 0.7;
  }

  function barWidth(value: number, maxAbs: number): number {
    if (maxAbs <= 0) return 0;
    return Math.min(Math.abs(value) / maxAbs * 100, 100);
  }

  function sectorBg(sharePct: number, maxShare: number, pnl: number): string {
    const opacity = heatOpacity(sharePct, maxShare);
    // Use CSS custom properties to follow the convention toggle.
    // Reads the computed values of --price-up-soft / --price-down-soft at render time.
    if (typeof window === "undefined") return "";
    const root = document.documentElement;
    const style = getComputedStyle(root);
    const upRaw = style.getPropertyValue("--price-up").trim();
    const downRaw = style.getPropertyValue("--price-down").trim();
    // Convert hex to rgba with opacity
    const hex = pnl >= 0 ? upRaw : downRaw;
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${opacity})`;
  }

  function greekRows(g: GreeksConc) {
    return [
      { label: "Δ DELTA", long: g.delta.long_val, short: g.delta.short_val, net: g.delta.net },
      { label: "Γ GAMMA", long: g.gamma.long_val, short: g.gamma.short_val, net: g.gamma.net },
      { label: "Θ THETA", long: g.theta.long_val, short: g.theta.short_val, net: g.theta.net },
      { label: "V VEGA", long: g.vega.long_val, short: g.vega.short_val, net: g.vega.net },
    ];
  }

  function greekMaxAbs(g: GreeksConc): number {
    return Math.max(
      Math.abs(g.delta.long_val), Math.abs(g.delta.short_val),
      Math.abs(g.gamma.long_val), Math.abs(g.gamma.short_val),
      Math.abs(g.theta.long_val), Math.abs(g.theta.short_val),
      Math.abs(g.vega.long_val), Math.abs(g.vega.short_val),
      0.001
    );
  }
</script>

<section class="heatmap">
  <h2>RISK HEAT MAP</h2>

  {#if loading && data === null}
    <LoadingState label="Loading risk heat map…" rows={4} />
  {:else if error}
    <ErrorState message={error} onRetry={load} />
  {:else if data === null}
    <EmptyState message="No risk data available." />
  {:else if data.position_count === 0}
    <EmptyState message="No open positions to analyze." />
  {:else}
    {@const maxShare = Math.max(...data.sector_exposure.map(s => s.share_pct), 1)}
    {@const maxAbs = greekMaxAbs(data.greeks)}
    {@const marginUnknown = data.margin.margin_used === null && data.margin.margin_available === null}
    {@const marginRatio = data.margin.utilization_pct !== null ? data.margin.utilization_pct / 100 : 0}
    {@const marginBarClass = data.margin.breach ? "breach" : marginRatio > 0.8 ? "warn" : ""}
    <ScrollArea class="flex-1 min-h-0">
      <div class="grid">
        <!-- 1. Sector Exposure -->
        <div class="block">
          <h3>SECTOR EXPOSURE</h3>
          {#if data.sector_exposure.length === 0}
            <p class="empty-text">No sector data.</p>
          {:else}
            <div class="sector-grid">
              {#each data.sector_exposure as s (s.sector)}
                <div class="sector-cell" style="background: {sectorBg(s.share_pct, maxShare, s.pnl)}">
                  <span class="sector-name">{s.sector}</span>
                  <span class="sector-pct mono">{fmtPct(s.share_pct)}</span>
                  <span class="sector-pnl mono {pnlClass(s.pnl)}">{fmtMoney(s.pnl)}</span>
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <!-- 2. Greeks Concentration -->
        <div class="block">
          <h3>GREEKS CONCENTRATION</h3>
          <div class="greeks-bars">
            {#each greekRows(data.greeks) as gr (gr.label)}
              <div class="greek-row">
                <span class="greek-label">{gr.label}</span>
                <div class="bar-container">
                  <div class="bar-track">
                    <div
                      class="bar-fill bar-long"
                      style="width: {barWidth(gr.long, maxAbs)}%"
                    ></div>
                  </div>
                  <div class="bar-track">
                    <div
                      class="bar-fill bar-short"
                      style="width: {barWidth(gr.short, maxAbs)}%"
                    ></div>
                  </div>
                </div>
                <span class="greek-net mono">{fmtNum(gr.net)}</span>
              </div>
            {/each}
          </div>
          {#if data.greeks.lopsided_warning}
            <div class="lopsided-chip">
              <span class="chip chip-warn">{data.greeks.lopsided_warning.toUpperCase()}</span>
            </div>
          {/if}
        </div>

        <!-- 3. Stress Test -->
        <div class="block">
          <h3>STRESS TEST</h3>
          {#if data.stress.scenarios.length === 0}
            <p class="empty-text">No stress data.</p>
          {:else}
            <table class="stress-table">
              <thead>
                <tr>
                  <th>SHIFT</th>
                  <th class="text-right">P&L</th>
                </tr>
              </thead>
              <tbody>
                {#each data.stress.scenarios as sc (sc.shift_pct)}
                  <tr class:worst-row={sc.shift_pct === data.stress.worst_case_shift}>
                    <td class="mono shift-cell">
                      {sc.shift_pct > 0 ? "+" : ""}{sc.shift_pct}%
                    </td>
                    <td class="mono text-right {pnlClass(sc.total_pnl)}">
                      {fmtMoney(sc.total_pnl)}
                      {#if sc.shift_pct === data.stress.worst_case_shift}
                        <span class="worst-badge">WORST</span>
                      {/if}
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        </div>

        <!-- 4. Margin Utilization -->
        <div class="block">
          <h3>MARGIN UTILIZATION</h3>
          {#if marginUnknown}
            <p class="empty-text">Margin data unavailable.</p>
          {:else}
            <div class="margin-bar-wrap">
              <div class="margin-bar">
                <div
                  class="margin-fill {marginBarClass}"
                  style="width: {Math.min(marginRatio * 100, 100)}%"
                ></div>
              </div>
              <div class="margin-labels">
                <span class="mono">{data.margin.margin_used !== null ? fmtMoney(data.margin.margin_used) : "—"}</span>
                <span class="margin-sep">/</span>
                <span class="mono">{data.margin.margin_available !== null ? fmtMoney(data.margin.margin_available) : "—"}</span>
              </div>
            </div>
            <div class="margin-chips">
              {#if data.margin.breach}
                <span class="chip chip-danger">MARGIN BREACH</span>
              {:else if marginRatio > 0.8}
                <span class="chip chip-warn">MARGIN > 80%</span>
              {/if}
              {#if data.margin.utilization_pct !== null}
                <span class="chip chip-info">{fmtPct(data.margin.utilization_pct)} USED</span>
              {/if}
            </div>
          {/if}
        </div>
      </div>
    </ScrollArea>
  {/if}
</section>

<style>
  .heatmap {
    display: flex;
    flex-direction: column;
    min-height: 240px;
    padding: 10px;
    height: 100%;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-radius: 6px;
  }
  h2 {
    margin: 0 0 8px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-transform: uppercase;
  }
  h3 {
    margin: 0 0 6px;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--faint);
    text-transform: uppercase;
  }
  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    min-height: 0;
  }
  .block {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px;
    background: var(--canvas-raised);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    min-height: 0;
  }
  .empty-text {
    font-size: 11px;
    color: var(--faint);
    margin: 0;
  }
  .mono {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
  }
  .text-right {
    text-align: right;
  }

  /* Sector grid */
  .sector-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
    gap: 4px;
  }
  .sector-cell {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 6px 8px;
    border-radius: 4px;
    min-width: 0;
  }
  .sector-name {
    font-size: 10px;
    font-weight: 600;
    color: var(--ink);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sector-pct {
    font-size: 12px;
    font-weight: 600;
    color: var(--ink);
  }
  .sector-pnl {
    font-size: 10px;
  }

  /* Greeks bars */
  .greeks-bars {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .greek-row {
    display: grid;
    grid-template-columns: 60px 1fr 50px;
    gap: 6px;
    align-items: center;
  }
  .greek-label {
    font-size: 9px;
    font-weight: 600;
    color: var(--muted);
    letter-spacing: 0.04em;
    white-space: nowrap;
  }
  .bar-container {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .bar-track {
    width: 100%;
    height: 4px;
    background: var(--surface-elevated);
    border-radius: 2px;
    overflow: hidden;
  }
  .bar-fill {
    height: 100%;
    border-radius: 2px;
    transition: width 120ms ease-out;
  }
  .bar-long {
    background: var(--price-up);
  }
  .bar-short {
    background: var(--price-down);
  }
  .greek-net {
    font-size: 10px;
    text-align: right;
    color: var(--body);
  }
  .lopsided-chip {
    margin-top: 4px;
  }

  /* Stress table */
  .stress-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
  }
  .stress-table th {
    font-size: 9px;
    font-weight: 600;
    color: var(--muted);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    padding: 2px 6px;
    border-bottom: 1px solid var(--hairline-strong);
    text-align: left;
  }
  .stress-table td {
    padding: 3px 6px;
    border-bottom: 1px solid var(--hairline);
  }
  .shift-cell {
    font-weight: 500;
  }
  .worst-row {
    background: rgba(229, 72, 77, 0.08);
  }
  .worst-badge {
    font-size: 8px;
    font-weight: 700;
    color: var(--danger);
    margin-left: 4px;
    letter-spacing: 0.04em;
  }

  /* Margin gauge */
  .margin-bar-wrap {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .margin-bar {
    width: 100%;
    height: 6px;
    background: var(--surface-elevated);
    border-radius: 3px;
    overflow: hidden;
  }
  .margin-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 3px;
    transition: width 120ms ease-out;
  }
  .margin-fill.warn {
    background: var(--warning);
  }
  .margin-fill.breach {
    background: var(--danger);
  }
  .margin-labels {
    display: flex;
    gap: 4px;
    font-size: 11px;
    color: var(--body);
    align-items: center;
  }
  .margin-sep {
    color: var(--faint);
    font-size: 10px;
  }
  .margin-chips {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    margin-top: 4px;
  }

  /* Chips */
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

  /* Color overrides */
  .price-up {
    color: var(--price-up);
  }
  .price-down {
    color: var(--price-down);
  }
</style>
