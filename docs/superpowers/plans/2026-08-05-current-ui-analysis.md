# Current UI Analysis — ShettyXtreme Terminal (v0.12.0)

**Date:** 2026-08-05
**Analyst:** Explorer (exp-1)

## Current Layout (App.svelte)
- 3-row grid: Header / workspace / PositionsRiskStrip
- 3-col workspace: rail (260px) | center (tabs) | right-col (320px)
- Right-col `display:none` below 1440px — **safety issue** (proposals unreachable)
- Hash routing: `/`, `/settings`, `/setup`

## Pain Points (Ranked)
1. **Right-col disappears <1440px** — execution approvals, research, knowledge unreachable
2. **Tab remount churn** — scanner/hints/analytics remount on every tab switch
3. **Horizontal overflow** — `.workspace` `overflow-x:auto` violates DESIGN §8
4. **No live chain** — REST + manual Load only; no WS subscription
5. **Header lacks LTP hero** — DESIGN §5 mandates `number-xl` for selected symbol
6. **Staleness not per contract** — Watchlist fades opacity instead of STALE chip
7. **No split-pane resizability / persistence**, no command palette, no ticker strip
8. **PositionsRiskStrip bare on canvas** — no `surface-card` bg/border
9. **Native `<select>`s** unstyled per DESIGN dropdown contract
10. **api.ts has no timeout/cancel**

## What Works
- Token discipline (design.css dual-theme + app.css alias layer)
- WS client (clean topic registry, handler isolation, 2s reconnect)
- Density largely spec-faithful (28/24/32px rows/tabs)
- Indian price convention honored everywhere (red=up, green=down)
- Consistent state trio (Loading/Error/Empty) in every data panel
- Safety: typed LIVE confirm, typed DISARM, always-visible kill switch

## Missing for Glanceable Cockpit
- Live chain streaming
- Header LTP hero (`number-xl`) for selected symbol
- STALE chips
- At-a-glance regime/IV/PCR summary in chrome
- Reachable research/knowledge/execution on all widths
- Keyboard nav in chain
- Split-pane persistence
- Custom scrollbars
