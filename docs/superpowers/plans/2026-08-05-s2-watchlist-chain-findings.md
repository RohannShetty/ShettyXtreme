# S2 Findings — Phase 3 Cockpit Redesign: Watchlist Polish + ChainGrid Live Streaming

**Date:** 2026-08-05
**Scope:** S2 of Phase 3 — `Watchlist.svelte` polish (STALE chip, tick flash, 28px rows, keyboard nav) and `ChainGrid.svelte` live streaming (WS ticks, auto-refresh, 24px rows, centered strike, keyboard nav, Load button removed)
**Status:** Complete — both verification gates pass

---

## Deliverables

| File | Change |
|---|---|
| `src/shettyxtreme/terminal/web/src/components/Watchlist.svelte` | STALE chip replaces opacity-fade; flash direction = tick-vs-prev move; fixed a latent flash-restart bug; 28px rows; per-row arrow-key navigation |
| `src/shettyxtreme/terminal/web/src/components/ChainGrid.svelte` | Live WS tick subscription with contract matching; per-cell LTP direction color + 150ms flash; auto-load on committed symbol/expiry change; quiet 15s IV/OI poll; LIVE/SYNC chip replaces the Load button; 24px rows; centered strike column; per-cell arrow-key strike navigation |

## Verification

- `npm run check` → **svelte-check: 0 errors, 0 warnings**
- `npm run build` → **vite production build succeeds** (bundle regenerated in `terminal/static/`, not committed)

---

## 1. Watchlist.svelte — polish

### 1.1 STALE chip replaces opacity fade (DESIGN §4, §7)

The old `.row.stale { opacity: 0.5 }` dimmed the entire row — a stale terminal that *looks* slightly dimmed but still shows a current-looking LTP is exactly the safety hazard DESIGN §7 forbids. Now each stale row renders a **STALE chip** in the symbol cell's corner (the meta line beside the exchange):

- `{colors.warning}` text on a `color-mix(warning 12%)` tint, 1px warning-border, 2px radius — the same chip vocabulary as the Header's ent-chip
- `micro` (11px) weight-600 **uppercase** with `0.08em` tracking (DESIGN §4)
- Appears when no tick has been seen for that symbol in >60s (`STALE_MS`, same `lastSeenMs` map as before, seeded from the REST `timestamp`)
- `title` tooltip retained on the row

### 1.2 LTP color + flash (Indian price law — never inverted)

- **Persistent LTP color** stays on `change_pct` sign: `> 0` → `--price-up` (red `#f6525c`), `< 0` → `--price-down` (green `#2ebd85`). This matches the S1 header hero and the backend session direction — consistent, no per-tick color flicker.
- **Flash direction** is now the tick-vs-previous-tick move (new `prevLtp` map), not `change_pct` sign — a symbol can be down on the day yet flash red on an up-tick. Matches Header.svelte §2.2 semantics.
- Flash uses the global `flash-up` / `flash-down` keyframes from `design.css` (150ms background fade to transparent). LTP cell bumped to `number-md` 13px; chg stays `number-sm` 11px.

### 1.3 Fixed a latent flash-restart bug

The old code stored flash state in a plain `Map` and deleted it via `setTimeout`. `Map` mutation is **non-reactive**, so the class never left the DOM between ticks — the CSS animation completed once and subsequent ticks could not restart it (same class string, no class change). Flash state is now a `$state` record with a per-symbol reset timer: assignment triggers re-render, the 150ms timer reassigns the record to remove the entry, so the next tick re-adds the class and the animation restarts. Same pattern applied to ChainGrid.

### 1.4 Layout (DESIGN §4 table contract)

- Rows fixed at **28px** (`height: 28px`, vertical padding removed) with tight two-line line-heights (14/14px) so the symbol+exch stack fits without overflow.
- Selected row unchanged and already compliant: `--row-selected` bg + 2px `--accent` left edge (`border-left`).
- Focus ring: 2px `--focus-ring` inset on `:focus-visible`.

### 1.5 Keyboard arrow navigation

ArrowUp/ArrowDown move selection **and** the focus ring together (rows are `role="button"`, `tabindex="0"`). Handled per-row (Enter/Space selects; arrows move + `rowEls[next].focus()`), so no non-interactive container carries a keydown listener (avoids the Svelte a11y warnings). Clamps at the ends (no wrap).

---

## 2. ChainGrid.svelte — live streaming

### 2.1 The critical backend constraint (drives the whole design)

`WatchlistProjection.on_market_data` broadcasts `{symbol, ltp, change_pct, volume}` only (`projections.py:55`). The WS `tick` payload **does not carry** `strike`, `option_type`, `iv`, or `oi` — even though `core/data_models.OptionContract` models them. Consequences:

1. **IV/OI cannot tick** — they only exist in the REST chain response. A quiet 15s poll keeps them live.
2. **Per-contract LTP matching must go through the symbol string** — `parseTickKey()` extracts strike+side from Fyers-style (`NIFTY24AUG24500CE`) and spaced (`NIFTY 24500 CE`) symbols; the payload is also checked for future explicit `strike`/`option_type` fields.
3. **Only watchlisted contracts tick** — the grid's 100 contracts are not individually subscribed by the backend, so real-time LTP/IV/OI for non-watched strikes arrives via the quiet poll.

