---
project: ShettyXtreme
type: design-contract
governs: terminal UI (Svelte + Vite, D9)
status: binding
themes:
  default: dark
  light: opt-in (operator chooses; never the default)
colors:
  canvas: "#0a0a0a"
  canvas-raised: "#141414"
  surface-card: "#1a1a1a"
  surface-elevated: "#262626"
  surface-overlay: "#333333"
  hairline: "#333333"
  hairline-strong: "#404040"
  ink: "#fafafa"
  body: "#d4d4d4"
  muted: "#737373"
  faint: "#525252"
  accent: "#f5b942"
  accent-active: "#ffce6b"
  accent-disabled: "#5c4712"
  on-accent: "#1a1405"
  price-up: "#f6525c"
  price-up-strong: "#ff7a82"
  price-up-soft: "rgba(246,82,92,0.12)"
  price-down: "#2ebd85"
  price-down-strong: "#3fd9a0"
  price-down-soft: "rgba(46,189,133,0.12)"
  flash-up: "rgba(246,82,92,0.16)"
  flash-down: "rgba(46,189,133,0.16)"
  success: "#22c55e"
  warning: "#ffb020"
  danger: "#e5484d"
  info: "#3b82f6"
  focus-ring: "#f5b942"
  row-hover: "#1f1f1f"
  row-selected: "#2a2a2a"
  scrim: "rgba(0,0,0,0.6)"
  candle-up: "#f6525c"
  candle-down: "#2ebd85"
  volume: "#333333"
  grid-line: "#1f1f1f"
  crosshair: "#737373"
  watermark: "#333333"
light:
  canvas: "#ffffff"
  canvas-raised: "#fafafa"
  surface-card: "#f5f5f5"
  surface-elevated: "#e5e5e5"
  surface-overlay: "#f5f5f5"
  hairline: "#e5e5e5"
  hairline-strong: "#d4d4d4"
  ink: "#0a0a0a"
  body: "#404040"
  muted: "#737373"
  faint: "#a3a3a3"
  accent: "#d97706"
  accent-active: "#b45309"
  accent-disabled: "#fde68a"
  on-accent: "#ffffff"
  price-up: "#f6525c"
  price-up-strong: "#f6525c"
  price-up-soft: "rgba(246,82,92,0.12)"
  price-down: "#1e9e6b"
  price-down-strong: "#2ebd85"
  price-down-soft: "rgba(30,158,107,0.12)"
  flash-up: "rgba(246,82,92,0.16)"
  flash-down: "rgba(30,158,107,0.16)"
  success: "#15803d"
  warning: "#92400e"
  danger: "#c62828"
  info: "#1e40af"
  focus-ring: "#d97706"
  row-hover: "#f5f5f5"
  row-selected: "#fef3c7"
  scrim: "rgba(0,0,0,0.4)"
  candle-up: "#f6525c"
  candle-down: "#1e9e6b"
  volume: "#d4d4d4"
  grid-line: "#e5e5e5"
  crosshair: "#737373"
  watermark: "#e5e5e5"
typography:
  sans: "Inter, system-ui, sans-serif"
  mono: "JetBrains Mono, IBM Plex Mono, ui-monospace, monospace"
  base-size: "13px"
  base-line-height: "20px"
spacing:
  base: "4px"
  micro-step: "2px"
rounded:
  control: "4px"
  panel: "6px"
  badge: "2px"
---

# ShettyXtreme DESIGN.md

Design contract for the ShettyXtreme terminal — a dark, data-dense, operator-grade trading workstation for the Indian market (NSE/BSE index options first, equities as terminal breadth). This file is binding for every agent that builds or modifies terminal UI (D4, D9). Modeled on the Stitch DESIGN.md specification; style references: Binance (trading semantics), VoltAgent (hairline dark-chrome), ClickHouse (surface ladder + single-accent voltage). Tone: Bloomberg-terminal discipline, precision, calm under pressure. NOT a marketing surface.

## 1. Visual Theme & Atmosphere

A pure black canvas `{colors.canvas}` carrying dense instrument panels. The chrome (borders, titles, tabs, scrollbars) recedes so the data dominates; the only animated elements are price flashes on tick, the pulsing LIVE indicator, and the selected row's accent edge. Everything reads as calibrated equipment — zero playfulness, zero decoration.

