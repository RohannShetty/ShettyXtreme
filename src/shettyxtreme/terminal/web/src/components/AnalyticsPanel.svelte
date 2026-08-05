<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { get } from "../lib/api";
  import type { CalibrationPoint, RegimeRow, ScorecardMetric, ScorecardResponse } from "../lib/api";
  import { Button } from "$lib/components/ui/button";
  import { RotateCw } from "@lucide/svelte";

  /** Analytics data older than this is flagged STALE (warning chip in the panel head). */
  const STALE_MS = 10 * 60_000;

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

  let timer: ReturnType<typeof setInterval> | undefined;

  onMount(() => {
    load();
    timer = setInterval(() => (now = Date.now()), 30_000);
  });

  onDestroy(() => {
    if (timer) clearInterval(timer);
  });

  async function load(): Promise<void> {
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

  let stale = $derived(fetchedAt !== null && now - fetchedAt > STALE_MS);

  /** Indian grouping (lakh/crore) on every numeric metric. */
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

  function chart(points: CalibrationPoint[]): string {
    // viewBox 0 0 320 120; x = 20 + (mid * 280) where mid = (lo+hi)/2 (conviction 0..1)
    // y = 104 - (win_rate * 96); reference diagonal from (20,104) to (300,8)
    // Colors are design tokens only — no hardcoded hex (DESIGN §2).
    const W = 320, H = 120, PX = 20, PY = 8, CW = 280, CH = 96;
    const x = (m: number) => PX + m * CW;
    const y = (r: number) => H - PY - r * CH;
    const pts = points
      .map((p, i) => `${x((p.conviction_bin[0] + p.conviction_bin[1]) / 2)},${y(p.actual_win_rate)}`)
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

<section class="panel analytics">
  <header class="panel-head">
    <div class="head-group">
      <h2>Analytics</h2>
      {#if stale}
        <span class="stale-chip" role="status">STALE</span>
      {/if}
    </div>
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
  </header>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  {#if !error}
    <div class="cards" role="listbox" aria-label="Scorecard metrics">
      {#each metrics as m (m.key)}
        <div
          class="card"
          class:na={!m.available}
          role="option"
          aria-selected={false}
          tabindex="0"
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
    overflow-y: auto;
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
</style>
