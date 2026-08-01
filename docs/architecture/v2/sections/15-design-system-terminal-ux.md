# Section 15 — Design System & Terminal UX

> The DESIGN.md contract and the terminal vision: a professional, dark, data-dense trading workstation for the Indian market — not a toy, not a marketing page. DESIGN.md is authored per D4 at the repo root (`D:\ShettyXtreme\DESIGN.md`), informed by the awesome-design-md fintech/terminal entries (Binance, VoltAgent, ClickHouse), the taste skill, and the ui-ux-pro-max skill (per the decisions pack, D4). The terminal is Svelte + Vite served by FastAPI (per D9).

## 1. The DESIGN.md contract (Google Stitch, 9 sections)

DESIGN.md is a plain-markdown design-system document an agent reads to generate visually consistent UI — one file, no Figma exports (format per BRIEF-awesome-design-md §1). It uses the YAML-frontmatter generation (token block + extended sections with `{token.refs}` in prose) — the richer model in the reference repo. The 9 Stitch sections and what each must state for ShettyXtreme:

| # | Section | Required content (Stitch spec) | ShettyXtreme specifics |
|---|---|---|---|
| 1 | Visual Theme & Atmosphere | Mood, density, design philosophy + 5-8 load-bearing "Key Characteristics" | Cockpit: near-black workstation canvas, density-first, calm chrome that recedes so data dominates; only price flashes and selected rows animate |
| 2 | Color Palette & Roles | Semantic name + hex + role, grouped: Brand/Accent, Surface, Text, Semantic, Focus | Canvas ladder (canvas / canvas-raised / card / elevated / overlay / hairline), text ladder (ink / body / muted / faint / on-accent), one scarce accent, **price semantics in the Indian convention (below)**, status colors never conflated with price |
| 3 | Typography Rules | Font families + full hierarchy table (Role/Size/Weight/Line Height/Tracking/Use) + principles | Mono/tabular face for **every number** (tabular-nums); number-xl/lg/md/sm roles; sans for labels/copy; tiny captions for column headers; weight-700 display only |
| 4 | Component Stylings | Buttons, cards, inputs, nav, badges, tables — each with color/radius/padding/typography token and states | Tables are the hero component (sticky header, right-aligned numeric columns, sort, row default/hover/selected/flash); chips (strike/expiry/lot), order-ticket modal, toast, custom thin scrollbar |
| 5 | Layout Principles | Spacing scale, base unit, grid widths, card padding, section rhythm, whitespace philosophy | 4px base with 2px steps; row-height tokens 24/28/32/36/40; desktop-first grid (watchlist/scanners/chain side by side); horizontal density over whitespace; min panel widths, resizable split panes |
| 6 | Depth & Elevation | Levels table (flat → modal) with treatment + use | Level 0-3: flat / hairline card / elevated card / modal overlay; **hairlines + surface contrast carry elevation — zero drop shadows**, no glassmorphism (VoltAgent/ClickHouse discipline) |
| 7 | Do's and Don'ts | 5-7 guardrails each, phrased as commands | Price colors text-only, never background fills; never repurpose price colors for success/error; mono numerals always; numbers never wrap; no decorative gradients/illustrations; accent scarcity; keep density |
| 8 | Responsive Behavior | Breakpoint table, touch targets, collapse strategy | Desktop-first; collapse to tabbed panes below ~1280px; tables become card lists on mobile; touch-target floor 40px with density tradeoff accepted |
| 9 | Agent Prompt Guide | Quick color reference (3-6 hexes with roles) + ready-to-use prompts | Quick ref (canvas, accent, price-up, price-down, selected-row) + prompts: "watchlist row", "scanner card", "option chain header + row", "risk panel gauge" |

## 2. Token decisions (binding for DESIGN.md)