**Key Characteristics (never violate):**
- Pure black canvas `{colors.canvas}` (`#0a0a0a`) carrying dense instrument panels; clean monochrome with warm amber accent. Dark is the default and the operator norm; a pure white light theme exists as an opt-in companion (see §2.1 Themes Contract).
- High information density with a fixed 4px grid — density is the product.
- Elevation is carried exclusively by hairline borders and surface steps; no drop shadows, no glassmorphism, no gradients.
- One accent color (warm amber) for the few moments that need attention (interactive, live, selected); every other hue is semantic.
- Price color convention is configurable via `data-convention` on `<html>`. **International (green = rise, red = fall) is the default**; Indian (red = rise, green = fall) is the legacy opt-in. The operator toggles in Settings; the choice persists (`sx-convention` in `localStorage`) and applies before first paint.
- Every numeral renders in the mono face with tabular figures; labels and chrome render in the sans face.
- Status colors never appear in price columns; price colors never appear in status badges.

## 2. Color Palette & Roles

### 2.1 Themes Contract

The terminal ships **two themes**:

- **Dark (default, operator norm)** — the pure black palette in §2.2. `data-theme="dark"` on `<html>`. This is what the operator runs in; light is never the default, and `--mode OBSERVER`-style behavior is theme-independent.
- **Light (opt-in)** — the pure white palette in §2.3. The operator may switch via the header toggle; the choice persists (`sx-theme` in `localStorage`) and applies before first paint.
- Both themes pass **WCAG AA for text** (contrast ≥ 4.5:1 for body text; the price tokens are the single documented exception — see below).
- **Convention is configurable; international (green = rise, red = fall) is the default in both themes.** Indian (red = rise, green = fall) remains the legacy opt-in. The price tokens `{colors.price-up}` / `{colors.price-down}` swap values per convention; in light theme the "down" hue may darken to `#1e9e6b` for AA (the up hue `#f6525c` is the one accepted sub-AA text usage at ~3.5:1 on paper, used in 600-weight data numerals only).
- Theme selection changes tokens only — never layout, density, typography, or component structure.

### 2.2 Token reference — dark (pure black + warm amber)

| Token | Hex | Role |
|---|---|---|
| `{colors.canvas}` | `#0a0a0a` | App background. The only full-screen surface. |
| `{colors.canvas-raised}` | `#141414` | Header bars, tab strips, status strips sitting on canvas. |
| `{colors.surface-card}` | `#1a1a1a` | Panels, cards, tables, dialogs' body background. |
| `{colors.surface-elevated}` | `#262626` | Hovered panels, dropdowns, tooltips, floating summary strips. |
| `{colors.surface-overlay}` | `#333333` | Modals, drawers, command palette. Always under `{colors.scrim}`. |
| `{colors.hairline}` | `#333333` | 1px borders between panels and on canvas. Default border. |
| `{colors.hairline-strong}` | `#404040` | Borders of interactive/active elements, table header underline, divider inside cards. |
| `{colors.ink}` | `#fafafa` | Primary text — LTP hero, panel titles, values of consequence. |
| `{colors.body}` | `#d4d4d4` | Regular text, table cell text. |
| `{colors.muted}` | `#737373` | Secondary labels, non-numeric captions, icon strokes. |
| `{colors.faint}` | `#525252` | Placeholders, empty states, disabled text, timestamps. |
| `{colors.accent}` | `#f5b942` | THE single accent — warm amber. Live indicators, active tab, selected controls, links, focus. |
| `{colors.accent-active}` | `#ffce6b` | Accent hover / pressed glow (brightens on dark). |
| `{colors.accent-disabled}` | `#5c4712` | Accent controls in disabled state. |
| `{colors.on-accent}` | `#1a1405` | Text on accent fills (inverse-contrast). |
| `{colors.price-up}` | Indian: `#f6525c`, Intl: `#2ebd85` | **Price rose.** All rising-market values: LTP up, up-change, bid-ask up side, candles. Hex swaps per convention. |
| `{colors.price-up-strong}` | Indian: `#ff7a82`, Intl: `#3fd9a0` | Brighter up color for LTP flash text, candle bodies. |
| `{colors.price-up-soft}` | Indian: `rgba(246,82,92,0.12)`, Intl: `rgba(46,189,133,0.12)` | Up-side column tint, soft up backgrounds (never text). |
| `{colors.price-down}` | Indian: `#2ebd85`, Intl: `#f6525c` | **Price fell.** All falling-market values: LTP down, down-change, candles. Hex swaps per convention. |
| `{colors.price-down-strong}` | Indian: `#3fd9a0`, Intl: `#ff7a82` | Brighter down color for LTP flash text, candle bodies. |
| `{colors.price-down-soft}` | Indian: `rgba(46,189,133,0.12)`, Intl: `rgba(246,82,92,0.12)` | Down-side column tint, soft down backgrounds (never text). |
| `{colors.flash-up}` | Indian: `rgba(246,82,92,0.16)`, Intl: `rgba(46,189,133,0.16)` | Transient row-flash background when a value ticks up; fades to transparent over 150ms. |
| `{colors.flash-down}` | Indian: `rgba(46,189,133,0.16)`, Intl: `rgba(246,82,92,0.16)` | Transient row-flash background when a value ticks down. |
| `{colors.success}` | `#22c55e` | Status-only success: connected, synced, order accepted, strategy validated. Emerald — NOT `{colors.price-down}`. |
| `{colors.warning}` | `#ffb020` | Stale data, margin near limit, OI spike, regime change alert, unsaved config. |
| `{colors.danger}` | `#e5484d` | Risk states: margin breach, feed disconnect, order rejection, kill-switch armed, session error. Crimson — NOT `{colors.price-up}`. |
| `{colors.info}` | `#3b82f6` | System/operator info: background sync, scheduled task, informational toast. |
| `{colors.focus-ring}` | `#f5b942` | Keyboard focus ring. 2px, offset 2px, only on `:focus-visible`. |
| `{colors.row-hover}` | `#211d17` | Table row hover background. |
| `{colors.row-selected}` | `#2b2210` | Selected row background; combined with a 2px `{colors.accent}` left edge inset. |
| `{colors.scrim}` | `rgba(0,0,0,0.6)` | Modal/drawer overlay scrim. |
| `{colors.candle-up}` | Indian: `#f6525c`, Intl: `#2ebd85` | Bull candle. |
| `{colors.candle-down}` | Indian: `#2ebd85`, Intl: `#f6525c` | Bear candle. |
| `{colors.volume}` | `#3b362c` | Volume bars (neutral); tinted `{colors.candle-*}` per bar direction. |
| `{colors.grid-line}` | `#211d17` | Chart grid lines. |
| `{colors.crosshair}` | `#948b7c` | Chart crosshair. |
| `{colors.watermark}` | `#26221c` | Chart watermark / background annotations. |

