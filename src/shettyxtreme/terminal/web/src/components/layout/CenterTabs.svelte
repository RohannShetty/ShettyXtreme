<!-- CenterTabs — tab bar + keep-alive panels for the workspace center column.
     Extracted from App.svelte (lines 238–275 for markup).
     DESIGN §4: panels stay mounted (keep-alive) so WS subscriptions and
     component state survive tab switches; inactive panels are hidden via
     scoped CSS `.tab-panel.hidden { display: none }`. -->
<script lang="ts">
  import { activeTab, type CenterTabId } from "$lib/activeTab.svelte";
  import AnalyticsPanel from "../AnalyticsPanel.svelte";
  import ChainGrid from "../ChainGrid.svelte";
  import GreeksPanel from "../GreeksPanel.svelte";
  import HintsPanel from "../HintsPanel.svelte";
  import ScannerPanel from "../ScannerPanel.svelte";
  import { Tabs, TabsList, TabsTrigger } from "$lib/components/ui/tabs";
  import { ScrollArea } from "$lib/components/ui/scroll-area";
</script>

<Tabs
  value={activeTab.value}
  onValueChange={(v) => (activeTab.value = v as CenterTabId)}
  class="flex h-full min-h-0 flex-col overflow-hidden rounded-[6px] border border-hairline bg-surface-card"
>
  <TabsList class="w-full flex-none justify-start">
    <TabsTrigger value="chain">CHAIN</TabsTrigger>
    <TabsTrigger value="scanner">SCANNER</TabsTrigger>
    <TabsTrigger value="hints">HINTS</TabsTrigger>
    <TabsTrigger value="analytics">ANALYTICS</TabsTrigger>
    <TabsTrigger value="greeks">GREEKS</TabsTrigger>
  </TabsList>
  <div class="tab-panel" class:hidden={activeTab.value !== "chain"}>
    <ScrollArea class="h-full w-full" orientation="horizontal">
      <ChainGrid />
    </ScrollArea>
  </div>
  <div class="tab-panel" class:hidden={activeTab.value !== "scanner"}>
    <ScrollArea class="h-full w-full" orientation="horizontal">
      <ScannerPanel />
    </ScrollArea>
  </div>
  <div class="tab-panel" class:hidden={activeTab.value !== "hints"}>
    <ScrollArea class="h-full w-full" orientation="horizontal">
      <HintsPanel />
    </ScrollArea>
  </div>
  <div class="tab-panel" class:hidden={activeTab.value !== "analytics"}>
    <ScrollArea class="h-full w-full" orientation="horizontal">
      <AnalyticsPanel />
    </ScrollArea>
  </div>
  <div class="tab-panel" class:hidden={activeTab.value !== "greeks"}>
    <ScrollArea class="h-full w-full" orientation="horizontal">
      <GreeksPanel />
    </ScrollArea>
  </div>
</Tabs>

<style>
  .tab-panel {
    flex: 1;
    min-height: 0;
    display: flex;
    flex-direction: column;
    /* Panels scroll inside their column — the ScrollArea viewport handles both
       axes (the chain grid, min 720px, scrolls horizontally inside the panel
       instead of pushing the viewport wide). */
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
</style>