- **Indian price-color convention — MANDATORY**: `price-up = RED` (rise), `price-down = GREEN` (fall), the inverse of Binance's international mapping (per BRIEF-awesome-design-md §5). Each price color has text, soft-bg, and strong variants; `flash-up` / `flash-down` transient row-flash backgrounds for ticks (~150ms fade).
- **Status is never price**: success / warning / danger / info are separate tokens and must not reuse price colors.
- **Every numeral in a tabular/mono face** — price, OI, volume, IV, P&L, percentage, time. Mixing is not optional.
- **Canvas ladder**: warm near-black canvas (Binance `#0b0e11` style — never pure black), 3-step surface ladder (ClickHouse), hairline elevation (VoltAgent `#3d3a39`-style hairlines on dark).
- **Single scarce accent** for the few moments that need attention: order buttons, active tab, connect status (VoltAgent green-as-center-of-gravity pattern; we choose our own accent).
- **India formatting**: INR with lakh/crore digit grouping; NSE/BSE symbol formats; lot size + expiry labels in the chain; market-hours status (closed / pre-open / continuous) as a status token, never a price color.
- Numbers right-aligned, letters left-aligned; price-flash only for live rows.

## 3. Terminal vision — the cockpit

A professional workstation: dark, dense, serious, single-screen. The layout is one cockpit, not a tab farm:

| Region | Content |
|---|---|
| Top bar | Session controls: mode switcher (OBSERVER default; LIVE requires explicit confirmation — per D10), health strip (feed, credential, 806 entitlement state), kill switch, market-hours status |
| Left rail | Watchlist (indices, stocks, futures groups), symbol search |
| Center | Scanner panels (gap, breakout, opportunity clusters) + market internals (NIFTY/BANKNIFTY, advance/decline, sector heatmap) |
| Right | Strategy-hints panel + option chain (strike, CE/PE, OI, IV, greeks) |
| Right drawer | Logs / alerts (min 320px, per DESIGN.md) |
| Bottom | Positions / risk strip (P&L, exposure, limits; min 240px tall) |

**Drill-down workflow**: watchlist row → quote detail → option chain → strategy hint → order ticket. Each step surfaces explainability (per [Section 14](14-data-decision-intelligence.md)): the hint shows the conviction score, disagreement indicator, participation, and **why each voter voted**; the EV line itemizes premium, slippage, spread, brokerage, STT, net EV; the order ticket shows the pre-trade risk summary (margin, loss limits, position caps) before approval.

**Command palette + F-key style navigation** (Fincept docking pattern, concept-level per BRIEF-fincept) keep dense screens navigable without tabs.

## 4. Svelte + Vite migration (per D9)

- FastAPI keeps the routers (watchlist, intelligence, execution, scanner, health, auth, postback, settings) and serves the **built Svelte SPA**; WebSocket stays the tick channel.
- The current static HTML dashboard/setup/settings pages are replaced component-by-component under DESIGN.md governance — every new component must match the token contract, so agent-generated and hand-written UI stay visually identical.
- UI churn never leaks into intelligence or core (layer F, per [Section 05](05-system-boundaries.md)).

## 5. Explicit non-goals

- **No charting-library dependency without need.** Phase 2 ships without a heavy charting dependency; candles start as lightweight canvas/SVG built on existing feature data. A third-party charting library enters only when requirements (crosshair sync, indicator overlays) prove it, justified in an ADR (dependency discipline per [Section 05](05-system-boundaries.md) external-deps table).
- **No multi-tab sprawl.** One cockpit with resizable panes, not a tab per feature. Features that don't fit the cockpit earn their place in the command palette instead of a new tab (per [Section 08](08-feature-map.md)).

Cross-references: [Section 08 — Feature Map](08-feature-map.md) (which features live in the cockpit, when), [Section 14 — Data & Decision Intelligence](14-data-decision-intelligence.md) (explainability surfaces the UI must render), [Section 05 — System Boundaries](05-system-boundaries.md) (terminal layer rules), [Section 17 — Delivery Roadmap](17-delivery-roadmap.md) (DESIGN.md authoring and Svelte migration in Phase 2).
