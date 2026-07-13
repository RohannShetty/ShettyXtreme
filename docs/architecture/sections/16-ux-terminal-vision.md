# Section 16: UX / TERMINAL VISION

### Interface Stance: Web-Based Professional Workstation

NOT a CLI/TUI. A web-based workstation with professional terminal feel. The "terminal" in the product name means "professional trading workstation" (like Bloomberg Terminal), not "CLI application."

Informed by:
- https://github.com/leonxlnx/taste-skill (design taste/quality skill)
- https://github.com/nextlevelbuilder/ui-ux-pro-max-skill (UI/UX excellence skill)

### Cockpit Layout

```
┌─────────────────────────────────────────────────────────────────────────┐
│ STATUS BAR: [Session: OPEN] [Mode: OBSERVER] [Dhan: ●] [Data: ●] [Risk: OK] │
├──────────────┬─────────────────────────────┬───────────────────────────┤
│ WATCHLIST    │ INTELLIGENCE COCKPIT         │ EXECUTION COCKPIT         │
│              │                              │                           │
│ NIFTY 24500  │ Regime: TRENDING_UP (72%)    │ Positions: 1 active       │
│  +0.45%      │ Conviction: 0.68 [████░░]    │ NIFTY 24500 CE            │
│              │ Direction: UP  Disagree: 0.12│   Entry: 85  LTP: 112     │
│ BANKNIFTY    │                              │   MTM: +₹1,755           │
│  +0.62%      │ VOTERS:                      │                           │
│              │ ✓ Options Flow  ↑ 0.70       │ RISK:                     │
│ FINNIFTY     │ ✓ ORB           ↑ 0.65       │ Daily P&L: +₹1,755       │
│  +0.31%     │ ✓ Micro         ↑ 0.55       │ Margin: ₹45,200 / ₹2L    │
│              │ ✓ Breadth       ↑ 0.40       │ Loss Limit: ₹8,000 used  │
│ OPTIONS:     | ✗ HMM (disabled)              │                           │
│ NIFTY 24500CE│ ✗ ML (disabled)              │ [KILL SWITCH]             │
│  85 → 112   │                              │                           │
│              │ STRATEGY HINT:               │                           │
│              │ Long CE, 1 lot, 24500 strike │                           │
│              │ EV: +₹12 after cost          │                           │
│              │                              │                           │
├──────────────┴─────────────────────────────┴───────────────────────────┤
│ SCANNER + ALERTS + LOGS                                                 │
│ [GAP] NIFTY gap-up 0.6%, breadth weak (38%) → fade risk                 │
│ [ALERT] OI data 3min stale                                              │
│ [SIGNAL] 09:42 TRENDING_UP conviction=0.68 (Options+ORB+Micro)         │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key UX Principles

1. **Keyboard-first**: All primary actions accessible via keyboard shortcuts
2. **Progressive disclosure**: Start with summary, drill down to detail
3. **Explainability surfaces**: Every signal shows WHY (voters, conviction, regime context)
4. **Not cluttered**: Max 3 main panels + status bar + bottom strip
5. **Session-aware**: UI adapts to session phase (pre-open, open, close)
6. **Mode-aware**: Observer mode hides execution panel; Live mode shows it
7. **Cost-visible**: EV shown as "after cost" not gross
8. **Honest uncertainty**: Conviction bar, disagreement indicator, participation level all visible

### Drill-Down Workflow

1. Scanner surfaces a candidate → click to open instrument
2. Instrument opens in Intelligence Cockpit → see regime, voters, conviction
3. If conviction passes threshold → Strategy Hint appears
4. Click Strategy Hint → see full explanation (voter breakdown, IV context, OI analysis)
5. If mode = Live → approve in Execution Cockpit (semi-auto)
6. Post-trade → outcome tracked in Journal

---

