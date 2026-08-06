# Phase 7 Wave 2 — Ticker strip / regime-IV-PCR chrome (roadmap #8) — Implementation

**Date:** 2026-08-05
**Scope:** New self-contained `TickerStrip.svelte` (regime + IV + PCR + max pain strip); no `App.svelte` / `Header.svelte` changes (integration is a later wave)
**Status:** Complete — `npm run check` 0 errors / 0 warnings; `npm run build` succeeds; `vitest` 17/17 passes
**Input:** `docs/superpowers/plans/2026-08-05-phase7-recon.md` §1.8

---

## Deliverables

| File | Change |
|---|---|
| `src/shettyxtreme/terminal/web/src/components/TickerStrip.svelte` | New self-contained ticker strip — 4 metric cards (REGIME, IV, PCR, MAX PAIN) in a horizontal flex bar, 30s REST poll, exported `refresh()` |
| `src/shettyxtreme/terminal/static/` | Regenerated committed bundle (vite build, AGENTS.md committed-bundle convention) |
| `docs/superpowers/plans/2026-08-05-phase7-wave2-ticker-strip.md` | This report |

## Verification

- `npm run check` → **0 errors, 0 warnings** (whole tree, including parallel-lane files).
- `npm run build` → **vite production build succeeds** (33.6s, 4630 modules).
- `npm run test` → **17 passed / 17** (7 files) — no frontend regressions.
- Python suite: **not run / not affected** — zero `.py` files touched; the strip is frontend-only and not yet imported by `App.svelte`.

---

## 1. Data sources — **important correction to the task brief**

The brief assumed IV/PCR/Max Pain come from an `intelligence/options-summary` endpoint that **"already exists" — it does not.** Recon §1.8 confirms only these intelligence endpoints exist (`terminal/api/intelligence_router.py`): `/regime`, `/signal`, `/voters`, `/options` (raw chain), `/strategy-hint`. There is no summary/posture endpoint; posture data lives server-side as a derived *text* in `research_source.py` (`render_options_posture` / `options_summary`), not as a REST JSON surface.

**Resolution (stays inside the "component-only" scope):** the component is self-contained against the two real endpoints and derives the metrics client-side as pure functions of the chain:

| Metric | Source | Derivation |
|---|---|---|
| Regime | `GET /api/intelligence/regime` (projection-backed, exists) | direct mapping |
| PCR | `GET /api/intelligence/options?symbol=NIFTY` (exists) | Σ put OI ÷ Σ call OI (matches backend `render_options_posture`) |
| Max Pain | same chain | strike minimizing total option payout at expiry (O(n) prefix/suffix sums) |
| IV level | same chain | mean positive chain IV; bands match backend (`HIGH ≥ 30`, `LOW < 20`, else NORMAL) |

**IV Rank caveat (flagged for the integration wave):** a true 0–100 *rank* requires the historical-IV `IVRankCalculator` (`research_source.py:145-162`), which is constructed server-side and not yet exposed on `app.state`. The strip renders a derived IV level on a 0–40% gauge today; the gauge fill is a single function (`ivFillOf`), so a real rank slots in when an `options-summary` endpoint lands. **Recommended follow-up:** add `GET /api/intelligence/options-summary` returning `{ iv_rank, pcr, max_pain, spot }` (backed by `IVRankCalculator` + `OITracker` + chain cache) — this is roadmap §1.12's "options_posture live" lane and is a backend change for a later wave.

## 2. Refresh strategy

