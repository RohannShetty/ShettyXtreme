import { writable } from "svelte/store";

export type CenterTabId = "chain" | "scanner" | "hints" | "analytics";

export const activeTab = writable<CenterTabId>("chain");
