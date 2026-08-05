# Design Research Findings — Cockpit Redesign External Resources

**Date:** 2026-08-05
**Scope:** ui-ux-pro-max-skill, taste-skill, awesome-design-md, shadcn-ui — what each offers a data-dense trading terminal
**Status:** Research complete; adoption candidates listed for cockpit redesign

---

## Executive Summary

- **3 of 4 resources are already vendored locally** in `.skills/` (`design-taste-frontend` = taste-skill v2, `ui-ux-pro-max` + `ui-ux-pro-max-data`, `industrial-brutalist-ui`) — the redesign should *use* them, not re-install.
- **awesome-design-md was already deep-briefed** in `docs/references/BRIEF-awesome-design-md.md` (picks: Binance, VoltAgent, ClickHouse) and its output is already codified in our binding `DESIGN.md` (root). Nothing new to ingest; use it for `preview.html` visual references.
- **shadcn-svelte gap**: we use 11 of ~58 components. The high-value missing set for a cockpit: `data-table`, `sheet`, `scroll-area`, `resizable`, `separator`, `popover`, `dropdown-menu`, `alert-dialog`, `select`, `switch`, `alert`, `progress`, `skeleton`, `sonner`, `command`, `kbd`.
- **Convergent guidance across all four**: density is a dial you turn up (`VISUAL_DENSITY 8–10` = "Cockpit"), one accent color, hairlines over shadows, mono numerals, zero decoration, explicit state coverage (loading/empty/error), keyboard-first. This matches our `DESIGN.md` contract exactly — the resources confirm it, they don't contradict it.

---

## 1. ui-ux-pro-max-skill — `github.com/nextlevelbuilder/ui-ux-pro-max-skill` (MIT)

**Status: already installed** at `.skills/ui-ux-pro-max/` (+ data variant `.skills/ui-ux-pro-max-data/`). Local copy is slightly older than upstream v2.x README (local: 50+ styles / 161 palettes / 57 pairings; upstream now: 84 styles / 192 palettes / 74 pairings / 161 reasoning rules) — refresh with `npm i -g ui-ux-pro-max-cli && uipro update` when convenient. Installable for OpenCode via `uipro init --ai opencode`.

### Key offerings for a trading terminal
- **Design System Generator** (`scripts/search.py "<query>" --design-system`): multi-domain search (product type × style × color × landing pattern × typography) run through a reasoning engine with industry rules. Finance is a first-class category (Fintech/Crypto, Banking, Personal Finance Tracker, Invoice & Billing) with its own anti-patterns (e.g., "AI purple/pink gradients" banned for banking).
- **10 BI/Analytics dashboard styles** — directly relevant: *Data-Dense Dashboard, Real-Time Monitoring, Drill-Down Analytics, Comparative Analysis Dashboard, Financial Dashboard, Executive Dashboard, Predictive Analytics*.
- **25 chart types** (`charts.csv`) with library recommendations — useful when we extend `CandleChart` / analytics panels.
- **Stack guidance includes Svelte AND shadcn** (`data/stacks/svelte.csv`, `shadcn.csv`) — query with `--stack svelte` for implementation-specific rules.
- **98 UX guidelines** (`ux-guidelines.csv`) — a checkable rubric; already surfaced in the local SKILL.md Quick Reference (contrast, focus, touch, animation timing, empty states).
- **Master + Overrides persistence pattern**: `--design-system --persist` writes `design-system/MASTER.md` + `pages/<page>.md` overrides; page file wins over master. Same hierarchical-retrieval idea as our DESIGN.md + per-view overrides.
- **Three design dials** (`--variance/--motion/--density`, 1–10): `--density 8` overrides the `--space-*` token table for dashboards.

### Adopt for the cockpit
1. Run the design-system generator once for the cockpit: `python .skills/ui-ux-pro-max/scripts/search.py "fintech options trading dashboard dark data-dense" --design-system --density 9 --variance 3 --motion 2 -f markdown` — use as a cross-check against our DESIGN.md tokens (do NOT let it override the contract).
2. Use `charts.csv` when picking viz for new analytics panels (greeks, IV skew, P&L distribution).
3. Use the 10 dashboard styles as a vocabulary in specs: name each cockpit view (watchlist = Real-Time Monitoring, chain = Data-Dense + Drill-Down, risk = Financial/Executive).
4. `ux-guidelines.csv` as a pre-delivery checklist per panel.

