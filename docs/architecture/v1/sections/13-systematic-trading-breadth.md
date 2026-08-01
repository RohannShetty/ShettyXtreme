# Section 13: SYSTEMATIC TRADING BREADTH CHECK

Using the Awesome Systematic Trading catalog as a blind-spot checklist:

### Categories We Cover

| Category | Our Coverage |
|----------|-------------|
| Backtesting | ✅ Phase 3 (strategy backtest viewer) |
| Live trading | ✅ Phase 2+ (execution cockpit) |
| Risk management | ✅ Phase 1+ (risk engine) |
| Strategy development | ✅ Phase 2+ (voter plugin system) |
| Technical analysis | ✅ Phase 2 (feature engine) |
| Logging/journaling | ✅ Phase 2 (signal + trade journal) |
| Visualization | ✅ Phase 1+ (terminal UI) |
| Market data | ✅ Phase 1 (Dhan Data API) |

### Categories We Might Be Missing

| Category | Assessment | Decision |
|----------|------------|----------|
| **Portfolio optimization** | We focus on single-instrument directional options, not portfolio-level optimization | Defer to Phase 4+. Not relevant for MVP. |
| **Cost modeling** | ShettyBot V1 had NO slippage/spread/brokerage anywhere | MUST include from Phase 1. Slippage model in feature engine, cost-adjusted EV in strike selection. |
| **Streaming TA** | ShettyBot V1 recomputed features from scratch each cycle | MUST implement O(1) per-tick streaming indicators from Phase 1. |
| **Execution profiling** | Latency measurement from tick to signal to order | Include from Phase 1 as part of observability. |
| **Pre-trade risk gate** | ShettyBot V1 had risk checks but they were bypassed on loss-limit breach | Include composable risk filter chain from Phase 1. |
| **DAG/incremental computation** | OpenBB uses this; could improve feature engine performance | Acknowledge but postpone. Not needed for MVP scale. |
| **Message queues** | OpenAlgo uses ZMQ; our event bus is asyncio pub/sub | asyncio pub/sub is sufficient for single-process. Postpone external MQ. |
| **Prediction markets** | Irrelevant for India-first practical product | Skip. |
| **Crypto/forex tools** | Irrelevant for India-first | Skip. |
| **QuantLib** | Heavy quantitative finance library, institutional-grade | Skip. We need practical options math, not institutional fixed-income pricing. |
| **ML/RL for trading** | ShettyBot V1's ML had AUC 0.518 (barely random) | Postpone entirely. No ML until we have enough data and a proven pipeline. |

---

