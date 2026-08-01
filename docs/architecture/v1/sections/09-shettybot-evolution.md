# Section 9: SHETTYBOT EVOLUTION

### What Retains

| ShettyBot V1 Concept | New Home | Status |
|---------------------|----------|--------|
| Regime detection methodology | `intelligence/regime/` | Reimplemented (no Markov on 1m noise) |
| Conviction scoring concept | `intelligence/signals/` | Reimplemented (D/P/G, participation-normalized) |
| Options-flow voter concept | `intelligence/voters/options_flow.py` | Reimplemented (time-of-day normalized OI) |
| Shadow model concept | `intelligence/signals/` | Reimplemented (shadow voters logged, don't gate) |
| Learning loop concept | `learning/` | Reimplemented (voter quality CONSUMED, not just logged) |
| Cockpit thinking | `terminal/` | Reimplemented (web-based, not Textual) |
| Risk awareness | `intelligence/risk/` | Reimplemented (entries-only loss limit) |

### What Gets Refactored

- Monolithic `live_dispatcher.py` (2,702 lines) → split into: Event Bus + Signal Engine + Execution Engine + Position Manager
- Monolithic `dashboard.py` (3,381 lines) → replaced by: FastAPI backend + web frontend
- Hardcoded strategies → YAML-configured voter plugins with registry

### What Gets Deprecated

- V1 direct OpenAlgo integration → superseded by first-party Dhan adapters
- V1 database schemas → replaced by new storage model (DuckDB + SQLite)
- V1 Telegram bot → optional plugin, not primary interface
- V1 Textual/Rich TUI → replaced by web-based terminal
- Markov voter (momentum follower, misleads as regime predictor) → removed or renamed `MomentumVoter`
- ML voter (AUC 0.518 = random) → removed entirely
- HMM voter (poorly calibrated) → removed

### What Gets Preserved as Concepts

- Regime classification methodology (trend/range/volatile detection)
- Signal scoring algorithms (direction score, participation, disagreement)
- Risk calculation approaches (position sizing, loss limits)
- Strategy-to-regime mapping
- Cockpit information architecture

These are extracted as specs, then reimplemented cleanly with 10 critical bugs fixed.

### 10 Critical Bugs Fixed in ShettyXtreme

| # | Bug | Fix |
|---|-----|-----|
| 1 | Strike selection = risk-neutral GBM noise | Signal-drift EV with actual exit policy |
| 2 | Loss limit freezes all trading | Loss limit blocks ENTRIES ONLY |
| 3 | TP3 unreachable | check_targets before update_tsl |
| 4 | No NEUTRAL signal (bearish tie-break) | Explicit NEUTRAL state |
| 5 | OI time-of-day clock bias | Normalize OI by time-of-day percentile |
| 6 | 3 inconsistent stop-loss definitions | One canonical (premium-relative, vol-aware) |
| 7 | Dead voters dilute confidence | Conviction (participation-normalized) — dead voters removed |
| 8 | Weights hardcoded in add_vote() | Weights in config YAML |
| 9 | No cost model | Slippage/spread/brokerage in ALL EV |
| 10 | No voter correlation awareness | Block caps per voter correlation group |

---

