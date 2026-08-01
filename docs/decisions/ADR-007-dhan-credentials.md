# ADR-007: Dhan Single-Primary + Data-Fallback Credentials

## Status
Accepted (2026-08-01). Corrects the v1 blueprint's "dual credentials required (error 806)" claim.

## Context
Verified against DhanHQ-py 2.2.0 (local) and upstream main: ONE `DhanContext(client_id, access_token)` serves trading REST, historical data, and the market-feed WS. The SDK's own examples use a single token everywhere. Error 806 on the feed is the SDK's disconnect message "Subscribe to Data APIs to continue" — an account entitlement, not a credential-mixing error. A separate Data-API token path exists (`auth.dhan.co/app/generateAccessToken` with PIN+TOTP, no app credentials).

## Decision
1. Primary model: single credential (client_id + OAuth consent token) for trading + data + feed — matches the SDK design.
2. Optional fallback: a second `data_access_token` slot (provisioned via PIN+TOTP generateAccessToken) used if the feed rejects the consent token.
3. 806 is surfaced as an actionable entitlement error in setup/health, not a silent failure or a credential error.
4. Token lifecycle owned by `SessionHealth` (auto-renew via `renew_token`; SDK does not do this).
5. Feed subscription uses v2 request codes 15/17/21 (the current `DhanDataAdapter` passes 2/8 — a latent bug fixed in Phase 2).

## Consequences
- Setup wizard stays 3-step single-credential; fallback slot only appears when needed.
- v1's dual-credential section is archived; all docs now state the corrected model.
