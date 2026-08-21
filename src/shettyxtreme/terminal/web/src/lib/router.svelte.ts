/**
 * Hash-based router state (Svelte 5 runes).
 *
 * Extracted from App.svelte to isolate routing concerns.  The route is
 * derived from `window.location.hash` on mount and on every `hashchange`
 * event.  The query string comes from `window.location.search`.
 *
 * Usage:
 *   import { route, query, initRouter, teardownRouter } from "./lib/router.svelte";
 *   onMount(() => { initRouter(); return teardownRouter; });
 */

export type Route = "/" | "/settings" | "/setup" | string;

export const route: { value: Route } = $state({ value: currentRoute() });
export const query: { value: URLSearchParams | null } = $state({ value: null });

function currentRoute(): Route {
  const hash = window.location.hash;
  return hash.startsWith("#/") ? (hash.slice(1) as Route) : "/";
}

function readQuery(): void {
  query.value = new URLSearchParams(window.location.search);
}

function onHashChange(): void {
  route.value = currentRoute();
  readQuery();
}

/** Attach global listeners and set initial state. */
export function initRouter(): void {
  window.addEventListener("hashchange", onHashChange);
  readQuery();
}

/** Detach global listeners.  Returns a void for direct use as an onMount teardown. */
export function teardownRouter(): void {
  window.removeEventListener("hashchange", onHashChange);
}
