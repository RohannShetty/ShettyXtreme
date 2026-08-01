# Section 7: UPDATE-RESILIENT DESIGN

> **CORRECTED from earlier session**: Not composition with OpenAlgo. Absorb patterns, track upstream, selectively incorporate.

### Anti-Corruption Layer (ACL) Pattern

| Boundary | ACL Pattern | How |
|----------|-------------|-----|
| DhanHQ-py | Dhan Trading Adapter + Dhan Data Adapter | Only code that imports dhanhq; core sees `OrderExecutor`/`MarketDataStream` protocols |
| Absorbed OpenAlgo code | `_absorbed/` directory with origin markers | Marked with source comments; reviewed when OpenAlgo publishes changes |
| Fincept | Zero (no code enters) | Patterns only |
| OpenBB | Zero (no code enters) | Patterns only |

### Absorb vs Composition vs Fork

| Strategy | When | Our Use |
|----------|------|---------|
| **Composition** (pip dep) | External library with stable API | DhanHQ-py |
| **Absorption** (copy + adapt) | External service with useful patterns | OpenAlgo broker adapter, order validation, Options Tools concepts |
| **Fork** | Never (unless upstream unmaintained 12+ months) | Not used |

### Upstream Sync Workflow (OpenAlgo)

1. Monitor OpenAlgo repo for changes (monthly review)
2. When changes detected, review the diff
3. Decision: absorb (copy + adapt), skip, or modify
4. If absorb: copy to `_absorbed/`, add origin marker, adapt to our interfaces
5. Run full test suite to validate
6. No auto-merge — human review always

### Upstream Sync Workflow (DhanHQ-py)

1. Version pin in pyproject.toml
2. Changelog-driven review before bumps
3. Integration tests validate adapter works with new version
4. Staged rollout: dev → staging → prod

### CI-Enforced Architecture Compliance

```bash
# core has zero external imports
! grep -r "import dhanhq\|import httpx\|import duckdb\|import openalgo" src/shettyxtreme/core/
# intelligence doesn't import integration
! grep -r "from.*integration\|import.*integration" src/shettyxtreme/intelligence/
# no file > 500 lines
! find src -name "*.py" -exec wc -l {} + | awk '$1 > 500'
# no openalgo dependency anywhere
! grep -r "import openalgo\|from openalgo" src/
```

---

