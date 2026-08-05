<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { get } from "../lib/api";
  import { Button } from "$lib/components/ui/button";
  import { RotateCw } from "@lucide/svelte";

  type Hint = {
    direction: string;
    strike: number | null;
    premium: number | null;
    ev_after_cost: number | null;
    rationale: string;
  };

  /** Hint data older than this is flagged STALE (warning chip in the panel head). */
  const STALE_MS = 5 * 60_000;

  let hint = $state<Hint | null>(null);
  let error = $state("");
  let fetchedAt = $state<number | null>(null);
  let now = $state(Date.now());
  let expanded = $state(false);

  let timer: ReturnType<typeof setInterval> | undefined;

  onMount(() => {
    load();
    timer = setInterval(() => (now = Date.now()), 30_000);
  });

  onDestroy(() => {
    if (timer) clearInterval(timer);
  });

  async function load(): Promise<void> {
    error = "";
    try {
      hint = await get<Hint>("/api/intelligence/strategy-hint");
      fetchedAt = Date.now();
      expanded = false;
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  let stale = $derived(fetchedAt !== null && now - fetchedAt > STALE_MS);

  let dir = $derived(String(hint?.direction ?? "").toLowerCase());
  let badgeClass = $derived(dir === "bullish" ? "up" : dir === "bearish" ? "down" : "neutral");
  let badgeText = $derived(dir === "bullish" ? "UP" : dir === "bearish" ? "DOWN" : "NEUTRAL");
  let strategyName = $derived(
    dir === "bullish" ? "Long Call" : dir === "bearish" ? "Long Put" : "Stand Aside",
  );

  /** Indian grouping (lakh/crore) for strike/premium/EV numerals. */
  function fmt(value: number | null | undefined): string {
    if (value === null || value === undefined || !isFinite(value)) return "—";
    return value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
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
      onclick={load}
      aria-label="Refresh hint"
    >
      <RotateCw class="size-3.5" />
    </Button>
  </header>

  {#if error}
    <p class="error">{error}</p>
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
        <span class="badge-direction {badgeClass}">{badgeText}</span>
        <span class="meta">{strategyName}</span>
        <span class="chev" aria-hidden="true">{expanded ? "▲" : "▼"}</span>
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
          <p class="rationale">{hint.rationale || "No rationale available."}</p>
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
  .hint-card {
    margin: 10px;
    padding: 10px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-radius: 6px;
    cursor: pointer;
  }
  /* Focus ring on the expandable hint card (keyboard-first, DESIGN §3.2). */
  .hint-card:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  .summary {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  /* Direction badge — UP price-up (red), DOWN price-down (green), NEUTRAL muted. */
  .badge-direction {
    display: inline-flex;
    align-items: center;
    padding: 1px 6px;
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-size: 11px;
    font-weight: 500;
    line-height: 14px;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    border: 1px solid;
    border-radius: 2px;
    white-space: nowrap;
  }
  .badge-direction.up {
    color: var(--price-up);
    border-color: var(--price-up);
  }
  .badge-direction.down {
    color: var(--price-down);
    border-color: var(--price-down);
  }
  .badge-direction.neutral {
    color: var(--muted);
    border-color: var(--hairline-strong);
  }
  .meta {
    flex: 1;
    color: var(--body);
    font-size: 12px;
    line-height: 16px;
    min-width: 0;
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