Recommended backend follow-up (out of scope): extend the `tick` broadcast with `strike`, `option_type`, `iv`, `oi` so every chain cell can update on the wire.

### 2.2 Auto-load — no manual Load button (mission)

- `snapshot` holds the **committed** `{symbol, expiry}` pair; the display inputs bind to `symbol`/`expiry` and update per keystroke, but the grid only reloads when the committed pair changes. This means no fetch-per-keystroke while typing a symbol.
- A `$effect` watches `snapshot` (fires on mount + on commit) and calls `load()` with a `reqId`; a response whose `reqId` is stale is dropped, so a newer request always wins (no race when selection and input commits interleave).
- Commits come from: symbol Input `onchange`/Enter, expiry select `onchange`, expiry Input `onchange`/Enter, and the `selectedSymbol` subscription.
- When the server resolves an expiry the request didn't pin (e.g. nearest expiry on first load), `applyResponse` aligns `snapshot` to the resolved value — one extra converging reload, never a loop.

### 2.3 Tick handling — color + flash

- `matchIndex` (`$derived`) maps `${strike}|${side}` → flat-contract index; ticks mutate the `$state` contract object (deep reactivity → row re-render).
- **LTP direction** = tick-vs-previous-tick: `price-up` (red) / `price-down` (green) persistent color from `dirMap`, 150ms `flash-up`/`flash-down` background fade from the reactive `flashes` record (same restart-safe pattern as Watchlist).
- IV/OI/bid/ask are applied defensively if a future payload carries them.
- A **LIVE/SYNC chip** replaces the removed Load button: pulsing `--accent` dot when a matched tick arrived within 60s, muted otherwise — the grid now streams, so the affordance is a status, not an action.

### 2.4 Quiet IV/OI poll

`refreshSilently()` fetches the committed pair every `REFRESH_MS` (15s) and updates contracts **without** flashing or touching `dirMap` — a flash storm across 100 rows every poll would be noise, not signal. A separate 5s timer feeds the LIVE-chip staleness check. Errors are swallowed (the committed path surfaces them). If backend load matters, the two timers can be tuned independently.

### 2.5 Grid contract (DESIGN §4, prompt 3)

- Rows fixed at **24px** (`h-6` on `TableRow`), cells `px-1.5`, mono 12px `tabular-nums`, right-aligned, `nowrap`.
- **Strike column centered** in mono 600 (was right-aligned), the strike cell is the focus anchor (`role="gridcell"`, `tabindex={0}`, 2px `--focus-ring` on `:focus-visible`).
- Selected row: `--row-selected` bg + 2px `--accent` left edge via the `TableRow` class prop (the `data-[state=selected]` variant is unusable — `TableRow` does not forward rest attributes).
- `:global()` scoping is required for the cell classes because the `<td>`/`<tr>` are rendered by the child table primitives — Svelte scoped CSS cannot target elements owned by a child component.

### 2.6 Keyboard arrow navigation

ArrowUp/ArrowDown on a focused strike cell moves `selectedStrike`, scrolls the row into view, and refocuses the target cell (`focusStrike` via `[data-strike]` query). Same a11y-clean per-element approach as Watchlist.

---

## Technical notes / findings for later phases

1. **`tick` payload lacks option identifiers (IV/OI/strike).** This is the single biggest lever for a truly live chain: extending `WatchlistProjection.on_market_data`'s broadcast to include `strike`/`option_type`/`iv`/`oi` would let ChainGrid (and a future per-strike detail panel) update entirely on the wire, removing the 15s poll. Currently blocked on `Tick` → dict serialization and per-contract subscription scope (only watchlist symbols tick).
2. **`selectedSymbol` needs an exchange** (confirmed again from S1): ChainGrid assumes `NSE_FNO` for the chart; a symbol chosen from a BSE watchlist row would misroute the chart fetch. S1 finding #1 stands.
3. **`TableRow` doesn't forward rest attributes** (`data-state`, `onkeydown`, `aria-*` all silently dropped). The shadcn table primitives should gain rest-forwarding (`{...rest}` on `<tr>`) so `data-[state=selected]` styling and row-level events work — a small, high-leverage primitive fix for the component-migration task.
4. **Concurrent working-tree churn observed during S2:** `npm run check` error/warning sets shifted between runs (ProposalQueue `title`-on-Badge and KnowledgePanel `bind:this` errors appeared and vanished without my touching those files). Final state is clean; if the other session reintroduces errors in *its* files, the gate will report them — they are not caused by S2.
5. The static bundle (`terminal/static/`) was regenerated by the mandatory build gate. **Not committed** per instructions.

## Files touched

- `src/shettyxtreme/terminal/web/src/components/Watchlist.svelte` (owned)
- `src/shettyxtreme/terminal/web/src/components/ChainGrid.svelte` (owned)
- `src/shettyxtreme/terminal/static/*` — regenerated build output (gate artifact, not a source change)

No other files were modified. DESIGN.md / design.css token changes in the working tree predate this task (prior session).
