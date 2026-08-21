<script lang="ts">
  import ProposalQueue from "./ProposalQueue.svelte";
  import OrderHistory from "./OrderHistory.svelte";
  import LogDrawer from "./LogDrawer.svelte";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
  import { rightDockTab, type RightDockTabId } from "$lib/rightDockTab.svelte";

  // Phase 7 S1: Research/Knowledge are heavy (graph + export) and only shown
  // on the research tab — lazy load as separate chunks.
  const ResearchPanelPromise = import("./ResearchPanel.svelte");
  const KnowledgePanelPromise = import("./KnowledgePanel.svelte");

  let { open = $bindable(false), dockLogsTick = 0 }: { open?: boolean; dockLogsTick?: number } = $props();

  let activeTab = $state<RightDockTabId>(rightDockTab.value);

  // Sync with external tab changes (e.g. HintsPanel jumping to Proposals).
  $effect(() => {
    activeTab = rightDockTab.value;
  });

  // Task 2.3: the header "logs drawer" button bumps dockLogsTick each time it
  // OPENS the dock — land on the Logs tab so the button actually reveals the
  // log panel. Ctrl+R and the palette's sx:open-dock set `open` without
  // bumping the tick, so they keep whatever tab is active.
  $effect(() => {
    if (dockLogsTick > 0) setActive("logs");
  });

  const tabs: { id: RightDockTabId; label: string }[] = [
    { id: "proposals", label: "Proposals" },
    { id: "orders", label: "Orders" },
    { id: "research", label: "Research" },
    { id: "logs", label: "Logs" },
  ];

  function setActive(id: RightDockTabId): void {
    activeTab = id;
    rightDockTab.value = id;
  }
</script>

<div class="right-dock-tabs">
  <div class="tab-bar">
    {#each tabs as tab}
      <button
        class="tab-btn"
        class:active={activeTab === tab.id}
        onclick={() => setActive(tab.id)}
        type="button"
      >
        {tab.label}
      </button>
    {/each}
  </div>

  <div class="tab-content">
    {#if activeTab === "proposals"}
      <ScrollArea class="h-full" orientation="vertical">
        <ProposalQueue />
      </ScrollArea>
    {:else if activeTab === "orders"}
      <ScrollArea class="h-full" orientation="vertical">
        <OrderHistory />
      </ScrollArea>
    {:else if activeTab === "research"}
      <ScrollArea class="h-full" orientation="vertical">
        <div class="research-stack">
          {#await ResearchPanelPromise}
            <div class="lazy-loading">Loading research…</div>
          {:then mod}
            <mod.default />
          {:catch}
            <div class="lazy-loading">Failed to load research.</div>
          {/await}
          {#await KnowledgePanelPromise}
            <div class="lazy-loading">Loading knowledge…</div>
          {:then mod}
            <mod.default />
          {:catch}
            <div class="lazy-loading">Failed to load knowledge.</div>
          {/await}
        </div>
      </ScrollArea>
    {:else if activeTab === "logs"}
      <LogDrawer bind:open />
    {/if}
  </div>
</div>

<style>
  .right-dock-tabs {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.4);
  }

  .tab-bar {
    display: flex;
    gap: 4px;
    padding: 8px 8px 0;
    border-bottom: 1px solid var(--hairline);
    flex-shrink: 0;
  }

  .tab-btn {
    flex: 1;
    padding: 6px 12px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: var(--muted);
    background: transparent;
    border: 1px solid transparent;
    border-radius: 6px 6px 0 0;
    cursor: pointer;
    transition: color 100ms ease, background 100ms ease, border-color 100ms ease;
  }

  .tab-btn:hover {
    color: var(--body);
    background: var(--row-hover);
  }

  .tab-btn.active {
    color: var(--ink);
    background: var(--surface-elevated);
    border-color: var(--hairline);
    border-bottom-color: var(--surface-elevated);
  }

  .tab-content {
    flex: 1;
    min-height: 0;
    overflow: hidden;
  }

  .research-stack {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 8px;
    min-height: 100%;
  }
  .lazy-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 16px;
    color: var(--muted);
    font-size: 12px;
  }
</style>
