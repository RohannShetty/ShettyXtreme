---
frozen_rules_count: 7
last_amended: "2026-08-05T00:00:00Z"
---

# Frozen Rules

These rules must never be violated — by any agent, in any phase.

---

## FR-001: India-First Market Model
**Established:** 2026-07-12 | **Status:** Active

NSE/BSE market structure, instrument types, expiry calendars, trading sessions, and settlement rules are first-class citizens. No international-market adapter pattern is applied to Indian markets — they are native, not special cases.

## FR-002: Fyers-Native Integration
**Established:** 2026-07-12 | **Amended:** 2026-08-05 | **Status:** Active

Fyers is the primary broker. All broker features (auth, orders, positions, data) work optimally with Fyers first. Other brokers are secondary and wired behind the `core/interfaces` Protocols (ADR-008).

## FR-003: Broker Plumbing Behind Protocols
**Established:** 2026-07-12 | **Amended:** 2026-08-05 | **Status:** Active

Order execution, broker abstraction, and WebSocket plumbing are implemented in `integration/<broker>/` behind the `core/interfaces` Protocols — never reimplemented in core. The integration layer wraps and adapts broker SDKs; it does not leak broker wire formats above `integration/`.

## FR-004: Anti-Corruption Layer
**Established:** 2026-07-12 | **Status:** Active

Every external dependency (OpenAlgo, DhanHQ-py, Fincept modules, future providers) must have an anti-corruption layer. Core domain code never imports external packages directly. Interfaces define what the core expects; adapters translate.

## FR-005: Interface-Driven Design
**Established:** 2026-07-12 | **Status:** Active

Every integration point, plugin, and module boundary has an explicit Python Protocol (typing.Protocol) or abstract base class defining its contract. Implementations are swappable. Tests verify contract compliance.

## FR-006: Composition Over Fork
**Established:** 2026-07-12 | **Status:** Active

External repos (OpenAlgo, DhanHQ-py, FinceptTerminal) are consumed as dependencies — never forked or embedded. Upstream updates are absorbed via version bumps and integration tests, not by merging branches.

## FR-007: Observability by Default
**Established:** 2026-07-12 | **Status:** Active

Every module must emit structured logs and metrics. Failures are detectable without user reports. Latency and errors are tracked at every integration boundary.
