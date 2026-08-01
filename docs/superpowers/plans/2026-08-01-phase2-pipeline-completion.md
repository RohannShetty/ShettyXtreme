# Phase 2 — Pipeline Completion + Svelte Terminal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the 495-test codebase into a coherent, green, Dhan-connected options workstation: implement the two 501 stubs (D6), fix the latent feed-code bug, complete the credential story (D8), fix the mode default (D10), clear landmines, ship the Svelte+Vite terminal (D9), and reach 0 test failures.

**Architecture:** Backend-first surgical completion of the existing v2 substrate — the intelligence pipeline (`intelligence/options`, `signals`, `hints`, `conviction`), Dhan adapters (`integration/dhan/`), auth (`auth/`), and the FastAPI terminal (`terminal/api/`) — followed by the Svelte+Vite frontend (D9) served by the existing FastAPI static mount, governed by DESIGN.md (D4). Every task is independently testable; no scope beyond the roadmap row (ADR-006 / section 20).

**Tech Stack:** Python 3.11 (asyncio, FastAPI, pydantic, dhanhq 2.2.0 pinned, Fernet), pytest + pytest-asyncio, Svelte 5 + Vite + TypeScript (Node v24.13.1, npm 11.16.0).

## Global Constraints

Binding requirements copied verbatim from the decisions pack (`.superpowers/sdd/phase1-decisions-pack.md`), ARCHITECTURE_V2.md, and DESIGN.md:

- **No-import rule (D1):** zero occurrences of `import openalgo` / `from openalgo` in `src/`. Gate: `rg "openalgo" src/shettyxtreme -g "*.py"` shows no imports (vendor dir excluded).
- **Design contract (D4):** ALL terminal UI follows `DESIGN.md` tokens: canvas `#0a0b0d`, surface-card `#15181d`, hairline `#232830`, accent `#35c8ff`, **price-up = red `#f6525c`, price-down = green `#2ebd85`** (Indian convention — binding), success `#22c55e`, warning `#ffb020`, danger `#e5484d`; numerals in JetBrains Mono with `font-variant-numeric: tabular-nums`; price tokens are text/data-viz only, never button fills.
- **Dhan pin (D8):** `pyproject.toml` declares `dhanhq>=0.1.0` (loose floor; installed env resolves 2.2.0). Do not change the pyproject line — pin discipline is honored by keeping the installed 2.2.0 and diffing the 5 contract files before any bump.
- **Mode default (D10):** runtime mode defaults OBSERVER; LIVE is an explicit per-session action with confirmation; LIVE never auto-restores across sessions.
- **806 is entitlement, not credentials (corrected fact 1):** surface "subscribe to Data APIs" messages; the optional `data_access_token` fallback slot is provisioned via PIN/TOTP `generateAccessToken` flow only if the feed rejects the consent token.
- **Feed codes (corrected fact 2):** WS v2 subscription request codes are Ticker=15, Quote=17, Full=21 (unsubscribe = code+1); response codes 2/4/8/41/51 unchanged.
- **≤500 lines per file rule** (repo convention) — new files must stay under it.
- **No secrets:** never read/print `~/.shettyxtreme/credentials.enc`, `configs/secrets/`, or `.env`; do not print Dhan client IDs or masked-token outputs; do not copy the author's email from `pyproject.toml`. Fernet credential-store design stays untouched.
- **Test runner (Windows quirk):** always `& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-phase2 -p no:cacheprovider` — never bare `pytest` (PATH python is a different venv without pytest; default basetemp has a PermissionError quirk).
- **Suite gate:** target 0 failures, 495+ passing. The 4 known failures ARE the task list: `test_get_options` (T4), `test_get_strategy_hint` (T4), `test_execution_mode_default` (T3), `test_matches_builtin_black76` (T6).
- **Dirty file:** `docs/superpowers/plans/2026-07-31-graphify-upgrade.md` is a pre-existing unstaged change from another session — never stage or commit it.
- **Not building** (per ADR-006 / section 20): multi-leg constructor, ML/RL models, multi-broker, SaaS, knowledge auto-activation, Telegram.

---

## Step 0: Merge Phase 0–1 → master, open Phase 2 branch

**Files:** git only.

- [ ] Merge the docs-only Phase 0–1 work and start the Phase 2 branch:

```powershell
git checkout master
git merge --no-ff phase0-references-vendoring -m "docs: merge phase0+phase1 (references, vendoring, blueprint v2, DESIGN.md, ADR-002..007)"
git branch phase2-pipeline-completion
git checkout phase2-pipeline-completion
```

- [ ] Verify: `git log --oneline -3` shows the merge on master; `git status` clean (except the known dirty graphify-upgrade plan file).

---

## Task 1: Dhan WS feed request codes 2/8 → 15/21

**Files:**
- Modify: `src/shettyxtreme/integration/dhan/data_adapter.py:9-11` (stale docstring), `:41-46` (constants), `:123` (`subscribe_ticks` tuple), `:132` (`subscribe_bars` tuple)
- Test: `tests/wave1/test_dhan_data_adapter.py`