### 2.3 Token reference — light (pure white)

Same roles as §2.2 — only the hex differs. Convention is configurable; international (green = rise, red = fall) is the default. In light theme the "down" hue may darken to `#1e9e6b` for AA.

| Token | Hex | Role |
|---|---|---|
| `{colors.canvas}` | `#ffffff` | App background. Pure white. |
| `{colors.canvas-raised}` | `#fafafa` | Header bars, tab strips, status strips. |
| `{colors.surface-card}` | `#f5f5f5` | Panels, cards, tables, dialogs' body background. |
| `{colors.surface-elevated}` | `#e5e5e5` | Hovered panels, dropdowns, tooltips, floating strips. |
| `{colors.surface-overlay}` | `#f5f5f5` | Modals, drawers, command palette. Under `{colors.scrim}`. |
| `{colors.hairline}` | `#e5e5e5` | 1px borders. Default border. |
| `{colors.hairline-strong}` | `#d4d4d4` | Borders of interactive/active elements, dividers. |
| `{colors.ink}` | `#0a0a0a` | Primary text. |
| `{colors.body}` | `#404040` | Regular text, table cell text. |
| `{colors.muted}` | `#737373` | Secondary labels, captions, icon strokes. |
| `{colors.faint}` | `#a3a3a3` | Placeholders, empty states, disabled text, timestamps. |
| `{colors.accent}` | `#d97706` | The single accent — dark amber (AA on white). |
| `{colors.accent-active}` | `#b45309` | Accent hover / pressed (darkens on light). |
| `{colors.accent-disabled}` | `#fde68a` | Accent controls in disabled state. |
| `{colors.on-accent}` | `#ffffff` | Text on accent fills. |
| `{colors.price-up}` | Indian: `#f6525c`, Intl: `#1e9e6b` | **Price rose.** Hex swaps per convention. |
| `{colors.price-up-strong}` | Indian: `#f6525c`, Intl: `#2ebd85` | LTP flash / candle body tone. |
| `{colors.price-up-soft}` | Indian: `rgba(246,82,92,0.12)`, Intl: `rgba(30,158,107,0.12)` | Up-side column tint, soft up backgrounds. |
| `{colors.price-down}` | Indian: `#1e9e6b`, Intl: `#f6525c` | **Price fell.** Hex swaps per convention. |
| `{colors.price-down-strong}` | Indian: `#2ebd85`, Intl: `#f6525c` | LTP flash / candle body tone. |
| `{colors.price-down-soft}` | Indian: `rgba(30,158,107,0.12)`, Intl: `rgba(246,82,92,0.12)` | Down-side column tint, soft down backgrounds. |
| `{colors.flash-up}` | Indian: `rgba(246,82,92,0.16)`, Intl: `rgba(30,158,107,0.16)` | Transient row-flash on tick up; 150ms fade. |
| `{colors.flash-down}` | Indian: `rgba(30,158,107,0.16)`, Intl: `rgba(246,82,92,0.16)` | Transient row-flash on tick down. |
| `{colors.success}` | `#15803d` | Status-only success (darkened for AA on paper). |
| `{colors.warning}` | `#92400e` | Stale data, margin near limit, OI spike, alerts. |
| `{colors.danger}` | `#c62828` | Risk states (darkened for AA on paper). |
| `{colors.info}` | `#1e40af` | System/operator info (darkened for AA on paper). |
| `{colors.focus-ring}` | `#a16207` | Keyboard focus ring. 2px, offset 2px, `:focus-visible` only. |
| `{colors.row-hover}` | `#f1eee8` | Table row hover background. |
| `{colors.row-selected}` | `#f4e9cf` | Selected row background + 2px accent left edge. |
| `{colors.scrim}` | `rgba(23,20,14,0.4)` | Modal/drawer overlay scrim (lighter than dark). |
| `{colors.candle-up}` | `#f6525c` | Bull candle (Indian convention). |
| `{colors.candle-down}` | `#1e9e6b` | Bear candle. |
| `{colors.volume}` | `#d6d0c4` | Volume bars (neutral). |
| `{colors.grid-line}` | `#e6e2d8` | Chart grid lines. |
| `{colors.crosshair}` | `#6f6a60` | Chart crosshair. |
| `{colors.watermark}` | `#e0dcd2` | Chart watermark / background annotations. |

