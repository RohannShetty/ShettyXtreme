<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import {
    getGreeksHistory,
    getRiskHeatmap,
    get,
    type GreeksHistoryPoint,
    type RiskHeatmapData,
  } from "../lib/api";
  import { lineChart } from "../lib/charts";
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
  import { Button } from "$lib/components/ui/button";
  import { Card, CardContent, CardHeader, CardTitle } from "$lib/components/ui/card";
  import EmptyState from "./state/EmptyState.svelte";
  import ErrorState from "./state/ErrorState.svelte";
  import LoadingState from "./state/LoadingState.svelte";

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

  type SortKey = "symbol" | "strike" | "option_type" | "expiry" | "net_quantity" | "delta" | "gamma" | "theta" | "vega";
  type SortDir = "asc" | "desc";
  type GreekKey = "net_delta" | "net_gamma" | "net_theta" | "net_vega";

  const REFRESH_MS = 15_000;
  const HISTORY_RANGES: { label: string; days: 1 | 7 | 30 }[] = [
    { label: "1D", days: 1 },
    { label: "7D", days: 7 },
    { label: "30D", days: 30 },
  ];

  // Portfolio greeks state
  let greeksData = $state<PortfolioGreeks | null>(null);
  let loadingGreeks = $state(true);
  let errorGreeks = $state("");

  // Greeks history state
  let historyData = $state<GreeksHistoryPoint[]>([]);
  let historyDays = $state<1 | 7 | 30>(7);
  let loadingHistory = $state(true);
  let errorHistory = $state("");

  // Risk heatmap state
  let riskData = $state<RiskHeatmapData | null>(null);
  let loadingRisk = $state(true);
  let errorRisk = $state("");

  let lastUpdated = $state<Date | null>(null);
  let sortKey = $state<SortKey>("symbol");
  let sortDir = $state<SortDir>("asc");

  let marginUnknown = $derived(
    riskData ? riskData.margin.margin_used === null && riskData.margin.margin_available === null : true,
  );
  let marginRatio = $derived(
    riskData && riskData.margin.utilization_pct !== null ? riskData.margin.utilization_pct / 100 : 0,
  );
  let marginBarClass = $derived(
    riskData ? (riskData.margin.breach ? "breach" : marginRatio > 0.8 ? "warn" : "") : "",
  );

  let refreshTimer: number | undefined;

  onMount(() => {
    void loadAll();
    refreshTimer = window.setInterval(() => void loadAll(), REFRESH_MS);
    const offPosition = onMessage("position", () => void loadGreeks());
    const offRisk = onMessage("risk", () => void loadRisk());
    return () => {
      offPosition();
      offRisk();
      if (refreshTimer !== undefined) window.clearInterval(refreshTimer);
    };
  });

  onDestroy(() => {
    if (refreshTimer !== undefined) window.clearInterval(refreshTimer);
  });

  async function loadAll(): Promise<void> {
    await Promise.all([loadGreeks(), loadHistory(), loadRisk()]);
    lastUpdated = new Date();
  }

  async function loadGreeks(): Promise<void> {
    try {
      greeksData = await get<PortfolioGreeks>("/api/execution/portfolio-greeks");
      errorGreeks = "";
    } catch (err) {
      errorGreeks = err instanceof Error ? err.message : String(err);
    } finally {
      loadingGreeks = false;
    }
  }

  async function loadHistory(): Promise<void> {
    loadingHistory = true;
    try {
      historyData = await getGreeksHistory(historyDays);
      errorHistory = "";
    } catch (err) {
      errorHistory = err instanceof Error ? err.message : String(err);
    } finally {
      loadingHistory = false;
    }
  }

  async function loadRisk(): Promise<void> {
    try {
      riskData = await getRiskHeatmap();
      errorRisk = "";
    } catch (err) {
      errorRisk = err instanceof Error ? err.message : String(err);
    } finally {
      loadingRisk = false;
    }
  }

  function setDays(days: 1 | 7 | 30): void {
    if (days === historyDays) return;
    historyDays = days;
    void loadHistory();
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

  function fmtMoney(value: number): string {
    const sign = value > 0 ? "+" : "";
    return `${sign}${value.toLocaleString("en-IN", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
  }

  function fmtPct(value: number): string {
    return `${value.toFixed(1)}%`;
  }

  function deltaClass(value: number): string {
    return value > 0 ? "price-up" : value < 0 ? "price-down" : "";
  }

  function pnlClass(value: number): string {
    return value > 0 ? "price-up" : value < 0 ? "price-down" : "";
  }

  function sortClass(key: SortKey): string {
    if (sortKey !== key) return "";
    return sortDir === "asc" ? "sort-asc" : "sort-desc";
  }

  function toggleSort(key: SortKey): void {
    if (sortKey === key) {
      sortDir = sortDir === "asc" ? "desc" : "asc";
    } else {
      sortKey = key;
      sortDir = "asc";
    }
  }

  function sortValue(p: PositionGreek, key: SortKey): number | string {
    switch (key) {
      case "symbol":
        return p.symbol;
      case "strike":
        return p.strike ?? 0;
      case "option_type":
        return p.option_type ?? "";
      case "expiry":
        return p.expiry ?? "";
      case "net_quantity":
        return p.net_quantity;
      case "delta":
        return p.greeks?.delta ?? 0;
      case "gamma":
        return p.greeks?.gamma ?? 0;
      case "theta":
        return p.greeks?.theta ?? 0;
      case "vega":
        return p.greeks?.vega ?? 0;
      default:
        return p.symbol;
    }
  }

  let optionPositions = $derived(
    (greeksData?.positions ?? []).filter((p) => p.greeks !== null && p.greeks !== undefined),
  );

  let sortedPositions = $derived(
    [...optionPositions].sort((a, b) => {
      const av = sortValue(a, sortKey);
      const bv = sortValue(b, sortKey);
      const dir = sortDir === "asc" ? 1 : -1;
      if (typeof av === "number" && typeof bv === "number") {
        return (av - bv) * dir;
      }
      return String(av).localeCompare(String(bv)) * dir;
    }),
  );

  function chartPoints(key: GreekKey): { x: Date; y: number }[] {
    return historyData.map((h) => ({ x: new Date(h.timestamp), y: h[key] }));
  }

  function greekChart(key: GreekKey, label: string): string {
    const points = chartPoints(key);
    return lineChart(points, {
      width: 320,
      height: 120,
      margin: { top: 10, right: 10, bottom: 24, left: 48 },
      lineColor: "var(--accent)",
      markerColor: "var(--accent)",
      yFormatter: (v) => {
        const abs = Math.abs(v);
        if (abs >= 1000) return `${(v / 1000).toFixed(1)}k`;
        if (abs >= 1) return v.toFixed(1);
        return v.toFixed(3);
      },
      ariaLabel: `${label} history`,
      title: label,
    });
  }

  const SECTOR_COLORS = [
    "var(--accent)",
    "var(--info)",
    "var(--success)",
    "var(--warning)",
    "var(--muted)",
    "var(--price-up)",
    "var(--price-down)",
  ];

  function sectorColor(index: number): string {
    return SECTOR_COLORS[index % SECTOR_COLORS.length];
  }

  function scenarioName(shift: number): string {
    return shift === 0 ? "BASE" : shift > 0 ? `+${shift}% SPOT` : `${shift}% SPOT`;
  }
</script>

<section class="panel greeks-panel">
  <header class="panel-head">
    <h2>Portfolio Greeks</h2>
    <div class="head-actions">
      {#if lastUpdated}
        <span class="updated">
          {lastUpdated.toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
        </span>
      {/if}
      <div class="range-group" role="group" aria-label="History range">
        {#each HISTORY_RANGES as r (r.days)}
          <Button
            variant={historyDays === r.days ? "default" : "outline"}
            size="sm"
            class="h-6 px-2 text-[10px]"
            onclick={() => setDays(r.days)}
            aria-pressed={historyDays === r.days}
          >
            {r.label}
          </Button>
        {/each}
      </div>
    </div>
  </header>

  {#if errorGreeks && !greeksData}
    <ErrorState message={errorGreeks} onRetry={loadAll} />
  {/if}

  {#if loadingGreeks && !greeksData}
    <div class="tiles">
      {#each ["NET Δ", "NET Γ", "NET Θ", "NET V"] as label (label)}
        <div class="tile">
          <span class="tile-label">{label}</span>
          <span class="tile-value skeleton-block">—</span>
        </div>
      {/each}
    </div>
  {:else if greeksData}
    <div class="tiles">
      <div class="tile">
        <span class="tile-label">NET Δ</span>
        <span class="tile-value {deltaClass(greeksData.net_delta)}">{fmtNum(greeksData.net_delta)}</span>
      </div>
      <div class="tile">
        <span class="tile-label">NET Γ</span>
        <span class="tile-value">{fmtNum(greeksData.net_gamma, 4)}</span>
      </div>
      <div class="tile">
        <span class="tile-label">NET Θ</span>
        <span class="tile-value">{fmtNum(greeksData.net_theta)}</span>
      </div>
      <div class="tile">
        <span class="tile-label">NET V</span>
        <span class="tile-value">{fmtNum(greeksData.net_vega)}</span>
      </div>
    </div>
  {/if}

  <ScrollArea class="flex-1 min-h-0">
    <div class="content">
      <!-- Greeks history charts -->
      <Card class="section-card">
        <CardHeader class="section-header">
          <CardTitle class="section-title">Greeks History</CardTitle>
          {#if loadingHistory && historyData.length === 0}
            <span class="status-chip">loading</span>
          {:else if errorHistory}
            <span class="status-chip status-error">error</span>
          {/if}
        </CardHeader>
        <CardContent class="section-body">
          {#if loadingHistory && historyData.length === 0}
            <LoadingState label="Loading greeks history…" rows={2} />
          {:else if errorHistory && historyData.length === 0}
            <ErrorState message={errorHistory} onRetry={loadHistory} />
          {:else if historyData.length === 0}
            <EmptyState message="No greeks history for the selected range." />
          {:else}
            <div class="chart-grid">
              <div class="chart-cell">
                <span class="chart-label">Net Delta</span>
                {@html greekChart("net_delta", "Net Delta")}
              </div>
              <div class="chart-cell">
                <span class="chart-label">Net Gamma</span>
                {@html greekChart("net_gamma", "Net Gamma")}
              </div>
              <div class="chart-cell">
                <span class="chart-label">Net Theta</span>
                {@html greekChart("net_theta", "Net Theta")}
              </div>
              <div class="chart-cell">
                <span class="chart-label">Net Vega</span>
                {@html greekChart("net_vega", "Net Vega")}
              </div>
            </div>
          {/if}
        </CardContent>
      </Card>

      <!-- Enhanced risk metrics -->
      <Card class="section-card">
        <CardHeader class="section-header">
          <CardTitle class="section-title">Risk Metrics</CardTitle>
          {#if loadingRisk && !riskData}
            <span class="status-chip">loading</span>
          {:else if errorRisk}
            <span class="status-chip status-error">error</span>
          {/if}
        </CardHeader>
        <CardContent class="section-body">
          {#if loadingRisk && !riskData}
            <LoadingState label="Loading risk metrics…" rows={2} />
          {:else if errorRisk && !riskData}
            <ErrorState message={errorRisk} onRetry={loadRisk} />
          {:else if riskData === null}
            <EmptyState message="No risk data available." />
          {:else}
            <div class="risk-grid">
              <!-- Sector exposure -->
              <div class="risk-block">
                <h3 class="risk-title">Sector Exposure</h3>
                {#if riskData.sector_exposure.length === 0}
                  <p class="empty-text">No sector data.</p>
                {:else}
                  <div class="sector-list">
                    {#each riskData.sector_exposure as s, i (s.sector)}
                      <div class="sector-row">
                        <span class="sector-name">{s.sector}</span>
                        <div class="sector-bar-wrap">
                          <div class="sector-bar-track">
                            <div
                              class="sector-bar-fill"
                              style="width: {Math.min(s.share_pct, 100)}%; background: {sectorColor(i)}"
                            ></div>
                          </div>
                        </div>
                        <span class="sector-pct mono">{fmtPct(s.share_pct)}</span>
                        <span class="sector-pnl mono {pnlClass(s.pnl)}">{fmtMoney(s.pnl)}</span>
                      </div>
                    {/each}
                  </div>
                {/if}
              </div>

              <!-- Stress scenarios -->
              <div class="risk-block">
                <h3 class="risk-title">Stress Scenarios</h3>
                {#if riskData.stress.scenarios.length === 0}
                  <p class="empty-text">No stress data.</p>
                {:else}
                  <Table class="stress-table text-[11px]">
                    <TableHeader>
                      <TableRow class="hover:bg-transparent">
                        <TableHead>Scenario</TableHead>
                        <TableHead class="text-right">Shift</TableHead>
                        <TableHead class="text-right">P&L Impact</TableHead>
                        <TableHead class="text-right">Worst</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {#each riskData.stress.scenarios as sc (sc.shift_pct)}
                        {@const isWorst = sc.shift_pct === riskData.stress.worst_case_shift}
                        <TableRow class={isWorst ? "worst-row" : ""}>
                          <TableCell class="font-mono">{scenarioName(sc.shift_pct)}</TableCell>
                          <TableCell class="font-mono text-right tabular-nums">
                            {sc.shift_pct > 0 ? "+" : ""}{sc.shift_pct}%
                          </TableCell>
                          <TableCell class="font-mono text-right tabular-nums {pnlClass(sc.total_pnl)}">
                            {fmtMoney(sc.total_pnl)}
                          </TableCell>
                          <TableCell class="text-right">
                            {#if isWorst}
                              <span class="worst-badge">WORST</span>
                            {:else}
                              <span class="muted">—</span>
                            {/if}
                          </TableCell>
                        </TableRow>
                      {/each}
                    </TableBody>
                  </Table>
                {/if}
              </div>

              <!-- Margin utilization -->
              <div class="risk-block">
                <h3 class="risk-title">Margin Utilization</h3>
                {#if marginUnknown}
                  <p class="empty-text">Margin data unavailable.</p>
                {:else}
                  <div class="margin-wrap">
                    <div class="margin-bar">
                      <div
                        class="margin-fill {marginBarClass}"
                        style="width: {Math.min(marginRatio * 100, 100)}%"
                      ></div>
                    </div>
                    <div class="margin-values">
                      <div class="margin-item">
                        <span class="margin-label">Used</span>
                        <span class="margin-num mono">
                          {riskData.margin.margin_used !== null ? fmtMoney(riskData.margin.margin_used) : "—"}
                        </span>
                      </div>
                      <div class="margin-item">
                        <span class="margin-label">Available</span>
                        <span class="margin-num mono">
                          {riskData.margin.margin_available !== null ? fmtMoney(riskData.margin.margin_available) : "—"}
                        </span>
                      </div>
                      <div class="margin-item">
                        <span class="margin-label">Total</span>
                        <span class="margin-num mono">
                          {riskData.margin.total !== null ? fmtMoney(riskData.margin.total) : "—"}
                        </span>
                      </div>
                      <div class="margin-item">
                        <span class="margin-label">Utilization</span>
                        <span class="margin-num mono {marginBarClass}">
                          {riskData.margin.utilization_pct !== null ? fmtPct(riskData.margin.utilization_pct) : "—"}
                        </span>
                      </div>
                    </div>
                    {#if riskData.margin.breach}
                      <span class="risk-chip chip-danger">MARGIN BREACH</span>
                    {:else if marginRatio > 0.8}
                      <span class="risk-chip chip-warn">MARGIN &gt; 80%</span>
                    {/if}
                  </div>
                {/if}
              </div>
            </div>
          {/if}
        </CardContent>
      </Card>

      <!-- Per-position greeks table -->
      {#if greeksData}
        <Card class="section-card">
          <CardHeader class="section-header">
            <CardTitle class="section-title">Per-Position Greeks</CardTitle>
            <span class="meta">{optionPositions.length} positions</span>
          </CardHeader>
          <CardContent class="section-body table-body">
            {#if optionPositions.length > 0}
              <div class="positions-table">
                <ScrollArea class="flex-1 min-h-0" orientation="horizontal">
                  <Table class="text-[11px]">
                    <TableHeader>
                      <TableRow class="hover:bg-transparent">
                        <TableHead class="cursor-pointer {sortClass('symbol')}" onclick={() => toggleSort('symbol')}>Symbol</TableHead>
                        <TableHead class="text-right cursor-pointer {sortClass('strike')}" onclick={() => toggleSort('strike')}>Strike</TableHead>
                        <TableHead class="text-right cursor-pointer {sortClass('option_type')}" onclick={() => toggleSort('option_type')}>Type</TableHead>
                        <TableHead class="text-right cursor-pointer {sortClass('expiry')}" onclick={() => toggleSort('expiry')}>Exp</TableHead>
                        <TableHead class="text-right cursor-pointer {sortClass('net_quantity')}" onclick={() => toggleSort('net_quantity')}>Qty</TableHead>
                        <TableHead class="text-right cursor-pointer {sortClass('delta')}" onclick={() => toggleSort('delta')}>Δ</TableHead>
                        <TableHead class="text-right cursor-pointer {sortClass('gamma')}" onclick={() => toggleSort('gamma')}>Γ</TableHead>
                        <TableHead class="text-right cursor-pointer {sortClass('theta')}" onclick={() => toggleSort('theta')}>Θ</TableHead>
                        <TableHead class="text-right cursor-pointer {sortClass('vega')}" onclick={() => toggleSort('vega')}>V</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {#each sortedPositions as p (p.symbol)}
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
              <EmptyState message="No option positions with greeks." />
            {/if}
          </CardContent>
        </Card>
      {/if}
    </div>
  </ScrollArea>
</section>

<style>
  .greeks-panel {
    display: flex;
    flex-direction: column;
    min-width: 0;
    height: 100%;
    gap: 8px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-radius: 6px;
  }
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
    flex-shrink: 0;
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
  .head-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    min-width: 0;
  }
  .updated {
    font-size: 10px;
    font-family: var(--font-mono);
    color: var(--faint);
    white-space: nowrap;
  }
  .range-group {
    display: flex;
    gap: 2px;
  }

  /* Summary tiles */
  .tiles {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 6px;
    padding: 6px 10px;
    flex-shrink: 0;
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

  /* Content sections */
  .content {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 0 10px 10px;
  }
  .section-card {
    background: var(--canvas-raised);
    border: 1px solid var(--hairline);
    border-radius: 4px;
  }
  :global(.section-card) {
    background: var(--canvas-raised) !important;
    border-color: var(--hairline) !important;
  }
  :global(.section-header) {
    display: flex !important;
    flex-direction: row !important;
    align-items: center !important;
    justify-content: space-between !important;
    padding: 8px 10px !important;
    border-bottom: 1px solid var(--hairline) !important;
  }
  :global(.section-title) {
    margin: 0 !important;
    font-size: 10px !important;
    font-weight: 700 !important;
    letter-spacing: 0.07em !important;
    color: var(--faint) !important;
    text-transform: uppercase !important;
  }
  :global(.section-body) {
    padding: 10px !important;
  }
  :global(.table-body) {
    padding: 0 !important;
  }
  .status-chip {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
    border: 1px solid var(--hairline-strong);
    border-radius: 2px;
    padding: 1px 5px;
  }
  .status-error {
    color: var(--danger);
    border-color: var(--danger);
  }
  .meta {
    font-size: 10px;
    color: var(--faint);
    font-family: var(--font-mono);
  }
  .empty-text {
    font-size: 11px;
    color: var(--faint);
    margin: 0;
  }

  /* Chart grid */
  .chart-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
  }
  .chart-cell {
    display: flex;
    flex-direction: column;
    gap: 4px;
    min-width: 0;
  }
  .chart-label {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .chart-cell :global(svg) {
    display: block;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-radius: 4px;
  }

  /* Risk grid */
  .risk-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
  }
  .risk-block {
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-width: 0;
  }
  .risk-title {
    margin: 0;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.06em;
    color: var(--muted);
    text-transform: uppercase;
  }

  /* Sector exposure bars */
  .sector-list {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .sector-row {
    display: grid;
    grid-template-columns: 60px 1fr 44px 64px;
    gap: 6px;
    align-items: center;
    font-size: 10px;
  }
  .sector-name {
    color: var(--body);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .sector-bar-wrap {
    min-width: 0;
  }
  .sector-bar-track {
    width: 100%;
    height: 5px;
    background: var(--surface-elevated);
    border-radius: 3px;
    overflow: hidden;
  }
  .sector-bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 150ms ease-out;
  }
  .sector-pct {
    text-align: right;
    color: var(--ink);
  }
  .sector-pnl {
    text-align: right;
  }

  /* Stress table */
  .stress-table {
    width: 100%;
    border-collapse: collapse;
  }
  .stress-table :global(th) {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    padding: 4px 6px;
    border-bottom: 1px solid var(--hairline-strong);
    white-space: nowrap;
  }
  .stress-table :global(td) {
    padding: 4px 6px;
    border-bottom: 1px solid var(--hairline);
    white-space: nowrap;
  }
  .worst-row {
    background: rgba(229, 72, 77, 0.08);
  }
  .worst-badge {
    font-size: 8px;
    font-weight: 700;
    color: var(--danger);
    letter-spacing: 0.04em;
  }
  .muted {
    color: var(--faint);
  }

  /* Margin gauge */
  .margin-wrap {
    display: flex;
    flex-direction: column;
    gap: 8px;
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
    transition: width 150ms ease-out;
  }
  .margin-fill.warn {
    background: var(--warning);
  }
  .margin-fill.breach {
    background: var(--danger);
  }
  .margin-values {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 6px;
  }
  .margin-item {
    display: flex;
    flex-direction: column;
    gap: 1px;
  }
  .margin-label {
    font-size: 9px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .margin-num {
    font-size: 12px;
    color: var(--ink);
  }
  .margin-num.warn {
    color: var(--warning);
  }
  .margin-num.breach {
    color: var(--danger);
  }
  .risk-chip {
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.05em;
    border-radius: 4px;
    padding: 2px 6px;
    white-space: nowrap;
    width: fit-content;
  }
  .chip-danger {
    color: var(--danger);
    border: 1px solid var(--danger);
  }
  .chip-warn {
    color: var(--warning);
    border: 1px solid var(--warning);
  }

  /* Positions table */
  .positions-table {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }
  .positions-table :global(th) {
    cursor: pointer;
    user-select: none;
    white-space: nowrap;
  }
  .positions-table :global(th:hover) {
    color: var(--ink);
  }
  .positions-table :global(th)::after {
    content: "";
    display: inline-block;
    width: 0;
    height: 0;
    margin-left: 4px;
    vertical-align: middle;
    opacity: 0.3;
    border-left: 3px solid transparent;
    border-right: 3px solid transparent;
    border-bottom: 4px solid currentColor;
  }
  .positions-table :global(th.sort-asc)::after {
    opacity: 1;
    border-bottom: 4px solid var(--accent);
    border-top: none;
  }
  .positions-table :global(th.sort-desc)::after {
    opacity: 1;
    border-top: 4px solid var(--accent);
    border-bottom: none;
  }

  /* Utility */
  .mono {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
  }
  .price-up {
    color: var(--price-up);
  }
  .price-down {
    color: var(--price-down);
  }
  .text-option-call {
    color: var(--price-up);
  }
  .text-option-put {
    color: var(--info);
  }

  /* Responsive */
  @media (max-width: 1024px) {
    .chart-grid {
      grid-template-columns: 1fr;
    }
    .risk-grid {
      grid-template-columns: 1fr;
    }
    .sector-row {
      grid-template-columns: 70px 1fr 44px 64px;
    }
  }
  @media (max-width: 640px) {
    .tiles {
      grid-template-columns: repeat(2, 1fr);
    }
    .head-actions {
      flex-wrap: wrap;
      justify-content: flex-end;
    }
  }
</style>