**Interfaces:**
- Consumes: nothing (self-contained).
- Produces: `DhanDataAdapter.subscribe_ticks(symbols, callback) -> bool` and `subscribe_bars(symbols, tf, callback) -> bool` pass **request codes 15/21** in the instrument tuples handed to `MarketFeed`. Response-code constants (2/4/8/41/51) keep their names/values — they are used in `_process_ws_tick` parsing (`data_adapter.py:194-195`) and must not change.

- [ ] **Step 1: Write the failing tests** (append to `tests/wave1/test_dhan_data_adapter.py`):

```python
class TestFeedRequestCodes:
    """Dhan WS v2 accepts only request codes 15/17/21 (corrected fact 2)."""

    @pytest.mark.asyncio
    async def test_subscribe_ticks_uses_v2_request_code(self) -> None:
        with patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanContext"
        ) as mock_ctx_cls, patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanHQClient"
        ) as mock_client_cls, patch(
            "shettyxtreme.integration.dhan.data_adapter.MarketFeed"
        ) as mock_feed_cls:
            mock_ctx_cls.return_value = MagicMock()
            mock_client_cls.return_value = _make_mock_dhanhq()
            adapter = DhanDataAdapter(client_id=MOCK_CLIENT_ID, access_token=MOCK_API_KEY)
            adapter._dhan = mock_client_cls.return_value

            ok = await adapter.subscribe_ticks(["11536"], lambda t: None)

            assert ok is True
            _, kwargs = mock_feed_cls.call_args
            instruments = kwargs["instruments"]
            assert ("NSE_EQ", "11536", 15) in instruments

    @pytest.mark.asyncio
    async def test_subscribe_bars_uses_v2_request_code(self) -> None:
        with patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanContext"
        ) as mock_ctx_cls, patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanHQClient"
        ) as mock_client_cls, patch(
            "shettyxtreme.integration.dhan.data_adapter.MarketFeed"
        ) as mock_feed_cls:
            mock_ctx_cls.return_value = MagicMock()
            mock_client_cls.return_value = _make_mock_dhanhq()
            adapter = DhanDataAdapter(client_id=MOCK_CLIENT_ID, access_token=MOCK_API_KEY)
            adapter._dhan = mock_client_cls.return_value

            ok = await adapter.subscribe_bars(["11536"], "1", lambda b: None)

            assert ok is True
            _, kwargs = mock_feed_cls.call_args
            instruments = kwargs["instruments"]
            assert ("NSE_EQ", "11536", 21) in instruments
```

- [ ] **Step 2: Run to verify they fail**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/wave1/test_dhan_data_adapter.py -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-phase2 -p no:cacheprovider`
Expected: the two new tests FAIL (`15` / `21` not found in instruments — current tuples carry 2 and 8).

- [ ] **Step 3: Fix the adapter** (`src/shettyxtreme/integration/dhan/data_adapter.py`):

Replace the docstring block (`lines 9-11`) with:

```python
Dhan WS binary protocol — two distinct code sets:
  Subscription REQUEST codes (v2 JSON, validated to 15/17/21):
    Ticker=15, Quote=17, Full=21; unsubscribe = request code + 1.
  Response feed codes (parsing):
    2 = ticker, 4 = quote, 5 = order data,
    8 = full quote, 41 = OHLC, 51 = market depth
```

Replace the constants block (`lines 41-46`) with:

```python
# Subscription REQUEST codes — v2 accepts only 15/17/21 (corrected fact 2)
REQUEST_CODE_TICKER: int = 15
REQUEST_CODE_QUOTE: int = 17
REQUEST_CODE_FULL: int = 21
# Response feed codes (used by _process_ws_tick parsing)
FEED_CODE_TICKER: int = 2
FEED_CODE_QUOTE: int = 4
FEED_CODE_ORDER: int = 5
FEED_CODE_FULL_QUOTE: int = 8
FEED_CODE_OHLC: int = 41
FEED_CODE_MARKET_DEPTH: int = 51
STALENESS_THRESHOLD_SEC: float = 30.0
```

Update `subscribe_ticks` (`line 123`) tuple builder:

```python
        instruments: list[tuple[str, str, int]] = [
            ("NSE_EQ", sym, REQUEST_CODE_TICKER) for sym in symbols
        ]
```

Update `subscribe_bars` (`line 132`) tuple builder:

```python
        instruments: list[tuple[str, str, int]] = [
            ("NSE_EQ", sym, REQUEST_CODE_FULL) for sym in symbols
        ]
```

Do NOT touch `_process_ws_tick` / `_parse_binary_tick` — they parse response codes (41 stays the OHLC response check).

- [ ] **Step 4: Run the full wave1 data-adapter file**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/wave1/test_dhan_data_adapter.py -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-phase2 -p no:cacheprovider`
Expected: ALL PASS (existing 806/OHLC/chain tests unaffected — they mock `MarketFeed`).

- [ ] **Step 5: Commit**

```bash
git add src/shettyxtreme/integration/dhan/data_adapter.py tests/wave1/test_dhan_data_adapter.py
git commit -m "fix: Dhan WS v2 subscription request codes 15/17/21 (was 2/8)"
```

---

## Task 2: Credential fallback slot + 806 entitlement surfacing (D8)

