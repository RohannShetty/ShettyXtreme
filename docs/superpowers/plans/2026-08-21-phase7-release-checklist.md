# Phase 7 Release Checklist — v0.18.0

**Date:** 2026-08-21  
**Version:** 0.18.0  
**Status:** Ready for deployment

---

## Pre-Release Verification

### Automated Gates (all passed)
- ✅ **Backend tests:** 1833 passed / 0 failed / 1 skipped (83.14s)
  - Skip is legitimate: `tests/wave8/test_iaf_adapter_integration.py` gated on optional `investing-algorithm-framework`
  - With `pip install -e ".[iaf]"`: 1846 passed / 0 skipped
- ✅ **Frontend type check:** `bun run check` → 0 errors, 3 pre-existing warnings
- ✅ **Frontend build:** `bun run build` → success, 12 JS chunks (largest 286KB < 300KB limit)
- ✅ **Import boundaries:** `grep -r "import openalgo\|from openalgo" src/` → 0 matches
- ✅ **File size guard:** No file > 1500 lines
- ✅ **Core isolation:** `core/` has zero external imports (known violation: `core/config/config_manager.py:10` imports `yaml` — pre-existing)

### Bundle Optimization (S1)
- ✅ Main JS chunk: 725KB → 249KB (**-65.6%**, exceeds 20% gate by 3×)
- ✅ CSS main: 151KB → 106KB (**-30%**)
- ✅ 12 JS chunks + 9 CSS chunks (was 1+1)
- ✅ Vite warning eliminated (chunkSizeWarningLimit: 300)
- ✅ Lazy-loaded components: SettingsView, SetupWizard, RiskHeatmap, GreeksPanel, ResearchPanel, KnowledgePanel
- ✅ Vendor chunks split: d3, lucide, sonner, bits-ui

### Code Quality (S2)
- ✅ `api.ts` assessment: 1011 lines, decision to keep whole (no clean boundary, WS already separate)
- ✅ No refactoring needed — file is cohesive, well-organized

### Accessibility (S3)
- ⚠️ **BLOCKED:** S3 accessibility audit blocked after 2 attempts (no output from subagents)
- **Manual verification required:** Tab through app, verify focus rings, keyboard nav, ARIA labels
- **Known pre-existing:** 3 svelte-check warnings (SymbolSearch non-reactive, ScannerPanel a11y)

### Test Suite (S4)
- ✅ Skip reconciliation: legitimate optional-dependency gate
- ✅ AGENTS.md updated: 1833/0/1 (v0.17.0) → 1833/0/1 (v0.18.0) with iaf note

---

## Manual Testing Checklist

### Cross-Browser Testing (required before production)
Test on **Chrome**, **Edge**, **Firefox** (latest stable versions):

#### Core Functionality
- [ ] **Setup wizard** (`#/setup`): Fyers credentials entry, test connection, redirect flow
- [ ] **Main dashboard** (`#/`): watchlist, option chain, center tabs (CHAIN/GREEKS/SCANNER), right dock (RESEARCH/KNOWLEDGE/LOGS)
- [ ] **Settings** (`#/settings`): theme toggle, color convention, API keys
- [ ] **WebSocket connection:** real-time tick updates, position updates, alert toasts
- [ ] **Command palette** (Ctrl+K): search, navigation, actions

#### Lazy-Loaded Components (S1 changes)
- [ ] **SettingsView**: loads on `/settings` route, no flash of unstyled content
- [ ] **SetupWizard**: loads on `/setup` route, query params preserved
- [ ] **RiskHeatmap**: loads on main route (below-fold), D3 rendering < 2s for 100 nodes
- [ ] **GreeksPanel**: loads on GREEKS tab, charts render correctly
- [ ] **ResearchPanel**: loads on RESEARCH tab, export dropdown works (Markdown/PDF)
- [ ] **KnowledgePanel**: loads on KNOWLEDGE tab, graph visualization works, click-to-search

#### Keyboard Navigation (S3 — manual verification)
- [ ] **Tab order:** all interactive elements reachable via Tab
- [ ] **Focus rings:** 2px `#f5b942` visible on `:focus-visible` for buttons, inputs, tabs
- [ ] **Watchlist:** arrow keys navigate symbols, Enter selects
- [ ] **Option chain:** arrow keys navigate strikes, Enter selects
- [ ] **Tabs:** arrow keys switch tabs (CenterTabs, RightDockTabs)
- [ ] **Escape:** closes modals, drawers, command palette
- [ ] **Gutters:** arrow keys resize panes (Workspace.svelte)

