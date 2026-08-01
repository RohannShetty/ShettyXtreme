# Section 04 — India-First Scope

> Scope of the market specialization: NSE/BSE reality, options workflows, session and settlement mechanics, Dhan-specific capabilities, and the exact line between "India-specialized" and "multi-asset generic" components (per D6).

## NSE/BSE market reality

ShettyXtreme is India-first (per D6): index options are the primary intelligence and execution pipeline; equities/indices are terminal breadth. The platform must model Indian market mechanics exactly, because options workflows are expiry-driven and session-bound.

| Aspect | Indian reality | Design consequence |
|---|---|---|
| **Exchanges** | NSE primary, BSE secondary (same instruments mirrored) | Instrument identity must carry exchange + series; cross-exchange dedupe in instrument master |
| **Instruments** | EQ, FUT, OPT (NIFTY/BANKNIFTY weekly + monthly, FINNIFTY/MIDCAPNIFTY monthly), indices | Domain model has one `Instrument` with `instrument_type`; contract normalization is broker-agnostic (per Section 07) |
| **Expiry** | Weekly options expire Thursdays; monthly on last Thursday; holiday-shifted expiries | Expiry calendar is a first-class data source; all expiry-relative logic (OI decay, theta, strike selection) keys off it |
| **Sessions** | Pre-open 09:00–09:15 IST, regular 09:15–15:30 IST, post-close 15:30–16:00 | Session state machine (per below) drives feed subscription, feature warm-up, EOD close (position manager EOD exit 15:15 by default), and scanner runs |
| **Settlement** | T+1 for equities and F&O; daily MTM on futures | Cash/settlement fields on positions; no overnight assumptions; EOD flattening is configurable per strategy |
| **Order types** | LIMIT, MARKET, SL, SL-M, AMO, CO (cover), BO (bracket), IOC | Order domain model carries `order_type`; execution layer validates type × instrument × session before dispatch |
| **Margins** | SPAN + exposure (VAR/ELM) computed by clearing corps; broker enforces | Margin estimation is an India-specialized module (per D6); risk engine uses broker-reported margin where available, estimates SPAN/VAR/ELM where not |
| **Fees** | Brokerage slabs, STT/CTT, exchange charges, GST, SEBI charges | Cost model in `intelligence/risk` (cost-aware entries); mpp slab logic adapted from vendored OpenAlgo `utils/mpp_slab.py` |

### Dhan-specific capabilities (per Section 11)

Dhan is the Dhan-first broker integration (per D1/D8): one `DhanContext(client_id, access_token)` serves trading REST, the `api-feed.dhan.co` websocket, and historical data (DhanHQ-py 2.2.0 design).

- **Super Orders** — multi-leg coordinated orders (e.g., spreads) sent as one logical order; relevant for the options strategy assistant's hedge/combination hints.
- **Forever Orders** — conditional orders placed/modified via `/forever/orders`; semantics beyond the API signature (whether they persist past 15:30 and re-arm next session) are an open question — no documented re-arm behavior in DhanHQ-py 2.2.0; verify live. Surfaced in the terminal as a distinct order class (we do not use the `place_forever` `symbol` param that 2.3.0rc1 removed — stay pinned 2.2.0, per corrected fact 5).
- **Conditional Orders** — trigger on market conditions; native building block for risk automation, though our risk engine keeps trigger logic first-party.
- **Position conversion** — intraday ↔ delivery conversion; only meaningful for equities; surfaced in the execution cockpit, never auto-invoked.
- **EDIS** — electronic delivery instruction processing; required for taking equities to delivery; exposed as an explicit user action only.
- **AMO** — after-market orders accepted 15:30–09:00 next session; the calendar and session modules expose the AMO window.

## Where India specialization is first-class

These modules are India-only by design and may hard-code NSE/BSE assumptions (per D6):

1. **Instrument master** — NSE/BSE scrip codes, series, expiry calendar with holiday awareness; seeded from Dhan API, cached in SQLite KV; the single source of truth for symbol → contract resolution.
2. **Options chain** — weekly/monthly expiry ladders, strike grid, ATM detection, Greeks, OI; the two 501 stubs (`get_option_chain`, `get_strategy_hint`) are Phase-2 implementations of this (per D6).
3. **Market status** — session state machine: `pre_open` (09:00–09:15), `open` (09:15–15:30), `post_close` (15:30–16:00), `closed`/holiday; consumed by feed, execution, and UI (already implemented in `terminal/api/health_router.py`).
4. **Calendar** — trading holidays, expiry schedule, result season; drives the session state machine and backtest date ranges.
5. **Margin models** — SPAN/VAR/ELM estimation for position sizing; India-specific and broker-agnostic in interface (broker-reported margin preferred).
6. **PCR/OI analytics** — put-call ratio and open-interest changes normalized by time of day and expiry proximity (an 11:00 AM OI spike means something different than a 15:10 one; a Thursday 14:30 spike means expiry pinning).

## Where multi-asset stays generic

These components are deliberately instrument-agnostic (per pack conventions):

| Component | Generality | Why |
|---|---|---|
| **Event bus** | `Topic` enum + `Event` dataclass carry any payload | Instrument identity is a field, not a type (per `core/event_bus/event_bus.py`) |
| **Storage** | SQLite KV + DuckDB TS stores any symbol/time-series | Instrument is just a key; index options and equities share stores |
| **Plugin system** | Voters, scanners, strategies register via protocols | A new asset class adds data adapters + voters, not plumbing |
| **Signal engine** | Consumes normalized `FeatureSet` dicts, votes on them | Indicator math is market-agnostic; India enters via features, not logic |
| **Risk parameters** | Position sizing, loss limits, exposure caps are config values | Market-agnostic parameters; India-specific margin estimation plugs in below |