### 2.4 Palette rules

- **Price semantics — Indian convention (binding, both themes):** `price-up` is red `#f6525c`, `price-down` is green `#2ebd85` (light: `#1e9e6b`). This is the NSE/BSE terminal convention and inverts Binance-style international mapping. Agents must treat "red = rise" as a law, not a suggestion. **Red = rise, green = fall in BOTH themes. Never invert.**
- Price tokens are **text and data-viz colors only**: never button fills, never card backgrounds, never badge backgrounds. The only permitted background usages are the `*-soft` tints and `flash-*` transient tick flashes.
- Price colors are never repurposed for success/error; status colors are never used to render a price.
- `{colors.accent}` is the single brand accent (warm amber in dark, dark amber in light). Do not introduce a second accent (no purple, no magenta). Reserve accent for: active tab, live indicator, selected row edge, primary CTA, focus ring, links.
- `{colors.success}` is emerald, `{colors.price-down}` is green — deliberately adjacent hues. They must never be confused: success appears only in labeled status chips ("SYNCED", "ACCEPTED"); price appears only in numeric/data columns.
- Market-hours status (closed / pre-open / continuous / halt) is a *semantic status* rendered with status tokens + text label — never with price tokens.
- Depth (order book) bid/ask columns use `{colors.price-down}` / `{colors.price-up}` for the best-bid/best-ask values (they are market data), with `*-soft` column tints for the quantity bars.

## 3. Typography Rules

**Faces:** Sans = Inter (`Inter, system-ui, sans-serif`) for labels, navigation, headings, buttons. Mono = JetBrains Mono (`JetBrains Mono, IBM Plex Mono, ui-monospace, monospace`) for every numeral, ticker, code, terminal/log text. JetBrains Mono has native tabular figures; enforce `font-variant-numeric: tabular-nums` on all numeric roles regardless.

**Principle: every number — price, LTP, change, OI, volume, IV, PCR, P&L, percentage, lot size, expiry, time — renders in the mono face. No exceptions.** A numeral in the sans face is a contract violation.

### 3.1 Hierarchy table

