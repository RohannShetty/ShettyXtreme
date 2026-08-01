# Section 15: KNOWLEDGE, REPORTS, AND REVERSE ENGINEERING

### Knowledge Ingestion Architecture

```
Upload Document (PDF/MD/TXT)
    ↓
[Knowledge Store] — document stored with metadata (title, author, date, source, tags)
    ↓
[Tagger] — auto-extract: topics, instruments, strategies, market conditions
    ↓
[Heuristic Extractor] — extract testable claims:
    "When PCR > 1.3 on expiry day and NIFTY gap-down → sell CE"
    ↓
[Backtest] — test the heuristic against historical data
    ↓
[Walkforward] — validate stability over time
    ↓
[Human Review] — is it economically sensible? Is it overfit?
    ↓
[Activate as Shadow Voter] — runs alongside live, doesn't gate
    ↓
[Shadow Validation] — 20+ sessions → compare shadow vs live outcomes
    ↓
[Human Approval] — promote to active voter
```

### What Can Be Structured

- Strategy definitions ("buy when X, sell when Y") → YAML strategy files
- Parameter sets ("IV threshold = 70, PCR threshold = 1.3") → config values
- Risk rules ("max 2% daily loss") → risk engine config
- Expiry rules ("switch to next week when DTE ≤ 2") → expiry selection config

### What Can Be Tagged

- Documents by topic (options, regime, intraday, swing, risk management)
- Documents by instrument (NIFTY, BANKNIFTY, FINNIFTY)
- Documents by strategy type (directional, spread, premium selling)
- Documents by market condition (bull, bear, range, volatile)

### What Can Become Heuristics

- "When PCR is above 1.3 on expiry day, market tends to reverse" → contrarian PCR voter threshold
- "ORB breakout above opening range with volume confirmation → directional long" → ORB voter parameters
- "When NIFTY opens with a gap > 0.5% and breadth < 40% → gap fade" → gap scanner rule

### What Should Remain Human-Reviewed

- All knowledge-derived heuristics MUST pass human review before activation
- Economic sensibility check: does the heuristic make economic sense?
- Overfit check: does it work on multiple time periods or just one?
- Context check: is it relevant to current market structure?

### How to Avoid Polluting Live Trading Logic

- Knowledge layer is PHYSICALLY SEPARATED from live trading logic
- Knowledge can READ from live data (to verify predictions) but CANNOT WRITE to live trading rules
- Heuristic activation is a gated process with explicit human approval
- Shadow mode for all new heuristics — never auto-activate
- Even after activation, heuristics can be disabled with a single config toggle

---

