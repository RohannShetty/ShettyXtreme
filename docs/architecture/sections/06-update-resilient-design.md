# Section 6: Update-Resilient Design

## Strategy

Multi-layered defense isolates core from upstream changes.

## Anti-Corruption Layer (ACL) Pattern

Every external dep has an adapter that:
1. Defines interface the core expects (in core/interfaces/)
2. Implements by translating to/from the external system
3. Is the ONLY code importing from the external package
4. Has contract tests against the real upstream

### OpenAlgoAdapter
- Core interface: OrderExecutor, MarketDataStream, AccountInfo
- Import chain: core -> OpenAlgoAdapter -> openalgo (NOT core -> openalgo)

### DhanAdapter
- Core interface: BrokerAccount, MarginProvider
- Import chain: core -> DhanAdapter -> dhanhq (NOT core -> dhanhq)

## Fork vs Composition: COMPOSITION WINS

| Aspect | Fork | Composition |
|--------|------|-------------|
| Upstream updates | Manual merge pain | Version bump + test |
| Divergence | Inevitable | Zero by design |
| Security patches | Re-merge needed | Bump version |
| Maintenance | Full repo to maintain | Near zero |

Exception: fork only if upstream is unmaintained (12+ months no updates).

## Upstream Sync Workflow

1. Version pin + range in pyproject.toml
2. Changelog-driven review before bumps
3. Contract tests run in CI
4. Staged rollouts: dev -> staging -> prod
5. Rollback plan for each dependency

## How to Not Create a Brittle Monster

1. NEVER import external directly in core/
2. NEVER pin exact versions without testing
3. NEVER customize external repos locally
4. ALWAYS write adapter tests first
5. ALWAYS review changelog before bumping
6. ALWAYS have a rollback plan
