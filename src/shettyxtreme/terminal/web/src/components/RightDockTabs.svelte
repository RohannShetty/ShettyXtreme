<script lang="ts">
  import { onMount } from "svelte";
  import ProposalQueue from "./ProposalQueue.svelte";
  import OrderHistory from "./OrderHistory.svelte";
  import ResearchPanel from "./ResearchPanel.svelte";
  import KnowledgePanel from "./KnowledgePanel.svelte";
  import LogDrawer from "./LogDrawer.svelte";
  import { ScrollArea } from "$lib/components/ui/scroll-area";

  type TabId = "proposals" | "orders" | "research" | "logs";

  let { open = $bindable(false) }: { open?: boolean } = $props();

  let activeTab = $state<TabId>("proposals");

  const tabs: { id: TabId; label: string }[] = [
    { id: "proposals", label: "Proposals" },
    { id: "orders", label: "Orders" },
    { id: "research", label: "Research" },
    { id: "logs", label: "Logs" },
  ];

  function setActive(id: TabId): void {
    activeTab = id;
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
          <ResearchPanel />
          <KnowledgePanel />
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
</style>
