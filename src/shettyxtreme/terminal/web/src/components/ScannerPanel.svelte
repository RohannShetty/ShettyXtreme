<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { get } from "../lib/api";
  import { Button } from "$lib/components/ui/button";
  import { RotateCw } from "@lucide/svelte";

  type Gap = { symbol: string; gap_type: string; gap_percent: number; direction: string };
  type Cluster = { symbol: string; cluster_type: string; strength: number; source_count: number };
  type Alert = { alert_type: string; severity: string; message: string; timestamp: string };

  /** Data older than this is flagged STALE (warning chip in the panel head). */
  const STALE_MS = 60_000;

  let gaps: Gap[] = $state([]);
  let clusters: Cluster[] = $state([]);
  let alerts: Alert[] = $state([]);
  let error = $state("");
  let fetchedAt = $state<number | null>(null);
  let now = $state(Date.now());

  // Keyboard navigation cursor over the flat item list (gaps → clusters → alerts).
  let active = $state(0);
  let navActive = $state(false);
  let panelEl: HTMLElement | undefined = $state();

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
      const [g, c, a] = await Promise.all([
        get<Gap[]>("/api/scanner/gaps"),
        get<Cluster[]>("/api/scanner/clusters"),
        get<Alert[]>("/api/scanner/alerts"),
      ]);
      gaps = g;
      clusters = c;
      alerts = a;
      fetchedAt = Date.now();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  let stale = $derived(fetchedAt !== null && now - fetchedAt > STALE_MS);

  let total = $derived(gaps.length + clusters.length + alerts.length);

  /** Flat index of the first item in each column (columns render in order). */
  let colStarts = $derived.by(() => ({
    gap: 0,
    cluster: gaps.length,
    alert: gaps.length + clusters.length,
  }));

  /** Non-empty columns as [start, end] flat ranges — for ArrowLeft/Right hops. */
  let cols = $derived.by(() => {
    const ranges: { start: number; end: number }[] = [];
    if (gaps.length > 0) ranges.push({ start: 0, end: gaps.length - 1 });
    if (clusters.length > 0)
      ranges.push({ start: gaps.length, end: gaps.length + clusters.length - 1 });
    if (alerts.length > 0) ranges.push({ start: gaps.length + clusters.length, end: total - 1 });
    return ranges;
  });

  const gapIdx = (i: number) => colStarts.gap + i;
  const clusterIdx = (i: number) => colStarts.cluster + i;
  const alertIdx = (i: number) => colStarts.alert + i;

  function select(idx: number): void {
    navActive = true;
    active = idx;
  }

  /** Roving-tabindex pattern: only the active item is in the Tab order, and
      arrow keys on any focused item move the cursor across the whole panel. */
  function onItemKeydown(e: KeyboardEvent, idx: number): void {
    if (total === 0) return;
    const len = total;
    let next = idx;
    switch (e.key) {
      case "ArrowDown":
        next = Math.min(len - 1, idx + 1);
        break;
      case "ArrowUp":
        next = Math.max(0, idx - 1);
        break;
      case "ArrowRight": {
        const col = cols.find((c) => idx >= c.start && idx <= c.end);
        const nxt = col ? cols.find((c) => c.start > col.end) : undefined;
        if (nxt) next = nxt.start;
        break;
      }
      case "ArrowLeft": {
        const col = cols.find((c) => idx >= c.start && idx <= c.end);
        const prv = col ? [...cols].reverse().find((c) => c.end < col.start) : undefined;
        if (prv) next = prv.start;
        break;
      }
      case "Home":
        next = 0;
        break;
      case "End":
        next = len - 1;
        break;
      default:
        return;
    }
    e.preventDefault();
    if (next !== idx) select(next);
  }

  // Keep the cursor inside the list when data shrinks.
  $effect(() => {
    if (total === 0) active = 0;
    else if (active >= total) active = total - 1;
  });

  // Move real focus onto the active item once the user starts navigating.
  $effect(() => {
    if (!navActive) return;
    const el = panelEl?.querySelector<HTMLElement>(`[data-scanner-idx="${active}"]`);
    if (el) {
      el.focus({ preventScroll: true });
      el.scrollIntoView({ block: "nearest" });
    }
  });

  /** Conviction-badge level from an alert severity string. */
  function convictionLevel(severity: string): string {
    const s = String(severity).toUpperCase();
    if (s === "EXTREME") return "extreme";
    if (s === "HIGH") return "high";
    if (s === "MEDIUM") return "medium";
    return "low";
  }

  function dirClass(direction: string): string {
    return String(direction).toLowerCase().includes("down") ? "price-down" : "price-up";
  }
</script>

