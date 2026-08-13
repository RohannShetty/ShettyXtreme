/**
 * Active right-dock tab (P3-3B.2).
 *
 * Lets panels outside the right dock (e.g. HintsPanel) switch the dock to
 * the Proposals tab after one-click proposal creation.
 *
 * Svelte 5 $state rune — read `rightDockTab.value`, update via direct
 * assignment: `rightDockTab.value = "proposals"`.
 */

export type RightDockTabId = "proposals" | "orders" | "research" | "logs";

export const rightDockTab: { value: RightDockTabId } = $state({ value: "proposals" });
