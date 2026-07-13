# Section 2: RE-AUDIT OF THE CURRENT DIRECTION

### What Is Probably Right

- **Product vision**: Unified intelligence + execution + research terminal for Indian market
- **Dhan-first**: Correct broker choice for API quality and cost
- **Regime-awareness**: Markets do have regimes and trading should adapt
- **Operator-in-the-loop**: Semi-auto is safer than full auto for a prosumer product
- **Conviction-based signals**: Better than single-indicator signals
- **Shadow model concept**: Validate before activating

### What Is Probably Wrong (Architecture)

- **OpenAlgo as runtime dependency** → ShettyXtreme becomes a client of OpenAlgo. If OpenAlgo breaks, changes, or is unmaintained, ShettyXtreme breaks. **CORRECTED: standalone software.**
- **Textual TUI** → Limited interactivity, no real-time charts, no web access, hard to extend. **CORRECTED: web-based terminal.**
- **Composing with ShettyBot V1 code** → Inherits god modules and architectural debt. **CORRECTED: reimplement concepts.**

### What Is Probably Wrong (Intelligence)

- **Risk-neutral GBM for strike selection** → Noise optimization, not edge. GBM produces random strike rankings. **Fix: signal-drift EV.**
- **Loss limit freezes ALL trading** → Position management stops too. TSL and TP targets don't run on existing positions. **Fix: entries only.**
- **TP3 unreachable** → `update_tsl` runs before `check_targets`. **Fix: check_targets before update_tsl.**
- **No NEUTRAL state** → Forces UP or DOWN when voters disagree. **Fix: explicit NEUTRAL.**
- **OI voter time-of-day bias** → Raw OI compared across session. OI builds from open to close. **Fix: time-of-day percentile normalization.**
- **Dead voters dilute confidence** → ML voter (AUC 0.518 = random) and HMM voter contribute to D/P/G. **Fix: remove dead voters.**
- **No cost model** → Marginal strategies pass as profitable. **Fix: cost model in all EV.**
- **3 inconsistent stop-loss definitions** → **Fix: one canonical definition.**

### What Is Missing (Product)

- **Dhan Trading vs Data API split** → Two separate auth flows, two WS connections, different rate limits, different failover behavior.
- **Knowledge ingestion layer** → No way to feed reports, books, or strategy notes into the system.
- **Cost model** → No slippage/spread/brokerage in any EV computation.
- **Streaming TA** → Features recomputed from scratch each cycle (O(n) not O(1)).
- **Execution profiling** → No latency measurement from tick to signal to order.

### Architecture Smells

- **Terminal vs bot vs platform confusion**: ShettyBot V1 was a bot (Telegram), V2 blueprint tried to be a platform, but the terminal aspect was underspecified.
- **Analytics vs execution boundary confusion**: ShettyBot V1 mixed analytics (regime detection) with execution (order placement) in the same monolith.
- **Knowledge system vs trading system confusion**: No clear boundary between "what the system knows" and "what the system does."
- **Circular assumption**: Regime detection drives signal generation → signal generation validates regime detection. Without independent validation, this is circular.

---

