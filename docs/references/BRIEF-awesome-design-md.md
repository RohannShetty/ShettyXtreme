# BRIEF — awesome-design-md research (feeds our own DESIGN.md)

Source repo: `D:\ShettyXtreme\references\awesome-design-md` (shallow clone of VoltAgent/awesome-design-md, MIT).
Purpose: extract the DESIGN.md format spec, understand repo organization, and pick style references for
ShettyXtreme's own DESIGN.md — a dark, data-dense professional trading workstation for the Indian market
(watchlists, scanners, option chain, strategy hints, risk panel), authored in Google Stitch format.

---

## 1. The DESIGN.md format spec (the 9 sections)

DESIGN.md is a Google Stitch concept: a plain-text markdown design-system document an AI agent reads to
generate visually consistent UI. No Figma exports, no schemas — one markdown file. Per the repo README, every
file follows the Stitch DESIGN.md specification (`stitch.withgoogle.com/docs/design-md/specification/`) with
these 9 sections. What each must contain, per the README's table and observed files:

1. **Visual Theme & Atmosphere** — Mood, density, design philosophy. Observed files write 1–2 paragraphs
   describing the canvas, the brand's core contrast (e.g., "near-black canvas + single yellow accent"), the
   decorative system (gradients? none? hairlines?), then a bulleted "Key Characteristics" list of the 5–8
   load-bearing facts an agent must never violate.
2. **Color Palette & Roles** — Semantic name + hex + functional role, grouped: Brand & Accent (primary,
   active/pressed, disabled, on-primary), Surface (canvas, canvas-soft, card, elevated, hairline),
   Text (ink, body, body-strong, muted, faint, on-dark variants), Semantic (success/error/price-direction),
   Focus (focus-ring). Every color gets a stated role, never a bare hex.
