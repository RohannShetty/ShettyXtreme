<script lang="ts">
  import { onMount } from "svelte";
  import { get } from "../lib/api";

  type Hint = {
    direction: string;
    strike: number | null;
    premium: number | null;
    ev_after_cost: number | null;
    rationale: string;
  };

  let hint: Hint | null = null;
  let error = "";

  onMount(() => {
    load();
  });

  async function load(): Promise<void> {
    error = "";
    try {
      hint = await get<Hint>("/api/intelligence/strategy-hint");
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  $: dir = hint ? String(hint.direction).toLowerCase() : "";
  $: badgeClass = dir === "bullish" ? "badge-bull" : dir === "bearish" ? "badge-bear" : "badge-neutral";
  $: badgeText =
    dir === "bullish" ? "BULLISH" : dir === "bearish" ? "BEARISH" : "NEUTRAL";
  $: strategyName =
    dir === "bullish" ? "Long Call" : dir === "bearish" ? "Long Put" : "Stand Aside";

  function fmt(value: number | null | undefined): string {
    if (value === null || value === undefined || !isFinite(value)) return "—";
    return value.toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }
</script>

<section class="panel hints">
  <header class="panel-head">
    <h2>Strategy Hint</h2>
    <button class="refresh" on:click={load} title="Refresh">↻</button>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {:else if hint}
    <div class="body">
      <div class="row1">
        <span class="badge {badgeClass}">{badgeText}</span>
        <span class="strategy">{strategyName}</span>
      </div>
      <div class="ev-line mono">
        <span>STRIKE <b>{hint.strike != null ? fmt(hint.strike) : "—"}</b></span>
        <span>PREM <b>{hint.premium != null ? fmt(hint.premium) : "—"}</b></span>
        <span>EV <b>{hint.ev_after_cost != null ? fmt(hint.ev_after_cost) : "—"}</b></span>
      </div>
      <p class="rationale">{hint.rationale || "No rationale available."}</p>
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
    height: 100%;
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
  .refresh {
    background: none;
    border: 1px solid var(--hairline);
    border-radius: 4px;
    color: var(--muted);
    cursor: pointer;
    padding: 2px 8px;
    font-size: 13px;
  }
  .refresh:hover {
    color: var(--ink);
    border-color: var(--hairline-strong);
  }
  .body {
    padding: 12px 10px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    overflow-y: auto;
  }
  .row1 {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .badge {
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.06em;
    border-radius: 4px;
    padding: 3px 8px;
    white-space: nowrap;
  }
  .badge-bull {
    color: var(--price-up);
    border: 1px solid var(--price-up);
  }
  .badge-bear {
    color: var(--price-down);
    border: 1px solid var(--price-down);
  }
  .badge-neutral {
    color: var(--muted);
    border: 1px solid var(--hairline-strong);
  }
  .strategy {
    color: var(--ink);
    font-size: 13px;
    font-weight: 600;
  }
  .ev-line {
    display: flex;
    gap: 14px;
    background: var(--canvas-raised);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    padding: 8px 10px;
    font-size: 11px;
    color: var(--muted);
    flex-wrap: wrap;
  }
  .ev-line b {
    color: var(--ink);
    font-weight: 600;
    margin-left: 4px;
  }
  .rationale {
    margin: 0;
    color: var(--body);
    font-size: 12px;
    line-height: 1.6;
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
