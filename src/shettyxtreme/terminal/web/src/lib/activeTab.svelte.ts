/**
 * Active centre-panel tab (P1-2.4).
 *
 * Svelte 5 $state rune — read `activeTab.value` in components.
 * Updated via direct assignment: `activeTab.value = "scanner"`.
 */

export type CenterTabId = "chain" | "scanner" | "hints" | "analytics" | "greeks";

export const activeTab: { value: CenterTabId } = $state({ value: "chain" });
