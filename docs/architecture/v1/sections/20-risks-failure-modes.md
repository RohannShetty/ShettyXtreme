# Section 20: RISKS AND FAILURE MODES

| Risk | Severity | Mitigation |
|------|----------|------------|
| **Overbuilding** | HIGH | Phase gates: no Phase N+1 work until Phase N test gates pass. Feature map marks "seductive distractions" clearly. |
| **Duplicate infra** | HIGH | Absorb, don't reinvent. DhanHQ-py is pip dependency. OpenAlgo patterns are absorbed as first-party code. No duplicate broker adapters. |
| **Tight coupling to upstream** | MEDIUM | Anti-corruption layers at all boundaries. Absorbed code marked with origin. Upstream changes reviewed, not auto-merged. |
| **Poor boundary design** | HIGH | CI-enforced import rules. Zero external imports in core. Intelligence can't import integration. Knowledge can't import intelligence. |
| **Latency assumptions** | MEDIUM | Measure from Phase 1 (latency metrics in observability). Don't assume sub-ms — measure and design around reality. |
| **Broker brittleness** | HIGH | Auto-reconnect for WS. Token auto-refresh. Fail-closed for Trading, fail-open for Data. Separate sessions. |
| **UI complexity** | MEDIUM | Web-based (not TUI). Progressive disclosure. Max 3 main panels. Keyboard-first. Start simple, add complexity based on real operator friction. |
| **Signal overfitting** | HIGH | Shadow mode for ALL new heuristics. 20+ session validation. Walkforward with honest evaluation. Cost model in all EV computations. |
| **Operational fragility** | HIGH | Session state persisted to DB (survives restart). OI/PCR baselines persisted (fixes ShettyBot V1's in-memory baselines). Kill switch file-based (independent of platform). |
| **Maintainability collapse** | HIGH | No god modules (500-line CI check). Single schema owner. Single config source. Plugin discovery (not hardcoded imports). |
| **Knowledge-layer contamination** | HIGH | Physical separation. Knowledge can't import intelligence. Human approval gate for all heuristic activations. Shadow validation before activation. |
| **False-confidence forecasting** | HIGH | No predictions — probabilistic framing. Uncertainty visible (conviction, disagreement, participation). Cost-aware EV. "Conditions X precede Y with probability P" not "market will go up." |

---