| Role | Face | Size | Weight | Line height | Letter spacing | Use |
|---|---|---|---|---|---|---|
| `number-xl` | mono | 28px | 700 | 32px | -0.01em | LTP hero (selected symbol header). |
| `number-lg` | mono | 20px | 600 | 24px | 0 | Panel headline stats (P&L, total OI, IV index). |
| `number-md` | mono | 13px | 500 | 20px | 0 | Table cell numerics, scanner rows. |
| `number-sm` | mono | 11px | 500 | 16px | 0 | % changes, deltas, tiny captions under values. |
| `ticker` | mono | 12px | 500 | 16px | 0.02em | Scrolling ticker strip, symbols, strike labels. |
| `display` | sans | 24px | 700 | 28px | -0.02em | Reserved: kill-switch confirm dialog, full-screen status moments. Weight 700 only. |
| `heading` | sans | 14px | 600 | 20px | 0 | Section headings inside panels. |
| `panel-title` | sans | 13px | 600 | 20px | 0 | Panel header titles. |
| `body` | sans | 13px | 400 | 20px | 0 | Default text, card body copy. |
| `caption` | sans | 12px | 400 | 16px | 0 | Secondary labels, helper text. |
| `micro` | sans | 11px | 400 | 14px | 0 | Timestamps, meta, footnotes. |
| `eyebrow` | sans | 11px | 600 | 14px | 0.14em uppercase | Section eyebrows, panel group labels. |
| `column-header` | sans | 11px | 500 | 14px | 0.08em uppercase | Table column headers. |
| `button-label` | sans | 13px | 600 | 16px | 0.02em | Button labels. Never all-caps except kill switch. |

### 3.2 Rules

- Display weight never drops below 600 — 400 display reads as a design portfolio, not a trading platform.
- Numbers never wrap, never truncate mid-digit, never use proportional numerals; use `white-space: nowrap` on numeric cells.
- Price flash toggles color weight, never font weight or size (no jitter).
- Column headers are uppercase micro-type; cell text is sentence case.
- Keyboard focus is always visible (2px `{colors.focus-ring}` ring).

## 4. Component Stylings

All radii: controls 4px, panels 6px, badges 2px (never pills except status chips). Hover states documented per component; transitions ≤ 120ms (except price flash 150ms fade).

**Component contract (P5a):** components are built from **shadcn-style primitives** (`$lib/components/ui/*`, Tailwind v4 + bits-ui + cva) on top of the design tokens in §2. Every primitive documents its four interaction states — **default / hover / active / disabled**, plus a 2px `{colors.focus-ring}` **focus-ring** state on `:focus-visible` — using the exact token roles in the table below. Primitives map to tokens via the shadcn alias layer (`primary` → `{colors.accent}`, `background` → `{colors.canvas}`, `card` → `{colors.surface-card}`, `border` → `{colors.hairline}`, `ring` → `{colors.focus-ring}`, etc.); the mapping lives in `src/lib/app.css` and never hard-codes hex. The drop-shadow ban (§6) applies to primitives with full force; one known violation — the LogDrawer's `box-shadow` — is tracked and fixed in the component-migration task.

