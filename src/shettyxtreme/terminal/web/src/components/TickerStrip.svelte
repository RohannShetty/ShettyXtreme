<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "../lib/api";
  import {
    Activity,
    ArrowDown,
    ArrowLeftRight,
    ArrowUp,
    Crosshair,
    Gauge,
    Scale,
  } from "@lucide/svelte";

  /* ── Wire types (mirror terminal/api/models.py) ─────────────────────────
     Regime comes from GET /api/intelligence/regime (projection-backed).
     IV/PCR/Max Pain are derived client-side from the option chain
     (GET /api/intelligence/options) — the chain cache the backend posture
     tool (research_source.py) reads. A dedicated options-summary endpoint
     does not exist yet; this component is self-contained against the two
     real endpoints and the derivations are pure functions of the chain. */

  type RegimeResponse = {
    regime: string;
    confidence: number;
    transition: boolean;
    adx: number | null;
    di_plus: number | null;
    di_minus: number | null;
  };

  type OptionsContract = {
    strike: number;
    option_type: string; // CE / PE
    ltp: number;
    iv: number;
    oi: number;
    volume: number;
    bid: number;
    ask: number;
  };

  type OptionsResponse = {
    underlying: string;
    expiry: string;
    timestamp: string | null;
    contracts: OptionsContract[];
  };

  type Tone = "success" | "warning" | "danger" | "muted";
  type PcrLabel = "OVERSOLD" | "NEUTRAL" | "OVERBOUGHT";
  type IvLabel = "LOW" | "NORMAL" | "HIGH";

  // Regime enum (intelligence/regime/regime_classifier.py): trending_up /
  // trending_down / range_bound / volatile. TRENDING = green, RANGING =
  // yellow, VOLATILE = red (wave-2 spec). Directional caret for trending
  // regimes follows the Indian price law: red ▲ = up, green ▼ = down.
  const REGIME_META: Record<string, { label: string; tone: Tone; dir?: "up" | "down" }> = {
    trending_up: { label: "TRENDING", tone: "success", dir: "up" },
    trending_down: { label: "TRENDING", tone: "success", dir: "down" },
    range_bound: { label: "RANGING", tone: "warning" },
    volatile: { label: "VOLATILE", tone: "danger" },
  };

  const REFRESH_MS = 30_000;
  const SYMBOL = "NIFTY";

  // PCR bands (contrarian read): low PCR = puts light = oversold zone;
  // high PCR = puts heavy = overbought zone.
  const PCR_OVERSOLD_MAX = 0.7;
  const PCR_OVERBOUGHT_MIN = 1.2;

  // IV-level bands match the backend posture renderer (research_source.py):
  // HIGH ≥ 30, LOW < 20, else NORMAL. True IV *rank* (0–100, history-based)
  // lives in the backend IVRankCalculator which is not yet app-wired — the
  // gauge here renders the derived level on a 0–40% scale, and the derivation
  // is a single function so a real rank can slot in when an options-summary
  // endpoint lands.
  const IV_HIGH_MIN = 30;
  const IV_LOW_MAX = 20;
  const IV_GAUGE_SCALE = 40;

  let regime = $state<RegimeResponse | null>(null);
  let contracts = $state<OptionsContract[]>([]);
  let loading = $state(true);
  let error = $state("");
  let timer: number | undefined;

  let regimeMeta = $derived.by(() => {
    const key = regime?.regime ?? "";
    return REGIME_META[key] ?? { label: "—", tone: "muted" as Tone };
  });
  let pcr = $derived(computePcr(contracts));
  let pcrTone = $derived(pcrToneOf(pcr));
  let ivLevel = $derived(computeIvLevel(contracts));
  let ivLabel = $derived(ivLabelOf(ivLevel));
  let ivTone = $derived(ivToneOf(ivLevel));
  let maxPain = $derived(computeMaxPain(contracts));

  onMount(() => {
    void load();
    timer = window.setInterval(() => void load(), REFRESH_MS);
    return () => {
      if (timer !== undefined) window.clearInterval(timer);
    };
  });

  /** Imperative force-update for the integration phase (bind:this). */
  export async function refresh(): Promise<void> {
    await load();
  }

  async function load(): Promise<void> {
    error = "";
    loading = true;
    // Parallel, independent sources: a regime failure must not blank the
    // posture cards or vice versa — each falls back to its own "—".
    const [regimeRes, optionsRes] = await Promise.allSettled([
      get<RegimeResponse>("/api/intelligence/regime"),
      get<OptionsResponse>(`/api/intelligence/options?symbol=${SYMBOL}`),
    ]);
    if (regimeRes.status === "fulfilled") {
      regime = regimeRes.value;
    }
    if (optionsRes.status === "fulfilled") {
      contracts = optionsRes.value.contracts ?? [];
    }
    const failures = [regimeRes, optionsRes].filter((r) => r.status === "rejected");
    if (failures.length > 0) {
      const first = failures[0] as PromiseRejectedResult;
      error = first.reason instanceof Error ? first.reason.message : String(first.reason);
    }
    loading = false;
  }

  // ── Chain derivations (pure functions of the contract list) ─────────────

  /** PCR = Σ put OI ÷ Σ call OI; null when the chain has no call OI. */
  function computePcr(list: OptionsContract[]): number | null {
    let put = 0;
    let call = 0;
    for (const c of list) {
      const side = String(c.option_type).toUpperCase();
      const oi = Number.isFinite(c.oi) ? c.oi : 0;
      if (oi <= 0) continue;
      if (side === "PE") put += oi;
      else if (side === "CE") call += oi;
    }
    return call > 0 ? put / call : null;
  }

  function pcrLabelOf(value: number | null): PcrLabel | null {
    if (value === null) return null;
    if (value < PCR_OVERSOLD_MAX) return "OVERSOLD";
    if (value > PCR_OVERBOUGHT_MIN) return "OVERBOUGHT";
    return "NEUTRAL";
  }

  function pcrToneOf(value: number | null): Tone {
    if (value === null) return "muted";
    if (value < PCR_OVERSOLD_MAX) return "success"; // oversold → cool / contrarian buy zone
    if (value > PCR_OVERBOUGHT_MIN) return "danger"; // overbought → heat / contrarian sell zone
    return "muted";
  }

  /** Mean positive chain IV — the level the backend posture tool reports. */
  function computeIvLevel(list: OptionsContract[]): number | null {
    let sum = 0;
    let n = 0;
    for (const c of list) {
      const iv = Number.isFinite(c.iv) ? c.iv : 0;
      if (iv > 0) {
        sum += iv;
        n += 1;
      }
    }
    return n > 0 ? sum / n : null;
  }

  function ivLabelOf(level: number | null): IvLabel | null {
    if (level === null) return null;
    if (level >= IV_HIGH_MIN) return "HIGH";
    if (level < IV_LOW_MAX) return "LOW";
    return "NORMAL";
  }

  function ivToneOf(level: number | null): Tone {
    if (level === null) return "muted";
    if (level >= IV_HIGH_MIN) return "danger";
    if (level < IV_LOW_MAX) return "success";
    return "warning";
  }

  /** Gauge fill 0–100: level mapped onto a 0–40% IV scale. */
  function ivFillOf(level: number | null): number {
    if (level === null) return 0;
    return Math.min(Math.max((level / IV_GAUGE_SCALE) * 100, 0), 100);
  }

  /**
   * Max pain — the strike minimizing total option payout if spot expires
   * there. O(n) via prefix/suffix sums:
   *   pain(K) = Σ_{s>K} (s−K)·ce[s] + Σ_{s<K} (K−s)·pe[s]
   */
  function computeMaxPain(list: OptionsContract[]): number | null {
    const byStrike = new Map<number, { ce: number; pe: number }>();
    for (const c of list) {
      if (!Number.isFinite(c.strike) || c.strike <= 0) continue;
      const side = String(c.option_type).toUpperCase();
      if (side !== "CE" && side !== "PE") continue;
      const oi = Number.isFinite(c.oi) ? c.oi : 0;
      if (oi <= 0) continue;
      const row = byStrike.get(c.strike) ?? { ce: 0, pe: 0 };
      if (side === "PE") row.pe += oi;
      else row.ce += oi;
      byStrike.set(c.strike, row);
    }
    const strikes = [...byStrike.keys()].sort((a, b) => a - b);
    if (strikes.length < 2) return null;

    const n = strikes.length;
    const ce = strikes.map((s) => byStrike.get(s)!.ce);
    const pe = strikes.map((s) => byStrike.get(s)!.pe);

    const suffixCeCount = new Array<number>(n + 1).fill(0);
    const suffixCeSum = new Array<number>(n + 1).fill(0);
    for (let i = n - 1; i >= 0; i -= 1) {
      suffixCeCount[i] = suffixCeCount[i + 1] + ce[i];
      suffixCeSum[i] = suffixCeSum[i + 1] + strikes[i] * ce[i];
    }
    const prefixPeCount = new Array<number>(n + 1).fill(0);
    const prefixPeSum = new Array<number>(n + 1).fill(0);
    for (let i = 0; i < n; i += 1) {
      prefixPeCount[i + 1] = prefixPeCount[i] + pe[i];
      prefixPeSum[i + 1] = prefixPeSum[i] + strikes[i] * pe[i];
    }

    let best = strikes[0];
    let bestPain = Infinity;
    for (let i = 0; i < n; i += 1) {
      const k = strikes[i];
      const painCe = suffixCeSum[i] - k * suffixCeCount[i];
      const painPe = k * prefixPeCount[i] - prefixPeSum[i];
      const pain = painCe + painPe;
      if (pain < bestPain) {
        bestPain = pain;
        best = k;
      }
    }
    return best;
  }

  // ── Formatting ──────────────────────────────────────────────────────────

  function fmtInt(value: number | null): string {
    if (value === null || !Number.isFinite(value)) return "—";
    return Math.round(value).toLocaleString("en-IN");
  }

  function fmtRupee(strike: number | null): string {
    return strike === null ? "—" : `₹${fmtInt(strike)}`;
  }