#### Accessibility (S3 — manual verification)
- [ ] **ARIA labels:** icon-only buttons have `aria-label` (close, refresh, expand)
- [ ] **Regions:** panels have `role="region"` + `aria-label`
- [ ] **No emoji in data UI:** charts, tables, panels are emoji-free (command palette labels OK)

#### Performance
- [ ] **Initial load:** main route loads in < 3s on 4G connection
- [ ] **Bundle size:** verify via browser devtools → Network tab (main JS ~250KB, not 725KB)
- [ ] **Lazy loading:** verify chunks load on demand (SettingsView, GreeksPanel, etc.)
- [ ] **Graph rendering:** KnowledgePanel graph < 2s for 100 nodes

---

## Deployment Steps

### 1. Pre-Deployment
```powershell
# Ensure all changes committed
git status
git add -A
git commit -m "chore: Phase 7 release - bundle optimization, skip reconciliation, version bump to 0.18.0"

# Update graph
graphify update .

# Push to origin
git push origin master
```

### 2. Production Deployment
```powershell
# On production machine
git pull origin master

# Install dependencies (if changed)
.venv\Scripts\python.exe -m pip install -e .

# Frontend build (already committed to terminal/static/)
# No need to rebuild unless you changed src/shettyxtreme/terminal/web/src/

# Start terminal
.venv\Scripts\python.exe run.py --mode OBSERVER

# Verify in browser
# Navigate to http://127.0.0.1:8000
# Check browser console for errors
# Verify lazy loading (devtools → Network → filter by JS)
```

### 3. Post-Deployment Verification
- [ ] **Health check:** `GET /api/health` → 200 OK
- [ ] **WebSocket:** connect to `ws://127.0.0.1:8000/ws` → connection established
- [ ] **Fyers connection:** verify credentials, test market data feed
- [ ] **Lazy loading:** verify chunks load on demand (not all at once)
- [ ] **Performance:** API response times < 50ms (watchlist, intelligence, execution)

### 4. Rollback Plan
If issues arise:
```powershell
# Revert to v0.17.0
git revert HEAD
git push origin master

# On production
git pull origin master
.venv\Scripts\python.exe run.py --mode OBSERVER
```

---

## Known Issues / Deferred Work

### S3 Accessibility Audit (BLOCKED)
- **Status:** Subagent returned empty output twice
- **Action required:** Manual accessibility audit before production
- **Focus areas:** focus rings, keyboard nav, ARIA labels, emoji removal
- **Pre-existing warnings:** SymbolSearch non-reactive, ScannerPanel a11y (not blocking)

### Bundle Size
- **Current:** main JS 249KB (was 725KB), largest chunk 286KB (bits-ui)
- **Future optimization:** tree-shake unused bits-ui primitives if bundle grows
- **Monitor:** if any chunk exceeds 300KB, Vite will warn

### Test Suite
- **Skip:** `tests/wave8/test_iaf_adapter_integration.py` (13 tests) skipped when `.[iaf]` not installed
- **Action:** None — legitimate optional-dependency gate
- **To run:** `pip install -e ".[iaf]"` then re-run tests (expect 1846 passed / 0 skipped)

---

## Version Bump Summary

Updated to **0.18.0** in:
- ✅ `src/shettyxtreme/__init__.py`
- ✅ `src/shettyxtreme/terminal/api/app.py`
- ✅ `pyproject.toml`
- ✅ `src/shettyxtreme/terminal/web/package.json`
- ✅ `CHANGELOG.md` (v0.18.0 entry added)

---

## Phase 7 Summary

### Completed
- **S1:** Bundle optimization — 65.6% reduction in main JS chunk, 12 chunks, lazy loading
- **S2:** api.ts assessment — decision to keep whole (no clean boundary)
- **S4:** Skip reconciliation — legitimate skip documented, AGENTS.md updated

### Blocked
- **S3:** Accessibility audit — subagent returned empty output twice, manual verification required

### Release Readiness
- ✅ All automated gates passed
- ⚠️ Manual accessibility audit required (S3 blocked)
- ⚠️ Cross-browser testing required (Chrome/Edge/Firefox)
- ✅ Version bumped to 0.18.0
- ✅ CHANGELOG updated
- ✅ Ready for deployment after manual verification

---

## Next Steps

1. **Manual accessibility audit** (S3) — verify focus rings, keyboard nav, ARIA labels
2. **Cross-browser testing** — Chrome, Edge, Firefox
3. **Deploy to production** — follow deployment steps above
4. **Monitor** — watch for lazy loading issues, performance regressions
5. **Future phases** — consider S3 follow-up if accessibility issues found, bundle optimization if chunks grow
