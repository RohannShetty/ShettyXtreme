# Phase 7 S2 — api.ts Split Assessment

**Date:** 2026-08-21
**File:** `src/shettyxtreme/terminal/web/src/lib/api.ts`
**Size:** 1011 lines / 29,225 bytes (guard: 1500 — **not a violation**)
**Companion:** `src/shettyxtreme/terminal/web/src/lib/ws.ts` — 8,423 bytes, already separate WS client

---

## 1. File Structure Analysis

### 1.1 Top-level shape

| Section | Lines | Kind | Notes |
|---|---|---|---|
| Header + `fetchWithTimeout` / `isAbortError` / `describeError` / `request` | 1–59 | impl | Shared transport. Single `FETCH_TIMEOUT_MS=10000`, `AbortController`, JSON-error unwrapping. Every verb funnels through `request<T>` or `fetchWithTimeout` directly for `Blob`/`File` cases. |
| Generic verbs `get` / `post` / `del` / `postBody` / `putBody` | 61–118 | impl | 58 lines. Thin wrappers over `request`. `del` and `postBody`/`putBody` duplicate the try/catch+`isAbortError` pattern (only because they need `JSON` body or `DELETE`). |
| Research domain types | 120–179 | types | 60 lines. `ResearchLens`, `ResearchToolDef`, `ResearchEvidence`, `ResearchBrief` (16 fields), `ResearchRun*`, `ResearchSchedulerStatus`, `ResearchScoringItem`. No functions. |
| Knowledge domain types (Phase 4) | 180–223 | types | 44 lines. `KnowledgeTag`, `KnowledgeNoteRequest`, `KnowledgeDoc`, `KnowledgeSearchHit`, `*Response`, `KnowledgeStatusResponse`, `KnowledgeSyncResponse`. |
| `exportResearchBrief` (blob) | 226–239 | impl | 14 lines. Direct `fetchWithTimeout` → `resp.blob()`. Not via `request<T>` because return type is `Blob`. |
| Symbol Search types | 243–259 | types | 17 lines. `SymbolSearchHit`, `SymbolSearchResponse`. |
| Analytics types | 262–319 | types | 58 lines. `CalibrationPoint`, `ScorecardMetric`, `RegimeRow`, `ScorecardResponse`, `IVRankHistoryPoint`, `PCRHistoryPoint`, `MaxPainHistoryPoint`, `RegimeHistoryPoint`, `ExportFormat`. |
| Analytics history + export fns | 321–367 | impl | 47 lines. `getIVRankHistory`, `getPCRHistory`, `getMaxPainHistory`, `getRegimeHistory`, `exportAnalytics` (blob). All thin `get<T>` or `fetchWithTimeout` wrappers. |
| Session types | 369–382 | types | 14 lines. `SessionRecord`, `SessionCounts`, `SessionsResponse`. |
| Auth types + fns | 383–423 | mixed | 41 lines. `AuthStatus`, `AuthStart`, `SaveResult`, `ValidationResult` (types) + `authStatus`, `saveCredentials`, `testCredentials`, `startAuth`, `reauth`, `logoutAuth` (6 fns, each 1–3 lines delegating to `get`/`postBody`/`post`). |
| Execution domain (largest block) | 425–685 | mixed | ~261 lines. `Proposal` (26 fields), `OrderRecord`, `CancelOrderResponse`, `ClosedPositionRecord`, `ExecutionMode`, `RiskSummary` + 15 fns/types: `approveProposal`, `ProposalsQuery`, `getProposals`, `rejectProposal`, `executionMode`, `riskSummary`, `GreeksHistoryPoint`..`RiskHeatmapData` (7 types), `getGreeksHistory`, `getRiskHeatmap`, `getOrders`, `cancelOrder`, `exportOrders` (blob→File with `content-disposition` parsing), `closePosition`, `getPositionHistory`. |
| Intelligence domain | 688–747 | mixed | 60 lines. `StrategyHint`, `ProposeFromHintRequest`, `RegimeHintStats`, `HintStatsResponse` + `getStrategyHint`, `proposeFromHint`, `getHintStats`. |
| Market bars | 750–774 | mixed | 25 lines. `MarketBar`, `MarketBarsResponse` + `getMarketBars`. |
| Scanner domain | 778–820 | mixed | 43 lines. `ScannerFinding`, `ScannerThresholds*`, `ScannerHistoryFilters` + `getScannerThresholds`, `updateScannerThresholds`, `getScannerHistory`. |
| Settings domain | 822–885 | mixed | 64 lines. `SettingsScheduler`, `SettingsResponse`, `SettingsUpdate`, `SchedulerUpdate`, `ThemeResponse`, `ColorConventionResponse` + `getSettings`, `updateSettings`, `setTheme`, `setColorConvention`, `getScheduler`, `updateScheduler`, `exportKnowledgeDoc` (blob, note: missing `credentials: "same-origin"` — pre-existing bug, not in scope). |
| Knowledge graph (Phase 5) | 892–932 | mixed | 41 lines. `GraphNode`, `GraphEdge`, `GraphResponse`, `RelatedDoc`, `RelatedResponse` + `getKnowledgeGraph`, `getRelatedDocs`. |
| V2 API | 934–1011 | mixed | 78 lines. `APIVersionInfo`, `WatchlistItemV2`, `OptionsChainItemV2`, `OptionsChainResponseV2` + `getAPIVersion`, `getWatchlistV2`, `getOptionsChainV2`. |

