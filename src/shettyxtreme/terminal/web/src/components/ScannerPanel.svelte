<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { get } from "$lib/api";
  import { Button } from "$lib/components/ui/button";
  import { Badge, type BadgeVariant } from "$lib/components/ui/badge";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import { Skeleton } from "$lib/components/ui/skeleton";
  import { RotateCw } from "@lucide/svelte";

  type Gap = { symbol: string; gap_type: string; gap_percent: number; direction: string };
  type Cluster = { symbol: string; cluster_type: string; strength: number; source_count: number };
  type Alert = { alert_type: string; severity: string; message: string; timestamp: string };
  type Finding = {
    scanner_type: string;
    symbol: string;
    severity: string;
    detail: Record<string, unknown>;
    timestamp: string;
  };

  /** Data older than this is flagged STALE (warning chip in the panel head). */
  const STALE_MS = 60_000;

  /** Human-readable labels for scanner types. */
  const SCANNER_LABELS: Record<string, string> = {
    gamma_spike: "Gamma Spike",
    iv_crush: "IV Crush",
    iv_expansion: "IV Expansion",
    pcr_extremes: "PCR Extremes",
    max_pain_drift: "Max Pain",
    theta_harvest: "Theta Harvest",
    calendar_spread: "Calendar",
    vertical_skew: "Vert Skew",
    gap_fill: "Gap Fill",
    volume_anomaly: "Vol Anomaly",
    oi_buildup: "OI Buildup",
  };

  let gaps: Gap[] = $state([]);
  let clusters: Cluster[] = $state([]);
  let alerts: Alert[] = $state([]);
  let findings: Finding[] = $state([]);
  let error = $state("");
  let loading = $state(true);
  let fetchedAt = $state<number | null>(null);
  let now = $state(Date.now());

  // Keyboard navigation cursor over the flat item list (findings → gaps → clusters → alerts).
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
    loading = true;
    try {
      const [g, c, a, f] = await Promise.all([
        get<Gap[]>("/api/scanner/gaps"),
        get<Cluster[]>("/api/scanner/clusters"),
        get<Alert[]>("/api/scanner/alerts"),
        get<Finding[]>("/api/scanner/findings?limit=50"),
      ]);
      gaps = g;
      clusters = c;
      alerts = a;
      findings = f;
      fetchedAt = Date.now();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      loading = false;
    }
  }

  let stale = $derived(fetchedAt !== null && now - fetchedAt > STALE_MS);

  /** Group findings by scanner_type for the per-type column grid. */
  let findingsByType = $derived.by(() => {
    const groups: Record<string, Finding[]> = {};
    for (const f of findings) {
      const t = f.scanner_type;
      if (!groups[t]) groups[t] = [];
      groups[t].push(f);
    }
    return groups;
  });

  let findingTypes = $derived(Object.keys(findingsByType).sort());

  let total = $derived(findings.length + gaps.length + clusters.length + alerts.length);

  /** Non-empty columns as [start, end] flat ranges — for ArrowLeft/Right hops. */
  let cols = $derived.by(() => {
    const ranges: { start: number; end: number }[] = [];
    let offset = 0;
    // Findings (grouped by type)
    for (const t of findingTypes) {
      const count = findingsByType[t].length;
      if (count > 0) ranges.push({ start: offset, end: offset + count - 1 });
      offset += count;
    }
    // Legacy columns
    if (gaps.length > 0) ranges.push({ start: offset, end: offset + gaps.length - 1 });
    offset += gaps.length;
    if (clusters.length > 0) ranges.push({ start: offset, end: offset + clusters.length - 1 });
    offset += clusters.length;
    if (alerts.length > 0) ranges.push({ start: offset, end: offset + alerts.length - 1 });
    return ranges;
  });

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

  /** Conviction-badge level from a severity string (DESIGN §4 4-level scale). */
  function convictionLevel(severity: string): BadgeVariant {
    const s = String(severity).toUpperCase();
    if (s === "EXTREME") return "conviction-extreme";
    if (s === "HIGH") return "conviction-high";
    if (s === "MEDIUM") return "conviction-medium";
    return "conviction-low";
  }

  function dirClass(direction: string): string {
    return String(direction).toLowerCase().includes("down") ? "price-down" : "price-up";
  }

  /** Format a finding detail key for display. */
  function fmtDetailKey(key: string): string {
    return key.replace(/_/g, " ");
  }

  /** Compute a flat index offset for a finding within the findings block. */
  function findingIdx(typeIdx: number, itemIdx: number): number {
    let offset = 0;
    for (let i = 0; i < typeIdx; i++) {
      offset += findingsByType[findingTypes[i]].length;
    }
    return offset + itemIdx;
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

  <ScrollArea class="flex-1 min-h-0">
    <div class="cards">
      <!-- ── Findings (11 scanner types) ────────────────────────────── -->
      {#if findings.length > 0}
        {#each findingTypes as typeKey, ti (typeKey)}
          <div class="card">
            <span class="eyebrow">{SCANNER_LABELS[typeKey] ?? typeKey}</span>
            <span class="stat">{findingsByType[typeKey].length}</span>
            <ul role="list">
              {#each findingsByType[typeKey] as f, fi (f.symbol + f.timestamp + fi)}
                {@const idx = findingIdx(ti, fi)}
                <li
                  class="item"
                  role="option"
                  aria-selected={idx === active}
                  tabindex={idx === active ? 0 : -1}
                  data-scanner-idx={idx}
                  onclick={() => select(idx)}
                  onkeydown={(e) => onItemKeydown(e, idx)}
                >
                  <span class="ticker">{f.symbol}</span>
                  <Badge variant={convictionLevel(f.severity)}>{f.severity}</Badge>
                  {#if f.detail}
                    {@const detailEntries = Object.entries(f.detail).slice(0, 2)}
                    {#each detailEntries as [key, val] (key)}
                      <span class="badge-regime">{fmtDetailKey(key)}: {String(val)}</span>
                    {/each}
                  {/if}
                </li>
              {/each}
            </ul>
          </div>
        {/each}
      {/if}

      <!-- ── Legacy: Gaps ───────────────────────────────────────────── -->
      <div class="card">
        <span class="eyebrow">Gaps</span>
        <span class="stat">{gaps.length}</span>
        <ul role="list">
          {#if loading}
            {#each Array.from({ length: 4 }) as _, i (i)}
              <li class="item">
                <Skeleton class="h-3.5 w-16" />
                <Skeleton class="h-3.5 w-14" />
                <Skeleton class="h-3.5 w-12 ml-auto" />
              </li>
            {/each}
          {:else}
            {#each gaps as g, i (g.symbol + g.gap_type + g.gap_percent)}
            {@const idx = findings.length + i}
            <li
              class="item"
              role="option"
              aria-selected={idx === active}
              tabindex={idx === active ? 0 : -1}
              data-scanner-idx={idx}
              onclick={() => select(idx)}
              onkeydown={(e) => onItemKeydown(e, idx)}
            >
              <span class="ticker">{g.symbol}</span>
              <span class="badge-regime">{g.gap_type}</span>
              <span class="num {dirClass(g.direction)}">{g.gap_percent > 0 ? "+" : ""}{g.gap_percent.toFixed(2)}%</span>
            </li>
          {/each}
          {/if}
          {#if gaps.length === 0 && !loading}
            <li class="empty">No gaps detected.</li>
          {/if}
        </ul>
      </div>

      <!-- ── Legacy: Clusters ───────────────────────────────────────── -->
      <div class="card">
        <span class="eyebrow">Clusters</span>
        <span class="stat">{clusters.length}</span>
        <ul role="list">
          {#if loading}
            {#each Array.from({ length: 4 }) as _, i (i)}
              <li class="item">
                <Skeleton class="h-3.5 w-16" />
                <Skeleton class="h-3.5 w-14" />
                <Skeleton class="h-3.5 w-12 ml-auto" />
              </li>
            {/each}
          {:else}
            {#each clusters as c, i (c.symbol + c.cluster_type)}
            {@const idx = findings.length + gaps.length + i}
            <li
              class="item"
              role="option"
              aria-selected={idx === active}
              tabindex={idx === active ? 0 : -1}
              data-scanner-idx={idx}
              onclick={() => select(idx)}
              onkeydown={(e) => onItemKeydown(e, idx)}
            >
              <span class="ticker">{c.symbol}</span>
              <span class="badge-regime">{c.cluster_type}</span>
              <span class="num">{c.strength.toFixed(1)} / 10</span>
            </li>
          {/each}
          {/if}
          {#if clusters.length === 0 && !loading}
            <li class="empty">No clusters found.</li>
          {/if}
        </ul>
      </div>

      <!-- ── Legacy: Alerts ─────────────────────────────────────────── -->
      <div class="card">
        <span class="eyebrow">Alerts</span>
        <span class="stat">{alerts.length}</span>
        <ul role="list">
          {#if loading}
            {#each Array.from({ length: 4 }) as _, i (i)}
              <li class="item">
                <Skeleton class="h-3.5 w-16" />
                <Skeleton class="h-3.5 flex-1" />
              </li>
            {/each}
          {:else}
            {#each alerts as a, i (a.message + a.timestamp)}
            {@const idx = findings.length + gaps.length + clusters.length + i}
            <li
              class="item"
              role="option"
              aria-selected={idx === active}
              tabindex={idx === active ? 0 : -1}
              data-scanner-idx={idx}
              onclick={() => select(idx)}
              onkeydown={(e) => onItemKeydown(e, idx)}
            >
              <Badge variant={convictionLevel(a.severity)}>{a.severity}</Badge>
              <span class="msg">{a.message}</span>
            </li>
          {/each}
          {/if}
          {#if alerts.length === 0 && !loading}
            <li class="empty">No alerts.</li>
          {/if}
        </ul>
      </div>
    </div>
  </ScrollArea>
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
  /* Conviction badge — consolidated onto the badge primitive's conviction-*
     variants (ui/badge/index.ts); no scoped classes. */
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