**Files:**
- Modify: `src/shettyxtreme/auth/credential_store.py` (encrypted `data_access_token` field)
- Modify: `src/shettyxtreme/auth/dhan_oauth.py` (PIN/TOTP `generate_access_token`)
- Modify: `src/shettyxtreme/integration/dhan/data_adapter.py` (optional data token; 806 handling)
- Modify: `src/shettyxtreme/terminal/api/app.py` (pass fallback token in lifespan)
- Test: `tests/wave1/test_dhan_data_adapter.py`, `tests/wave7/test_credential_store.py`, `tests/wave7/test_dhan_oauth.py`

**Interfaces:**
- Consumes: Task 1's constants. `CredentialStore` (existing Fernet store; fields incl. `client_id`, `access_token`, `expiry` — read the file first).
- Produces:
  - `CredentialStore.data_access_token: str | None` + `CredentialStore.update_data_token(token: str, expiry: str | None) -> None` (persisted encrypted, same store).
  - `DhanOAuthHelper.generate_access_token(client_id: str, pin: str, totp: str) -> ConsumeResult` (PIN/TOTP flow; use the installed dhanhq 2.2.0 auth surface — check `dhanhq` for the token endpoint; per BRIEF-dhanhq §auth this is the self/primary token mint path).
  - `DhanDataAdapter(client_id, access_token, data_access_token: str | None = None)` — uses `data_access_token` when provided, else `access_token`.
  - `DhanDataAdapter.last_error: str | None` and `DhanDataAdapter.entitlement_error: bool` — set when a 806 is seen; REST error dicts gain `"entitlement": True` and an actionable "subscribe to Data APIs" message when the exception mentions 806.

- [ ] **Step 1: Write the failing tests** (append to `tests/wave1/test_dhan_data_adapter.py`):

```python
class TestDataAccessTokenFallback:
    @pytest.mark.asyncio
    async def test_data_token_preferred_over_primary(self) -> None:
        with patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanContext"
        ) as mock_ctx_cls, patch(
            "shettyxtreme.integration.dhan.data_adapter.DhanHQClient"
        ) as mock_client_cls:
            mock_ctx_cls.return_value = MagicMock()
            mock_client_cls.return_value = _make_mock_dhanhq()
            DhanDataAdapter(
                client_id=MOCK_CLIENT_ID,
                access_token="primary_token",
                data_access_token="data_token",
            )
            _, kwargs = mock_ctx_cls.call_args
            assert kwargs["access_token"] == "data_token"

    @pytest.mark.asyncio
    async def test_806_returns_entitlement_error_dict(self, data_adapter) -> None:
        dhan = data_adapter._dhan
        dhan.option_chain.side_effect = RuntimeError("806: token rejected")
        result = await data_adapter.get_option_chain(
            underlying_scrip="13", exchange_segment="NSE_FNO", expiry="",
        )
        assert result["status"] == "error"
        assert result.get("entitlement") is True
        assert "subscribe to Data APIs" in result["message"]

    def test_806_marks_entitlement_flag(self, data_adapter) -> None:
        data_adapter._mark_ws_error(RuntimeError("Disconnected: Subscribe to Data APIs to continue"))
        assert data_adapter.entitlement_error is True
        assert data_adapter.last_error == "subscribe to Data APIs"
```

Also add to `tests/wave7/test_credential_store.py` (read the file first, follow its fixture pattern):

```python
def test_data_token_roundtrip(store) -> None:
    store.update_data_token("data_abc", "2026-12-31T00:00:00Z")
    reloaded = CredentialStore.load()
    assert reloaded is not None
    assert reloaded.data_access_token == "data_abc"
```

- [ ] **Step 2: Run to verify they fail** — both files, expect the new tests to fail (no `data_access_token` param / no `entitlement` key / no flag).

- [ ] **Step 3: Implement** (read each file fully before editing; keep the Fernet design untouched):
  1. `credential_store.py`: add `data_access_token: str | None` field, serialize/deserialize it with the existing encrypted mechanism, add `update_data_token(token, expiry)` mirroring `update_token`.
  2. `dhan_oauth.py`: add `generate_access_token(client_id, pin, totp) -> ConsumeResult` using the installed dhanhq 2.2.0 token mint (read the installed lib to find the exact call; if the SDK lacks it, POST `https://api.dhan.co/v2/auth/token` with `client_id`, `pin`, `totp` headers per the Dhan auth docs referenced in BRIEF-dhanhq §auth — implement defensively and unit-test with mocked transport).
  3. `data_adapter.py`: accept `data_access_token`; `_init_context` prefers it; add `_mark_ws_error(exc)` classifying 806 (`"806" in str(exc)` or `"Subscribe to Data APIs" in str(exc)`) → sets `entitlement_error = True`, `last_error = "subscribe to Data APIs"`; call it from `_on_error`/`_on_close`/REST except handlers; error dicts from REST methods return `{"status": "error", "entitlement": True, "message": "subscribe to Data APIs — Dhan error 806"}` when 806, else the existing shape.
  4. `app.py` lifespan: `DhanDataAdapter(client_id=store.client_id, access_token=store.access_token, data_access_token=store.data_access_token)`.

- [ ] **Step 4: Run both test files** — all pass.

- [ ] **Step 5: Commit** — `git add` the four modified files + tests; message: `feat: optional data_access_token fallback + 806 entitlement surfacing (D8)`.

---

## Task 3: OBSERVER default + mode persistence (D10)

