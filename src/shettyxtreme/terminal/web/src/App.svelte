<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { activeTab, type CenterTabId } from "./lib/activeTab";
  import AnalyticsPanel from "./components/AnalyticsPanel.svelte";
  import ChainGrid from "./components/ChainGrid.svelte";
  import CommandPalette, { paletteOpen } from "./components/CommandPalette.svelte";
  import Header from "./components/Header.svelte";
  import HintsPanel from "./components/HintsPanel.svelte";
  import TickerStrip from "./components/TickerStrip.svelte";
  import KnowledgePanel from "./components/KnowledgePanel.svelte";
  import LogDrawer from "./components/LogDrawer.svelte";
  import PositionsRiskStrip from "./components/PositionsRiskStrip.svelte";
  import ProposalQueue from "./components/ProposalQueue.svelte";
  import ResearchPanel from "./components/ResearchPanel.svelte";
  import ScannerPanel from "./components/ScannerPanel.svelte";
  import SettingsView from "./components/SettingsView.svelte";
  import SetupWizard from "./components/SetupWizard.svelte";
  import Watchlist from "./components/Watchlist.svelte";
  import { Tabs, TabsList, TabsTrigger } from "$lib/components/ui/tabs";
  import { Separator } from "$lib/components/ui/separator";
  import { Toaster } from "$lib/components/ui/sonner";
  import { Kbd } from "$lib/components/ui/kbd";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import { toast } from "svelte-sonner";
  import { X } from "@lucide/svelte";
  import { connect, onMessage, stop } from "./lib/ws";

  let route = $state(currentRoute());
  let query: URLSearchParams | null = $state(null);
  let drawerOpen = $state(false);

  // ── Resizable split panes (recon §1.3, ARCHITECTURE_V2 §15) ─────────────
  // Rail and right-dock widths are CSS custom props on .workspace so the grid
  // tracks track them; the 8px gutter columns replace the old 8px column gap
  // (identical spacing). Widths persist to localStorage, clamped to
  // [min, min(hard-max, 0.5×vw)] on restore so a narrow viewport can never be
  // asked to render two oversized panes. Below 1440px the right dock becomes
  // the overlay drawer and its gutter + width are unused (media query).
  const RAIL_MIN = 260;
  const RAIL_MAX = 480;
  const RIGHT_MIN = 320;
  const RIGHT_MAX = 640;
  const RAIL_KEY = "sx:rail-w";
  const RIGHT_KEY = "sx:right-w";

  let railW = $state(loadPaneWidth(RAIL_KEY, RAIL_MIN, RAIL_MIN, RAIL_MAX));
  let rightW = $state(loadPaneWidth(RIGHT_KEY, RIGHT_MIN, RIGHT_MIN, RIGHT_MAX));
  let drag: { kind: "rail" | "right"; startX: number; startW: number } | null = $state(null);

  function loadPaneWidth(key: string, fallback: number, min: number, max: number): number {
    try {
      const raw = Number(localStorage.getItem(key));
      if (!Number.isFinite(raw) || raw <= 0) return fallback;
      return clampPane(raw, min, max);
    } catch {
      return fallback;
    }
  }

  function clampPane(value: number, min: number, max: number): number {
    const upper = Math.max(min, Math.min(max, 0.5 * window.innerWidth));
    return Math.min(Math.max(value, min), upper);
  }

  function persistPane(key: string, value: number): void {
    try {
      localStorage.setItem(key, String(Math.round(value)));
    } catch {
      /* storage unavailable — resizing still applies for the session */
    }
  }

  function onGutterPointerDown(kind: "rail" | "right", event: PointerEvent): void {
    event.preventDefault();
    const el = event.currentTarget as HTMLElement;
    el.setPointerCapture(event.pointerId);
    drag = { kind, startX: event.clientX, startW: kind === "rail" ? railW : rightW };
  }

  function onGutterPointerMove(event: PointerEvent): void {
    if (!drag) return;
    const delta = event.clientX - drag.startX;
    if (drag.kind === "rail") {
      railW = clampPane(drag.startW + delta, RAIL_MIN, RAIL_MAX);
    } else {
      rightW = clampPane(drag.startW - delta, RIGHT_MIN, RIGHT_MAX);
    }
  }

  function onGutterPointerUp(): void {
    if (!drag) return;
    persistPane(RAIL_KEY, railW);
    persistPane(RIGHT_KEY, rightW);
    drag = null;
  }

  // Keyboard nudge on the separator (focusable, role=separator): ←/→ steps
  // the boundary by 8px and persists immediately.
  function onGutterKeydown(kind: "rail" | "right", event: KeyboardEvent): void {
    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
    event.preventDefault();
    const step = event.key === "ArrowRight" ? 8 : -8;
    if (kind === "rail") {
      railW = clampPane(railW + step, RAIL_MIN, RAIL_MAX);
      persistPane(RAIL_KEY, railW);
    } else {
      rightW = clampPane(rightW - step, RIGHT_MIN, RIGHT_MAX);
      persistPane(RIGHT_KEY, rightW);
    }
  }

  function currentRoute(): string {
    const hash = window.location.hash;
    return hash.startsWith("#/") ? hash.slice(1) : "/";
  }

  function readQuery(): void {
    query = new URLSearchParams(window.location.search);
  }

  function onHashChange(): void {
    route = currentRoute();
    readQuery();
  }

  // Ctrl+R toggles the right-side dock. Above 1440px it is docked in the grid;
  // below that it slides in as a level-3 overlay drawer (DESIGN §5/§8). This is
  // a workstation shortcut — the browser reload is intentionally suppressed
  // while the cockpit is mounted. Esc closes the overlay drawer — unless the
  // command palette is open, in which case Esc belongs to the palette (its
  // Dialog EscapeLayer closes it; closing the drawer underneath too would be
  // a double-close).
  function onKeydown(event: KeyboardEvent): void {
    if (
      event.ctrlKey &&
      !event.metaKey &&
      !event.altKey &&
      event.key.toLowerCase() === "r"
    ) {
      event.preventDefault();
      drawerOpen = !drawerOpen;
    } else if (event.key === "Escape" && drawerOpen && !$paletteOpen) {
      drawerOpen = false;
    }
  }

  onMount(() => {
    window.addEventListener("hashchange", onHashChange);
    window.addEventListener("keydown", onKeydown);
    // Command palette "Research"/"Knowledge" items open the right dock behind
    // App's drawer state via this window event (CommandPalette.svelte §3
    // integration contract). Above 1440px the dock is grid-pinned, so this is
    // a no-op visually; below it slides the overlay in.
    window.addEventListener("sx:open-dock", onOpenDock);
    readQuery();
    connect();
    // WS alerts → toasts. The server broadcasts {alert_type, severity, message}
    // on the "alert" topic (AlertProjection, projections.py). Severity maps to
    // the DESIGN status tokens: danger for HIGH, warning for MEDIUM, info else.
    const offAlert = onMessage("alert", (data) => {
      const a = data as { alert_type?: string; severity?: string; message?: string };
      const message = typeof a.message === "string" && a.message ? a.message : "Alert";
      const severity = String(a.severity ?? "").toUpperCase();
      if (severity === "HIGH" || severity === "CRITICAL") {
        toast.error(message, { description: a.alert_type ?? undefined });
      } else if (severity === "MEDIUM") {
        toast.warning(message, { description: a.alert_type ?? undefined });
      } else {
        toast.info(message, { description: a.alert_type ?? undefined });
      }
    });
    return () => {
      window.removeEventListener("hashchange", onHashChange);
      window.removeEventListener("keydown", onKeydown);
      window.removeEventListener("sx:open-dock", onOpenDock);
      offAlert();
      stop();
    };
  });

  onDestroy(() => {
    stop();
  });

  function onOpenDock(): void {
    drawerOpen = true;
  }