</script>

<div class="strip" role="group" aria-label="Market ticker strip" title={error || undefined}>
  <div class="metric" title="Current market regime — ADX / ATR classifier">
    <div class="metric-head">
      <Activity class="metric-icon" size={13} strokeWidth={2} aria-hidden="true" />
      <span class="metric-label">REGIME</span>
    </div>
    <div class="metric-value">
      <span class="chip tone-{regimeMeta.tone}">{regimeMeta.label}</span>
      {#if regimeMeta.dir === "up"}
        <ArrowUp class="dir-up size-3" aria-hidden="true" />
      {:else if regimeMeta.dir === "down"}
        <ArrowDown class="dir-down size-3" aria-hidden="true" />
      {/if}
    </div>
    <div class="metric-sub">
      {#if regime}
        <span class="mono">{Math.round(regime.confidence * 100)}%</span>
        <span class="muted-text">conf</span>
        {#if regime.transition}
          <ArrowLeftRight class="chip-warn size-3" aria-hidden="true" />
        {/if}
      {:else}
        <span class="muted-text">—</span>
      {/if}
    </div>
  </div>

  <div class="metric" title="Implied volatility level — mean chain IV (gauge 0–40%)">
    <div class="metric-head">
      <Gauge class="metric-icon" size={13} strokeWidth={2} aria-hidden="true" />
      <span class="metric-label">IV RANK</span>
    </div>
    <div class="metric-value mono">
      {ivLevel === null ? "—" : `${ivLevel.toFixed(1)}%`}
      {#if ivLabel}
        <span class="chip tone-{ivTone}">{ivLabel}</span>
      {/if}
    </div>
    <div class="gauge-track" role="img" aria-label={`IV ${ivLabel ?? "n/a"}`}>
      <div class="gauge-mask" style="width: {100 - ivFillOf(ivLevel)}%"></div>
    </div>
  </div>

  <div class="metric" title="Put-call ratio — put OI ÷ call OI">
    <div class="metric-head">
      <Scale class="metric-icon" size={13} strokeWidth={2} aria-hidden="true" />
      <span class="metric-label">PCR</span>
    </div>
    <div class="metric-value mono">{pcr === null ? "—" : pcr.toFixed(2)}</div>
    <div class="metric-sub">
      <span class="chip tone-{pcrTone}">{pcrLabelOf(pcr) ?? "—"}</span>
    </div>
  </div>

  <div class="metric" title="Max pain — strike minimizing total option payout at expiry">
    <div class="metric-head">
      <Crosshair class="metric-icon" size={13} strokeWidth={2} aria-hidden="true" />
      <span class="metric-label">MAX PAIN</span>
    </div>
    <div class="metric-value mono">{fmtRupee(maxPain)}</div>
    <div class="metric-sub"><span class="muted-text">expiry pin</span></div>
  </div>

  <div class="strip-foot">
    <span class="mono">{SYMBOL}</span>
    {#if !loading && error}
      <span class="dot" aria-hidden="true"></span>
    {/if}
  </div>
</div>

<style>
  /* Chrome strip on the canvas — hairline top + raised surface, the same
     surface language as the header (DESIGN §2.2). Not a card: no radius,
     no inner padding beyond the flex gutters. */
  .strip {
    display: flex;
    flex-wrap: wrap;
    align-items: stretch;
    gap: 6px;
    padding: 5px 8px;
    background: var(--canvas-raised);
    border-top: 1px solid var(--hairline);
  }
  .metric {
    display: flex;
    flex-direction: column;
    gap: 2px;
    flex: 1 1 130px;
    min-width: 110px;
    max-width: 210px;
    padding: 4px 8px;
    border-left: 1px solid var(--hairline);
  }
  .metric:first-child {
    border-left: none;
  }
  .metric-head {
    display: flex;
    align-items: center;
    gap: 4px;
  }
  .metric-icon {
    color: var(--faint);
  }
  .metric-label {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .metric-value {
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
    line-height: 1.2;
    white-space: nowrap;
  }
  .metric-sub {
    display: flex;
    align-items: center;
    gap: 5px;
    font-size: 9px;
    min-height: 12px;
  }
  .mono {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
  }
  .muted-text {
    color: var(--muted);
  }
  .chip {
    font-family: var(--font-mono);
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.06em;
    border-radius: 3px;
    padding: 1px 5px;
    border: 1px solid currentColor;
    white-space: nowrap;
  }
  .tone-success {
    color: var(--success);
  }
  .tone-warning {
    color: var(--warning);
  }
  .tone-danger {
    color: var(--danger);
  }
  .tone-muted {
    color: var(--muted);
  }
  /* Regime direction caret — Indian price law: red = up, green = down.
     Rendered as Lucide SVGs (size-3) carrying these color tokens. */
  .dir-up {
    color: var(--price-up);
  }
  .dir-down {
    color: var(--price-down);
  }
  .chip-warn {
    color: var(--warning);
  }
  /* IV gauge: gradient green (low) → amber → red (high); the mask hides the
     un-filled right portion so the fill color encodes the level. */
  .gauge-track {
    position: relative;
    height: 4px;
    border-radius: 2px;
    overflow: hidden;
    background: linear-gradient(90deg, var(--success), var(--warning), var(--danger));
  }
  .gauge-mask {
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    background: var(--canvas-raised);
    transition: width 200ms ease-out;
  }
  .strip-foot {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-left: auto;
    padding: 4px 6px;
    font-size: 10px;
    color: var(--faint);
  }
  /* Fetch-failure indicator: red dot, message in the strip title. */
  .dot {
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: var(--danger);
  }

  /* Narrow screens: force two cards per row so nothing clips. */
  @media (max-width: 720px) {
    .metric {
      flex-basis: calc(50% - 3px);
      min-width: 0;
      max-width: none;
    }
  }
</style>