The invariant: **India-specific knowledge lives in `integration/` (instrument master, calendar) and `intelligence/` (options, margin estimation, PCR normalization); generic machinery lives in `core/`.** Violating this (e.g., hard-coding Thursday expiry in the signal engine) is an architecture error (per Section 05 import rules).

## Intraday vs swing relevance for index options

Index options are an **intraday-first product** in this platform: weekly expiries create time decay that punishes swing holds through Thursday; overnight gap risk on leveraged option positions is material. Consequences:

- Feature engine runs O(1)/tick streaming indicators on 1m bars for intraday signals (per `intelligence/features`); regime classification uses coarser bars to avoid Markov-on-noise overfitting (per v1 architecture, retained).
- Swing (multi-day) trades are supported for monthly-expiry contracts only, gated by explicit risk config (max hold days, theta-drain guard).
- EOD handling is default-on: position manager flattens at 15:15 by default (configurable), because carrying weekly options overnight is a deliberate, non-default decision.
- Backtest and walkforward evaluation (per `learning/`) must use India session boundaries — a bar that spans 15:30→09:15 is a gap artifact, not a candle.

## Prosumer workflow realities

The user is a solo, own-capital trader (per D2/D11) running a live observer → live pipeline on one machine:

| Reality | Design response |
|---|---|
| One Windows machine, one Dhan account, one session | Single `DhanContext`, single process, modular monolith (per Section 18) |
| Morning setup is 09:00–09:15 pre-open | Pre-open window used for credential health check, instrument master refresh, subscription setup — so 09:15 starts clean |
| Trader reviews before acting | Semi-auto approval in execution engine; OBSERVER default (per D10); LIVE is an explicit per-session action |
| Distraction-free during 09:15–15:30 | Terminal is read-oriented (cockpit panels per Section 15); execution is a deliberate second action |
| Post-close review 15:30–16:00 | Outcome tracking and journaling run in post-close; AMO window for next-day equity orders |
| Weekly expiry Thursday is the "event day" | Expiry calendar raises alert cadence; strategy hints bias toward expiry-aware setups on Thursday |

## Live session realities

Facts that shape the integration layer (per D8 and corrected facts):

1. **Token expiry ~03:00 IST daily** — access tokens minted today die tomorrow ~3AM. DhanHQ-py has no auto-refresh. The auth layer must run a pre-open token health check and re-consent via PIN/TOTP `generateAccessToken` flow before 09:00 (per `auth/DhanOAuthHelper`, `TokenHealthMonitor`, `CredentialValidator`).
2. **806 is an entitlement error, not a credentials bug** — `"Disconnected: Subscribe to Data APIs to continue"` means the Data-API subscription is missing (corrects v1). D8's single-primary + data-fallback design: one client_id + consent token serves both; an optional second `data_access_token` slot is provisioned via the PIN/TOTP flow only if the feed rejects the consent token.
3. **Feed request codes v2 (corrected fact 2)** — subscription requests use code 15 (Ticker) / 17 (Quote) / 21 (Full); unsubscribe = code + 1; disconnect = RequestCode 12; server error packets 805–809. **Our `DhanDataAdapter` currently sends codes 2/8 (response codes) — a latent bug; Phase-2 fix.**
4. **Rate limits** — per-endpoint, per-second caps on REST; the adapter owns throttling and retry-with-backoff; bulk endpoints (positions, holdings) are polled on a cadence, never per-tick.
5. **Positions payload carries no LTP** — position P&L requires a separate `multiquote` call; the portfolio/risk state must reconcile position snapshots with multiquote LTP rather than assuming it arrives in the positions response (verified: src/shettyxtreme/integration/dhan/trading_adapter.py get_positions_with_ltp).
6. **Intraday historical data window limits are an open question** — DhanHQ-py passes from/to dates without documented bounds; verify against a live account. Backtest data strategy must mirror (and persist) live-captured data into DuckDB TS from day one (per Section 06 storage).
7. **Binary websocket protocol** — DhanFeed is binary, separate from REST; the data adapter is the only place that decodes it (per Section 05 integration boundary).

## India-first vs generic — decision table

| Question | Answer | Where enforced |
|---|---|---|
| Is Thursday expiry a core concept? | No — a calendar fact consumed by intelligence | Calendar in `integration/`, expiry logic in `intelligence/options/` |
| Is SPAN margin a core concept? | No — a risk input | Margin estimation in `intelligence/risk/`, interface in `core/interfaces/` |
| Is NIFTY/BANKNIFTY hard-coded anywhere? | Only in default configs and option-chain defaults, never in `core/` | Config + instrument master |
| Is the 09:15–15:30 session a core concept? | Yes — sessions gate everything | `core/` session module (market status) |
| Can a US symbol trade tomorrow? | Structurally yes (new instrument master + adapter), practically no effort planned | Generic core + swappable integration (per Section 07) |

Cross-references: [Section 05 — System Boundaries](05-system-boundaries.md) (where these modules sit), [Section 06 — Proposed Architecture](06-proposed-architecture.md) (data flow), [Section 11 — Dhan Integration](11-dhan-integration.md) (Dhan specifics), [Section 14 — Data Decision Intelligence](14-data-decision-intelligence.md) (PCR/OI normalization consumers).
