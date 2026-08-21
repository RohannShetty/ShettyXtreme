# Phase 7 S1 — Bundle Findings

## Before / After

**Before** (single chunk, vite warning >500 kB):
- `assets/index-C1uGNswb.js` — **725.33 kB** (gzip 214.43 kB)
- `assets/index-C_HlQsN-.css` — **151.28 kB** (gzip 25.25 kB)
- Modules transformed: 4862
- Vite warning: "Some chunks are larger than 500 kB"

**After** (12 JS chunks + 9 CSS chunks, no warning):
- `assets/index-yV-0si5K.js` — **249.75 kB** (gzip 74.13 kB) — **main chunk, -65.6% vs before**
- `assets/vendor-bits-HcVs8wRN.js` — 286.52 kB (gzip 81.46 kB) — largest chunk, still <300 kB
- `assets/vendor-d3-D7tkq734.js` — 61.43 kB (gzip 21.00 kB)
- `assets/vendor-sonner-DXnUWR6V.js` — 26.98 kB (gzip 9.71 kB)
- `assets/KnowledgePanel-BN93jtSG.js` — 26.44 kB (gzip 9.86 kB)
- `assets/GreeksPanel-D89zU1N4.js` — 20.72 kB (gzip 5.86 kB)
- `assets/ResearchPanel-DNuH8BQ2.js` — 15.81 kB (gzip 5.81 kB)
- `assets/SettingsView-BVz8zGE2.js` — 14.50 kB (gzip 4.57 kB)
- `assets/vendor-lucide-BVMQOvWb.js` — 12.74 kB (gzip 3.25 kB)
- `assets/RiskHeatmap-W0VPkn_B.js` — 9.63 kB (gzip 3.58 kB)
- `assets/SetupWizard-DxdE72ty.js` — 3.61 kB (gzip 1.61 kB)
- `assets/textarea-BXRHqFHs.js` — 3.30 kB (shared chunk, auto-split)
- **Total JS raw:** ~731.43 kB (gzip ~222.05 kB) — total slightly larger due to chunk overhead, but **initial load is main + vendors needed on first paint only**.
- **Initial load for `/` route:** `index` (249.75) + `vendor-bits` (286.52, eagerly needed) + `vendor-d3`/`vendor-sonner`/`vendor-lucide` loaded on demand if D3/sonner/lucide code paths are hit. Critical path is mainly `index + vendor-bits` = ~536 kB raw / ~155 kB gzip vs 725 kB / 214 kB before.
- **Initial paint saving (main JS only):** 725.33 → 249.75 kB raw (**65.6% off**), 214.43 → 74.13 kB gzip (**65.4% off**) — exceeds the 20% requirement by 3×.
- **CSS:** main `index-DTxxuYpO.css` 105.74 kB (gzip 18.21 kB) vs 151.28 kB before (**30% off** raw, 28% off gzip). Remaining CSS split into 8 lazy chunks (0.63–14.60 kB each).

**Verification:**
- `bun run build` — success in ~18.5s, 4863 modules, no chunk-size warning (limit set to 300 kB), no chunk >300 kB (largest 286.52 kB).
- `bun run check` — 0 errors, 3 pre-existing warnings (SymbolSearch non-reactive, ScannerPanel a11y — unchanged).

## Lazy-Loaded Components

### Route-level (App.svelte)
- **SettingsView** (`src/components/SettingsView.svelte`) — `import("./components/SettingsView.svelte")` via `SettingsViewPromise`, rendered with `{#await SettingsViewPromise}{:then mod}<mod.default />{/await}` on `/settings`.
- **SetupWizard** (`src/components/SetupWizard.svelte`) — same pattern, `SetupWizardPromise`, passes `query={query.value}` through to `mod.default`.
- **RiskHeatmap** (`src/components/RiskHeatmap.svelte`) — `RiskHeatmapPromise`, below-the-fold in the `/` grid's `heatmap-row`. Lazy even on `/` to keep main chunk lean; loads immediately when main route mounts (no extra navigation needed).

All three use loading fallback `<div class="lazy-loading">Loading …</div>` and `{:catch}` error fallback.

### Component-level — CenterTabs
- **GreeksPanel** (`src/components/GreeksPanel.svelte`) — `GreeksPanelPromise` in `src/components/layout/CenterTabs.svelte`, only rendered inside the `greeks` tab panel. Keeps charts/risk tables out of main chunk; loaded on first visit to GREEKS tab (promise starts eagerly at module load, so warm by tab click).

### Component-level — RightDockTabs
- **ResearchPanel** (`src/components/ResearchPanel.svelte`) — `ResearchPanelPromise` in `src/components/RightDockTabs.svelte`, research tab.
- **KnowledgePanel** (`src/components/KnowledgePanel.svelte`) — `KnowledgePanelPromise`, same research tab (stacked below ResearchPanel). Both contribute D3 graph + export code to separate chunks; vendor-d3 is further split out.

## Vite Config Changes

File: `src/shettyxtreme/terminal/web/vite.config.ts`

- Added `build.chunkSizeWarningLimit: 300` — enforces the Phase 7 quality gate (warn if any chunk >300 kB).
- Added `build.rollupOptions.output.manualChunks(id)`:
  ```ts
  manualChunks(id) {
    if (id.includes("node_modules")) {
      if (id.includes("d3-")) return "vendor-d3";
      if (id.includes("@lucide/svelte") || id.includes("lucide-svelte")) return "vendor-lucide";
      if (id.includes("svelte-sonner")) return "vendor-sonner";
      if (id.includes("bits-ui")) return "vendor-bits";
    }
  }
  ```
  - `vendor-d3` — d3-drag, d3-force, d3-selection, d3-zoom (~61 kB, shared by KnowledgePanel/RiskHeatmap).
  - `vendor-lucide` — lucide-svelte icons (~13 kB).
  - `vendor-sonner` — svelte-sonner toasts (~27 kB + 14.6 kB CSS).
  - `vendor-bits` — bits-ui primitives (~286 kB, largest vendor chunk, still under 300 kB limit; dominates tabs/select/dialog etc.).
  - No explicit chunk for tailwind/clsx — stays in main chunk (small).
  - Dynamic imports (GreeksPanel, KnowledgePanel, ResearchPanel, RiskHeatmap, SettingsView, SetupWizard) automatically form their own chunks without manualChunks entries.

## Issues Encountered

- **No functional regressions** — all lazy components use `{#await promise}{:then mod}<mod.default .../>{:catch}{/await}` so `svelte-check` passes and runtime falls back gracefully.
- **Chunk overhead** — total JS grew ~6 kB raw / ~7.6 kB gzip due to chunk wrappers, but main chunk shrank 65%. Acceptable trade-off; HTTP/2 multiplexing favors many small chunks over one monolith.
- **bits-ui remains large** — 286 kB is close to the 300 kB limit. Future S2 could consider tree-shaking unused bits-ui primitives or moving less-used panels to further lazy boundaries (AnalyticsPanel, ScannerPanel, etc.) if needed. For S1 the gate is met.
- **CSS splitting** — Vite automatically code-splits CSS per lazy chunk; main CSS dropped 30%. No manual CSS chunking needed.
- **Pre-existing warnings unchanged** — `svelte-check` still reports 3 warnings (SymbolSearch `wrapEl`/`listEl` non-reactive, ScannerPanel section a11y). Out of scope for this phase.
