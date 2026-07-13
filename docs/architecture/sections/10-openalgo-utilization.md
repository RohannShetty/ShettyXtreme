# Section 10: OPENALGO UTILIZATION (ABSORB, DON'T DEPEND)

> **COMPLETELY REWRITTEN from earlier session.** Old plan: "compose with OpenAlgo as external service." New plan: "absorb patterns as first-party code, NO runtime dependency."

### What to Absorb from OpenAlgo

| OpenAlgo Component | Absorb Into | How |
|-------------------|-------------|-----|
| Broker adapter pattern (plugin.json discovery, standardized module structure) | `integration/` | Copy pattern, implement for Dhan as first-party |
| Dhan adapter (auth_api, order_api, data mapping, streaming) | `integration/dhan/` | Copy code, adapt to our interfaces, mark origin |
| Order validation (exchanges, actions, price types, product types) | `integration/` | Copy constants and validation logic |
| WebSocket architecture concept (broker WS → internal bus → consumer) | `integration/dhan/` | Implement as first-party asyncio pattern, not ZMQ subprocess |
| Options Tools (Option Chain, IV Smile, Max Pain, GEX, Vol Surface) | `intelligence/options/` | Study and reimplement in our options intelligence |

### What to Delegate to Absorbed Code

- Order validation for NSE/BSE exchanges, actions, price types (already done well in OpenAlgo)
- Dhan order mapping (DhanHQ order format → standard order model)
- Broker adapter interface pattern (proven in OpenAlgo's multi-broker design)

### What to NEVER Build from Scratch

- Order validation constants for Indian exchanges (NSE/BSE) — already exists in OpenAlgo
- Broker adapter interface pattern — proven in OpenAlgo
- Dhan order mapping (DhanHQ order format → standard order model) — adapt from OpenAlgo's Dhan adapter

### What Should Remain Independent from OpenAlgo

- **All core domain models** — our own frozen dataclasses
- **All intelligence** — signal engine, regime, options intelligence
- **All execution logic** — order lifecycle, position management
- **All learning** — outcome tracking, walkforward, calibration
- **All UI** — web-based terminal
- **All storage** — our own DuckDB + SQLite schema
- **All config** — our own YAML + env system

### How to Structure the Code So OpenAlgo Is Used Heavily Without Becoming a Tangle

1. Absorbed code lives in `integration/_absorbed/` with clear origin markers
2. Core domain and intelligence have ZERO imports from absorbed code
3. Absorbed code is adapted to implement our `core/interfaces/` protocols
4. When OpenAlgo publishes changes, we review the diff and decide: absorb, skip, or adapt
5. No `import openalgo` anywhere in our codebase — ever
6. DhanHQ-py remains a pip dependency (library, acceptable) — it's NOT an external service

---