### 1.2 Types vs. implementation

*Approx counts (manual, from section table above):*

- **Type-only lines:** ~420 lines (~42%) — 30+ exported `type` declarations, each domain colocated with its endpoint types.
- **Implementation lines:** ~530 lines (~52%) — 5 generic verbs + ~28 domain functions. Domain functions are uniformly 1–10 lines: build `URLSearchParams` or `encodeURIComponent`, then delegate to `get<T>`/`post<T>`/`postBody<T>`/`putBody<T>` or `fetchWithTimeout` for `Blob`/`File`.
- **Shared infra + headers + blanks/comments:** ~61 lines (~6%).

No hidden classes, no state, no WS logic. Every function is a pure `fetch` call — the file is a **stateless REST client + its DTO types**.

### 1.3 Domain boundaries

The only real boundary is **domain grouping**, not technical layering:

- Research / Knowledge / SymbolSearch / Analytics / Auth / Execution / Intelligence / Market / Scanner / Settings / KnowledgeGraph / V2 — 12 product domains sharing identical transport.
- There is **no WS code** in `api.ts`. The WebSocket client lives fully in `src/shettyxtreme/terminal/web/src/lib/ws.ts` (topic registry, reconnect, subscribe/unsubscribe). `api.ts:27` mentioning `AbortError` is the only `ws`-adjacent string; grep for `WebSocket|wsUrl|socket` hits only `ws.ts` and `connection.svelte.ts`.

A split on `types / rest-client / ws-client` would therefore be:

- `ws-client` — **already done**. No code to extract.
- `types` vs `rest-client` — would separate each domain's DTO type from the 1–3 line function that uses it, forcing every consumer to import from two places or via a barrel that re-exports both.

### 1.4 Internal dependencies

- Internal: `Theme` (from `./theme`), `ColorConvention` (from `./color-convention`) — leaf type imports only.
- No imports from `ws.ts`, `connection.svelte.ts`, `stores`, or components. Acyclic by construction.
- All functions depend only on `fetchWithTimeout`/`request`/`describeError`/`isAbortError` defined at top. No cross-domain coupling (e.g., `getProposals` never calls `getSettings`).

---

## 2. Import Graph — Who Imports from `api.ts`

`rg "from.*api" src/shettyxtreme/terminal/web/src` → **42 hits across ~30 files** (all `from "$lib/api"` or `from "../lib/api"` / `from "../../lib/api"`). No dynamic imports.

| Consumer | Import style | Symbols used |
|---|---|---|
| `components/ChainGrid.svelte` | `../lib/api` | `get` |
| `components/ChainGrid.test.ts` | `../lib/api` | `get`, `getMarketBars` |
| `components/CandleChart.svelte` | `../lib/api` | `getMarketBars`, `MarketBar` (type) |
| `components/CandleChart.test.ts` | `../lib/api` | `getMarketBars`, `MarketBarsResponse` (type) |
| `components/GreeksPanel.svelte` | `../lib/api` | (greeks/heatmap fns) |
| `components/KillSwitch.svelte` | `../lib/api` | `get`, `post`, `postBody` |
| `components/Header.svelte` | `../lib/api` | `authStatus`, `get`, `AuthStatus` |
| `components/HintsPanel.svelte` | `$lib/api` | (hint/proposal fns) |
| `components/KnowledgePanel.svelte` | `../lib/api` | `get`, `post`, `postBody` + knowledge types |
| `components/LogDrawer.svelte` | `../lib/api` | `get` |
| `components/LogDrawer.test.ts` | `../lib/api` | `get` |
| `components/AnalyticsPanel.svelte` | `../lib/api` | `get` + analytics types |
| `components/knowledge/KnowledgeGraph.svelte` | `../../lib/api` | `getKnowledgeGraph`, `GraphEdge`, `GraphNode` |
| `components/knowledge/KnowledgeDetail.svelte` | `../../lib/api` | `KnowledgeDoc`, `RelatedDoc`, `exportKnowledgeDoc`, `getRelatedDocs` |
| `components/knowledge/knowledge-shared.ts` | `../../lib/api` | `KnowledgeDoc` (type only) |
| `components/ModeSwitcher.svelte` | `../lib/api` | `get`, `post`, `postBody` |
| `components/ProposalQueue.svelte` | `../lib/api` | `approveProposal` etc. + `Proposal` |
| `components/ProposalQueue.test.ts` | `../lib/api` | proposal types/fns |
| `components/OrderHistory.svelte` | `../lib/api` | `getOrders`, `cancelOrder`, etc. |
| `components/ResearchPanel.svelte` | `../lib/api` | `get`, `post`, `postBody` + research types |
| `components/ResearchBriefDetail.svelte` | `../lib/api` | `ResearchBrief`, `exportResearchBrief` |
| `components/PositionsRiskStrip.svelte` | `../lib/api` | `get`, `closePosition`, `getPositionHistory`, `ClosedPositionRecord` |
| `components/RiskHeatmap.svelte` | `../lib/api` | `get` |
| `components/RiskHeatmap.test.ts` | `../lib/api` | `get` |
| `components/ScannerPanel.svelte` | `$lib/api` | `get`, `proposeFromHint`, `ProposeFromHintRequest` + scanner fns |
| `components/SettingsView.svelte` | `../lib/api` | `getSettings`, `updateSettings`, `setTheme`, etc. + settings types |
| `components/SettingsView.test.ts` | `../lib/api` | `authStatus`, `reauth` |
| `components/SetupWizard.svelte` | `../lib/api` | `authStatus`, `saveCredentials`, `testCredentials`, `startAuth`, etc. |
| `components/SymbolSearch.svelte` | `../lib/api` | `get` |
| `components/Watchlist.svelte` | `../lib/api` | `del`, `get`, `post` |
| `components/TickerStrip.svelte` | `../lib/api` | `get` |