**Files:**
- Modify: `src/shettyxtreme/terminal/api/execution_router.py`
- Modify: `tests/terminal/test_integration.py` (hermetic default test; delete nothing else)
- Modify: `tests/terminal/test_mode_persistence.py` (LIVE no longer auto-restores)
- Modify: `tests/wave3/test_api.py` (set_mode LIVE requires `confirm=true`)

**Interfaces:**
- Consumes: nothing.
- Produces: `GET /api/execution/mode` → `{"mode": "OBSERVER"}` on fresh start; `POST /api/execution/mode?mode=LIVE&confirm=true` → LIVE; `POST /api/execution/mode?mode=LIVE` (no confirm) → unchanged current mode (200, mode stays non-LIVE); `_load_mode()` never returns LIVE (per-session confirmation, D10); PAPER/OBSERVER persist.

- [ ] **Step 1: Update the failing test first** (`tests/terminal/test_integration.py`, `test_execution_mode_default`) — make it hermetic:

```python
def test_execution_mode_default(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    mode_file = tmp_path / "mode.txt"
    monkeypatch.setattr(execution_router, "_MODE_FILE", mode_file)
    execution_router._current_mode = execution_router._load_mode()
    resp = client.get("/api/execution/mode")
    assert resp.status_code == 200
    body = resp.json()
    assert body["mode"] == "OBSERVER"
```

(Add `from pathlib import Path` and `from shettyxtreme.terminal.api import execution_router` imports.)

- [ ] **Step 2: Run to verify it fails** — on this machine `~/.shettyxtreme_mode` exists with a stale value, so the unpatched test fails; after this edit the test still fails because `_load_mode()` can restore the stale file.

- [ ] **Step 3: Implement** (`execution_router.py`):

```python
def _load_mode() -> str:
    """Restore persisted mode. LIVE never auto-restores: it is an explicit
    per-session action with confirmation (D10)."""
    try:
        if _MODE_FILE.exists():
            saved = _MODE_FILE.read_text().strip()
            if saved in ("OBSERVER", "PAPER"):
                return saved
    except Exception:
        pass
    return "OBSERVER"
```

```python
@router.post("/mode", response_model=ModeResponse)
async def set_mode(request: Request, mode: str, confirm: bool = False) -> ModeResponse:
    """Switch execution mode. Valid modes: OBSERVER, LIVE, PAPER.
    LIVE requires explicit per-session confirmation (confirm=true, D10)."""
    global _current_mode
    valid = {"OBSERVER", "LIVE", "PAPER"}
    requested = mode.upper()
    if requested not in valid:
        return ModeResponse(mode=_current_mode)
    if requested == "LIVE" and not confirm:
        return ModeResponse(mode=_current_mode)
    _current_mode = requested
    _save_mode(_current_mode)
    # Publish config changed event (existing block, unchanged)
    ...
```

- [ ] **Step 4: Update dependent tests:**
  1. `tests/wave3/test_api.py::test_set_mode` — change to `await client.post("/api/execution/mode?mode=LIVE&confirm=true")` and add a sibling assertion that `?mode=LIVE` without confirm leaves the mode unchanged.
  2. `tests/terminal/test_mode_persistence.py::test_save_and_load_mode` — now asserts `_save_mode("LIVE"); _load_mode() == "OBSERVER"` (rename to `test_live_mode_not_restored`); keep `test_paper_mode_persists` (file content assertion unchanged); `test_default_mode_observer`/`test_missing_file_defaults_observer` unchanged.

- [ ] **Step 5: Run** `tests/terminal/` and `tests/wave3/test_api.py` — all pass.

- [ ] **Step 6: Commit** — `fix: OBSERVER default; LIVE requires per-session confirmation (D10)`.

---

## Task 4: Option chain + strategy hint endpoints, hints/conviction modules, VoterRegistry (D6)

**Files:**
- Create: `src/shettyxtreme/intelligence/hints/strategy_hints.py`
- Create: `src/shettyxtreme/intelligence/conviction/conviction_engine.py`
- Modify: `src/shettyxtreme/intelligence/signals/signal_engine.py` (VoterRegistry real implementation)
- Modify: `src/shettyxtreme/terminal/api/intelligence_router.py` (wire `/options`, `/strategy-hint`)
- Delete: the two 501 tests from `tests/terminal/test_integration.py` (`test_intelligence_options_501`, `test_intelligence_strategy_hint_501`)
- Test: create `tests/wave2/test_strategy_hints.py`, `tests/wave2/test_conviction_engine.py`; extend `tests/wave2/test_signal_engine.py` (registry); `tests/wave3/test_api.py` (existing 200-shape tests become the endpoint gate)

