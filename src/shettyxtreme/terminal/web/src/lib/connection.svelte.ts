/**
 * Unified connection store (P1-2.4).
 *
 * Single source of truth for the header connection pip.  Fed by:
 *   1. Server-pushed "connection" broadcasts via WebSocket (primary).
 *   2. The /api/health REST poll as a fallback/backfill.
 *   3. The browser WS client's own open/close/error events.
 *
 * The store exposes a Svelte 5 $state rune so any component that reads
 * $connectionStore reactively re-renders on transition.
 */

export type PipState = "live" | "connecting" | "stale" | "disconnected" | "expired" | "unknown";

/** Connection detail for the pip tooltip. */
export type ConnectionInfo = {
  state: PipState;
  detail: string;
};

/** Svelte 5 $state store — read `$connectionStore` in components. */
export const connectionStore: ConnectionInfo = $state({
  state: "unknown",
  detail: "",
});

/**
 * Update the store from a server-pushed "connection" broadcast.
 * Called by the `onMessage("connection", ...)` handler in ws.ts.
 */
export function applyServerState(state: string, detail: string): void {
  connectionStore.state = mapState(state);
  connectionStore.detail = detail;
}

/**
 * Update the store from a /api/health REST poll response.
 * Only overwrites if the server hasn't pushed a more specific state.
 */
export function applyHealthState(state: string, detail: string): void {
  // Server-pushed states always take precedence — only apply REST
  // backfill when the store is still in its initial "unknown" state.
  if (connectionStore.state === "unknown") {
    connectionStore.state = mapState(state);
    connectionStore.detail = detail;
  }
}

/**
 * Update the store from the browser WS client's own open/close events.
 * These are local to the tab — a dropped browser WS means the tab is
 * disconnected even if the backend is healthy.
 */
export function applyLocalWsState(connected: boolean): void {
  if (!connected) {
    // Browser WS dropped — show CONNECTING (the client is retrying).
    connectionStore.state = "connecting";
    connectionStore.detail = "Browser WebSocket reconnecting…";
  }
  // On reconnect: don't override — wait for the server's "connection"
  // broadcast to tell us the real backend state.
}

function mapState(raw: string): PipState {
  switch (raw) {
    case "connected":
      return "live";
    case "connecting":
      return "connecting";
    case "stale":
      return "stale";
    case "expired":
      return "expired";
    case "disconnected":
      return "disconnected";
    default:
      return "unknown";
  }
}