3. **Typography Rules** — Font families (display / UI / mono, with open-source substitutes documented) and a
   full hierarchy table: Role | Size | Weight | Line Height | Letter Spacing | Use. Plus "Principles" —
   the couple of rules that define the voice (e.g., "display weight 700, never 400"; "every number in the
   mono/tabular face").
4. **Component Stylings** — Buttons (primary/secondary/ghost/outline/danger with default + active + disabled
   states), cards, inputs, nav, badges, tables — each with backgroundColor, textColor, radius, padding,
   typography token. States are separate entries, hover is deliberately not documented.
5. **Layout Principles** — Spacing scale tokens, base unit (4px or 8px), grid/container widths, card interior
   padding, section rhythm, and a Whitespace Philosophy (e.g., "denser than typical marketing sites — 80px
   section rhythm", "whitespace is the entire layout").
6. **Depth & Elevation** — A levels table (Level 0 flat → Level N modal), each with treatment + use. Trading/
   terminal-oriented files reject drop shadows: "hairlines + surface contrast carry elevation".
7. **Do's and Don'ts** — Guardrails and anti-patterns, usually 5–7 each, phrased as commands: "Reserve X for
   primary CTAs", "Never use price colors as background fills", "Don't introduce a second brand color",
   "Don't add atmospheric gradients".
8. **Responsive Behavior** — Breakpoint table (name | width | key changes), touch-target sizes, collapsing
   strategy (nav, grids, tables), image/mockup behavior.
9. **Agent Prompt Guide** — Quick color reference (3–6 hex values with roles) + ready-to-use example prompts
   ("Create hero: …").

Two format generations coexist in the repo (see section 2). The frontmatter generation adds a YAML token
block (colors / typography / rounded / spacing / components) above the markdown, plus extended sections:
Shapes (border-radius scale), Iteration Guide, Known Gaps. `{token.refs}` (e.g. `{colors.canvas}`) are used
throughout prose instead of raw values.

## 2. Repo organization

- `README.md` — the collection index: ~73–74 sites grouped by category (AI, Dev Tools, Backend/DB, Fintech,
  Retail, Media, Automotive, Retro), each with a one-line design summary. License MIT.
- `design-md/<site>/` — one directory per site. Each contains exactly two files in this clone:
  - `DESIGN.md` — the design system document.
  - `README.md` — a stub pointing to https://getdesign.md/<site>/design-md for previews and downloads.
- `preview.html` and `preview-dark.html` per site are documented in the README (visual catalog of swatches,
  type scale, buttons, cards — dark variant with dark surfaces) but are NOT present in this shallow clone
  (0 preview files found; they live on getdesign.md).
- `CONTRIBUTING.md` — quality rules for edits; `LICENSE` — MIT, "as is", tokens extracted from public CSS.
- Format generations: ~8 newer files use the literal 9 numbered Stitch sections (kraken, lovable, lamborghini,
  sanity, runwayml, mastercard, dell-1996, nintendo-2001). The rest (binance, sentry, warp, voltagent, ollama,
  clickhouse, posthog, revolut, coinbase, …) use YAML frontmatter + extended sections (Overview, Colors,
  Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts, Responsive Behavior,
  Iteration Guide, Known Gaps). The frontmatter style is richer and the better model for our file.
- Caveat: `kraken/DESIGN.md` is only 125 lines — a compact 9-section skeleton describing the light marketing
  site (white canvas, purple), NOT the data-dense dark dashboards the README advertises. Useful as a
  structural template, useless as a dark-density reference.

## 3. Candidate style references (3 picks + alternates)

Selection criteria: dark surface, data density, semantic rigor, terminal/data-native typography — NOT brand
or domain match.

**Pick 1 — Binance** (`design-md/binance/DESIGN.md`, 634 lines). The only true trading-domain file and the
single most transferable reference. Concrete attributes:
- Dark canvas `#0b0e11` (near-black, warm tint, never pure black) with flat color-block separation; elevation
  via surface ladder `#1e2329` / `#2b3139`, no drop shadows, no glassmorphism.
- Dedicated trading semantics: `trading-up #0ecb81` (green) and `trading-down #f6465d` (red), with an explicit
  rule — text color only, never button/card backgrounds; and a separate rule that trading colors are never
  repurposed for generic success/error.
- Numeric typography as first-class tokens: `number-display` (40px/700), `number-md` (16px/500), `number-sm`
  (14px/500), always in a tabular face (BinancePlex): "Mixing them is not optional… every number in
  BinancePlex" — directly maps to our monospace-numeric requirement.
- Markets table anatomy: 5-column header, 8/4 main-panel + side-rail layout, ~1440px max width on product
  surfaces, 6–12px radius hierarchy, weight-700 display ("going to 400 reads as design-portfolio, not trading
  platform"), 80px section rhythm because "product pages need denser layouts".
- Do's/Don'ts nearly verbatim reusable: don't add atmospheric gradients, don't introduce a second brand color,
  don't use price colors as backgrounds, don't soften display weight.
- Caveat (stated in its own Known Gaps): it documents marketing surfaces; order book / candlestick chart /
  position cards were NOT extracted. Its light "transactional mode" is not relevant to us.

**Pick 2 — VoltAgent** (`design-md/voltagent/DESIGN.md`, 521 lines). The terminal-native dark chrome model.
Concrete attributes:
- Dark-only system: canvas `#101010` is the only surface, "no light-mode counterpart" — matches a cockpit
  that never leaves dark.
- Single electric-green accent `#00d992` reserved for CTAs, status pills, live indicators; Do's: "The green
  is the brand's centre of gravity", Don't: "use primary as body-text fill".
- Elevation entirely by 1px hairline borders (`#3d3a39`) + an explicit 4-level ladder (flat / hairline /
  inset glow / modal stack); "Hairlines on dark IS the brand's elevation system" — the exact elevation
  philosophy a dense terminal needs.
- SF Mono reserved for code AND "metric counters" — "every metric is rendered in a numeric monospace".
- Tight geometry: 6px buttons, 8px cards, pill only for status tags; uppercase eyebrows with 2.52px tracking;
  Inter + mono pairing with documented open-source substitutes.

**Pick 3 — ClickHouse** (`design-md/clickhouse/DESIGN.md`, 544 lines). The data-density + high-contrast
single-accent model. Concrete attributes:
- Near-pure black canvas `#0a0a0a` with a 3-step surface ladder: `#121212` (soft) / `#1a1a1a` (card) /
  `#242424` (elevated) — "cards barely lighter than canvas — color-block contrast is subtle" — exactly the
  layered surface system an option-chain panel needs.
- One electric accent (yellow `#faff69`) doing all brand voltage, with active/disabled variants; black text
  on accent ("the high-contrast accent+black combo is the brand action signal").
- JetBrains Mono for code/terminal surfaces; stat numbers as huge mono/sans-700 moments; semantic emerald
  `#22c55e` / rose `#ef4444` tokens; hierarchical radius (8px buttons, 12px cards, pill only for tags);
  no light-mode marketing surface.

Alternates (rejected or bench): Warp — warm-dark hairline elevation and DM Mono pairing are excellent, but
its single off-white accent and absence of any semantic palette make it a chrome reference only; Sentry —
dark dashboard with dense-table polarity and "developer console" uppercase cadence, but violet/lime brand
palette and sticker-mascot decoration are not transferable; Coinbase — has `semantic-up #05b169` /
`semantic-down #cf202f` tokens and a CoinbaseMono tabular face, but surfaces are mostly white and display
weight is deliberately 400 (institutional calm, not trading urgency); Revolut — true-black storytelling
canvas but 136px display type and pill buttons, consumer-marketing scale; Kraken — 9-section skeleton only
(light stub). Ollama, PostHog, Stripe: light/playful — see section 4.

## 4. What NOT to copy, and how to map the format

What NOT to copy:
- Marketing-style light themes: Ollama (flat white, no semantic palette), Stripe (white canvas, weight-300
  elegance), Coinbase's white editorial rhythm.
- Playful palettes: PostHog (warm cream `#eeefe9` canvas, hedgehog mascots, pastel callout bands — its dark
  surface exists only as code blocks), Sentry's sticker mascots/starfield.
- Scale that fights density: Revolut's 136px hero displays; Ollama's 88px section air; pill-everywhere
  geometry (Coinbase, Revolut).
- Binance's light transactional mode and its yellow brand voltage (we pick our own accent); Binance's yellow
  gradient hero backdrop (single-page launch treatment, explicitly not system-wide).
- Decorative systems in general: no gradient meshes, no aurora backdrops, no illustration suites — the
  strongest dark references (Binance, VoltAgent, ClickHouse) all reject these.

Mapping the format to a trading-terminal design language:
- Visual Theme & Atmosphere: describe a cockpit — near-black workstation canvas, density-first, calm chrome
  that recedes so data dominates; only price flashes and selected rows animate.
- Color Palette & Roles: replace marketing semantics with trading semantics (see token list); accent kept
  scarce for the few moments that need attention (order buttons, active tab, connect status).
- Typography Rules: mono/tabular numerals for every number, sans for labels and copy, tiny captions for
  column headers; numbers right-aligned, letters left-aligned.
- Component Stylings: tables are the hero component (row states: default/hover/selected/flash); panels,
  split panes, tabs, chips (strike, expiry, lot size), order-ticket modal, scanner cards.
- Layout Principles: 4px base with 2px steps for dense rows; fixed row-height tokens; desktop-first grid
  (watchlists/scanners/chain side by side); horizontal density over whitespace.
- Depth & Elevation: hairline + surface-ladder elevation, zero drop shadows, thin custom scrollbars, subtle
  focus rings.
- Do's/Don'ts: price colors are text-only; never reuse price colors for success/error; mono numerals always;
  no decorative gradients; red/green mapping is the Indian convention (see section 5); numbers never wrap.
- Responsive Behavior: desktop-first; collapse to tabbed panes below ~1280px; tables become card lists on
  mobile; touch-target floor 40px with density tradeoff accepted.
- Agent Prompt Guide: quick hex reference + prompts like "render an option chain row with price, OI change,
  IV, and flash on tick".

## 5. Tokens a trading DESIGN.md must define

Colors:
- Canvas ladder: canvas, canvas-raised, surface-card, surface-elevated, surface-overlay (modals), hairline,
  hairline-strong (borders on dark).
- Text ladder: ink, body, muted, faint, on-accent, on-dark-muted.
- Accent: accent + accent-active + accent-disabled + on-accent (single brand accent, scarce use).
- Price semantics (Indian convention — MANDATORY, opposite of Binance's international mapping):
  price-up = RED (rise), price-down = GREEN (fall); each with text, soft-bg, and strong variants;
  flash-up / flash-down transient row-flash backgrounds for ticks.
- Status (never conflated with price): success, warning, danger, info, focus-ring.
- Selection: row-selected, row-hover; bid/ask tint for order-book columns; chart palette: candle-up,
  candle-down, volume, grid-line, crosshair, watermark.

Typography:
- Numeric roles in a tabular/monospace face with `font-variant-numeric: tabular-nums`: number-xl (LTP hero),
  number-lg (panel stats), number-md (table cells), number-sm (captions, % changes), ticker.
- Text roles: display, heading, body, caption, micro, eyebrow (uppercase), column-header, button label.
- Explicit rule: every numeral — price, OI, volume, IV, P&L, percentage, time — uses the numeric face;
  no exceptions.

Layout:
- Spacing scale: 4px base, 2px micro-steps; section rhythm 48–80px (tighter than marketing).
- Row-height tokens: 24 / 28 / 32 / 36 / 40px (dense → comfortable); column-density classes.
- Grid: desktop-first breakpoints (~1280 collapse, ~768 single-pane), min panel widths for watchlist/scanner/
  chain/risk, resizable split-pane widths.

Components (each with states): primary/ghost/outline/danger buttons (compact + default), symbol-search input,
table (sticky header, right-aligned numeric columns, sort indicators, row hover/selected/flash), panel card,
tab bar, chip (expiry/strike/lot), toast (fill/order notifications), order-ticket modal, dropdown, tooltip,
custom thin scrollbar.

Depth & interaction: elevation levels 0–3 (flat / hairline card / elevated card / modal overlay); focus
rings; transition timings for price flash (~150ms fade); scroll behavior.

India-specific: red=rise / green=fall mapping; INR formatting with Indian digit grouping (lakh/crore);
NSE/BSE symbol formats; lot size + expiry labels in the chain; market-hours status indicator (closed/
pre-open/continuous) as a semantic status, not a price color.

Do's/Don'ts must encode: price colors text-only; never repurpose price colors; mono numerals everywhere;
numbers right-aligned; no decorative illustration/gradient systems; accent scarcity; keep density — no
whitespace-driven marketing layouts.

Agent Prompt Guide: quick color reference (canvas, accent, price-up, price-down, selected-row) + 3–4 example
prompts ("watchlist row", "scanner card", "option chain header + row", "risk panel gauge").

---

Bottom line: model our DESIGN.md on the frontmatter-generation files (YAML tokens + extended sections,
`{token.refs}` in prose), take Binance's trading semantics and numeric typography, VoltAgent's hairline
dark-chrome discipline, and ClickHouse's surface ladder + single-accent voltage — then invert Binance's
green/red mapping to the Indian convention and replace all brand colors with our own.
