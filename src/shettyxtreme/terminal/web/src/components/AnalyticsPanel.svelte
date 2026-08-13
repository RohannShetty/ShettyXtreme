<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { get } from "../lib/api";
  import type {
    CalibrationPoint,
    RegimeRow,
    ScorecardMetric,
    ScorecardResponse,
    IVRankHistoryPoint,
    PCRHistoryPoint,
    MaxPainHistoryPoint,
    RegimeHistoryPoint,
    ExportFormat,
  } from "../lib/api";
  import {
    getIVRankHistory,
    getPCRHistory,
    getMaxPainHistory,
    getRegimeHistory,
    exportAnalytics,
  } from "../lib/api";
  import { selectedSymbol } from "../lib/selection.svelte.ts";
  import { lineChart, multiLineChart, regimeTimeline, type LineBand } from "../lib/charts";
  import { useDebounce } from "../lib/debounce.svelte";
  import { Button } from "$lib/components/ui/button";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import { Skeleton } from "$lib/components/ui/skeleton";
  import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
  } from "$lib/components/ui/select";
  import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogFooter,
    DialogTrigger,
  } from "$lib/components/ui/dialog";
  import { Label } from "$lib/components/ui/label";
  import { RotateCw, Download } from "@lucide/svelte";

  /** Analytics data older than this is flagged STALE (warning chip in the panel head). */
  const STALE_MS = 10 * 60_000;
  const DAY_OPTIONS = [7, 30, 90];

  const IV_BANDS: LineBand[] = [
    { min: 0, max: 20, color: "var(--success)", label: "low" },
    { min: 20, max: 30, color: "var(--warning)", label: "normal" },
    { min: 30, max: 100, color: "var(--danger)", label: "high" },
  ];

  const PCR_BANDS: LineBand[] = [
    { min: 0, max: 0.7, color: "var(--success)", label: "oversold" },
    { min: 0.7, max: 1.2, color: "var(--warning)", label: "neutral" },
    { min: 1.2, max: Number.MAX_SAFE_INTEGER, color: "var(--danger)", label: "overbought" },
  ];

  let metrics: ScorecardMetric[] = $state([]);
  let byRegime: RegimeRow[] = $state([]);
  let calibration: CalibrationPoint[] = $state([]);
  let reliable = $state(false);
  let loading = $state(true);
  let error = $state("");
  let fetchedAt = $state<number | null>(null);
  let now = $state(Date.now());
  /** Current regime carried on the scorecard payload — drives the accent bar. */
  let currentRegime = $state<string | null>(null);

  let days = $state(30);
  let symbol = $derived(selectedSymbol.symbol || "NIFTY");

  let ivRank: IVRankHistoryPoint[] = $state([]);
  let pcr: PCRHistoryPoint[] = $state([]);
  let maxPain: MaxPainHistoryPoint[] = $state([]);
  let regimeHistory: RegimeHistoryPoint[] = $state([]);
  let historiesLoading = $state(false);
  let historiesError = $state("");

  // Debounce chart inputs so rapid updates (e.g. WS ticks) render at most once per 500ms.
  const debouncedIVRank = useDebounce(() => ivRank, 500);
  const debouncedPCR = useDebounce(() => pcr, 500);
  const debouncedMaxPain = useDebounce(() => maxPain, 500);
  const debouncedRegimeHistory = useDebounce(() => regimeHistory, 500);

  let exportOpen = $state(false);
  let exportFormat: ExportFormat = $state("csv");
  let exportDays = $state(30);
  let exportLoading = $state(false);

  let timer: ReturnType<typeof setInterval> | undefined;

  onMount(() => {
    load();
    timer = setInterval(() => (now = Date.now()), 30_000);
  });

  onDestroy(() => {
    if (timer) clearInterval(timer);
  });

  async function load(): Promise<void> {
    await Promise.all([loadScorecard(), loadHistories()]);
  }

  async function loadScorecard(): Promise<void> {
    loading = true;
    error = "";
    try {
      const resp = await get<ScorecardResponse>("/api/analytics/scorecard");
      metrics = resp.metrics;
      byRegime = resp.by_regime;
      calibration = resp.calibration;
      reliable = resp.reliable_calibration;
      currentRegime = resp.current_regime ?? null;
      fetchedAt = Date.now();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
      metrics = [];
      byRegime = [];
      calibration = [];
    } finally {
      loading = false;
    }
  }

  async function loadHistories(): Promise<void> {
    historiesLoading = true;
    historiesError = "";
    try {
      const [iv, p, mp, rh] = await Promise.all([
        getIVRankHistory(symbol, days),
        getPCRHistory(symbol, days),
        getMaxPainHistory(symbol, days),
        getRegimeHistory(days),
      ]);
      ivRank = iv;
      pcr = p;
      maxPain = mp;
      regimeHistory = rh;
    } catch (err) {
      historiesError = err instanceof Error ? err.message : String(err);
      ivRank = [];
      pcr = [];
      maxPain = [];
      regimeHistory = [];
    } finally {
      historiesLoading = false;
    }
  }

  function setDays(value: string): void {
    days = Number(value);
    loadHistories();
  }

  async function downloadExport(): Promise<void> {
    exportLoading = true;
    try {
      const blob = await exportAnalytics(exportFormat, symbol, exportDays);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `analytics_export.${exportFormat}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      exportOpen = false;
    } catch (err) {
      historiesError = err instanceof Error ? err.message : String(err);
    } finally {
      exportLoading = false;
    }
  }

  let stale = $derived(fetchedAt !== null && now - fetchedAt > STALE_MS);

  let ivRankPoints = $derived(
    debouncedIVRank.current.map((r) => ({ x: new Date(r.timestamp), y: r.iv_rank_percent })),
  );
  let pcrPoints = $derived(
    debouncedPCR.current.map((r) => ({ x: new Date(r.timestamp), y: r.pcr })),
  );
  let maxPainSeries = $derived([
    {
      key: "max pain",
      points: debouncedMaxPain.current.map((r) => ({ x: new Date(r.timestamp), y: r.max_pain })),
      color: "var(--muted)",
      dashed: true,
    },
    {
      key: "spot",
      points: debouncedMaxPain.current
        .filter((r) => r.spot_price != null)
        .map((r) => ({ x: new Date(r.timestamp), y: r.spot_price! })),
      color: "var(--accent)",
    },
  ]);

  function fmtValue(m: ScorecardMetric): string {
    if (!m.available) return "—";
    if (typeof m.value === "boolean") return m.value ? "reliable" : "unreliable";
    if (typeof m.value !== "number") return String(m.value);
    if (m.unit === "%")
      return `${(m.value * 100).toLocaleString("en-IN", { maximumFractionDigits: 1 })}%`;
    if (Number.isInteger(m.value)) return m.value.toLocaleString("en-IN");
    return m.value.toLocaleString("en-IN", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function winPct(r: RegimeRow): string {
    return r.with_outcome === 0 ? "0" : (r.win_rate * 100).toFixed(0);
  }

  function barWidth(r: RegimeRow): string {
    return r.with_outcome === 0 ? "0%" : `${Math.round(r.win_rate * 100)}%`;
  }

  /** accent bar for the current regime; muted for the rest. Regime unknown → all accent. */
  function isCurrent(r: RegimeRow): boolean {
    if (currentRegime === null) return true;
    return r.regime === currentRegime;
  }

  function lastIVRank(): string {
    const last = ivRank.at(-1);
    return last ? `${last.iv_rank_percent.toFixed(1)}%` : "—";
  }

  function lastPCR(): string {
    const last = pcr.at(-1);
    return last ? last.pcr.toFixed(2) : "—";
  }

  function lastMaxPain(): string {
    const last = maxPain.at(-1);
    return last
      ? last.max_pain.toLocaleString("en-IN", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })
      : "—";
  }

  function lastSpot(): string {
    const last = maxPain.at(-1);
    return last && last.spot_price != null
      ? last.spot_price.toLocaleString("en-IN", {
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        })
      : "—";
  }

  function lastRegime(): string {
    const last = debouncedRegimeHistory.current.at(-1) ?? regimeHistory.at(-1);
    return last ? last.regime.replace(/_/g, " ").toUpperCase() : "—";
  }

  function chart(points: CalibrationPoint[]): string {
    // viewBox 0 0 320 120; x = 20 + (mid * 280) where mid = (lo+hi)/2 (conviction 0..1)
    // y = 104 - (win_rate * 96); reference diagonal from (20,104) to (300,8)
    // Colors are design tokens only — no hardcoded hex (DESIGN §2).
    const W = 320,
      H = 120,
      PX = 20,
      PY = 8,
      CW = 280,
      CH = 96;
    const x = (m: number) => PX + m * CW;
    const y = (r: number) => H - PY - r * CH;
    const pts = points
      .map(
        (p, i) =>
          `${x((p.conviction_bin[0] + p.conviction_bin[1]) / 2)},${y(p.actual_win_rate)}`,
      )
      .join(" ");
    const whisk = points
      .map((p) => {
        const mx = (p.conviction_bin[0] + p.conviction_bin[1]) / 2;
        return `<line x1="${x(mx)}" y1="${y(p.confidence_interval[1])}" x2="${x(mx)}" y2="${y(p.confidence_interval[0])}" stroke="var(--hairline-strong)" stroke-width="1"/>`;
      })
      .join("");
    const dots = points
      .map((p) => {
        const mx = (p.conviction_bin[0] + p.conviction_bin[1]) / 2;
        return `<circle cx="${x(mx)}" cy="${y(p.actual_win_rate)}" r="${Math.max(2, Math.min(6, Math.sqrt(p.sample_size)))}" fill="var(--accent)"/>`;
      })
      .join("");
    return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="calibration curve">
    <line x1="${PX}" y1="${H - PY}" x2="${W - PX}" y2="${PY}" stroke="var(--hairline)" stroke-dasharray="3 3"/>
    ${whisk}${dots}<polyline points="${pts}" fill="none" stroke="var(--accent)" stroke-width="1.5"/>
  </svg>`;
  }
</script>

<section class="panel analytics" aria-label="Analytics panel">
  <header class="panel-head">
    <div class="head-group">
      <h2 id="analytics-title">Analytics</h2>
      {#if stale}
        <span class="stale-chip" role="status">STALE</span>
      {/if}
    </div>
    <div class="head-actions">
      <Select type="single" value={String(days)} onValueChange={setDays}>
        <SelectTrigger class="h-7 w-[90px] text-[11px]" aria-label="History range">
          <span>{days}D</span>
        </SelectTrigger>
        <SelectContent>
          {#each DAY_OPTIONS as d (d)}
            <SelectItem value={String(d)} label="{d}D">{d}D</SelectItem>
          {/each}
        </SelectContent>
      </Select>

      <Dialog open={exportOpen} onOpenChange={(v) => (exportOpen = v)}>
        <DialogTrigger
          class="inline-flex h-7 items-center justify-center gap-1.5 whitespace-nowrap rounded-[4px] border border-hairline-strong bg-surface-elevated px-3 text-[11px] font-semibold text-body transition-colors hover:border-muted hover:text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          <Download class="size-3.5" />
          Export
        </DialogTrigger>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Export analytics</DialogTitle>
          </DialogHeader>
          <div class="export-grid">
            <div class="field">
              <Label class="text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">Format</Label>
              <Select
                type="single"
                value={exportFormat}
                onValueChange={(v) => (exportFormat = v as ExportFormat)}
              >
                <SelectTrigger class="h-8 text-[12px]" aria-label="Export format">
                  <span>{exportFormat.toUpperCase()}</span>
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="csv" label="CSV">CSV</SelectItem>
                  <SelectItem value="json" label="JSON">JSON</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div class="field">
              <Label class="text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">Range</Label>
              <Select
                type="single"
                value={String(exportDays)}
                onValueChange={(v) => (exportDays = Number(v))}
              >
                <SelectTrigger class="h-8 text-[12px]" aria-label="Export range">
                  <span>Last {exportDays} days</span>
                </SelectTrigger>
                <SelectContent>
                  {#each DAY_OPTIONS as d (d)}
                    <SelectItem value={String(d)} label="Last {d} days"
                      >Last {d} days</SelectItem
                    >
                  {/each}
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onclick={() => (exportOpen = false)}
              >Cancel</Button
            >
            <Button size="sm" onclick={downloadExport} disabled={exportLoading}
              >Download</Button
            >
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Button
        variant="ghost"
        size="icon"
        class="size-7 text-muted-foreground hover:text-ink"
        onclick={load}
        disabled={loading}
        aria-label="Refresh analytics"
      >
        <RotateCw class="size-3.5" />
      </Button>
    </div>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if !error}
    <ScrollArea class="flex-1 min-h-0">
      <div class="cards" aria-label="Scorecard metrics">
        {#each metrics as m (m.key)}
          <div
            class="card"
            class:na={!m.available}
            title={m.available ? "" : m.note ?? undefined}
          >
            <span class="card-label">{m.label}</span>
            <span class="card-value">{fmtValue(m)}</span>
          </div>
        {/each}
        {#if metrics.length === 0 && !loading}
          <p class="empty">No scorecard metrics.</p>
        {/if}
      </div>

      <div class="block">
        <div class="block-head">
          <h3>Calibration</h3>
          {#if calibration.length > 0}
            <span class={reliable ? "badge badge-reliable" : "badge badge-unreliable"}>
              {reliable ? "reliable" : "unreliable"}
            </span>
          {/if}
        </div>
        {#if calibration.length > 0}
          {@html chart(calibration)}
          <p class="chart-note mono">diagonal = perfect calibration · dots sized by sample</p>
        {:else if !loading}
          <p class="empty">Not enough decided outcomes to fit a calibration curve.</p>
        {/if}
      </div>

      <div class="block">
        <h3>By regime</h3>
        {#if byRegime.length > 0}
          <ul class="regimes">
            {#each byRegime as r (r.regime)}
              <li class:current={isCurrent(r)}>
                <span class="regime-label mono" class:current={isCurrent(r)}>{r.regime}</span>
                <div class="bar-track">
                  <div
                    class="bar"
                    class:current={isCurrent(r)}
                    style="width: {barWidth(r)}"
                  ></div>
                </div>
                <span class="regime-pct mono">{winPct(r)}%</span>
                <span class="regime-counts mono">d{r.decided}·o{r.with_outcome}</span>
              </li>
            {/each}
          </ul>
        {:else if !loading}
          <p class="empty">No regime data yet.</p>
        {/if}
      </div>

      <div class="block history-block">
        <div class="block-head">
          <h3>History</h3>
          {#if historiesError}
            <span class="error-inline">{historiesError}</span>
          {/if}
        </div>

        <div class="chart-grid">
          <div class="chart-card">
            <div class="chart-card-head">
              <span class="chart-title">IV Rank</span>
              <span class="chart-current mono">{lastIVRank()}</span>
            </div>
            {#if historiesLoading}
              <Skeleton class="h-[140px] w-full" />
            {:else if ivRank.length > 0}
              {@html lineChart(ivRankPoints, {
                yMin: 0,
                yMax: 100,
                bands: IV_BANDS,
                lineColor: "var(--accent)",
                markerColor: "var(--ink)",
                ariaLabel: "IV rank history",
                title: "IV rank over time",
              })}
            {:else}
              <p class="empty">No IV rank history.</p>
            {/if}
          </div>

          <div class="chart-card">
            <div class="chart-card-head">
              <span class="chart-title">PCR</span>
              <span class="chart-current mono">{lastPCR()}</span>
            </div>
            {#if historiesLoading}
              <Skeleton class="h-[140px] w-full" />
            {:else if pcr.length > 0}
              {@html lineChart(pcrPoints, {
                bands: PCR_BANDS,
                lineColor: "var(--accent)",
                markerColor: "var(--ink)",
                ariaLabel: "PCR history",
                title: "Put call ratio over time",
              })}
            {:else}
              <p class="empty">No PCR history.</p>
            {/if}
          </div>

          <div class="chart-card">
            <div class="chart-card-head">
              <span class="chart-title">Max Pain vs Spot</span>
              <span class="chart-current mono">{lastMaxPain()} / {lastSpot()}</span>
            </div>
            {#if historiesLoading}
              <Skeleton class="h-[140px] w-full" />
            {:else if maxPain.length > 0}
              {@html multiLineChart({
                series: maxPainSeries,
                ariaLabel: "Max pain versus spot price",
                title: "Max pain versus spot price",
              })}
            {:else}
              <p class="empty">No max pain history.</p>
            {/if}
          </div>

          <div class="chart-card">
            <div class="chart-card-head">
              <span class="chart-title">Regime Timeline</span>
              <span class="chart-current mono">{lastRegime()}</span>
            </div>
            {#if historiesLoading}
              <Skeleton class="h-[80px] w-full" />
            {:else if debouncedRegimeHistory.current.length > 0}
              {@html regimeTimeline(debouncedRegimeHistory.current, {
                ariaLabel: "Regime history timeline",
                title: "Regime changes over time",
              })}
            {:else}
              <p class="empty">No regime history.</p>
            {/if}
          </div>
        </div>
      </div>
    </ScrollArea>
  {/if}
</section>

<style>
  .analytics {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
    flex: 1 1 0;
    border-radius: 6px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
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
  .head-group {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .head-actions {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  /* STALE chip — warning, micro uppercase (DESIGN.md staleness marker). */
  .stale-chip {
    font-size: 11px;
    line-height: 14px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--warning);
    border: 1px solid var(--warning);
    border-radius: 2px;
    padding: 0 5px;
    white-space: nowrap;
  }
  .error {
    color: var(--danger);
    font-size: 11px;
    padding: 8px 10px;
    margin: 0;
  }
  .error-inline {
    color: var(--danger);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .cards {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
    gap: 8px;
    padding: 10px;
  }
  /* Scorecard metric card — surface-card bg, caption label, number-lg value. */
  .card {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 8px 10px;
    border: 1px solid var(--hairline);
    border-radius: 6px;
    background: var(--surface-card);
  }
  /* Tab reaches the metric cards; focus must always be visible (DESIGN §3.2). */
  .card:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  .card.na {
    border-style: dashed;
    opacity: 0.7;
  }
  .card-label {
    font-size: 12px;
    line-height: 16px;
    color: var(--muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .card-value {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-size: 20px;
    font-weight: 600;
    line-height: 24px;
    color: var(--ink);
    white-space: nowrap;
  }
  .block {
    padding: 0 10px 12px;
  }
  .block-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 6px;
  }
  .block h3 {
    margin: 0 0 6px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.07em;
    color: var(--faint);
    text-transform: uppercase;
  }
  .block-head h3 {
    margin: 0;
  }
  .badge {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    border: 1px solid var(--hairline-strong);
    border-radius: 4px;
    padding: 1px 5px;
  }
  .badge-reliable {
    color: var(--success);
    border-color: var(--success);
  }
  .badge-unreliable {
    color: var(--warning);
    border-color: var(--warning);
  }
  .chart-note {
    margin: 4px 0 0;
    font-size: 9px;
    color: var(--faint);
  }
  ul.regimes {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .regimes li {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 0;
    font-size: 11px;
    border-bottom: 1px solid var(--hairline);
  }
  .regime-label {
    color: var(--body);
    min-width: 96px;
    font-size: 10px;
  }
  /* Current regime: accent label + accent bar; others muted (DESIGN §2 palette rules). */
  .regime-label.current {
    color: var(--accent);
  }
  .bar-track {
    flex: 1;
    height: 6px;
    background: var(--surface-elevated);
    border: 1px solid var(--hairline);
    border-radius: 3px;
    overflow: hidden;
  }
  .bar {
    height: 100%;
    background: var(--muted);
    border-radius: 2px;
  }
  .bar.current {
    background: var(--accent);
  }
  .regime-pct {
    color: var(--ink);
    min-width: 34px;
    text-align: right;
    font-size: 10px;
  }
  .regime-counts {
    color: var(--faint);
    font-size: 9px;
    min-width: 40px;
    text-align: right;
  }
  .empty {
    color: var(--faint);
    font-size: 11px;
    padding: 4px 0;
    margin: 0;
  }
  .history-block {
    border-top: 1px solid var(--hairline);
    padding-top: 12px;
  }
  .chart-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 10px;
  }
  .chart-card {
    min-width: 0;
    border: 1px solid var(--hairline);
    border-radius: 6px;
    padding: 10px;
    background: var(--surface-card);
  }
  .chart-card-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin-bottom: 8px;
  }
  .chart-title {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.07em;
    color: var(--faint);
    text-transform: uppercase;
  }
  .chart-current {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-size: 14px;
    font-weight: 600;
    color: var(--ink);
  }
  .export-grid {
    display: grid;
    gap: 12px;
  }
  .field {
    display: grid;
    gap: 4px;
  }
  /* Responsive: panels work in narrow right dock. */
  @media (max-width: 460px) {
    .analytics {
      min-width: 0;
    }
    .panel-head {
      flex-wrap: wrap;
      gap: 8px;
    }
    .head-actions {
      width: 100%;
      justify-content: space-between;
    }
    .cards {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .chart-grid {
      grid-template-columns: 1fr;
    }
    .regimes li {
      flex-wrap: wrap;
      gap: 4px 8px;
    }
    .regime-label {
      min-width: auto;
      flex: 1 1 100%;
    }
    .bar-track {
      flex: 1 1 100%;
    }
  }
  /* Coarse pointers: floor tap targets at 44px. */
  @media (pointer: coarse) {
    .head-actions :global(button),
    .head-actions :global([role="combobox"]) {
      min-height: 44px;
      min-width: 44px;
    }
    .card {
      min-height: 44px;
    }
  }
</style>