<section class="panel scanner" bind:this={panelEl}>
  <header class="panel-head">
    <div class="head-group">
      <h2>Scanner</h2>
      {#if stale}
        <span class="stale-chip" role="status">STALE</span>
      {/if}
    </div>
    <Button
      variant="ghost"
      size="icon"
      class="size-7 text-muted-foreground hover:text-ink"
      onclick={load}
      aria-label="Refresh scanner"
    >
      <RotateCw class="size-3.5" />
    </Button>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <div class="cards">
    <div class="card">
      <span class="eyebrow">Gaps</span>
      <span class="stat">{gaps.length}</span>
      <ul role="list">
        {#each gaps as g, i (g.symbol + g.gap_type + g.gap_percent)}
          <li
            class="item"
            role="option"
            aria-selected={gapIdx(i) === active}
            tabindex={gapIdx(i) === active ? 0 : -1}
            data-scanner-idx={gapIdx(i)}
            onclick={() => select(gapIdx(i))}
            onkeydown={(e) => onItemKeydown(e, gapIdx(i))}
          >
            <span class="ticker">{g.symbol}</span>
            <span class="badge-regime">{g.gap_type}</span>
            <span class="num {dirClass(g.direction)}">{g.gap_percent > 0 ? "+" : ""}{g.gap_percent.toFixed(2)}%</span>
          </li>
        {/each}
        {#if gaps.length === 0}
          <li class="empty">No gaps detected.</li>
        {/if}
      </ul>
    </div>

    <div class="card">
      <span class="eyebrow">Clusters</span>
      <span class="stat">{clusters.length}</span>
      <ul role="list">
        {#each clusters as c, i (c.symbol + c.cluster_type)}
          <li
            class="item"
            role="option"
            aria-selected={clusterIdx(i) === active}
            tabindex={clusterIdx(i) === active ? 0 : -1}
            data-scanner-idx={clusterIdx(i)}
            onclick={() => select(clusterIdx(i))}
            onkeydown={(e) => onItemKeydown(e, clusterIdx(i))}
          >
            <span class="ticker">{c.symbol}</span>
            <span class="badge-regime">{c.cluster_type}</span>
            <span class="num">{c.strength.toFixed(1)} / 10</span>
          </li>
        {/each}
        {#if clusters.length === 0}
          <li class="empty">No clusters found.</li>
        {/if}
      </ul>
    </div>

    <div class="card">
      <span class="eyebrow">Alerts</span>
      <span class="stat">{alerts.length}</span>
      <ul role="list">
        {#each alerts as a, i (a.message + a.timestamp)}
          <li
            class="item"
            role="option"
            aria-selected={alertIdx(i) === active}
            tabindex={alertIdx(i) === active ? 0 : -1}
            data-scanner-idx={alertIdx(i)}
            onclick={() => select(alertIdx(i))}
            onkeydown={(e) => onItemKeydown(e, alertIdx(i))}
          >
            <span class="badge-conv {convictionLevel(a.severity)}">{a.severity}</span>
            <span class="msg">{a.message}</span>
          </li>
        {/each}
        {#if alerts.length === 0}
          <li class="empty">No alerts.</li>
        {/if}
      </ul>
    </div>
  </div>
</section>

<style>
  .scanner {
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
  .cards {
    flex: 1;
    overflow-y: auto;
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 10px;
  }
  /* Scanner card — surface-card, eyebrow label, number-lg headline stat. */
  .card {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 10px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-radius: 6px;
  }
  .eyebrow {
    font-size: 11px;
    font-weight: 600;
    line-height: 14px;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .stat {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-size: 20px;
    font-weight: 600;
    line-height: 24px;
    color: var(--ink);
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  .item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 3px 6px 3px 4px;
    font-size: 11px;
    border-bottom: 1px solid var(--hairline);
    border-left: 2px solid transparent;
    min-height: 26px;
    cursor: pointer;
  }
  .item:last-child {
    border-bottom: none;
  }
  /* Selected/focused item: row-selected bg + 2px accent left edge (DESIGN §4). */
  .item:focus {
    outline: none;
    background: var(--row-selected);
    border-left-color: var(--accent);
  }
  .ticker {
    color: var(--ink);
    font-weight: 600;
    min-width: 70px;
    white-space: nowrap;
  }
  /* Regime-style badge — surface-elevated bg, hairline border, micro uppercase. */
  .badge-regime {
    display: inline-flex;
    align-items: center;
    padding: 1px 5px;
    font-size: 11px;
    line-height: 14px;
    font-weight: 400;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--body);
    background: var(--surface-elevated);
    border: 1px solid var(--hairline);
    border-radius: 2px;
    white-space: nowrap;
  }
  /* Conviction badge — LOW muted / MEDIUM warning / HIGH accent / EXTREME ink on row-selected. */
  .badge-conv {
    display: inline-flex;
    align-items: center;
    padding: 1px 5px;
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-size: 11px;
    font-weight: 500;
    line-height: 14px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    border: 1px solid;
    border-radius: 2px;
    white-space: nowrap;
  }
  .badge-conv.low {
    color: var(--muted);
    border-color: var(--hairline);
  }
  .badge-conv.medium {
    color: var(--warning);
    border-color: var(--warning);
  }
  .badge-conv.high {
    color: var(--accent);
    border-color: var(--accent);
  }
  .badge-conv.extreme {
    color: var(--ink);
    border-color: var(--hairline-strong);
    background: var(--row-selected);
  }
  .msg {
    color: var(--body);
    flex: 1;
    min-width: 0;
  }
  .empty {
    color: var(--faint);
    border-bottom: none;
    padding: 3px 4px;
  }
  .error {
    color: var(--danger);
    font-size: 11px;
    padding: 8px 10px;
    margin: 0;
  }
</style>