### Anti-patterns to avoid
- Don't let the generator's marketing-flavored output (hero-centric, social-proof) leak into the cockpit — it's a dashboard generator, and landing patterns are its default bias. Query with dashboard keywords + density dial.
- "AI purple/pink gradients" anti-pattern for finance — consistent with DESIGN.md "no gradients".
- Local copy is stale vs upstream — don't cite its style/palette counts as authoritative; refresh first.

---

## 2. taste-skill — `github.com/leonxlnx/taste-skill` (MIT)

**Status: already installed** at `.skills/design-taste-frontend/` (v2, experimental) and `.skills/industrial-brutalist-ui/`. Also has `redesign-skill` (audit-first), `soft-skill`, `minimalist-skill` upstream — only two of the code skills are vendored here.

### Key offerings for a trading terminal
- **Three dials** — the core mechanism. `VISUAL_DENSITY` is the one that matters for us: **8–10 = "Cockpit / Packed Data"** — tight paddings, **no card boxes**, 1px lines separate data, `font-mono` for ALL numbers. That is literally our DESIGN.md density profile, expressed as a dial.
- **Brief inference protocol** (§0): read the room before generating — page kind, vibe words, audience, existing brand assets (our DESIGN.md), quiet constraints. For a cockpit: "data-dense operator tool, regulated/financial audience" → dials `VARIANCE 3–4 / MOTION 2–3 / DENSITY 8–10`.
- **Design-system map** (§2): "one system per project" — reach for the official system, never ship shadcn default state; for us that means bits-ui/shadcn-svelte primitives restyled to DESIGN.md tokens.
- **Anti-slop rules** (§4, §9) that are directly transferable: max 1 accent color, no pure `#000000` (we use `#0d0c0a` ✓), no neon glows (we use hairlines ✓), shape consistency lock (our `rounded: control 4 / panel 6 / badge 2` ✓), **no fake-precise numbers** (relevant — our figures are real market data, don't invent precision), color consistency lock (one accent per page).
- **State coverage mandate** (§4.5): loading skeletons shaped like final layout, composed empty states, inline error states, tactile `:active` feedback — maps to our `LoadingState/ErrorState/EmptyState` components.
- **v2 additions**: redesign-audit protocol (audit-first for existing UI — right fit for a *redesign*), strict pre-flight check, em-dash ban (note: our DESIGN.md prose uses em-dashes; that rule targets visible marketing copy, not internal docs).

### Adopt for the cockpit
1. Treat `VISUAL_DENSITY: 8–10` as the explicit target for the redesign; use dial language in specs ("density 9, variance 3, motion 2") instead of vague "make it denser".
2. Run the **redesign-audit protocol** (from v2, §Redesign) against current panels before restyling — audit-first beats greenfield instinct.
3. Adopt its **pre-flight check** as a gate before any panel ships (contrast, focus states, reduced-motion, shape lock, one-accent audit).
4. `minimalist-skill` / `soft-skill` rules for secondary surfaces (settings, setup wizard) if we want a calmer counterpoint to the dense cockpit — optional.

### Anti-patterns to avoid
- **Inter as default is discouraged by taste-skill** (prefers Geist/Outfit/etc.) — but our DESIGN.md mandates Inter for labels. DESIGN.md is binding; keep Inter. The tension is noted, not a violation (Inter is the "acceptable when explicitly asked/standard" override path).
- Banned defaults that would corrupt a trading UI: AI-purple gradients, glassmorphism on everything, serif display defaults, centered-hero layouts, emoji as icons, decorative-only motion, `window scroll` listeners, `h-screen` (use `min-h-dvh`).
- "Cards banned at density > 7" — use hairlines/rows, not card containers, for dense data lists (watchlist, chain rows).

---

## 3. awesome-design-md — `github.com/VoltAgent/awesome-design-md` (MIT)

**Status: already briefed** — see `docs/references/BRIEF-awesome-design-md.md` (repo-local research with full 9-section format spec, token lists, and 3 reference picks). 73 DESIGN.md files, each in Google Stitch format (9 sections: Theme, Colors, Typography, Components, Layout, Elevation, Do/Don'ts, Responsive, Agent Prompt Guide) + `preview.html` / `preview-dark.html`.

### Key offerings for a trading terminal
- **Fintech & Crypto category is the goldmine**: Binance ("trading-floor urgency"), Coinbase, **Kraken ("data-dense dashboards")**, Revolut, Stripe, Wise, Mastercard.
- **Data-dense dev tools worth reading**: Sentry ("data-dense, dark dashboard"), ClickHouse ("fast analytics, technical doc style"), Warp (terminal UI), Raycast ("keyboard-first"), Cursor, Superhuman ("keyboard-first, premium dark").
- **Terminal-native references**: VoltAgent ("void-black canvas, emerald accent, terminal-native"), Ollama ("terminal-first, monochrome").
- Prior BRIEF already extracted the transferable anatomy: Binance's numeric-typography tokens + trading-up/down semantics, VoltAgent's hairline elevation system, ClickHouse's 3-step surface ladder — **already baked into our DESIGN.md** (canvas ladder `#0d0c0a → #1e1b17`, mono numerals, hairline elevation).

### Adopt for the cockpit
1. Pull **Kraken + Sentry + Binance DESIGN.md** (via `getdesign.md/<site>/design-md`) as the closest data-dense references; read their Component Stylings + Do's/Don'ts sections as checklists during redesign.
2. Use their `preview.html`/`preview-dark.html` as visual mood references for density calibration (how many rows, how tight).
3. When writing per-view overrides, mirror the Stitch 9-section shape (our DESIGN.md already follows it — keep new view specs in the same shape).
4. The repo's Agent Prompt Guide pattern (quick hex reference + ready prompts) is worth copying into our DESIGN.md if not already present (§9).

### Anti-patterns to avoid
- Don't copy DESIGN.md files wholesale — they encode *other brands'* tokens; we borrow *structure and density discipline*, never palettes (our DESIGN.md explicitly replaced Binance's green/red with the Indian red=up/green=down convention).
- Avoid the collection's marketing-heavy entries (Stripe weight-300 elegance, Revolut 136px displays, PostHog playful palettes) — already flagged in the prior BRIEF.
- Kraken's DESIGN.md is only a 125-line light-marketing skeleton, NOT its data-dense dashboards — don't cite it as a density reference (noted in BRIEF §2).

---

## 4. shadcn-ui — `github.com/shadcn-ui/ui` (MIT)

**Important framing:** shadcn/ui is React; **we are Svelte 5 + bits-ui + Tailwind v4** (`package.json`). The operative catalog is the shadcn-svelte port (58 components, `shadcn-svelte.com/docs/components`) — the React repo's component names map 1:1. We already have 11.

### Already in use (`src/lib/components/ui/`)
`button, card, dialog, table, tabs, input, badge, checkbox, label, textarea, tooltip`

### Missing catalog — ranked by cockpit value (adopt from shadcn-svelte, styled to DESIGN.md)

| Tier | Component | Cockpit use | Notes |
|---|---|---|---|
| **1 — data density** | `data-table` | Sortable/filterable watchlist, scanner results, positions | TanStack-based; sort + aria-sort, column toggles, density variants |
| | `scroll-area` | Thin custom scrollbars for panels | DESIGN.md calls for thin scrollbars; replaces default OS bars |
| | `resizable` | Split panes: watchlist / chain / risk side-by-side | ARCHITECTURE_V2 §15 calls for resizable split panes |
| | `separator` | Hairline dividers between data regions | Matches hairline-elevation system |
| | `pagination` | Scanner/chain pagination or lazy-load footers | Optional |
| | `kbd` | Keyboard shortcut hints (trading terminals are keyboard-first) | Pairs with Raycast/Superhuman "keyboard-first" references |
| **2 — overlays** | `sheet` | Settings / proposal detail / order ticket slide-over | Lighter than dialog for side contexts (ModeSwitcher, SettingsView) |
| | `dropdown-menu` | Row actions on watchlist/positions (close, straddle, hedge) | Currently likely ad-hoc |
| | `context-menu` | Right-click on chain rows / chart | Pro users expect it |
| | `alert-dialog` | KillSwitch / LIVE-mode typed confirmation | **D10 safety surface** — pairs with typed-confirm flows |
| | `command` | Symbol search command palette (⌘K-style) | Upgrade over plain input for symbol lookup |
| | `popover` | Quick symbol info, IV/tick detail on hover | |
| **3 — forms** | `select` / `native-select` | Expiry, strategy, interval pickers | Current UI may hand-roll these |
| | `switch` | OBSERVER/LIVE toggle (guarded), auto-approve, alerts on/off | |
| | `radio-group` | Strategy type selection in proposal builder | |
| | `slider` | Risk limits, position-size calculator | |
| | `toggle` / `toggle-group` | Chart timeframe / view-density switcher | |
| **4 — feedback** | `alert` | Dhan error **806** (Data-API entitlement) surfacing — "surface it, never paper it over" | Per AGENTS.md |
| | `progress` | P&L bars, margin utilization, IV percentile gauges | |
| | `skeleton` | Panel loading placeholders shaped like final layout | Upgrade our `LoadingState` |
| | `sonner` | Toasts: fill notifications, order status, errors | Current `LogDrawer` may not toast |
| | `empty` | Empty states for scanner/watchlist with guidance | Upgrade `EmptyState` |
| **5 — layout** | `sidebar` | Cockpit left rail (if we adopt one) | Architecture v2 §15 mentions panels, not sidebar — decide |
| | `accordion` / `collapsible` | Collapsible settings groups, research brief sections | |
| | `breadcrumb` | Research/knowledge drill-down paths | Optional |
| | `calendar` / `range-calendar` | Expiry calendar, backtest date ranges | Optional |
| **Skip** | `avatar`, `carousel`, `aspect-ratio`, `menubar`, `navigation-menu`, `breadcrumb`(maybe) | Consumer-web components, low cockpit value | |

### Anti-patterns to avoid
- **Never ship shadcn default styling** — every ported component must be re-skinned to DESIGN.md tokens (canvas ladder, accent `#f5b942`, mono numerals, radius 4/6/2). Default shadcn gray-on-white will break the contract.
- Don't pull React shadcn code into Svelte — use the shadcn-svelte ports / bits-ui primitives (we already depend on `bits-ui`).
- "One system per project" (taste-skill): don't mix a second component family for the same surface type.
- Avoid component sprawl — add only what a panel actually needs; a cockpit is density, not a component museum.

---

## Cross-resource synthesis — what the redesign should actually do

1. **Density dial, explicitly**: `VARIANCE 3–4 / MOTION 2–3 / DENSITY 8–10` (taste-skill) = `--density 9 --variance 3 --motion 2` (ui-ux-pro-max). One shared number to put in every panel spec.
2. **Audit-first**: run taste-skill v2 redesign-audit protocol + ui-ux-pro-max `ux-guidelines.csv` checklist against current panels before restyling.
3. **Component gap closure** (shadcn-svelte, DESIGN.md-skinned): `data-table` + `scroll-area` + `resizable` + `separator` (density tier), `sheet` + `dropdown-menu` + `alert-dialog` (KillSwitch/D10) + `command` (symbol search), `select/switch/slider` (forms), `alert/progress/skeleton/sonner/empty` (feedback).
4. **Reference check**: read Kraken/Sentry/Binance DESIGN.md + previews (awesome-design-md) for density calibration; keep our DESIGN.md as the single binding contract — resources confirm it, never override it.
5. **Refresh local skills**: `uipro update` for ui-ux-pro-max (local copy is behind upstream v2.x).

---

### Sources
- ui-ux-pro-max-skill: `github.com/nextlevelbuilder/ui-ux-pro-max-skill` README (v2.0, 161 rules / 84 styles / 192 palettes / 74 pairings / 25 chart types / 22 stacks); local `.skills/ui-ux-pro-max/SKILL.md` + `ui-ux-pro-max-data/`
- taste-skill: `github.com/leonxlnx/taste-skill` README + CHANGELOG (v2); local `.skills/design-taste-frontend/SKILL.md` (v2), `.skills/industrial-brutalist-ui/SKILL.md`
- awesome-design-md: `github.com/VoltAgent/awesome-design-md` README; repo-local `docs/references/BRIEF-awesome-design-md.md`
- shadcn-ui: `github.com/shadcn-ui/ui`; shadcn-svelte component catalog (`shadcn-svelte.com/docs/components`, 58 components); local `src/lib/components/ui/` inventory; `package.json` (bits-ui ^2.18.1, Svelte 5, Tailwind v4)
- Binding contract: root `DESIGN.md` (tokens quoted above); `docs/architecture/v2/sections/15-design-system-terminal-ux.md`
