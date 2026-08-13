<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { route, query, initRouter, teardownRouter } from "./lib/router.svelte";
  import CommandPalette, { paletteOpen } from "./components/CommandPalette.svelte";
  import Header from "./components/Header.svelte";
  import TickerStrip from "./components/TickerStrip.svelte";
  import PositionsRiskStrip from "./components/PositionsRiskStrip.svelte";
  import RiskHeatmap from "./components/RiskHeatmap.svelte";
  import RightDockTabs from "./components/RightDockTabs.svelte";
  import SettingsView from "./components/SettingsView.svelte";
  import SetupWizard from "./components/SetupWizard.svelte";
  import Workspace from "./components/layout/Workspace.svelte";
  import CenterTabs from "./components/layout/CenterTabs.svelte";
  import Watchlist from "./components/Watchlist.svelte";
  import { Toaster } from "$lib/components/ui/sonner";
  import { toast } from "svelte-sonner";
  import { connect, onMessage, stop } from "./lib/ws";

  let drawerOpen = $state(false);
  // Task 2.3: bumped each time the header "logs drawer" button OPENS the dock,
  // so RightDockTabs can land on the Logs tab. Ctrl+R / Esc / the command
  // palette's sx:open-dock event set `drawerOpen` directly and must NOT touch
  // the right-dock tab — only the logs button means "show me the logs".
  let dockLogsTick = $state(0);

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
    initRouter();
    window.addEventListener("keydown", onKeydown);
    // Command palette "Research"/"Knowledge" items open the right dock behind
    // App's drawer state via this window event (CommandPalette.svelte §3
    // integration contract). Above 1440px the dock is grid-pinned, so this is
    // a no-op visually; below it slides the overlay in.
    window.addEventListener("sx:open-dock", onOpenDock);
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
      teardownRouter();
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

  // Header "logs drawer" button → toggle the dock; when opening, bump the tick
  // so the right dock lands on the Logs tab (task 2.3).
  function onDrawerToggle(e: { open: boolean }): void {
    drawerOpen = e.open;
    if (e.open) dockLogsTick++;
  }
</script>

<Toaster />
<!-- Mounted at the app root (outside the route branches) so Ctrl+K / ⌘K works
     on every route. CommandPalette registers its own global keydown listener;
     mounting it alone enables the shortcut (wave-2 palette report §1.4). -->
<CommandPalette />

{#if route.value === "/"}
  <div class="app-grid">
    <Header bind:drawerOpen={drawerOpen} onDrawer={onDrawerToggle} />
    <!-- Ticker strip row — regime / IV / PCR / max pain chrome directly below
         the header (wave-2 strip report §3). Self-contained: fetches its own
         data and polls on a 30s interval. Wrapped so the grid-row placement is
         explicit (its root shares the `.strip` class with PositionsRiskStrip). -->
    <div class="ticker-row">
      <TickerStrip />
    </div>
    <Workspace bind:drawerOpen={drawerOpen}>
      {#snippet rail()}
        <Watchlist />
      {/snippet}
      {#snippet center()}
        <CenterTabs />
      {/snippet}
      {#snippet rightDock()}
        <RightDockTabs bind:open={drawerOpen} dockLogsTick={dockLogsTick} />
      {/snippet}
    </Workspace>
    <div class="positions-row">
      <PositionsRiskStrip />
    </div>
    <div class="heatmap-row">
      <RiskHeatmap />
    </div>
  </div>
{:else if route.value === "/settings"}
  <SettingsView />
{:else if route.value === "/setup"}
  <SetupWizard query={query.value} />
{:else}
  <div class="simple-view">
    <h1>404</h1>
    <p>Unknown route <code class="mono">{route.value}</code>.</p>
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
    grid-template-rows: auto auto minmax(0, 1fr) auto auto;
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
  .heatmap-row {
    grid-row: 5;
    min-height: 0;
  }
  /* LIVE banner slot (36px, full width, directly below the header) — reserved
     only while a banner is actually mounted, so the dense 4-row layout is
     untouched outside LIVE sessions (DESIGN §4 alert bar). The bar itself stays
     position:fixed and visually fills this slot; the reserved space keeps the
     workspace clear of it. Header stays row 1 via auto-placement. */
  .app-grid:has(:global(.live-banner)) {
    grid-template-rows: auto 36px auto minmax(0, 1fr) auto auto;
  }
  .app-grid:has(:global(.live-banner)) .ticker-row {
    grid-row: 3;
  }
  .app-grid:has(:global(.live-banner)) :global(.workspace) {
    grid-row: 4;
  }
  .app-grid:has(:global(.live-banner)) .positions-row {
    grid-row: 5;
  }
  .app-grid:has(:global(.live-banner)) .heatmap-row {
    grid-row: 6;
  }
  /* Two-row header below 1024px (wave-2 header report §5): 8px grid padding +
     4px head padding + two 36px rows = 88px. Without this bump the LIVE banner
     would overlap the header's second row. */
  @media (max-width: 1024px) {
    .app-grid {
      --header-bottom: 88px;
    }
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
    /* Prevent a dangling word on the last line (R13). */
    text-wrap: pretty;
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
</style>
