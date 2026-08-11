# Phase 4 Lane D — Frontend Quick Wins: Findings

**Date:** 2026-08-05
**Lane:** D-front
**Items:** 3 (Oracle #6 WS backoff, fetch timeout, dead-code removal)
**Status:** Implemented — both verification gates pass

---

## Summary

All 3 Lane-D quick wins from the [Phase 4 roadmap](2026-08-05-phase4-plus-roadmap.md)
(#11–#13) are implemented. Files touched are disjoint and self-contained; no
API/schema/behavioral contract changed. Nothing was committed.

---

## 1. Oracle #6 — WS exponential backoff + jitter

**File:** `src/shettyxtreme/terminal/web/src/lib/ws.ts`

**Before:** `RECONNECT_MS = 2000` fixed delay — every reconnect retried in exactly
2s regardless of how long the server had been down. A fleet of clients would
thundering-herd the server after an outage.

**After:**
- `reconnectDelay()` computes `min(2000 × 2^attempt, 30000)` → 2s → 4s → 8s →
  16s → capped at 30s — then applies ±20% random jitter
  (`0.8 + Math.random() * 0.4`).
- `reconnectAttempt` increments per failed reconnect; resets to 0 on a
  successful `ws.onopen` **and** on `stop()` (so a fresh `connect()` starts at
  the 2s baseline).
- The existing "one pending retry timer" guard (`retryTimer !== undefined`) is
  preserved — no overlapping reconnect loops.

**Test:** N/A (behavioral). Browser-console check: kill the backend, watch the
reconnect cadence climb 2s → 4s → 8s → … → 30s with ~±20% variance; restart the
backend and confirm the next reconnect lands within one backoff step.

---

## 2. Fetch timeout / AbortController

**File:** `src/shettyxtreme/terminal/web/src/lib/api.ts`

**Before:** bare `fetch()` with no deadline — a stalled request stayed in flight
forever; repeated triggers (e.g. the 3s LogDrawer poll) piled up in-flight
requests.

**After:**
- New `fetchWithTimeout(path, init)` helper: creates an `AbortController`, arms a
  10s `window.setTimeout` that aborts it, and clears the timer in `finally`.
  All three call sites (`request` → GET/POST, `del`, `postBody`) route through
  it.
- New `isAbortError()` guard: `err instanceof Error && err.name === "AbortError"`
  (covers `DOMException`-shaped abort errors across browsers).
- Every call site's catch now maps `AbortError` → `new Error("Request timeout")`
  and only falls through to the existing `Network error reaching <path>` for
  genuine network failures.

**Test:** N/A (behavioral). Browser network-tab check: throttle the network to
"offline" or block the API host, confirm each request aborts at ~10s and the UI
surfaces "Request timeout" instead of hanging.

---

## 3. Dead-code removal

**Files:**
- `src/shettyxtreme/terminal/web/src/components/knowledge/KnowledgeHitList.svelte` — **deleted**
- `src/shettyxtreme/terminal/web/src/App.svelte` — vestigial `:global(.drawer)` block removed

**Before:**
- `KnowledgeHitList.svelte` was unused — hits are rendered inline in
  `KnowledgePanel.svelte` since S6. Grep confirmed **zero** imports/references
  anywhere (only its own self-reference to `statusTagClass`).
- App.svelte carried a `@media (max-width: 1439px)` block
  `.right-col :global(.drawer) { … !important }` whose sole purpose was to
  neutralize LogDrawer's *self-overlay* mode (`position: fixed`,
  `transform: translateX`, etc.). LogDrawer's own comment confirms that media
  query was removed in Phase 3 S6 — the override had nothing left to neutralize.

**After:**
- `KnowledgeHitList.svelte` deleted.
- The `:global(.drawer)` override block (8 declarations) removed from App.svelte.
- `knowledge-shared.ts` is **kept** — `statusTagClass` is still consumed by
  `KnowledgeDetail.svelte`.

**Test:** no import errors (svelte-check 0 errors); production build succeeds.

---

## Verification

| Gate | Result |
|------|--------|
| `npm run check` (svelte-check) | **0 errors, 0 warnings** |
| `npm run build` (vite) | **success** — 4527 modules, `static/` bundle written |

Post-edit grep confirms: no `KnowledgeHitList` references, no stale
`RECONNECT_MS`, no `.right-col :global(.drawer)` selector anywhere in `web/src`.

---

## Observations (non-blocking)

- The removed `:global(.drawer)` override was also forcing
  `background: var(--surface-overlay)` and `border-radius: 0` on LogDrawer below
  1440px via `!important`. LogDrawer now renders with its own docked-panel
  styling (`--canvas-raised`, 6px radius) at all widths. This matches the
  docked-panel contract in LogDrawer's S6 comment and DESIGN §6 — the
  `!important`s were collateral of the dead overlay mode, not an independent
  style decision.
- Backend equivalent (Dhan/Fyers `data_adapter` disconnect-code-aware
  backoff+jitter) is tracked separately in Phase 5 Lane B — this fix only covers
  the browser WS client.

---

## Handoff

- **Fixer:** Lane-D work complete; no follow-up required from this lane.
- **Next:** Lane A/B/C items from the Phase 4 roadmap; version-drift alignment
  (#14) is a separate change that will bump the frontend `package.json`.
