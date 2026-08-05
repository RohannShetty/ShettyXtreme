<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { activeTab, type CenterTabId } from "./lib/activeTab";
  import AnalyticsPanel from "./components/AnalyticsPanel.svelte";
  import ChainGrid from "./components/ChainGrid.svelte";
  import Header from "./components/Header.svelte";
  import HintsPanel from "./components/HintsPanel.svelte";
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
  import { X } from "@lucide/svelte";
  import { connect, stop } from "./lib/ws";

  let route = $state(currentRoute());
  let query: URLSearchParams | null = $state(null);
  let drawerOpen = $state(false);

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
  // while the cockpit is mounted. Esc closes the overlay drawer.
  function onKeydown(event: KeyboardEvent): void {
    if (
      event.ctrlKey &&
      !event.metaKey &&
      !event.altKey &&
      event.key.toLowerCase() === "r"
    ) {
      event.preventDefault();
      drawerOpen = !drawerOpen;
    } else if (event.key === "Escape" && drawerOpen) {
      drawerOpen = false;
    }
  }

  onMount(() => {
    window.addEventListener("hashchange", onHashChange);
    window.addEventListener("keydown", onKeydown);
    readQuery();
    connect();
    return () => {
      window.removeEventListener("hashchange", onHashChange);
      window.removeEventListener("keydown", onKeydown);
      stop();
    };
  });

  onDestroy(() => {
    stop();
  });
</script>

{#if route === "/"}
  <div class="app-grid">
    <Header bind:drawerOpen={drawerOpen} onDrawer={(e) => (drawerOpen = e.open)} />
    <div class="workspace">
      <div class="rail">
        <Watchlist />
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
            <ChainGrid />
          </div>
          {#if $activeTab === "scanner"}
            <div class="tab-panel">
              <ScannerPanel />
            </div>
          {/if}
          {#if $activeTab === "hints"}
            <div class="tab-panel">
              <HintsPanel />
            </div>
          {/if}
          {#if $activeTab === "analytics"}
            <div class="tab-panel">
              <AnalyticsPanel />
            </div>
          {/if}
        </Tabs>
      </div>
      <div class="right-col" class:open={drawerOpen}>
        <header class="drawer-head">
          <h2>Right Dock</h2>
          <button
            class="drawer-close"
            onclick={() => (drawerOpen = false)}
            aria-label="Close right dock"
          >
            <X class="size-4" />
          </button>
        </header>
        <ProposalQueue />
        <ResearchPanel />
        <KnowledgePanel />
        <LogDrawer bind:open={drawerOpen} />
      </div>
    </div>
    <PositionsRiskStrip />
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
    grid-template-rows: auto minmax(0, 1fr) auto;
    gap: 8px;
    padding: 8px;
    height: 100vh;
  }
  /* 3-col workspace: rail 260px | center flex | right-col 320px (DESIGN §5/§15).
     No overflow-x here — every panel scrolls inside itself (DESIGN §8). */
  .workspace {
    display: grid;
    grid-template-columns: 260px minmax(0, 1fr) 320px;
    gap: 8px;
    min-height: 0;
    overflow: hidden;
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
      grid-template-columns: 260px minmax(0, 1fr);
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
  }
</style>