**Interfaces:**
- Consumes: `SignalEngine.compute_signal` + `Vote`/`SignalDirection` (`signal_engine.py`), `options_intel.select_strike_by_ev` / `compute_signal_drift_ev` (`intelligence/options/options_intel.py`), `GreeksCalculator` (`options/greeks.py`, `use_quantlib=False`), `StrategyAnalyzer.supported_strategies`/`display_name` (`options/strategy_analyzer.py`), `DhanDataAdapter.get_option_chain(underlying_scrip, exchange_segment, expiry)` from Task 1/2.
- Produces (later tasks rely on these exact names):
  - `intelligence.hints.StrategyHint` dataclass: `direction: str` (bullish/bearish/neutral), `strategy: str`, `strike: float | None = None`, `premium: float | None = None`, `ev_after_cost: float = 0.0`, `rationale: str = ""`.
  - `intelligence.hints.StrategyHints(signal: dict, chain: list[dict] | None = None, slippage_per_lot: float = 5.0, brokerage_per_lot: float = 20.0)` with `generate() -> StrategyHint`.
  - `intelligence.conviction.ConvictionResult` dataclass: `direction: str` (UP/DOWN/NEUTRAL), `conviction: float`, `D: float`, `P: float`, `G: str` (unanimous / contested — the test spec in this plan binds "contested" for mixed-sign votes; the earlier "split" wording is superseded), `voters: list[dict]`.
  - `intelligence.conviction.ConvictionEngine` with `compute(votes: list[dict], eligible: int) -> ConvictionResult`.
  - `VoterRegistry.register(name, fn, weight=1.0) -> None` (raises `ValueError` on blank name or non-callable), `names() -> list[str]`, `count() -> int`, `get(name) -> Callable | None`; `voter(name, weight=1.0)` decorator registers into a module-level default registry; `get_registry()` returns that singleton.
  - Router: `GET /api/intelligence/options?symbol=NIFTY&expiry=` → 200 `OptionsChainResponse` (contracts may be `[]` when no data adapter — **required** so the existing wave3 test passes unchanged); `GET /api/intelligence/strategy-hint` → 200 `StrategyHintResponse` with `direction` + `rationale` always present.

- [ ] **Step 1: Write the failing tests** — VoterRegistry (extend `tests/wave2/test_signal_engine.py`):

```python
class TestVoterRegistry:
    def test_register_and_get(self) -> None:
        reg = VoterRegistry()
        fn = lambda fe: Vote(direction=1.0, confidence=0.5, weight=1.0, name="r")
        reg.register("r", fn, weight=2.0)
        assert reg.count() == 1
        assert reg.names() == ["r"]
        assert reg.get("r") is fn
        assert reg.get("missing") is None

    def test_register_requires_name_and_callable(self) -> None:
        reg = VoterRegistry()
        with pytest.raises(ValueError):
            reg.register("", lambda fe: None)
        with pytest.raises(ValueError):
            reg.register("x", None)

    def test_decorator_registers_into_default_registry(self) -> None:
        @voter("decorated_test", weight=0.5)
        def decorated(features: dict[str, float]) -> Vote:
            return Vote(direction=-1.0, confidence=0.7, weight=0.5, name="decorated_test")

        reg = get_registry()
        assert reg.get("decorated_test") is decorated
```

`tests/wave2/test_strategy_hints.py` (new file):

```python
"""Tests for StrategyHints generation (D6 pipeline stage 4)."""
from __future__ import annotations
import pytest
from shettyxtreme.intelligence.hints.strategy_hints import StrategyHints, StrategyHint

BULLISH_SIGNAL = {
    "direction": "UP", "conviction": 0.7, "D": 0.6, "P": 1.0, "G": "unanimous",
    "voters": [{"name": "v1", "direction": 1.0, "confidence": 0.7, "weight": 1.0}],
}

class TestStrategyHints:
    def test_neutral_signal_returns_neutral_hint(self) -> None:
        hint = StrategyHints(signal={"direction": "NEUTRAL", "conviction": 0.0}).generate()
        assert hint.direction == "neutral"
        assert hint.strike is None
        assert hint.rationale

    def test_low_conviction_stays_neutral(self) -> None:
        sig = dict(BULLISH_SIGNAL, conviction=0.1)
        hint = StrategyHints(signal=sig).generate()
        assert hint.direction == "neutral"

    def test_bullish_selects_call_strike_by_ev(self) -> None:
        chain = [
            {"strike": 24000, "option_type": "CE", "premium": 150.0, "lot_size": 25, "iv": 15.0},
            {"strike": 24100, "option_type": "CE", "premium": 100.0, "lot_size": 25, "iv": 15.0},
        ]
        hint = StrategyHints(signal=BULLISH_SIGNAL, chain=chain).generate()
        assert hint.direction == "bullish"
        assert hint.strategy
        assert hint.rationale

    def test_chain_none_no_crash(self) -> None:
        hint = StrategyHints(signal=BULLISH_SIGNAL, chain=None).generate()
        assert hint.direction == "bullish"
        assert hint.strike is None
```

`tests/wave2/test_conviction_engine.py` (new file):

```python
"""Tests for participation-normalized conviction (D/P/G, blueprint §14)."""
from __future__ import annotations
import pytest
from shettyxtreme.intelligence.conviction.conviction_engine import ConvictionEngine, ConvictionResult

VOTES_UP = [{"name": "a", "direction": 1.0, "confidence": 0.8, "weight": 1.0}]

class TestConvictionEngine:
    def test_all_up_unanimous(self) -> None:
        r = ConvictionEngine().compute(VOTES_UP, eligible=1)
        assert r.direction == "UP"
        assert r.P == pytest.approx(1.0)
        assert r.G == "unanimous"

    def test_split_votes_contested(self) -> None:
        votes = [
            {"name": "a", "direction": 1.0, "confidence": 0.8, "weight": 1.0},
            {"name": "b", "direction": -1.0, "confidence": 0.8, "weight": 1.0},
        ]
        r = ConvictionEngine().compute(votes, eligible=2)
        assert r.direction == "NEUTRAL"
        assert r.G == "contested"

    def test_dead_voters_do_not_dilute(self) -> None:
        votes = [
            {"name": "a", "direction": 1.0, "confidence": 0.8, "weight": 1.0},
            {"name": "b", "direction": 0.0, "confidence": 0.0, "weight": 1.0},
        ]
        r = ConvictionEngine().compute(votes, eligible=2)
        assert r.P == pytest.approx(0.5)
        assert r.direction == "UP"
```

