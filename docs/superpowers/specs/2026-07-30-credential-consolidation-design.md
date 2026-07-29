# Single Credential Consolidation

## Problem
ShettyXtreme currently requires TWO Dhan API credentials (trading + data), forcing users to create two apps in the Dhan Developer Portal and complete two separate OAuth flows. DhanHQ-py (the upstream library) uses a single `DhanContext(client_id, access_token)` for all APIs — proving a single app with both "Trading" and "Market Data" capabilities works fine.

## Impact

| Before (dual) | After (single) |
|---|---|
| 10 credential fields | 6 fields |
| 9 auth endpoints | 6 endpoints |
| 4-step setup wizard | 3-step wizard |
| User creates 2 Dhan apps | User creates 1 Dhan app |
| 2 OAuth flows | 1 OAuth flow |

## Files Changed

| File | Change |
|---|---|
| `credential_store.py` | Merge `trading_*`/`data_*` → single set; add migration |
| `config_manager.py` | Remove `dhan_trading_*`, `dhan_data_*` fields |
| `validator.py` | Remove `validate_trading`/`validate_data` duality |
| `auth_router.py` | Collapse 9 endpoints → 6 |
| `setup.html` | 4-step → 3-step wizard |
| `test_credential_store.py` | Remove data tests, rename |
| `test_auth_router.py` | Remove data endpoint tests |

## Preserved Unchanged
- `dhan_oauth.py` — already single-purpose, only state param removed
- `trading_adapter.py` — already uses `DhanContext(client_id, access_token)`
- `data_adapter.py` — already uses `DhanContext(client_id, access_token)`

## Migration
`CredentialStore.load()` checks for old `trading_api_key` key → transforms payload in-memory, saves new format, returns migrated store

## Risks
1. **Error 806** if user's Dhan app lacks Market Data capability — mitigated by setup instructions: "Enable BOTH capabilities in your single Dhan app"
2. **Old credentials.enc** silently loads empty — mitigated by migration path
3. **External scripts reading `data_api_key`** — ConfigManager silently ignores unknown env vars

## Tests
All existing tests updated to remove dual paths. No new test coverage needed (same logic, fewer cases).