**Pattern:** Most components import **both** a domain type and its adjacent function from the same path (e.g., `Proposal` + `approveProposal`). The colocation is load-bearing for ergonomics.

**Barrel cost if split:** Every consumer above would need either (a) two imports (`from "$lib/api/types"` + `from "$lib/api/client"`) or (b) a new barrel `src/lib/api/index.ts` that re-exports both — which restores `from "$lib/api"` but adds indirection and `svelte-check` barrel-resolution risk for zero cohesion gain.

---

## 3. Decision

### **Option A — Keep whole. Do not split.**

**One-line rationale:** 1011 lines is well under the 1500 guard, WS is already isolated in `ws.ts`, and types are intentionally colocated with their endpoint functions — splitting would create an artificial `types`/`client` seam that doubles imports for 30 consumers with no cohesion or cycle benefit.

### Why not Option B

A clean `api/types.ts` / `api/rest.ts` / `api/ws.ts` boundary does **not** emerge:

1. **No WS to extract** — `api.ts` contains zero WS code; `ws.ts` is already the WS client. The criterion's third bucket is satisfied without touching `api.ts`.
2. **Types and functions are domain-coherent, not layer-coherent.** `Proposal` is meaningless without `getProposals`/`approveProposal`; `GraphNode` without `getKnowledgeGraph`. Separating them by technical layer (all types in one file, all fns in another) scatters each domain across two files. The domain grouping *is* the cohesion.
3. **No size or cycle pressure.** 1011 < 1500, no circular deps, no god-module symptoms (no state, no cross-domain calls, no file >1500).
4. **Churn vs. value.** A split touches ~30 import sites (42 hits) plus barrel wiring, `svelte-check`/`vite` alias verification, and future merge conflicts — for a file that is a flat list of `get<T>`/`postBody<T>` wrappers.

### If this file grows

Revisit only if it **crosses 1500** or a domain becomes stateful/complex (e.g., execution acquiring a state machine). At that point prefer a **domain split** (`api/execution.ts`, `api/research.ts`, …) over a horizontal `types`/`client` split, with a barrel `api/index.ts` preserving `from "$lib/api"` for existing consumers. That preserves domain cohesion. Today that split is premature.

---

## 4. What was checked

- [x] Read `src/shettyxtreme/terminal/web/src/lib/api.ts` (1011 lines) and `src/shettyxtreme/terminal/web/src/lib/ws.ts` metadata.
- [x] Ran `rg "from.*api" src/shettyxtreme/terminal/web/src` — 42 hits, enumerated above.
- [x] Verified no `WebSocket`/`wsUrl`/`socket` usage inside `api.ts` (only `ws.ts` + `connection.svelte.ts`).
- [x] Verified import acyclicity (`api.ts` imports only `./theme`, `./color-convention`).
- [x] Confirmed guard: 1011 < 1500, so no violation.

---

## 5. No implementation plan (keep-whole)

No code changes, no `bun run check`/`bun run build` gate, no import rewrites. Re-evaluate at next 1500-line breach or if a domain acquires nontrivial logic warranting its own module.

---

*Phase 7 S2 — assessed 2026-08-21. File stays at `src/shettyxtreme/terminal/web/src/lib/api.ts`.*