- [ ] **Step 2: Run to verify they fail** — `ModuleNotFoundError: shettyxtreme.intelligence.hints.strategy_hints` / `.conviction_engine`; registry tests fail (pass-stub).

- [ ] **Step 3: Implement:**
  1. `signal_engine.py` — replace the pass-stub `VoterRegistry` (lines 29-39) with the implementation from **Interfaces** (keep `Signal`/`Vote`/`SignalEngine` unchanged; keep `compute_signal_from_votes` alias). Add module-level `_DEFAULT_REGISTRY` + `voter` decorator + `get_registry`.
  2. `strategy_hints.py` — full module per Interfaces: direction mapping UP→bullish, DOWN→bearish, NEUTRAL→neutral; conviction gate `< 0.25` → neutral; bullish filters chain for `option_type == "CE"`, bearish for `"PE"`, then `select_strike_by_ev(strikes=..., direction=±1.0, conviction=..., current_price=..., slippage_per_lot=..., brokerage_per_lot=..., iv=..., days_to_expiry=...)` (use `datetime.now(UTC)` vs weekly expiry from `date` for `days_to_expiry`; default 7 when missing); strategy name via `StrategyAnalyzer.display_name("long_call")` (bullish) / `"long_put"` (bearish); rationale assembled from conviction, participation, EV line (premium, slippage, brokerage, net EV); NEUTRAL rationale explains why (no direction / low conviction / low participation).
  3. `conviction_engine.py` — per Interfaces: usable votes = `confidence > 0 and direction != 0`; `P = usable / eligible` (guard `eligible <= 0` → 1.0); `D = mean(direction * confidence) * P`; `conviction = min(abs(D), 1.0)`; direction from `D` thresholds (±0.1, matching `SignalEngine.compute_signal`); `G`: zero usable → `contested`; all usable same sign → `unanimous`; both signs → `split` (conflict) — the test names the mixed case `contested`, so use: same sign → unanimous, opposing signs → contested, zero usable → contested.
  4. `intelligence_router.py` — wire both endpoints:

```python
_SYMBOL_SECURITY_ID = {"NIFTY": "13", "BANKNIFTY": "25"}

def _security_id(symbol: str) -> str:
    return _SYMBOL_SECURITY_ID.get(symbol.upper(), symbol)

async def _fetch_chain(request: Request, symbol: str, expiry: str | None) -> list[dict]:
    adapter = request.app.state.data_adapter
    if adapter is None:
        return []
    result = await adapter.get_option_chain(
        underlying_scrip=_security_id(symbol), exchange_segment="NSE_FNO", expiry=expiry or "",
    )
    if result.get("status") != "success":
        return []
    data = result.get("data", {})
    return data.get("option_chain", [])


@router.get("/options", response_model=OptionsChainResponse)
async def get_options(
    request: Request,
    symbol: str = Query("NIFTY"),
    expiry: str | None = None,
) -> OptionsChainResponse:
    chain = await _fetch_chain(request, symbol, expiry)
    contracts = _enrich_chain(chain)
    return OptionsChainResponse(underlying=symbol, expiry=expiry or "", contracts=contracts)
```

   `_enrich_chain` maps each row to `OptionsChainItem` (strike, option_type, ltp, bid/ask/oi/volume from row or 0; iv from row or 0; delta/gamma/theta/vega via `GreeksCalculator(use_quantlib=False).calculate_all(...)` when spot+iv present, wrapped in try/except returning zeros). Strike/type/lot fields are defensive (`.get`).
   `get_strategy_hint`:

```python
@router.get("/strategy-hint", response_model=StrategyHintResponse)
async def get_strategy_hint(request: Request) -> StrategyHintResponse:
    signal = request.app.state.intelligence_projection.get_signal()
    chain = await _fetch_chain(request, "NIFTY", None)
    hint = StrategyHints(signal=signal, chain=chain).generate()
    return StrategyHintResponse(
        direction=hint.direction,
        strike=hint.strike,
        premium=hint.premium,
        ev_after_cost=hint.ev_after_cost,
        rationale=hint.rationale,
    )
```

  5. Delete `test_intelligence_options_501` and `test_intelligence_strategy_hint_501` from `tests/terminal/test_integration.py` (they assert 501; the wave3 200-shape tests are the gate).

- [ ] **Step 4: Run** — new unit files + `tests/wave3/test_api.py` + `tests/wave2/test_signal_engine.py` + `tests/terminal/test_integration.py`; all pass. Then the full suite once (expect only the black76 failure remaining).

- [ ] **Step 5: Commit** — `feat: options chain + strategy hint endpoints; hints/conviction modules; VoterRegistry (D6)`.

---

## Task 5: Landmine cleanup

