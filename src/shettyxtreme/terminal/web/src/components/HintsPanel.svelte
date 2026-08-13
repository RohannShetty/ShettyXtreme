<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import {
    getStrategyHint,
    proposeFromHint,
    getHintStats,
    type StrategyHint,
    type HintStatsResponse,
  } from "$lib/api";
  import { Button } from "$lib/components/ui/button";
  import {
    Card,
    CardContent,
    CardHeader,
    CardTitle,
  } from "$lib/components/ui/card";
  import { Progress } from "$lib/components/ui/progress";
  import { Badge, type BadgeVariant } from "$lib/components/ui/badge";
  import { RotateCw, ArrowRight, Loader2 } from "@lucide/svelte";
  import { toast } from "svelte-sonner";
  import { selectedSymbol } from "$lib/selection.svelte";
  import { rightDockTab } from "$lib/rightDockTab.svelte";

  /** Hint data older than this is flagged STALE (warning chip in the panel head). */
  const STALE_MS = 5 * 60_000;

  let hint = $state<StrategyHint | null>(null);
  let stats = $state<HintStatsResponse | null>(null);
  let hintError = $state("");
  let statsError = $state("");
  let fetchedAt = $state<number | null>(null);
  let now = $state(Date.now());
  let expanded = $state(false);
  let creating = $state(false);

  let timer: ReturnType<typeof setInterval> | undefined;

  onMount(() => {
    loadHint();
    loadStats();
    timer = setInterval(() => (now = Date.now()), 30_000);
  });

  onDestroy(() => {
    if (timer) clearInterval(timer);
  });

  async function loadHint(): Promise<void> {
    hintError = "";
    try {
      hint = await getStrategyHint();
      fetchedAt = Date.now();
      expanded = false;
    } catch (err) {
      hintError = err instanceof Error ? err.message : String(err);
    }
  }

  async function loadStats(): Promise<void> {
    statsError = "";
    try {
      stats = await getHintStats(30);
    } catch (err) {
      statsError = err instanceof Error ? err.message : String(err);
    }
  }

  async function createProposal(event: MouseEvent): Promise<void> {
    event.stopPropagation();
    if (!hint) return;
    creating = true;
    try {
      const symbol = selectedSymbol.symbol || "NIFTY";
      const quantity =
        hint.lot_size && hint.lots ? hint.lot_size * hint.lots : null;
      const proposal = await proposeFromHint({
        symbol,
        direction: hint.direction,
        strike: hint.strike,
        premium: hint.premium,
        expiry: hint.expiry,
        option_type: hint.option_type,
        lot_size: hint.lot_size,
        lots: hint.lots,
        stop_loss: hint.stop_loss,
        target: hint.target,
        rationale: hint.rationale,
        confidence: hint.confidence,
        conviction: hint.confidence,
        quantity,
      });
      toast.success("Proposal created", {
        description: `${proposal.symbol} ${proposal.option_type ?? ""} ${proposal.strike != null ? fmt(proposal.strike) : ""}`.trim(),
      });
      rightDockTab.value = "proposals";
    } catch (err) {
      toast.error("Failed to create proposal", {
        description: err instanceof Error ? err.message : String(err),
      });
    } finally {
      creating = false;
    }
  }

  let stale = $derived(fetchedAt !== null && now - fetchedAt > STALE_MS);

  let dir = $derived(String(hint?.direction ?? "").toLowerCase());
  let badgeClass = $derived(dir === "bullish" ? "up" : dir === "bearish" ? "down" : "neutral");
  let badgeText = $derived(dir === "bullish" ? "UP" : dir === "bearish" ? "DOWN" : "NEUTRAL");
  let strategyName = $derived(
    (hint?.strategy && hint.strategy.trim() !== ""
      ? hint.strategy
      : null) ??
      (dir === "bullish" ? "Long Call" : dir === "bearish" ? "Long Put" : "Stand Aside"),
  );

  let confidence = $derived(Math.min(1, Math.max(0, hint?.confidence ?? 0)));
  let confidencePct = $derived(Math.round(confidence * 100));
  let convictionVariant = $derived<BadgeVariant>(
    confidence >= 0.75
      ? "conviction-extreme"
      : confidence >= 0.5
        ? "conviction-high"
        : confidence >= 0.25
          ? "conviction-medium"
          : "conviction-low",
  );

  let actionable = $derived(dir !== "neutral" && hint?.strike != null && hint?.premium != null);

  function computeSltp(
    h: StrategyHint | null,
  ): { sl: number; entry: number; tp: number } | null {
    const sl = h?.stop_loss;
    const entry = h?.premium;
    const tp = h?.target;
    if (sl == null || entry == null || tp == null) return null;
    const min = Math.min(sl, entry, tp);
    const max = Math.max(sl, entry, tp);
    const range = max - min;
    if (range <= 0) return { sl: 0, entry: 50, tp: 100 };
    return {
      sl: ((sl - min) / range) * 100,
      entry: ((entry - min) / range) * 100,
      tp: ((tp - min) / range) * 100,
    };
  }

  let sltp = $derived(computeSltp(hint));

  /** Indian grouping (lakh/crore) for strike/premium/EV numerals. */
  function fmt(value: number | null | undefined): string {
    if (value === null || value === undefined || !isFinite(value)) return "—";
    return value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function fmtPct(value: number | null | undefined): string {
    if (value === null || value === undefined || !isFinite(value)) return "—";
    return `${(value * 100).toFixed(1)}`;
  }

  function fmtCurrency(value: number | null | undefined): string {
    if (value === null || value === undefined || !isFinite(value)) return "—";
    const negative = value < 0;
    const abs = Math.abs(value);
    return `${negative ? "-" : ""}₹${fmt(abs)}`;
  }
</script>

<section class="panel hints">
  <header class="panel-head">
    <div class="head-group">
      <h2>Strategy Hint</h2>
      {#if stale}
        <span class="stale-chip" role="status">STALE</span>
      {/if}
    </div>
    <Button
      variant="ghost"
      size="icon"
      class="size-7 text-muted-foreground hover:text-ink"
      onclick={loadHint}
      aria-label="Refresh hint"
    >
      <RotateCw class="size-3.5" />
    </Button>
  </header>

  <Card class="mx-2 mt-2 border-hairline bg-surface-card">
    <CardHeader class="pb-2">
      <CardTitle class="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
        Hint Accuracy — Last 30 days
      </CardTitle>
    </CardHeader>
    <CardContent class="pt-0">
      {#if statsError}
        <p class="text-[11px] text-danger">{statsError}</p>
      {:else if stats}
        {@const muted = stats.sample_size < 10}
        <div class="stats-grid">
          <div class="stat">
            <span class="stat-label">Win Rate</span>
            <span class="stat-value font-mono {muted ? 'text-muted-foreground' : 'text-ink'}">
              {stats.win_rate != null ? `${fmtPct(stats.win_rate)}%` : "—"}
            </span>
          </div>
          <div class="stat">
            <span class="stat-label">Avg P&L</span>
            <span
              class="stat-value font-mono {muted
                ? 'text-muted-foreground'
                : (stats.avg_pnl ?? 0) >= 0
                  ? 'text-price-up'
                  : 'text-price-down'}"
            >
              {stats.avg_pnl != null ? fmtCurrency(stats.avg_pnl) : "—"}
            </span>
          </div>
          <div class="stat">
            <span class="stat-label">Sample</span>
            <span class="stat-value font-mono {muted ? 'text-muted-foreground' : 'text-ink'}">
              {stats.sample_size}
            </span>
          </div>
        </div>
        {#if muted}
          <p class="mt-2 text-[10px] text-muted-foreground">
            Not enough data ({stats.sample_size} hint{stats.sample_size === 1 ? "" : "s"}).
          </p>
        {/if}
      {:else}
        <div class="flex items-center gap-2 text-[11px] text-muted-foreground">
          <Loader2 class="size-3 animate-spin" />
          Loading stats…
        </div>
      {/if}
    </CardContent>
  </Card>

  {#if hintError}
    <p class="error">{hintError}</p>
  {:else if hint}
    <div
      class="hint-card"
      class:expanded
      tabindex="0"
      role="button"
      aria-expanded={expanded}
      aria-controls="hint-details"
      onclick={() => (expanded = !expanded)}
      onkeydown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          expanded = !expanded;
        }
      }}
    >
      <div class="summary">
        <div class="summary-left">
          <Badge variant={convictionVariant}>{badgeText}</Badge>
          <span class="strategy-name">{strategyName}</span>
        </div>
        <div class="summary-right">
          <Badge variant="outline" class="font-mono text-[10px]">{confidencePct}%</Badge>
          <span class="chev" aria-hidden="true">{expanded ? "▲" : "▼"}</span>
        </div>
      </div>

      {#if expanded}
        <div class="details" id="hint-details">
          <div class="ev-line">
            <span class="ev-cell">
              <span class="ev-label">STRIKE</span>
              <span class="ev-value">{hint.strike != null ? fmt(hint.strike) : "—"}</span>
            </span>
            <span class="ev-cell">
              <span class="ev-label">PREM</span>
              <span class="ev-value">{hint.premium != null ? fmt(hint.premium) : "—"}</span>
            </span>
            <span class="ev-cell">
              <span class="ev-label">EV</span>
              <span class="ev-value">{hint.ev_after_cost != null ? fmt(hint.ev_after_cost) : "—"}</span>
            </span>
          </div>

          {#if sltp}
            <div class="sltp-track">
              <div class="sltp-row">
                <span class="sltp-label">
                  <span class="sltp-dot bg-sl-level"></span>
                  SL {fmt(hint.stop_loss)}
                </span>
                <span class="sltp-label">
                  <span class="sltp-dot bg-body"></span>
                  Entry {fmt(hint.premium)}
                </span>
                <span class="sltp-label">
                  <span class="sltp-dot bg-tgt-level"></span>
                  TP {fmt(hint.target)}
                </span>
              </div>
              <div class="sltp-bar">
                <div class="sltp-marker bg-sl-level" style="left: {sltp.sl}%"></div>
                <div class="sltp-marker bg-body" style="left: {sltp.entry}%"></div>
                <div class="sltp-marker bg-tgt-level" style="left: {sltp.tp}%"></div>
              </div>
            </div>
          {/if}

          <div class="confidence-row">
            <span class="ev-label">Confidence</span>
            <Progress value={confidencePct} class="h-1 flex-1 bg-surface-elevated" />
            <span class="confidence-value font-mono">{confidencePct}%</span>
          </div>

          <p class="rationale">{hint.rationale || "No rationale available."}</p>

          {#if actionable}
            <Button class="w-full" onclick={createProposal} disabled={creating}>
              {#if creating}
                <Loader2 class="mr-1 size-3.5 animate-spin" />
                Creating…
              {:else}
                Create Proposal
                <ArrowRight class="ml-1 size-3.5" />
              {/if}
            </Button>
          {/if}
        </div>
      {:else}
        <p class="expand-hint">Press Enter to expand details</p>
      {/if}
    </div>
  {:else}
    <p class="empty">Loading…</p>
  {/if}
</section>

<style>
  .hints {
    display: flex;
    flex-direction: column;
    min-width: 320px;
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
    flex-shrink: 0;
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
  .stats-grid {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    gap: 8px;
  }
  .stat {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .stat-label {
    font-size: 10px;
    line-height: 14px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .stat-value {
    font-size: 13px;
    line-height: 20px;
    font-weight: 500;
    white-space: nowrap;
  }
  .hint-card {
    margin: 10px;
    padding: 10px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-radius: 6px;
    cursor: pointer;
    flex-shrink: 0;
  }
  /* Focus ring on the expandable hint card (keyboard-first, DESIGN §3.2). */
  .hint-card:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  .summary {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 10px;
  }
  .summary-left,
  .summary-right {
    display: flex;
    align-items: center;
    gap: 8px;
    min-width: 0;
  }
  .summary-right {
    flex-shrink: 0;
  }
  .strategy-name {
    font-size: 12px;
    line-height: 16px;
    color: var(--body);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .chev {
    font-family: var(--font-mono);
    font-size: 9px;
    color: var(--faint);
  }
  .details {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-top: 10px;
    border-top: 1px solid var(--hairline);
    padding-top: 10px;
  }
  /* Strike/premium/EV — mono numerals, Indian grouping, tabular figures. */
  .ev-line {
    display: flex;
    flex-wrap: wrap;
    gap: 14px;
  }
  .ev-cell {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .ev-label {
    font-size: 11px;
    line-height: 14px;
    letter-spacing: 0.08em;
    color: var(--faint);
    text-transform: uppercase;
  }
  .ev-value {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-size: 13px;
    font-weight: 500;
    line-height: 20px;
    color: var(--ink);
    white-space: nowrap;
  }
  .sltp-track {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .sltp-row {
    display: flex;
    justify-content: space-between;
    gap: 4px;
  }
  .sltp-label {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 10px;
    line-height: 14px;
    color: var(--body);
  }
  .sltp-dot {
    width: 6px;
    height: 6px;
    border-radius: 999px;
    flex-shrink: 0;
  }
  .sltp-bar {
    position: relative;
    height: 4px;
    background: var(--surface-elevated);
    border-radius: 2px;
  }
  .sltp-marker {
    position: absolute;
    top: 50%;
    width: 8px;
    height: 8px;
    border-radius: 999px;
    transform: translate(-50%, -50%);
    border: 1px solid var(--surface-card);
  }
  .confidence-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .confidence-value {
    font-size: 11px;
    line-height: 14px;
    color: var(--ink);
    min-width: 28px;
    text-align: right;
  }
  .rationale {
    margin: 0;
    color: var(--body);
    font-size: 13px;
    line-height: 20px;
  }
  .expand-hint {
    margin: 8px 0 0;
    color: var(--faint);
    font-size: 11px;
    line-height: 14px;
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
    padding: 8px 10px;
    margin: 0;
  }
</style>
