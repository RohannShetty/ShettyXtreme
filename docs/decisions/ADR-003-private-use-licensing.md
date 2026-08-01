# ADR-003: Private-Use Licensing Posture

## Status
Accepted (2026-08-01).

## Context
ShettyXtreme's LICENSE is Proprietary. Reference licenses: OpenAlgo and FinceptTerminal are AGPL-3.0 (Fincept additionally has a USD 50k damages clause), DhanHQ-py MIT, awesome-design-md MIT, ai-hedge-fund MIT, anthropics/financial-services Apache-2.0, Quant-Developers-Resources unlicensed (link list).

## Decision
1. ShettyXtreme is private-use only (never distributed, sold, or offered as a network service) — AGPL §2 permits non-conveying private use; absorption of AGPL code is legal without publication obligations.
2. Vendored AGPL files keep intact notices + modification dates + the AGPL license text in `vendor/openalgo/LICENSE`.
3. No quarantine ceremony: origin markers + README statements suffice under D2.
4. If distribution is ever contemplated, it is a v3 discussion requiring clean-room rework of every absorbed file.

## Consequences
- Monetization = trading edge + prop-style scale (Section 16), never software sales.
- No SaaS/multi-tenancy/billing anywhere in the architecture.
- Legal boundary is documented in `vendor/openalgo/README.md` and Section 10.