| Component | Default | Hover | Active / Selected | Disabled |
|---|---|---|---|---|
| **Button primary** | bg `{colors.accent}`, text `{colors.on-accent}`, 4px radius, 8px×24px padding, `button-label` | bg `{colors.accent-active}` | bg `{colors.accent-active}`, 1px inset `{colors.accent}` | bg `{colors.accent-disabled}`, text `{colors.faint}`, no shadow, cursor default |
| **Button secondary** | bg `{colors.surface-elevated}`, border 1px `{colors.hairline-strong}`, text `{colors.body}` | border `{colors.muted}`, text `{colors.ink}` | bg `{colors.row-hover}` | text `{colors.faint}`, border `{colors.hairline}` |
| **Button ghost** | transparent, text `{colors.body}` | text `{colors.ink}`, bg `{colors.row-hover}` | text `{colors.accent}` | text `{colors.faint}` |
| **Button danger** | bg `{colors.danger}`, text `#fff` | bg `#ff5f64` | darker inset | bg `#7a2a2e`, text `#ffb9bb` |
| **Kill switch** | Always rendered in the header status strip: bg `{colors.danger}`, text `#fff`, `button-label` 13px/700, min-height 36px, left-edge position, shortcut `Ctrl+Shift+K` | bg `#ff5f64` | armed state: pulsing 1s stroke, bg `#c2262b` | Never disabled. Ever. |
| **Input / search** | bg `{colors.canvas-raised}`, border 1px `{colors.hairline}`, text `{colors.ink}`, padding 6px×10px, radius 4px | border `{colors.muted}` | border `{colors.accent}`, focus ring 2px | bg `{colors.canvas}`, text `{colors.faint}` |
| **Panel / card** | bg `{colors.surface-card}`, border 1px `{colors.hairline}`, radius 6px; header: `panel-title` + eyebrow above | border `{colors.hairline-strong}` (only for docked/floating panels) | — | — |
| **Table / data grid** | header: `{colors.canvas-raised}` bg, `column-header` text `{colors.muted}`, sticky, bottom border `{colors.hairline-strong}`; rows 28px high, 8px horizontal cell padding, borders `{colors.hairline}` only between grouped rows | row bg `{colors.row-hover}` | row bg `{colors.row-selected}` + 2px accent left edge | cell text `{colors.faint}` |
| **Tabs** | 32px high, text `{colors.muted}`, 2px bottom border `{colors.hairline}` | text `{colors.body}` | text `{colors.ink}`, border `{colors.accent}` | text `{colors.faint}` |
| **Badge — regime** | bg `{colors.surface-elevated}`, border `{colors.hairline}`, mono 11px `number-sm`, uppercase label (e.g. TREND, RANGE, VOL-EXPAND) | — | — | — |
| **Badge — conviction** | 4 levels: LOW `{colors.muted}` text / MEDIUM `{colors.warning}` text / HIGH `{colors.accent}` text / EXTREME `{colors.ink}` text on `{colors.row-selected}` bg. Mono, `number-sm`. | — | — | — |
| **Status chip** | 16px high, radius 999px, 6px×10px padding, `micro` uppercase + 6px dot; colors per status token (`success`/`warning`/`danger`/`info`) | — | — | — |
| **Mode indicator** | Header status strip right side: OBSERVER = `{colors.faint}` dot + label; LIVE = pulsing `{colors.accent}` dot (1s blink) + label; plus session banner when LIVE | — | — | — |
| **Toast** | bg `{colors.surface-overlay}`, border 1px `{colors.hairline-strong}`, radius 6px, `body` text, 4px left edge in status token; auto-dismiss except danger toasts (dismiss-only) | — | — | — |
| **Alert bar** | 36px, full panel width, bg = status token at 10% on `{colors.surface-card}`, border-bottom `{colors.hairline-strong}`, leading dot + `body` text + dismiss (except danger) | — | — | — |
| **Chip (strike/expiry/lot)** | bg `{colors.canvas-raised}`, border `{colors.hairline}`, mono `ticker` 12px, 4px×10px | border `{colors.muted}` | bg `{colors.row-selected}`, border `{colors.accent}`, text `{colors.accent}` | — |
| **Dropdown / select** | styled like input; menu on `{colors.surface-elevated}`, 1px `{colors.hairline}` border, row hover `{colors.row-hover}`, item padding 8px×10px | — | — | — |
| **Tooltip** | bg `{colors.surface-overlay}`, border `{colors.hairline}`, `caption` 12px, delay 400ms | — | — | — |
| **Split-pane divider** | 1px `{colors.hairline}` with 8px transparent drag hit area; drag ghost = `{colors.accent}` 1px line | — | — | — |
| **Scrollbar** | 10px track transparent, thumb `{colors.hairline-strong}` radius 5px | thumb `{colors.muted}` | — | — |
| **Modal / dialog** | bg `{colors.surface-overlay}`, border `{colors.hairline-strong}`, radius 6px, scrim `{colors.scrim}`; order-confirm dialog shows margin/risk summary block in mono before placement | — | — | — |
| **Toggle / switch** | off: track `{colors.hairline-strong}`, knob `{colors.muted}`; on: track `{colors.accent}`, knob `#fff` | — | — | — |

**Table alignment rules (binding):** all numeric columns right-aligned, all text columns left-aligned; row height 28px (dense) default, 24px in chain grids, never below 22px; sticky header always; sort indicators as 11px `{colors.muted}` arrows; staleness marker = `{colors.warning}` `micro` "STALE" chip in the cell corner (or `{colors.faint}` timestamp); LTP columns flash `{colors.flash-up}` / `{colors.flash-down}` on tick with 150ms fade to row bg.

## 5. Layout Principles

**Spacing scale (4px base, 2px micro-steps):** `space-0` 2px, `space-1` 4px, `space-2` 8px, `space-3` 12px, `space-4` 16px, `space-5` 24px, `space-6` 32px, `space-7` 48px. Use only these values for all padding/margin/gaps.

**Grid:** desktop-first 12-column fluid grid, max width 1920px; 8px gutters; panels span columns in multiples of 2 (watchlist 2, scanner 3, chain 6+). Never a centered narrow column — the terminal fills the viewport.

