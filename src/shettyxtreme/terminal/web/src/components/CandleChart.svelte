<script lang="ts">
  import { getMarketBars } from "../lib/api";
  import type { MarketBar } from "../lib/api";

  let {
    symbol = "NIFTY",
    exchange = "NSE_FNO",
    tf = 1,
  }: { symbol?: string; exchange?: string; tf?: number } = $props();

  let bars = $state<MarketBar[]>([]);
  let loading = $state(false);
  let error = $state("");

  $effect(() => {
    void load();
  });

  async function load(): Promise<void> {
    loading = true;
    error = "";
    try {
      const resp = await getMarketBars(symbol, exchange, tf);
      bars = resp.bars ?? [];
    } catch (err) {
      bars = [];
      error = err instanceof Error ? err.message : String(err);
    }
    loading = false;
  }

  const MAX_BARS = 90;
  const PLOT_LEFT = 8;
  const PLOT_TOP = 8;
  const PLOT_RIGHT = 668;
  const PLOT_BOTTOM = 216;
  const VOL_TOP = 222;
  const VOL_BOTTOM = 252;
  const TICK_COUNT = 4;

  const shown = $derived(bars.slice(-MAX_BARS));
  const lo = $derived(shown.length ? Math.min(...shown.map((b) => b.low)) : 0);
  const hi = $derived(shown.length ? Math.max(...shown.map((b) => b.high)) : 0);
  const pad = $derived(shown.length ? Math.max((hi - lo) * 0.04, Math.max(hi, 1) * 0.001) : 1);
  const yMax = $derived(hi + pad);
  const yMin = $derived(Math.max(0, lo - pad));
  const span = $derived(yMax - yMin || 1);
  const maxVol = $derived(shown.length ? Math.max(...shown.map((b) => b.volume)) : 0);
  const slotW = $derived((PLOT_RIGHT - PLOT_LEFT) / Math.max(shown.length, 1));
  const bodyW = $derived(Math.max(2, slotW * 0.6));
  const ticks = $derived(
    Array.from({ length: TICK_COUNT }, (_, i) => yMin + (span * (i + 0.5)) / TICK_COUNT),
  );

  function yFor(v: number): number {
    return PLOT_TOP + ((yMax - v) / span) * (PLOT_BOTTOM - PLOT_TOP);
  }

  function candleColor(b: MarketBar): string {
    return b.close >= b.open ? "var(--candle-up)" : "var(--candle-down)";
  }

  function fmt(v: number): string {
    const digits = Math.abs(v) >= 1000 ? 0 : Math.abs(v) >= 10 ? 1 : 2;
    return v.toLocaleString("en-IN", { maximumFractionDigits: digits });
  }
</script>

<div class="chart">
  <div class="chart-head">
    <span class="chart-title mono">{symbol}</span>
    <span class="chart-sub mono">{exchange} · {tf}m</span>
    <span class="legend mono">
      <i class="sw sw-up"></i>UP
      <i class="sw sw-down"></i>DOWN
    </span>
  </div>

  {#if error}
    <p class="error">{error}</p>
  {:else if shown.length > 0}
    <svg viewBox="0 0 720 260" class="canvas" role="img" aria-label="Candlestick chart for {symbol}">
      {#each ticks as t (t)}
        <line
          x1={PLOT_LEFT}
          y1={yFor(t)}
          x2={PLOT_RIGHT}
          y2={yFor(t)}
          stroke="var(--grid-line)"
          stroke-width="1"
        />
        <text x={PLOT_RIGHT + 6} y={yFor(t) + 3} class="mono axis" fill="var(--muted)">{fmt(t)}</text>
      {/each}
      {#each shown as b, i (b.timestamp)}
        {@const cx = PLOT_LEFT + slotW * (i + 0.5)}
        {@const bodyTop = yFor(Math.max(b.open, b.close))}
        {@const bodyH = Math.max(1, Math.abs(yFor(b.open) - yFor(b.close)))}
        {@const volH = maxVol > 0 ? (b.volume / maxVol) * (VOL_BOTTOM - VOL_TOP) : 0}
        <line
          x1={cx}
          y1={yFor(b.high)}
          x2={cx}
          y2={yFor(b.low)}
          stroke={candleColor(b)}
          stroke-width="1"
        />
        <rect x={cx - bodyW / 2} y={bodyTop} width={bodyW} height={bodyH} fill={candleColor(b)} />
        <rect
          x={cx - bodyW / 2}
          y={VOL_BOTTOM - volH}
          width={bodyW}
          height={volH}
          fill="var(--muted)"
          fill-opacity="0.25"
        />
      {/each}
    </svg>
  {:else if loading}
    <p class="chart-note mono">loading…</p>
  {:else}
    <p class="empty">No chart data.</p>
  {/if}
</div>

<style>
  .chart {
    display: flex;
    flex-direction: column;
    border-bottom: 1px solid var(--hairline);
    height: 268px;
  }
  .chart-head {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 10px;
  }
  .chart-title {
    font-size: 12px;
    font-weight: 700;
    color: var(--ink);
  }
  .chart-sub {
    font-size: 10px;
    color: var(--faint);
  }
  .legend {
    margin-left: auto;
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 9px;
    color: var(--faint);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .sw {
    width: 8px;
    height: 8px;
    border-radius: 1px;
  }
  .sw-up {
    background: var(--candle-up);
  }
  .sw-down {
    background: var(--candle-down);
  }
  .canvas {
    flex: 1;
    width: 100%;
    height: 100%;
    display: block;
  }
  .axis {
    font-size: 10px;
  }
  .error {
    color: var(--danger);
    font-size: 11px;
    padding: 4px 10px;
    margin: 0;
  }
  .empty {
    color: var(--faint);
    font-size: 12px;
    padding: 16px 10px;
    margin: 0;
  }
  .chart-note {
    margin: 0;
    padding: 8px 10px;
    font-size: 9px;
    color: var(--faint);
  }
</style>