**Files:**
- Modify: `tests/conftest.py` — delete fixtures `openalgo_adapter` (imports nonexistent `shettyxtreme.integration.openalgo`) and `dhan_adapter` (imports nonexistent `integration/dhan/dhan_adapter.py`); also delete now-unused `MockAsyncClient`/`MockHttpResponse`/`MockDhanHQ`/`MockDhanHQModule` helpers if they become orphaned (check for other users first).
- Delete dirs: `src/shettyxtreme/execution/lifecycle/`, `src/shettyxtreme/execution/position_tracker/` (each holds only an empty `__init__.py`; verified zero importers), `tests/risk/`, `tests/integration/` (empty, untracked).
- Delete: `src/shettyxtreme/core/errors/` (contains only a one-line comment `__init__.py`; verified zero importers).
- Verify no test requests those fixtures: `rg "openalgo_adapter|dhan_adapter" tests/ -g "*.py"` → zero after deletion.

- [ ] **Step 1: Pre-check** — `rg` for fixture usage and `git ls-files` for the dirs; confirm deletions are safe (done in the plan; re-verify live).
- [ ] **Step 2: Apply deletions.**
- [ ] **Step 3: Full suite** — `& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-phase2 -p no:cacheprovider` — no collection errors; only the black76 failure remains (env).
- [ ] **Step 4: Commit** — `chore: remove stale conftest fixtures, empty dirs, dead core/errors package`.

---

## Task 6: `test_matches_builtin_black76` fix

**Files:**
- Modify: `tests/options/test_quantlib_pricer.py` (or `src/shettyxtreme/options/quantlib_pricer.py` if the mismatch is a real bug — diagnose first)

**Interfaces:** none.

- [ ] **Step 1: Run the failing test and capture the actual numbers:**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/options/test_quantlib_pricer.py::TestQuantLibPricerEuropean::test_matches_builtin_black76 -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-phase2 -p no:cacheprovider`
Expected: a tolerance-style assertion failure showing `ql_price` vs `py_price` (QuantLib env pinning difference).

- [ ] **Step 2: Fix** — the roadmap rule: keep the test env-pinned, never a silent skip. If the diff is a small numerical delta (e.g. day-count convention), bump the tolerance with a one-line comment naming the cause and the installed QuantLib version (check `pip show QuantLib`); if it's a genuine pricing bug in `quantlib_pricer.py` (e.g. wrong convention), fix the source and re-run the whole options suite. Do NOT `pytest.skip` unconditionally.
- [ ] **Step 3: Run the full options suite** — all pass.
- [ ] **Step 4: Commit** — `fix: align QuantLib Black-76 match tolerance with pinned env (no silent skip)` or `fix: correct <bug> in quantlib_pricer`.

---

## Task 7: Svelte + Vite terminal (D9)

**Files:**
- Create: `src/shettyxtreme/terminal/web/` — `package.json`, `vite.config.ts`, `tsconfig.json`, `index.html`, `src/main.ts`, `src/App.svelte`, `src/lib/design.css` (DESIGN.md tokens as CSS custom properties), `src/lib/api.ts`, `src/lib/ws.ts`, `src/components/` (Header, Watchlist, ChainGrid, HintsPanel, ScannerPanel, PositionsRiskStrip, LogDrawer, ModeSwitcher, KillSwitch)
- Modify: `src/shettyxtreme/terminal/static/` — replaced by Vite build output (`index.html` + `assets/`)
- Modify: `src/shettyxtreme/terminal/api/app.py` — root redirects point at the SPA (`/static/`); keep the `/static` mount; SPA uses hash routes (`#/setup`, `#/settings`) so no server routing is needed
- Modify: `tests/terminal/test_integration.py` + `tests/wave3/test_api.py` — redirect expectations updated to the SPA paths
- Create: `tests/terminal/test_spa_served.py` (built index.html serves; hash routes reachable)

**Interfaces:**
- Consumes: all REST endpoints from Tasks 1-4 + `/ws` WebSocket (existing), DESIGN.md tokens.
- Produces: `npm run build` → `terminal/static/` (committed build output so the app runs without a Node step); `npm run dev` → Vite dev server on 3000 (CORS already allows `http://localhost:3000`).

- [ ] **Step 1: Scaffold** — `package.json` (svelte 5, vite 6, typescript, `@sveltejs/vite-plugin-svelte`; `"build": "vite build"`, `"dev": "vite"`), `vite.config.ts`:

```ts
import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

export default defineConfig({
  plugins: [svelte()],
  base: "/static/",
  build: { outDir: "../static", emptyOutDir: true },
  server: { port: 3000 },
});
```