</script>

<Toaster />
<!-- Mounted at the app root (outside the route branches) so Ctrl+K / ⌘K works
     on every route. CommandPalette registers its own global keydown listener;
     mounting it alone enables the shortcut (wave-2 palette report §1.4). -->
<CommandPalette />

{#if route === "/"}
  <div class="app-grid">
    <Header bind:drawerOpen={drawerOpen} onDrawer={(e) => (drawerOpen = e.open)} />
    <!-- Ticker strip row — regime / IV / PCR / max pain chrome directly below
         the header (wave-2 strip report §3). Self-contained: fetches its own
         data and polls on a 30s interval. Wrapped so the grid-row placement is
         explicit (its root shares the `.strip` class with PositionsRiskStrip). -->
    <div class="ticker-row">
      <TickerStrip />
    </div>
    <div
      class="workspace"
      style="--rail-w: {railW}px; --right-w: {rightW}px"
      class:dragging={drag !== null}
    >
      <div class="rail">
        <Watchlist />
      </div>
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <!-- Focusable role="separator" with arrow-key resize is the WAI-ARIA resizable
           separator widget; svelte-check's interactive-role list predates it. -->
      <div
        class="gutter"
        class:drag-active={drag?.kind === "rail"}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize watchlist"
        aria-valuenow={railW}
        aria-valuemin={RAIL_MIN}
        aria-valuemax={RAIL_MAX}
        tabindex="0"
        onpointerdown={(e) => onGutterPointerDown("rail", e)}
        onpointermove={onGutterPointerMove}
        onpointerup={onGutterPointerUp}
        onpointercancel={onGutterPointerUp}
        onkeydown={(e) => onGutterKeydown("rail", e)}
      >
        <span class="gutter-line" aria-hidden="true"></span>
      </div>
      <div class="center">
        <Tabs
          value={$activeTab}
          onValueChange={(v) => activeTab.set(v as CenterTabId)}
          class="flex h-full min-h-0 flex-col overflow-hidden rounded-[6px] border border-hairline bg-surface-card"
        >
          <TabsList class="w-full flex-none justify-start">
            <TabsTrigger value="chain">CHAIN</TabsTrigger>
            <TabsTrigger value="scanner">SCANNER</TabsTrigger>
            <TabsTrigger value="hints">HINTS</TabsTrigger>
            <TabsTrigger value="analytics">ANALYTICS</TabsTrigger>
          </TabsList>
          <div class="tab-panel" class:hidden={$activeTab !== "chain"}>
            <ScrollArea class="h-full w-full" orientation="horizontal">
              <ChainGrid />
            </ScrollArea>
          </div>
          <div class="tab-panel" class:hidden={$activeTab !== "scanner"}>
            <ScrollArea class="h-full w-full" orientation="horizontal">
              <ScannerPanel />
            </ScrollArea>
          </div>
          <div class="tab-panel" class:hidden={$activeTab !== "hints"}>
            <ScrollArea class="h-full w-full" orientation="horizontal">
              <HintsPanel />
            </ScrollArea>
          </div>
          <div class="tab-panel" class:hidden={$activeTab !== "analytics"}>
            <ScrollArea class="h-full w-full" orientation="horizontal">
              <AnalyticsPanel />
            </ScrollArea>
          </div>
        </Tabs>
      </div>
      <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
      <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
      <!-- Focusable role="separator" with arrow-key resize is the WAI-ARIA resizable
           separator widget; svelte-check's interactive-role list predates it. -->
      <div
        class="gutter gutter-right"
        class:drag-active={drag?.kind === "right"}
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize right dock"
        aria-valuenow={rightW}
        aria-valuemin={RIGHT_MIN}
        aria-valuemax={RIGHT_MAX}
        tabindex="0"
        onpointerdown={(e) => onGutterPointerDown("right", e)}
        onpointermove={onGutterPointerMove}
        onpointerup={onGutterPointerUp}
        onpointercancel={onGutterPointerUp}
        onkeydown={(e) => onGutterKeydown("right", e)}
      >
        <span class="gutter-line" aria-hidden="true"></span>
      </div>
      <div class="right-col" class:open={drawerOpen}>
        <header class="drawer-head">
          <h2>Right Dock</h2>
          <div class="drawer-head-actions">
            <Kbd>Ctrl+R</Kbd>
            <button
              class="drawer-close"
              onclick={() => (drawerOpen = false)}
              aria-label="Close right dock"
            >
              <X class="size-4" />
            </button>
          </div>
        </header>
        <div class="drawer-sep" aria-hidden="true">
          <Separator />
        </div>
        <ProposalQueue />
        <ResearchPanel />
        <KnowledgePanel />
        <LogDrawer bind:open={drawerOpen} />
      </div>
    </div>
    <div class="positions-row">
      <PositionsRiskStrip />
    </div>
  </div>
  {:else if route === "/settings"}
  <SettingsView />
  {:else if route === "/setup"}
  <SetupWizard {query} />
{:else}
  <div class="simple-view">
    <h1>404</h1>
    <p>Unknown route <code class="mono">{route}</code>.</p>
    <a href="#/">← Back to terminal</a>
  </div>
{/if}

<style>
  .app-grid {
    display: grid;
    grid-template-columns: 1fr;
    /* Rows: header | ticker strip | workspace | positions strip (wave-2
       integration). Explicit grid-row placement (below) keeps the LIVE banner
       slot from stealing a row from the workspace — auto-placement alone would
       crush the workspace into the 36px banner row (latent bug, fixed here). */
    grid-template-rows: auto auto minmax(0, 1fr) auto;
    gap: 8px;
    padding: 8px;
    height: 100vh;
    /* Measurement coupling (LIVE banner): the header strip is 44px tall and
       the grid has 8px padding, so its bottom edge sits at 52px in viewport
       coordinates. ModeSwitcher's .live-banner reads this var instead of
       measuring the header with JS. Keep in sync with .head's height. */
    --header-bottom: 52px;
  }
  .ticker-row {
    grid-row: 2;
    min-height: 0;
  }
  .positions-row {
    grid-row: 4;
    min-height: 0;
  }
  /* LIVE banner slot (36px, full width, directly below the header) — reserved
     only while a banner is actually mounted, so the dense 4-row layout is
     untouched outside LIVE sessions (DESIGN §4 alert bar). The bar itself stays
     position:fixed and visually fills this slot; the reserved space keeps the
     workspace clear of it. Header stays row 1 via auto-placement. */
  .app-grid:has(:global(.live-banner)) {
    grid-template-rows: auto 36px auto minmax(0, 1fr) auto;
  }
  .app-grid:has(:global(.live-banner)) .ticker-row {
    grid-row: 3;
  }
  .app-grid:has(:global(.live-banner)) .workspace {
    grid-row: 4;
  }
  .app-grid:has(:global(.live-banner)) .positions-row {
    grid-row: 5;
  }
  /* Two-row header below 1024px (wave-2 header report §5): 8px grid padding +
     4px head padding + two 36px rows = 88px. Without this bump the LIVE banner
     would overlap the header's second row. */
  @media (max-width: 1024px) {
    .app-grid {
      --header-bottom: 88px;
    }
  }
  /* 3-col workspace: rail | gutter | center | gutter | right-col (DESIGN §5/§15,
     recon §1.3). The 8px gutter columns replace the old 8px column gap — the
     spacing is byte-identical, but the gutter gives a drag handle (pointer
     events, rail/right widths clamped + persisted). No overflow-x here — every
     panel scrolls inside itself (DESIGN §8). */
  .workspace {
    display: grid;
    grid-template-columns: var(--rail-w, 260px) 8px minmax(0, 1fr) 8px var(--right-w, 320px);
    gap: 0;
    min-height: 0;
    overflow: hidden;
  }
  .workspace.dragging {
    user-select: none;
  }
  .gutter {
    position: relative;
    display: flex;
    align-items: center;
    justify-content: center;
    cursor: col-resize;
    touch-action: none;
    outline: none;
  }
  .gutter:focus-visible {
    box-shadow: inset 0 0 0 2px var(--focus-ring);
  }
  .gutter-line {
    width: 2px;
    height: 28px;
    border-radius: 1px;
    background: var(--hairline-strong);
    opacity: 0;
    transition: opacity 100ms ease-out;
  }
  .gutter:hover .gutter-line,
  .gutter:focus-visible .gutter-line,
  .gutter.drag-active .gutter-line {
    opacity: 1;
  }
  .gutter.drag-active .gutter-line,
  .gutter:active .gutter-line {
    background: var(--accent);
  }
  .rail {
    min-width: 260px;
    min-height: 0;
    border-radius: 6px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    overflow: hidden;
  }
  .center {
    display: flex;
    flex-direction: column;
    min-width: 0;
    min-height: 0;
  }
  .tab-panel {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    /* Panels scroll inside their column. The chain grid (min 720px) scrolls
       horizontally here instead of pushing the viewport wide. */
    overflow-x: auto;
    overflow-y: hidden;
  }
  /* Keep-alive hidden state (DESIGN §4 tabs). Tailwind's .hidden utility is
     emitted inside @layer utilities, which the cascade ranks BELOW this
     component's unlayered scoped rules — a bare `hidden` class would lose to
     .tab-panel's display:flex above. Pinning the state here (higher
     specificity, same unlayered context) is what actually hides a panel while
     keeping it mounted, preserving state + WS subscriptions across tab
     switches. */
  .tab-panel.hidden {
    display: none;
  }
  .tab-panel > :global(*) {
    flex: 1;
    min-height: 0;
  }
  .right-col {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 320px;
    min-height: 0;
    overflow: hidden;
  }
  /* Drawer chrome — only rendered in overlay mode below 1440px. */
  .drawer-head {
    display: none;
    align-items: center;
    justify-content: space-between;
    padding: 6px 10px;
    background: var(--surface-elevated);
    border: 1px solid var(--hairline-strong);
    border-radius: 6px 6px 0 0;
  }
  .drawer-head h2 {
    margin: 0;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .drawer-head-actions {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .drawer-sep {
    display: none;
  }
  .drawer-close {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    background: none;
    border: none;
    color: var(--faint);
    cursor: pointer;
    padding: 2px;
  }
  .drawer-close:hover {
    color: var(--ink);
  }
  .simple-view {
    height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
    color: var(--body);
    padding: 24px;
  }
  .simple-view h1 {
    color: var(--ink);
    margin: 0;
    font-size: 22px;
  }
  .simple-view p {
    max-width: 560px;
    text-align: center;
    color: var(--muted);
    line-height: 1.6;
    margin: 0;
  }
  .simple-view code {
    color: var(--accent);
  }
  .simple-view a {
    color: var(--accent-active);
    text-decoration: none;
  }
  .simple-view a:hover {
    text-decoration: underline;
  }

  @media (max-width: 1439px) {
    .workspace {
      grid-template-columns: var(--rail-w, 260px) 8px minmax(0, 1fr);
    }
    /* Right dock is no longer a grid column below 1440px — its gutter (and the
       persisted --right-w) is unused until the viewport grows back. */
    .gutter-right {
      display: none;
    }
    /* Right dock becomes a level-3 overlay drawer: surface-overlay +
       hairline-strong, no drop shadow (DESIGN §6). Toggle: Ctrl+R, Esc,
       the header logs button, or the drawer's own close. */
    .right-col {
      position: fixed;
      top: 0;
      right: 0;
      bottom: 0;
      z-index: 30;
      width: min(380px, 88vw);
      min-width: min(380px, 88vw);
      display: flex;
      flex-direction: column;
      gap: 8px;
      padding: 8px;
      overflow-y: auto;
      background: var(--surface-overlay);
      border-left: 1px solid var(--hairline-strong);
      border-radius: 0;
      transform: translateX(100%);
      transition: transform 120ms ease-out;
    }
    .right-col.open {
      transform: translateX(0);
    }
    .drawer-head {
      display: flex;
    }
    .drawer-sep {
      display: block;
    }
  }
</style>
