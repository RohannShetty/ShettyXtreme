<script lang="ts">
  import { onMount, onDestroy } from "svelte";
  import { toast } from "svelte-sonner";
  import { get } from "$lib/api";
  import {
    getScannerThresholds,
    updateScannerThresholds,
    getScannerHistory,
    type ScannerFinding,
  } from "$lib/api";
  import { onMessage } from "$lib/ws";
  import { Button } from "$lib/components/ui/button";
  import { Input } from "$lib/components/ui/input";
  import { Badge, type BadgeVariant } from "$lib/components/ui/badge";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import { Skeleton } from "$lib/components/ui/skeleton";
  import {
    Collapsible,
    CollapsibleContent,
    CollapsibleTrigger,
  } from "$lib/components/ui/collapsible";
  import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
  } from "$lib/components/ui/select";
  import {
    Tabs,
    TabsList,
    TabsTrigger,
    TabsContent,
  } from "$lib/components/ui/tabs";
  import {
    RotateCw,
    ChevronDown,
    Settings2,
    History,
    Zap,
    Plus,
  } from "@lucide/svelte";

  type Gap = { symbol: string; gap_type: string; gap_percent: number; direction: string };
  type Cluster = { symbol: string; cluster_type: string; strength: number; source_count: number };
  type Alert = { alert_type: string; severity: string; message: string; timestamp: string };

  /** Data older than this is flagged STALE (warning chip in the panel head). */
  const STALE_MS = 60_000;
  const HISTORY_PAGE_SIZE = 50;

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

  /** Known configurable threshold parameters per scanner type (Phase 3A.1).
   *  These mirror SCANNER_THRESHOLD_SPECS in intelligence/scanners/__init__.py.
   *  The UI renders an input for every known param; empty values are treated as
   *  "use default" and omitted from the PUT payload. */
  const SCANNER_PARAMS: Record<string, { key: string; label: string; step?: string }[]> = {
    gamma_spike: [
      { key: "gamma_spike_multiplier", label: "Multiplier", step: "0.1" },
      { key: "min_observations", label: "Min Obs", step: "1" },
    ],
    iv_crush: [
      { key: "iv_rank_threshold", label: "IV Rank %", step: "1" },
      { key: "dte_threshold", label: "DTE", step: "1" },
    ],
    iv_expansion: [
      { key: "iv_rank_low", label: "IV Rank Low %", step: "1" },
      { key: "vix_1d_return_threshold", label: "VIX 1D Return %", step: "0.1" },
    ],
    pcr_extremes: [
      { key: "pcr_low", label: "PCR Low", step: "0.05" },
      { key: "pcr_high", label: "PCR High", step: "0.05" },
    ],
    max_pain_drift: [
      { key: "drift_threshold", label: "Drift %", step: "0.1" },
      { key: "dte_threshold", label: "DTE", step: "1" },
    ],
    theta_harvest: [
      { key: "theta_vega_ratio", label: "Theta/Vega", step: "0.1" },
      { key: "dte_threshold", label: "DTE", step: "1" },
    ],
    calendar_spread: [{ key: "iv_diff_threshold", label: "IV Diff %", step: "0.5" }],
    vertical_skew: [{ key: "skew_threshold", label: "Skew %", step: "0.1" }],
    gap_fill: [{ key: "gap_threshold", label: "Gap %", step: "0.1" }],
    volume_anomaly: [
      { key: "volume_multiplier", label: "Vol Multiplier", step: "0.1" },
      { key: "price_change_epsilon", label: "Price Δ %", step: "0.1" },
    ],
    oi_buildup: [{ key: "oi_change_threshold", label: "OI Change %", step: "1" }],
  };

  const SEVERITY_OPTIONS = ["", "LOW", "MEDIUM", "HIGH", "EXTREME"];

  let gaps: Gap[] = $state([]);
  let clusters: Cluster[] = $state([]);
  let alerts: Alert[] = $state([]);
  let findings: (ScannerFinding & { isNew?: boolean })[] = $state([]);
  let error = $state("");
  let loading = $state(true);
  let fetchedAt = $state<number | null>(null);
  let now = $state(Date.now());

  // View state: "active" | "history"
  let activeTab: "active" | "history" = $state("active");

  // Threshold config state
  let thresholdsOpen = $state(false);
  let thresholds: Record<string, Record<string, string>> = $state({});
  let thresholdsLoading = $state(false);
  let thresholdsSaving = $state(false);
  let thresholdsError = $state("");
  let thresholdsSavedAt = $state<number | null>(null);

  // History state
  let history: ScannerFinding[] = $state([]);
  let historyLoading = $state(false);
  let historyError = $state("");
  let historyCursor = $state(0);
  let historyHasMore = $state(true);
  let historyFilterType = $state("");
  let historyFilterSeverity = $state("");
  let historyFilterSince = $state("");

  // Keyboard navigation cursor over the flat item list (findings → gaps → clusters → alerts).
  let active = $state(0);
  let navActive = $state(false);
  let panelEl: HTMLElement | undefined = $state();
  let activeListEl: HTMLElement | undefined = $state();

  let timer: ReturnType<typeof setInterval> | undefined;
  let offWs: (() => void) | undefined;
  let newItemTimer: ReturnType<typeof setTimeout> | undefined;

  onMount(() => {
    load();
    loadThresholds();
    timer = setInterval(() => (now = Date.now()), 30_000);

    // Phase 3B.1: real-time scanner findings via WebSocket.
    offWs = onMessage("scanner_finding", (data) => {
      const f = data as ScannerFinding;
      if (!f || typeof f.scanner_type !== "string") return;
      const finding: ScannerFinding & { isNew?: boolean } = { ...f, isNew: true };
      findings = [finding, ...findings];
      toast.info(`${SCANNER_LABELS[finding.scanner_type] ?? finding.scanner_type}: ${finding.symbol}`, {
        description: `Severity ${finding.severity}`,
      });
      // Auto-scroll the active list to reveal the newest finding.
      requestAnimationFrame(() => {
        activeListEl?.scrollTo({ top: 0, behavior: "smooth" });
      });
      // Pulse indicator fades after 3 seconds.
      clearNewFlagDebounced();
    });
  });

  onDestroy(() => {
    if (timer) clearInterval(timer);
    if (newItemTimer) clearTimeout(newItemTimer);
    if (offWs) offWs();
  });

  function clearNewFlagDebounced(): void {
    if (newItemTimer) clearTimeout(newItemTimer);
    newItemTimer = setTimeout(() => {
      findings = findings.map((f) => ({ ...f, isNew: false }));
    }, 3000);
  }

  async function load(): Promise<void> {
    error = "";
    loading = true;
    try {
      const [g, c, a, f] = await Promise.all([
        get<Gap[]>("/api/scanner/gaps"),
        get<Cluster[]>("/api/scanner/clusters"),
        get<Alert[]>("/api/scanner/alerts"),
        get<ScannerFinding[]>("/api/scanner/findings?limit=50"),
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

  async function loadThresholds(): Promise<void> {
    thresholdsLoading = true;
    thresholdsError = "";
    try {
      const r = await getScannerThresholds();
      // Convert numbers to strings for controlled inputs; preserve empty for defaults.
      const next: Record<string, Record<string, string>> = {};
      for (const [type, params] of Object.entries(r.scanner_thresholds)) {
        next[type] = {};
        for (const [key, val] of Object.entries(params as Record<string, number>)) {
          next[type][key] = String(val);
        }
      }
      thresholds = next;
    } catch (err) {
      thresholdsError = err instanceof Error ? err.message : String(err);
    } finally {
      thresholdsLoading = false;
    }
  }

  async function saveThresholds(): Promise<void> {
    thresholdsSaving = true;
    thresholdsError = "";
    thresholdsSavedAt = null;
    try {
      const payload: Record<string, Record<string, number>> = {};
      for (const [type, params] of Object.entries(thresholds)) {
        for (const [key, val] of Object.entries(params)) {
          const trimmed = val.trim();
          if (trimmed === "" || trimmed === "-" || trimmed === ".") continue;
          const num = Number(trimmed);
          if (Number.isNaN(num)) {
            throw new Error(`${SCANNER_LABELS[type] ?? type} — ${key}: invalid number`);
          }
          if (!payload[type]) payload[type] = {};
          payload[type][key] = num;
        }
      }
      await updateScannerThresholds(payload);
      thresholdsSavedAt = Date.now();
      toast.success("Scanner thresholds saved");
    } catch (err) {
      thresholdsError = err instanceof Error ? err.message : String(err);
      toast.error("Failed to save thresholds", { description: thresholdsError });
    } finally {
      thresholdsSaving = false;
    }
  }

  function setThreshold(type: string, key: string, value: string): void {
    thresholds = {
      ...thresholds,
      [type]: { ...(thresholds[type] ?? {}), [key]: value },
    };
  }

  async function loadHistory(reset = false): Promise<void> {
    if (reset) {
      history = [];
      historyCursor = 0;
      historyHasMore = true;
    }
    if (!historyHasMore && !reset) return;

    historyLoading = true;
    historyError = "";
    try {
      const since = historyFilterSince ? new Date(historyFilterSince).toISOString() : undefined;
      const page = await getScannerHistory({
        scanner_type: historyFilterType || undefined,
        since,
        limit: HISTORY_PAGE_SIZE,
      });
      const filtered = historyFilterSeverity
        ? page.filter((f: ScannerFinding) => String(f.severity).toUpperCase() === historyFilterSeverity)
        : page;
      history = [...history, ...filtered];
      historyCursor += HISTORY_PAGE_SIZE;
      historyHasMore = page.length === HISTORY_PAGE_SIZE;
    } catch (err) {
      historyError = err instanceof Error ? err.message : String(err);
    } finally {
      historyLoading = false;
    }
  }

  function applyHistoryFilters(): void {
    loadHistory(true);
  }

  // Load history when the tab becomes visible for the first time.
  let historyInitialized = $state(false);
  $effect(() => {
    if (activeTab === "history" && !historyInitialized) {
      historyInitialized = true;
      loadHistory(true);
    }
  });

  let stale = $derived(fetchedAt !== null && now - fetchedAt > STALE_MS);

  /** Group findings by scanner_type for the per-type column grid. */
  let findingsByType = $derived.by(() => {
    const groups: Record<string, (ScannerFinding & { isNew?: boolean })[]> = {};
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

  function formatTimestamp(ts: string | null): string {
    if (!ts) return "—";
    try {
      const d = new Date(ts);
      return d.toLocaleTimeString("en-IN", { hour12: false });
    } catch {
      return String(ts);
    }
  }

  function detailEntries(detail: Record<string, unknown> | undefined): [string, unknown][] {
    if (!detail || typeof detail !== "object") return [];
    return Object.entries(detail);
  }

  function severityScore(severity: string): number {
    const s = String(severity).toUpperCase();
    if (s === "EXTREME") return 4;
    if (s === "HIGH") return 3;
    if (s === "MEDIUM") return 2;
    return 1;
  }

  function cardBorderClass(severity: string): string {
    const score = severityScore(severity);
    if (score >= 4) return "border-l-danger";
    if (score >= 3) return "border-l-warning";
    if (score >= 2) return "border-l-primary";
    return "border-l-transparent";
  }

  function isActionable(f: ScannerFinding): boolean {
    const d = f.detail ?? {};
    return (
      typeof d.direction === "string" &&
      d.direction !== "" &&
      d.direction !== "neutral" &&
      (typeof d.strike === "number" || typeof d.suggested_strike === "number")
    );
  }

  function onCreateProposal(_f: ScannerFinding): void {
    // Phase 3B.2 integration point: emit a window event so the workspace can
    // switch to the Proposals tab and pre-fill a proposal from this finding.
    window.dispatchEvent(
      new CustomEvent("sx:create-proposal-from-finding", { detail: _f }),
    );
    toast.info("Create proposal request sent", {
      description: `${_f.symbol} · ${_f.scanner_type}`,
    });
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
    <div class="head-actions">
      <Button
        variant="ghost"
        size="icon"
        class="size-7 text-muted-foreground hover:text-ink"
        onclick={load}
        aria-label="Refresh scanner"
      >
        <RotateCw class="size-3.5" />
      </Button>
    </div>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <!-- Threshold configuration (collapsible) -->
  <Collapsible bind:open={thresholdsOpen} class="threshold-section">
    <CollapsibleTrigger
      class="flex w-full h-8 items-center justify-between gap-2 px-3 text-[11px] font-semibold tracking-[0.06em] uppercase text-muted-foreground hover:text-ink hover:bg-canvas-raised border-b border-hairline outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      <span class="inline-flex items-center gap-2">
        <Settings2 class="size-3.5" />
        Scanner Thresholds
      </span>
      <ChevronDown class="size-3.5 transition-transform {thresholdsOpen ? 'rotate-180' : ''}" />
    </CollapsibleTrigger>
    <CollapsibleContent>
      <div class="threshold-content">
        {#if thresholdsLoading}
          <div class="threshold-grid">
            {#each Array.from({ length: 6 }) as _, i (i)}
              <Skeleton class="h-8 w-full" />
            {/each}
          </div>
        {:else}
          {#if thresholdsError}
            <p class="threshold-error">{thresholdsError}</p>
          {/if}
          <div class="threshold-grid">
            {#each Object.entries(SCANNER_PARAMS) as [type, params]}
              <div class="threshold-card">
                <span class="threshold-label">{SCANNER_LABELS[type] ?? type}</span>
                <div class="threshold-inputs">
                  {#each params as p (p.key)}
                    <label class="threshold-field">
                      <span>{p.label}</span>
                      <Input
                        type="number"
                        step={p.step ?? "any"}
                        value={thresholds[type]?.[p.key] ?? ""}
                        oninput={(e) => setThreshold(type, p.key, e.currentTarget.value)}
                        placeholder="default"
                        class="h-7 text-[12px]"
                      />
                    </label>
                  {/each}
                </div>
              </div>
            {/each}
          </div>
          <div class="threshold-actions">
            <Button
              size="sm"
              class="h-7 text-[12px]"
              onclick={saveThresholds}
              disabled={thresholdsSaving}
            >
              {#if thresholdsSaving}
                <RotateCw class="size-3.5 mr-1 animate-spin" />
              {/if}
              Save Thresholds
            </Button>
            {#if thresholdsSavedAt}
              <span class="threshold-success">Saved {formatTimestamp(new Date(thresholdsSavedAt).toISOString())}</span>
            {/if}
          </div>
        {/if}
      </div>
    </CollapsibleContent>
  </Collapsible>

  <!-- Active / History tabs -->
  <Tabs value={activeTab} onValueChange={(v) => { if (v === "active" || v === "history") activeTab = v; }} class="flex-1 min-h-0 flex flex-col">
    <TabsList class="w-full rounded-none border-b border-hairline bg-canvas-raised px-2">
      <TabsTrigger value="active" class="gap-1.5">
        <Zap class="size-3.5" />
        Active
      </TabsTrigger>
      <TabsTrigger value="history" class="gap-1.5">
        <History class="size-3.5" />
        History
      </TabsTrigger>
    </TabsList>

    <TabsContent value="active" class="flex-1 min-h-0 flex flex-col">
      <ScrollArea class="flex-1 min-h-0">
        <div class="cards" bind:this={activeListEl}>
          <!-- ── Findings (11 scanner types) ────────────────────────────── -->
          {#if findings.length > 0}
            {#each findingTypes as typeKey, ti (typeKey)}
              <div class="card">
                <span class="eyebrow">{SCANNER_LABELS[typeKey] ?? typeKey}</span>
                <span class="stat">{findingsByType[typeKey].length}</span>
                <ul role="list">
                  {#each findingsByType[typeKey] as f, fi (f.symbol + (f.timestamp ?? "") + fi)}
                    {@const idx = findingIdx(ti, fi)}
                    {@const expanded = active === idx && navActive}
                    {@const entries = detailEntries(f.detail)}
                    <li
                      class="item {cardBorderClass(f.severity)} {f.isNew ? 'pulse-new' : ''}"
                      role="option"
                      aria-selected={idx === active}
                      tabindex={idx === active ? 0 : -1}
                      data-scanner-idx={idx}
                      onclick={() => select(idx)}
                      onkeydown={(e) => onItemKeydown(e, idx)}
                    >
                      <div class="item-row">
                        <span class="ticker">{f.symbol}</span>
                        <Badge variant={convictionLevel(f.severity)}>{f.severity}</Badge>
                        <span class="timestamp">{formatTimestamp(f.timestamp)}</span>
                        {#if isActionable(f)}
                          <Button
                            variant="ghost"
                            size="icon"
                            class="size-6 ml-auto text-muted-foreground hover:text-accent"
                            onclick={(e) => { e.stopPropagation(); onCreateProposal(f); }}
                            aria-label="Create proposal"
                            title="Create proposal"
                          >
                            <Plus class="size-3.5" />
                          </Button>
                        {/if}
                      </div>
                      {#if entries.length > 0}
                        <div class="detail-summary">
                          {#each entries.slice(0, 2) as [key, val] (key)}
                            <span class="badge-regime">{fmtDetailKey(key)}: {String(val)}</span>
                          {/each}
                        </div>
                        {#if expanded}
                          <div class="detail-full">
                            {#each entries as [key, val] (key)}
                              <div class="detail-row">
                                <span class="detail-key">{fmtDetailKey(key)}</span>
                                <span class="detail-value mono">{String(val)}</span>
                              </div>
                            {/each}
                          </div>
                        {/if}
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
    </TabsContent>

    <TabsContent value="history" class="flex-1 min-h-0 flex flex-col">
      <div class="history-filters">
        <Select type="single" value={historyFilterType} onValueChange={(v) => { historyFilterType = v; applyHistoryFilters(); }}>
          <SelectTrigger class="h-7 text-[12px] min-w-[120px]" aria-label="Scanner type filter">
            <span>{historyFilterType ? (SCANNER_LABELS[historyFilterType] ?? historyFilterType) : "All scanners"}</span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">All scanners</SelectItem>
            {#each Object.entries(SCANNER_LABELS) as [key, label]}
              <SelectItem value={key}>{label}</SelectItem>
            {/each}
          </SelectContent>
        </Select>
        <Select type="single" value={historyFilterSeverity} onValueChange={(v) => { historyFilterSeverity = v; applyHistoryFilters(); }}>
          <SelectTrigger class="h-7 text-[12px] min-w-[100px]" aria-label="Severity filter">
            <span>{historyFilterSeverity || "All severities"}</span>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="">All severities</SelectItem>
            {#each SEVERITY_OPTIONS.slice(1) as sev}
              <SelectItem value={sev}>{sev}</SelectItem>
            {/each}
          </SelectContent>
        </Select>
        <Input
          type="date"
          bind:value={historyFilterSince}
          onchange={() => applyHistoryFilters()}
          class="h-7 text-[12px] min-w-[130px]"
        />
      </div>

      {#if historyError}
        <p class="error px-3 py-2">{historyError}</p>
      {/if}

      <ScrollArea class="flex-1 min-h-0">
        <div class="history-list">
          {#if historyLoading && history.length === 0}
            {#each Array.from({ length: 6 }) as _, i (i)}
              <div class="history-item">
                <Skeleton class="h-3.5 w-20" />
                <Skeleton class="h-3.5 w-16" />
                <Skeleton class="h-3.5 w-24 ml-auto" />
              </div>
            {/each}
          {:else if history.length === 0}
            <div class="empty-state">No historical findings match the filters.</div>
          {:else}
            {#each history as h, i (h.symbol + (h.timestamp ?? "") + i)}
              <div class="history-item {cardBorderClass(h.severity)}">
                <div class="history-main">
                  <span class="ticker">{h.symbol}</span>
                  <Badge variant={convictionLevel(h.severity)}>{h.severity}</Badge>
                  <span class="badge-regime">{SCANNER_LABELS[h.scanner_type] ?? h.scanner_type}</span>
                  <span class="timestamp ml-auto">{formatTimestamp(h.timestamp)}</span>
                </div>
                {#if h.detail && Object.keys(h.detail).length > 0}
                  <div class="history-detail">
                    {#each Object.entries(h.detail) as [key, val] (key)}
                      <span class="detail-pill">{fmtDetailKey(key)}: {String(val)}</span>
                    {/each}
                  </div>
                {/if}
              </div>
            {/each}
            {#if historyHasMore}
              <Button
                variant="ghost"
                size="sm"
                class="w-full h-8 text-[12px] text-muted-foreground hover:text-ink"
                onclick={() => loadHistory()}
                disabled={historyLoading}
              >
                {#if historyLoading}
                  <RotateCw class="size-3.5 mr-1 animate-spin" />
                {/if}
                Load More
              </Button>
            {/if}
          {/if}
        </div>
      </ScrollArea>
    </TabsContent>
  </Tabs>
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
  .head-actions {
    display: flex;
    align-items: center;
    gap: 4px;
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
  .threshold-section :global([data-slot="collapsible"]) {
    display: flex;
    flex-direction: column;
  }
  .threshold-content {
    padding: 10px;
    border-bottom: 1px solid var(--hairline);
    background: var(--canvas-raised);
  }
  .threshold-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
    gap: 10px;
  }
  .threshold-card {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-radius: 4px;
  }
  .threshold-label {
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
  }
  .threshold-inputs {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }
  .threshold-field {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .threshold-field span {
    font-size: 11px;
    color: var(--body);
  }
  .threshold-actions {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 10px;
  }
  .threshold-success {
    font-size: 11px;
    color: var(--success);
  }
  .threshold-error,
  .error {
    color: var(--danger);
    font-size: 11px;
    padding: 8px 10px;
    margin: 0;
  }
  .threshold-error {
    padding: 0 0 8px;
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
    flex-direction: column;
    gap: 4px;
    padding: 4px 6px 4px 4px;
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
  .item-row {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
  }
  .ticker {
    color: var(--ink);
    font-weight: 600;
    min-width: 70px;
    white-space: nowrap;
  }
  .timestamp {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    font-size: 10px;
    color: var(--faint);
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
  .detail-summary {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .detail-full {
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 4px;
    margin-top: 2px;
    background: var(--canvas-raised);
    border: 1px solid var(--hairline);
    border-radius: 4px;
  }
  .detail-row {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    font-size: 11px;
  }
  .detail-key {
    color: var(--muted);
    text-transform: capitalize;
  }
  .detail-value {
    color: var(--body);
    text-align: right;
  }
  .mono {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
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
  /* Severity-based left border accent on cards/items. */
  .border-l-danger {
    border-left-color: var(--danger);
  }
  .border-l-warning {
    border-left-color: var(--warning);
  }
  .border-l-primary {
    border-left-color: var(--accent);
  }
  .border-l-transparent {
    border-left-color: transparent;
  }
  /* Pulse animation for newly-arrived WS findings. */
  @keyframes pulse-new {
    0%, 100% { background: transparent; }
    50% { background: var(--flash-up); }
  }
  .pulse-new {
    animation: pulse-new 1.5s ease-in-out 2;
  }
  .history-filters {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
    background: var(--canvas-raised);
  }
  .history-list {
    display: flex;
    flex-direction: column;
    padding: 10px;
    gap: 8px;
  }
  .history-item {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-left-width: 2px;
    border-radius: 4px;
  }
  .history-main {
    display: flex;
    align-items: center;
    gap: 8px;
    width: 100%;
  }
  .history-detail {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .detail-pill {
    font-size: 10px;
    color: var(--body);
    background: var(--canvas-raised);
    border: 1px solid var(--hairline);
    border-radius: 2px;
    padding: 1px 4px;
  }
  .empty-state {
    color: var(--faint);
    font-size: 12px;
    padding: 24px;
    text-align: center;
  }
  .num {
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
    margin-left: auto;
  }
  .price-up {
    color: var(--price-up);
  }
  .price-down {
    color: var(--price-down);
  }
  /* Responsive: panels work in narrow right dock. */
  @media (max-width: 460px) {
    .threshold-grid {
      grid-template-columns: 1fr;
    }
    .history-filters {
      flex-direction: column;
    }
    .history-filters > :global(*) {
      width: 100%;
    }
  }
</style>