**Cockpit panel taxonomy (Section 15 — binding names):** watchlist (left rail, min 260px), scanner panels (min 320px each), market internals (breadth panel), option chain grid (min 720px), strategy-hints panel (min 320px), positions/risk strip (bottom, min 240px tall), logs/alerts drawer (right, min 320px), session controls (header strip). All panels dockable/resizable via split-pane dividers; state persists across sessions.

**Row-height tokens:** 24 / 28 / 32 / 36 / 40px (chain grid → dense tables → default rows → comfortable lists → touch rows). Column density classes: `dense` (8px padding), `default` (12px), `comfortable` (16px).

**Whitespace philosophy:** tight in data, generous in chrome. Data surfaces (tables, chain, scanners, ticker) pack to the 4px grid with 8px cell padding and 2px micro-steps — never airy. Chrome (headers, status strips, modals, empty states) uses `space-4`/`space-5` rhythm. Section rhythm inside panels: 16px.

**Header strip (top, 44px):** logo/session, active symbol + `number-xl` LTP cluster, kill switch (left), tabs (center), mode indicator + market-hours status (right).

## 6. Depth & Elevation

Flat color-block elevation only. No drop shadows, no blur, no glassmorphism, no gradients anywhere. (Re-affirmed under the P5a component contract: shadcn primitives inherit this ban; the pre-existing `box-shadow` on the LogDrawer is a known violation fixed in the component-migration task.)

| Level | Treatment | Use |
|---|---|---|
| 0 — flat | `{colors.canvas}` | App background, table headers, plain surfaces |
| 1 — hairline card | `{colors.surface-card}` + 1px `{colors.hairline}` | Panels, tables, watchlist rail |
| 2 — elevated | `{colors.surface-elevated}` + 1px `{colors.hairline-strong}` | Hovered/floating panels, dropdowns, tooltips, drawers at rest |
| 3 — overlay | `{colors.surface-overlay}` + `{colors.scrim}` + 1px `{colors.hairline-strong}` | Modals, command palette, log drawer open |

Focus is depth: 2px `{colors.focus-ring}` on `:focus-visible`, offset 2px, never removed. Price flash is the only transient depth effect: `{colors.flash-up}`/`{colors.flash-down}` row background fading over 150ms.

## 7. Do's and Don'ts

**Do:**
- Render every number in the mono face with tabular figures; right-align numerics, left-align text. No exceptions, no excuses.
- Keep one accent (`{colors.accent}` cyan) and use it sparingly: active tab, live dot, selected row, primary CTA, focus.
- Use red `{colors.price-up}` for rises and green `{colors.price-down}` for falls — Indian convention — and state it in every component that renders a price.
- Use hairline borders and surface steps for all depth; flat color-block panels.
- Mark stale data with a visible `{colors.warning}` STALE chip; a trading terminal that looks fresh but is stale is a safety hazard.
- Keep the kill switch permanently visible in the header strip, never disabled, never behind a menu.
- Show market-hours status (closed / pre-open / continuous) as a labeled semantic status chip.
- Format INR with Indian digit grouping (lakh/crore, e.g. `1,23,45,678`) in all monetary/OI/volume numbers.
- Use uppercase `micro`/`column-header` type for labels and headers; keep body text sentence case.
- Right-align time columns in mono `number-sm` (HH:MM:SS, local IST + market session context).

**Don't:**
- Don't introduce ad-hoc surfaces outside the two theme palettes (§2.2 dark / §2.3 light) — no full-white surfaces in dark, no full-black surfaces in light, no theme drift colors.
- Don't use emoji in data UI — no emoji in prices, tables, badges, toasts, or headers. Text labels only.
- Don't introduce chart-library chrome (toolbars, watermark logos, default palette, floating legends) — charts are ink-only: candles, grid, crosshair, volume; all other chrome comes from this contract.
- Don't use drop shadows, gradients, glows, or glassmorphism — on anything, ever.
- Don't bury the kill switch, mode indicator, or disconnect alert.
- Don't repurpose price colors as button fills, card backgrounds, or status; don't use success/error for prices.
- Don't invert the Indian red-up/green-down mapping to "match international platforms" — in either theme.
- Don't add a second accent, decorative illustrations, mascots, or atmospheric backdrops.
- Don't let numbers wrap, shrink, or switch to proportional numerals.
- Don't use weight 400 for display-scale text.

## 8. Responsive Behavior

Desktop-first; this is a keyboard-first workstation, mobile is a degraded fallback, not a target.

