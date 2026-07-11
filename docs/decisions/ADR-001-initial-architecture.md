# ADR-001: Initial Architecture and System Boundary Decisions

## Status
Accepted

## Context
ShettyXtreme is a greenfield project building a unified Indian-market trading intelligence and execution platform. We have four key reference systems:
1. OpenAlgo - execution/broker abstraction
2. DhanHQ-py - Dhan-specific SDK
3. ShettyBot V1 - intelligence/decision layer
4. FinceptTerminal - multi-asset terminal reference

We need to decide how to compose these into a coherent, maintainable system.

## Decision

### 1. OpenAlgo Relationship: COMPOSITION over fork/embed
OpenAlgo will be consumed as an external dependency via its REST API and WebSocket protocol. We will NOT fork it, NOT embed its source, and NOT subclass its internals. Our integration layer wraps OpenAlgo behind our own execution interfaces. This keeps upstream updates cleanly adoptable.

### 2. Dhan Relationship: DUAL PATH
We use DhanHQ-py directly for broker-specific operations (auth, account-specific data) AND via OpenAlgo for order execution. This gives us Dhan-native depth where it matters and OpenAlgo's multi-broker abstraction where it doesn't.

### 3. ShettyBot: MODULAR REINCARNATION
ShettyBot V1's intelligence logic (regime detection, signal generation, strategy hints) will be extracted into the intelligence/ module. The old monolithic architecture is discarded. The unique analytical value is preserved.

### 4. FinceptTerminal: INSPIRATION only
No code will be copied from FinceptTerminal. Its breadth serves as a product vision reference. If specific modules prove useful later, they will be adapted through our integration layer.

### 5. Core Platform: Python Monolith with Plugins
The core is a single Python package (shettyxtreme) with strict internal interface boundaries. Plugins are loaded dynamically for strategies, data providers, and broker adapters.

## Consequences
- OpenAlgo updates flow freely without breaking our core
- Dhan integration is deeper than generic brokers
- ShettyBot intelligence is preserved but properly modularized
- No architectural coupling to FinceptTerminal
- Plugin system allows third-party extension without core changes
