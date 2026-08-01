<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import ChainGrid from "./components/ChainGrid.svelte";
  import Header from "./components/Header.svelte";
  import HintsPanel from "./components/HintsPanel.svelte";
  import LogDrawer from "./components/LogDrawer.svelte";
  import PositionsRiskStrip from "./components/PositionsRiskStrip.svelte";
  import ScannerPanel from "./components/ScannerPanel.svelte";
  import Watchlist from "./components/Watchlist.svelte";
  import { connect, stop } from "./lib/ws";

  let route = currentRoute();
  let drawerOpen = false;

  function currentRoute(): string {
    const hash = window.location.hash;
    return hash.startsWith("#/") ? hash.slice(1) : "/";
  }

  function onHashChange(): void {
    route = currentRoute();
  }

  onMount(() => {
    window.addEventListener("hashchange", onHashChange);
    connect();
    return () => {
      window.removeEventListener("hashchange", onHashChange);
      stop();
    };
  });

  onDestroy(() => {
    stop();
  });

  function onDrawer(event: CustomEvent<{ open: boolean }>): void {
    drawerOpen = event.detail.open;
  }
</script>

{#if route === "/"}
  <div class="app-grid">
    <Header on:drawer={onDrawer} drawerOpen={drawerOpen} />
    <div class="workspace">
      <div class="rail">
        <Watchlist />
      </div>
      <div class="center">
        <ChainGrid />
        <HintsPanel />
      </div>
      <div class="right-col">
        <ScannerPanel />
        <LogDrawer bind:open={drawerOpen} />
      </div>
    </div>
    <PositionsRiskStrip />
  </div>
{:else if route === "/settings"}
  <div class="simple-view">
    <h1>Settings</h1>
    <p>Credential and token management lives in the Python service layer — see the <code class="mono">/api/settings</code> and <code class="mono">/api/auth</code> endpoints.</p>
    <a href="#/">← Back to terminal</a>
  </div>
{:else if route === "/setup"}
  <div class="simple-view">
    <h1>Setup</h1>
    <p>Configure your Dhan credentials, exchange segments, and watchlist through the setup endpoints (<code class="mono">/api/settings</code>).</p>
    <a href="#/">← Back to terminal</a>
  </div>
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
  .workspace {
    display: grid;
    grid-template-columns: minmax(260px, 3fr) minmax(0, 6fr) minmax(320px, 3fr);
    gap: 8px;
    min-height: 0;
    overflow-x: auto;
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
    display: grid;
    grid-template-columns: minmax(720px, 5fr) minmax(320px, 2fr);
    gap: 8px;
    min-width: 0;
  }
  .right-col {
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 320px;
    min-height: 0;
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
      grid-template-columns: minmax(260px, 3fr) minmax(0, 9fr);
    }
    .right-col {
      display: none;
    }
  }
</style>