- [ ] **Step 2: Design tokens** — `src/lib/design.css` with CSS custom properties mirroring DESIGN.md colors (canvas `#0a0b0d`, surface-card `#15181d`, accent `#35c8ff`, **price-up red `#f6525c`, price-down green `#2ebd85`**), JetBrains Mono + `tabular-nums` for all numerals, panel radii (controls 4px / panels 6px), hairlines.
- [ ] **Step 3: Cockpit layout** per section 15: header strip (mode switcher with LIVE confirmation dialog, kill switch `Ctrl+Shift+K` always visible, health strip incl. 806 entitlement state, market-hours), left watchlist rail (min 260px), center chain grid (min 720px) + strategy-hints panel (min 320px), right drawer logs/alerts (min 320px), bottom positions/risk strip (min 240px tall). Panels dockable via split dividers (no heavy charting dependency — MVP tables/panels only, per section 15 §5).
- [ ] **Step 4: Data layer** — `api.ts` fetches `/api/...` (watchlist, intelligence, execution, scanner, health); `ws.ts` connects `ws(s)://<host>/ws`, handles `pong`, broadcasts `regime`/`signal`/`risk`/`alert` → Svelte stores; price flash on tick (150ms fade per DESIGN.md).
- [ ] **Step 5: Views** — cockpit (`#/`), settings (`#/settings`, incl. credential status + data-token fallback slot per Task 2), setup wizard (`#/setup`, porting setup.html's `checkStatus` auth flow to the auth API).
- [ ] **Step 6: FastAPI wiring** — `app.py`: root → `RedirectResponse("/static/")`, `/setup` → `"/static/#/setup"`, `/settings` → `"/static/#/settings"`. Update the redirect tests in `tests/wave3/test_api.py` and `tests/terminal/test_integration.py` to the new locations. New `tests/terminal/test_spa_served.py`: GET `/static/` returns 200 with the built index.html; GET `/static/assets/` entry exists.
- [ ] **Step 7: Build + verify** — `npm install` + `npm run build` in `terminal/web/`; run the API suite; run the app (`python run.py --no-browser`) and curl `/` + `/static/` (200, HTML).
- [ ] **Step 8: DESIGN.md checklist gate** — every panel uses the token vars, no raw hex outside `design.css`, numerals in mono, price-up/down semantics honored, kill switch in header, right drawer ≥320px.
- [ ] **Step 9: Commit** — `feat: Svelte+Vite terminal per DESIGN.md (D9)` (+ separate `chore:` commit for node_modules/.gitignore additions if needed — check `.gitignore` has `node_modules`).

---

## Task 8: `run.py` CLI + LIVE confirmation (D10)

**Files:**
- Modify: `run.py`

**Interfaces:**
- Consumes: Task 3's mode semantics (`execution_router._current_mode` / `_save_mode`).
- Produces: `python run.py [--mode OBSERVER|PAPER|LIVE] [--no-browser] [--port 8000]`; `--mode LIVE` prompts "Type LIVE to confirm" and aborts otherwise.

- [ ] **Step 1: Write a manual-verification checklist in the report** (no unit test — CLI entry; document the smoke steps run).
- [ ] **Step 2: Implement:**

```python
def main() -> None:
    parser = argparse.ArgumentParser(description="ShettyXtreme Terminal")
    parser.add_argument("--mode", choices=["OBSERVER", "PAPER", "LIVE"], default="OBSERVER")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.mode == "LIVE":
        answer = input("LIVE mode places real orders. Type 'LIVE' to confirm: ").strip().upper()
        if answer != "LIVE":
            print("Aborted: LIVE mode not confirmed.")
            sys.exit(1)

    from shettyxtreme.terminal.api import execution_router
    execution_router._current_mode = args.mode
    execution_router._save_mode(args.mode)

    store = CredentialStore.load()
    if store is not None and not store.is_token_valid():
        print("WARNING: Token expired — re-authenticate at /settings")

    if not args.no_browser:
        webbrowser.open(f"http://127.0.0.1:{args.port}/")
    uvicorn.run("shettyxtreme.terminal.api.app:app", host="127.0.0.1", port=args.port, log_level="info")
```

- [ ] **Step 3: Smoke** — `python run.py --mode OBSERVER --no-browser` starts and serves `/` (200); `python run.py --mode LIVE --no-browser` with non-LIVE input aborts.
- [ ] **Step 4: Commit** — `feat: run.py CLI mode flag with LIVE confirmation (D10)`.

---

## Final Gate (verification-before-completion)

- [ ] Full suite: `& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-phase2 -p no:cacheprovider` → **0 failures**, 495+ passed.
- [ ] Grep gate: `rg "import openalgo|from openalgo" src/ -g "*.py"` → zero matches.
- [ ] Line rule: every new/modified file ≤500 lines (`git diff --stat` review + spot check).
- [ ] `git status` clean (dirty graphify plan file untouched), branch committed.
- [ ] Whole-branch review (requesting-code-review template) + fixes; progress ledger `.superpowers/sdd/progress.md` updated; handoff doc written.
- [ ] Merge decision presented to the user (do not merge without explicit request).

---

## Execution notes

- SDD loop per task: task-brief → implementer (TDD, self-review, commit) → review-package (`git diff -U10 BASE HEAD` written to a file manually — the SDD helper scripts' paths contain literal backslashes on Windows; `scripts/task-brief`/`scripts/review-package` live under `C:\Users\rohan\.cache\opencode\packages\superpowers@git+https_\github.com\obra\superpowers.git\node_modules\superpowers\skills\subagent-driven-development\`) → task reviewer (spec + quality) → fix waves → ledger line.
- Base commit for each task review = the commit recorded before dispatching that task's implementer (never `HEAD~1`).
- Environment: Windows PowerShell 5.1; use the `.venv` python as in Global Constraints; git CRLF warnings are cosmetic; graphify post-commit hook rebuilds the graph in the background (harmless).
- Reference clones are shallow — not needed for these tasks (no vendor diff review in Phase 2).