- **On mount:** `onMount` → `load()` (both sources fetched in parallel via `Promise.allSettled` — a regime failure never blanks the posture cards and vice versa).
- **Periodic:** `setInterval(load, 30_000)` per the brief (mirrors `ChainGrid`'s poll pattern; `window.setInterval` returned handle cleared in `onDestroy`).
- **Imperative:** `export async function refresh()` — the component API the brief requires; integration calls it via `bind:this={strip}; strip.refresh()`.
- **WS (future):** recon §1.8 notes the `regime` topic is already WS-broadcast; switching regime to WS push (zero polling) is an integration-wave optimization, deliberately out of scope here.

## 3. Visual design decisions

All tokens from `design.css` (DESIGN.md §2) — no hard-coded hex.

- **Layout:** horizontal flex bar, `flex-wrap: wrap`, cards `flex: 1 1 130px` (`min 110px` / `max 210px`), hairline-left separators. Chrome surface: `--canvas-raised` + hairline top (header's surface language, DESIGN §2.2) — a strip, not a card (no radius).
- **Per card:** lucide icon (Activity / Gauge / Scale / Crosshair, 13px, `--faint`) + 9px uppercase micro label (Inter) + value. Numerals and chips in JetBrains Mono tabular (`design.css` `.num` law); labels in Inter.
- **Regime colors (brief-mandated):** TRENDING = `--success` green, RANGING = `--warning` yellow, VOLATILE = `--danger` red. Regime is a categorical *state*, not a price — the mandate overrides the price color law (which governs price numerals only). Mapping from the classifier enum: `trending_up`/`trending_down` → TRENDING, `range_bound` → RANGING, `volatile` → VOLATILE, unknown → muted "—".
- **Regime direction caret:** for trending regimes a ▲/▼ caret follows the **Indian price law** — red ▲ = up, green ▼ = down (`--price-up`/`--price-down`) — so the strip still communicates trend *direction* without violating "never fix red=up/green=down" on a price-like signal. Confidence % + a `⇄` chip when `transition=true` sit in the sub-row.
- **IV gauge:** green→amber→red `linear-gradient` track (`--success`→`--warning`→`--danger`); a `--canvas-raised` mask covers the un-filled right portion. Fill = level/40 scale; chip LOW/NORMAL/HIGH matches the backend's bands.
- **PCR interpretation (heat convention, documented):** OVERSOLD < 0.7 → `--success`, NEUTRAL 0.7–1.2 → muted, OVERBOUGHT > 1.2 → `--danger`. (Chosen to match the regime color philosophy — green = cool/contrarian buy zone, red = heat/contrarian sell zone — and the common Indian RSI convention. The direction-expectation alternative — red=OVERSOLD/up-bias, green=OVERBOUGHT/down-bias per the price law — is equally defensible; flagged for the DESIGN contract owner.)
- **Max Pain:** `₹24,500`-style (en-IN grouping) in mono.
- **Responsive:** flex-wrap wraps naturally; `@media (max-width: 720px)` forces 2-up (`flex-basis: calc(50% - 3px)`).
- **Liveness:** a `--danger` dot in the foot shows a fetch failure; the message rides the strip `title` for hover diagnostics. Every metric falls back to "—" independently when its source is missing — honest-by-construction like the backend's `[UNSOURCED]`.

## 4. Component API (integration contract)

```svelte
<script lang="ts">
  import TickerStrip from "./TickerStrip.svelte";
  let strip: TickerStrip; // instance type from the component
</script>
<TickerStrip bind:this={strip} />
<!-- later: strip.refresh() on WS regime push or manual trigger -->
```

- Mounts → loads → polls every 30s; teardown clears the interval.
- `refresh(): Promise<void>` — awaited force reload.
- No props; symbol fixed at `NIFTY` (matches the backend chain prime `prime_options_chain`); a future symbol prop is trivial.

## 5. Non-goals / untouched

- `App.svelte` / `Header.svelte` — **not modified** (placement is the integration wave; recon §1.7/§1.8 coupling notes apply there).
- Backend endpoints — not added; the `options-summary` gap is documented above for the §1.12 lane.
- Python tests — no `.py` changed.
- Other metric cards (spot, open interest delta) — out of the brief's four metrics.

## 6. Ops notes

- Working tree was clean at HEAD `10752ab` (phase7-wave1); only the new component + regenerated bundle + this report are added.
- Per AGENTS.md, `graphify update .` run after the change to refresh the graph.