| Breakpoint | Behavior |
|---|---|
| ≥ 1440px | Full cockpit: watchlist rail + scanner + chain/panel zone + risk strip + optional log drawer, all docked |
| 1024–1439px | Collapse scanner panels and strategy hints into tabs behind the chain zone; log drawer becomes overlay drawer |
| 768–1023px | Single-pane stack: watchlist → tabs (scanner/chain/strategy); risk strip collapses to a 48px summary bar; command palette still available |
| < 768px | Stack everything; tables become card lists (header above each row, numerics right-aligned); kill switch stays visible in header; side rails become horizontal scrollers |

Rules:
- Breakpoints follow container queries inside panels; panels never overflow the viewport horizontally — content scrolls inside its panel.
- Touch: on coarse pointers, interactive targets floor at 40px and table row height rises to 40px (density tradeoff accepted and documented); on fine pointers keep 28px rows and keyboard-first focus order.
- Data tables never reflow mid-row: they truncate with `nowrap`, scroll horizontally, or degrade to card lists — never squeeze.
- The header strip (kill switch, mode, market-hours) never collapses on any breakpoint.

## 9. Agent Prompt Guide

**Quick hex reference — dark (default):**
- Canvas `#0a0a0a` · Surface card `#1a1a1a` · Surface elevated `#262626` · Hairline `#333333`
- Ink `#fafafa` · Body `#d4d4d4` · Muted `#737373`
- Accent amber `#f5b942` · Focus ring `#f5b942`
- **Rise (red)** `#f6525c` · **Fall (green)** `#2ebd85` · Flash tints `rgba(246,82,92,0.16)` / `rgba(46,189,133,0.16)`
- Success `#22c55e` · Warning `#ffb020` · Danger `#e5484d` · Info `#3b82f6`
- Row hover `#1f1f1f` · Row selected `#2a2a2a` + accent left edge

**Quick hex reference — light (opt-in):**
- Canvas `#ffffff` · Surface card `#f5f5f5` · Surface elevated `#e5e5e5` · Hairline `#e5e5e5`
- Ink `#0a0a0a` · Body `#404040` · Muted `#737373`
- Accent amber `#d97706` · Focus ring `#d97706`
- **Rise (red)** `#f6525c` · **Fall (green)** `#1e9e6b` (AA-darkened; hue stays green)
- Success `#15803d` · Warning `#92400e` · Danger `#c62828` · Info `#1e40af`
- Row hover `#f5f5f5` · Row selected `#fef3c7` + accent left edge

**Prompt templates:**

1. *"Build the watchlist left rail panel: `{colors.surface-card}` bg, 1px `{colors.hairline}` border, sticky `column-header` row, 28px rows, symbol left-aligned in `ticker`, LTP right-aligned `number-md` mono colored `{colors.price-up}`/`{colors.price-down}` by tick direction, change% in `number-sm`, row hover `{colors.row-hover}`, selected `{colors.row-selected}` with 2px accent edge, 150ms flash bg on tick, STALE chip in `{colors.warning}` when the feed lags."*

2. *"Render a scanner card: `{colors.surface-card}` bg, `eyebrow` label, one `number-lg` headline stat, mono `number-sm` sub-stats right-aligned, regime badge (uppercase `micro` on `{colors.surface-elevated}` with `{colors.hairline}` border), conviction badge in mono (LOW muted / MEDIUM warning / HIGH accent / EXTREME ink), no shadows, no gradients."*

3. *"Create the option chain grid: sticky header on `{colors.canvas-raised}`, uppercase `column-header` 11px, 24px rows, strike column centered in `ticker` mono, CE and PE sides with `number-md` mono cells, LTP colored `{colors.price-up}`/`{colors.price-down}` (red=rise, green=fall — Indian convention), OI/volume right-aligned with lakh/crore grouping, `*-soft` tints for the bid/ask quantity bars, row flash on tick, keyboard arrow navigation with focus ring."*

4. *"Build the positions/risk strip: 240px tall bottom panel, per-position rows (symbol `ticker`, qty + avg + LTP mono right-aligned, unrealized P&L in `{colors.price-up}`/`{colors.price-down}` by sign), margin-used vs limit with `{colors.warning}` when > 80%, a `{colors.danger}` breach chip when exceeded, and an always-visible kill switch in the header strip with `Ctrl+Shift+K`."*

**Anti-pattern reminder for agents:** ad-hoc theme colors, emoji, drop shadows, gradients, second accent, sans-serif numerals, left-aligned numbers, wrapping numbers, price colors as button fills, buried kill switch, chart-library chrome, green-for-up.

---

*Contract end. If a future change contradicts this file, update DESIGN.md first, then the code. (D4, D9)*
