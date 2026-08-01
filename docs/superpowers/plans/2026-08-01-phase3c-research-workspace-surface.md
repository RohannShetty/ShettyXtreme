# Phase 3C — Research Workspace Full Surface: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the research workspace surface on the 3B core: read-only data tools with mid-run function calling (provider v2), an env-config scheduler, a richer terminal research panel with WS live updates, and brief outcome scoring with `decided_at` surfacing.

**Architecture:** Research-layer (`research/`) owns the tool registry (`tools.py`), provider v2 (`provider.py`), the bounded tool loop (`orchestrator.py`), the scheduler (`scheduler.py`), and scoring (`store.py`) — data injected via a `DataSource` protocol so `research/` never imports `terminal/`. The terminal layer (router + app.py + a `ProjectionDataSource`) wires tools, WS broadcast, and the scheduler under lifespan. The frontend consumes the new endpoints via `postBody` + typed models and renders the 3-region panel (run bar / brief list / detail) with WS topic `research`.

**Tech Stack:** Python 3.11, FastAPI, pydantic v2, sqlite3, httpx (existing), asyncio; Svelte 5 + Vite + TypeScript (existing `terminal/web`).

## Global Constraints

- **D3:** `research/provider.py` is the ONLY LLM-touching module; no LLM output reaches signal/gate/execution; tools are read-only (no order tool exists in the registry — absence beats instruction).
- **D1:** zero `import openalgo` / `from openalgo` in `src/` (grep gate).
- **≤500 lines per file; zero new runtime dependencies** (stdlib + httpx + pydantic + existing only; NO `mcp` package).
- **Suite gate:** 612 passed / 0 failed / **0 skipped** → never shrinks, never skips.
- **Test runner (Windows):** `& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=... -p no:cacheprovider` — never bare `pytest`. Distinct basetemp per concurrent subagent.
- **PYTHONPATH=""** env prefix for all python invocations.
- **Secrets:** `DEEPSEEK_API_KEY` env-only, read at call time. No test calls the real DeepSeek API; `scripts/research_smoke.py` stays env-gated.
- **Dirty file:** `docs/superpowers/plans/2026-07-31-graphify-upgrade.md` — never stage/commit.
- **Commit protocol:** subagents NEVER commit. The coordinator stages and commits per task on branch `phase3c`.
- **Frontend gate:** `npm run check` (svelte-check) 0 errors; `npm run build` at the end produces the committed bundle.

## File Structure

| File | Responsibility | Task |
|---|---|---|
| `src/shettyxtreme/research/provider.py` | v2: `ToolCall`, `ProviderResponse`, `generate(tools=, history=)`; DeepSeek tool-call parsing | 1 |
| `tests/wave8/test_research_provider.py` | Migrate to `ProviderResponse` + new tool-call tests | 1 |
| `src/shettyxtreme/research/tools.py` | `ResearchTool` registry (4 tools), `DataSource` protocol, `set_data_source`, `run_tool` | 2 |
| `tests/wave8/test_research_tools.py` | New: registry, unsourced fallback, param errors, unknown tool | 2 |
| `src/shettyxtreme/research/orchestrator.py` | Tool loop (MAX_TOOL_CALLS=3), `tools` param, `on_brief` callback | 3 |
| `tests/wave8/test_research_orchestrator.py` | Migrate to v2 + new tool-loop tests | 3 |
| `src/shettyxtreme/research/scheduler.py` | `ResearchScheduler`: start/stop, tick-never-crashes, status fields | 4 |
| `tests/wave8/test_research_scheduler.py` | New: tick persists, failure continues, idempotent start/stop | 4 |
| `src/shettyxtreme/research/briefs.py` | `decided_at` field (harness-owned) | 5 |
| `src/shettyxtreme/research/store.py` | `decide` writes `decided_at`; `set_outcome` guard (409-class); `scoring()` aggregates | 5 |
| `tests/wave8/test_research_briefs_store.py` | New: decided_at, outcome guards, scoring aggregates + empty DB | 5 |
| `src/shettyxtreme/terminal/api/models.py` | Research tool/scheduler/outcome/scoring response models; `decided_at`; `tools` on run request | 6 |
| `src/shettyxtreme/terminal/api/research_router.py` | `init_research(broadcast_fn, scheduler)`, `build_orchestrator`, `/tools`, run `tools` 400s, outcome, scoring, scheduler status, decision broadcast | 6 |
| `tests/wave8/test_research_api.py` | New endpoint tests (existing tests keep passing) | 6 |
| `src/shettyxtreme/terminal/api/research_source.py` | `ProjectionDataSource` implementing the `DataSource` protocol from `app.state` | 7 |
| `src/shettyxtreme/terminal/api/app.py` | Lifespan: `set_data_source`, broadcast wrapper, scheduler start, `init_research`, teardown stop | 7 |
| `src/shettyxtreme/terminal/web/src/lib/api.ts` | `postBody<T>`, research types | 8 |
| `src/shettyxtreme/terminal/web/src/components/ResearchPanel.svelte` | 3-region panel + WS topic `research` | 9 |
| `src/shettyxtreme/terminal/web/src/App.svelte` | Mount `<ResearchPanel />` | 10 |

## Execution Protocol (SDD waves)

- **Wave 1 (parallel, disjoint ownership):** SA1 = Tasks 1–3 (tool loop core); SA2 = Task 4 (scheduler); SA3 = Tasks 8–10 (frontend). Each agent owns exactly its file set above. No agent commits.
- **Wave 2 (coordinator, sequential):** Tasks 5–7 (briefs/store → router/models → app wiring) — touches `store.py`/`briefs.py` (shared with SA1's running code? No — SA1 touches provider/orchestrator/tools only; store/briefs are untouched by SA1) and router/app (untouched by wave 1).
- **Wave 3:** per-wave code-review (code-reviewer subagent) → fix waves → final whole-branch review → gates → smoke gate (user sets `DEEPSEEK_API_KEY`) → docs + merge + push (hygiene + 3C together).

**Expected mid-wave red state:** after Task 1 lands, `test_research_orchestrator.py` and `test_research_api.py` fail (SimulatedProvider returns `ProviderResponse`; orchestrator still expects `str`) until Task 3. Agents run ONLY their own task tests mid-wave; the full-suite gate runs at wave end.

---

## Task 1: Provider v2 — ToolCall / ProviderResponse / tools+history

**Files:**
- Modify: `src/shettyxtreme/research/provider.py` (whole file, v2)
- Test: `tests/wave8/test_research_provider.py` (migrate + extend)

**Interfaces:**
- Consumes: nothing new.
- Produces: `ToolCall(name: str, arguments: dict)`, `ProviderResponse(content: str | None, tool_calls: list[ToolCall] | None)`, `BriefProvider.generate(*, system, prompt, max_output_tokens, tools: list[dict] | None = None, history: list[dict] | None = None) -> ProviderResponse`. `SimulatedProvider` gains `simulate_tool_calls: list[ToolCall] | None = None` (last repeats; when exhausted/absent → content behavior). `DeepSeekProvider._parse_tool_calls(message) -> list[ToolCall] | None` (static).

- [ ] **Step 1: Write the failing tests** — replace `tests/wave8/test_research_provider.py` with:

```python
"""Tests for the research provider abstraction (spec §3.1, §3.2 v2)."""
from __future__ import annotations

import pytest

from shettyxtreme.research.provider import (
    DeepSeekProvider,
    ProviderError,
    ProviderResponse,
    SimulatedProvider,
    ToolCall,
)


@pytest.mark.asyncio
async def test_simulated_default_brief() -> None:
    p = SimulatedProvider()
    out = await p.generate(system="s", prompt="p", max_output_tokens=100)
    assert out.tool_calls is None
    assert out.content is not None and '"direction": 0' in out.content


@pytest.mark.asyncio
async def test_simulated_script_cycle() -> None:
    p = SimulatedProvider(script=["one", "two", "three"])
    got = [
        await p.generate(system="s", prompt="p", max_output_tokens=1) for _ in range(4)
    ]
    assert [g.content for g in got] == ["one", "two", "three", "three"]
    assert len(p.calls) == 4


@pytest.mark.asyncio
async def test_simulated_failure_injection() -> None:
    p = SimulatedProvider(fail="network")
    with pytest.raises(ProviderError, match="network"):
        await p.generate(system="s", prompt="p", max_output_tokens=10)
    p2 = SimulatedProvider(fail="invalid_json")
    out = await p2.generate(system="s", prompt="p", max_output_tokens=10)
    assert out.content == "this is not json"


@pytest.mark.asyncio
async def test_simulated_tool_script() -> None:
    tc = ToolCall(name="chain_snapshot", arguments={"symbol": "NIFTY"})
    p = SimulatedProvider(script=["final"], simulate_tool_calls=[tc])
    first = await p.generate(system="s", prompt="p", max_output_tokens=10)
    assert first.content is None
    assert first.tool_calls == [tc]
    second = await p.generate(system="s", prompt="p", max_output_tokens=10)
    assert second.content == "final"
    assert second.tool_calls is None


@pytest.mark.asyncio
async def test_simulated_tool_script_single_repeats() -> None:
    tc = ToolCall(name="regime_snapshot", arguments={})
    p = SimulatedProvider(simulate_tool_calls=[tc])
    for _ in range(3):
        out = await p.generate(system="s", prompt="p", max_output_tokens=10)
        assert out.content is None
        assert out.tool_calls == [tc]


@pytest.mark.asyncio
async def test_simulated_records_tools_and_history() -> None:
    p = SimulatedProvider()
    await p.generate(
        system="s",
        prompt="p",
        max_output_tokens=10,
        tools=[{"type": "function", "function": {"name": "x"}}],
        history=[{"role": "user", "content": "h"}],
    )
    assert p.calls[-1]["tools"] == [{"type": "function", "function": {"name": "x"}}]
    assert p.calls[-1]["history"] == [{"role": "user", "content": "h"}]


@pytest.mark.asyncio
async def test_deepseek_provider_no_key(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    p = DeepSeekProvider(api_key="")
    with pytest.raises(ProviderError, match="DEEPSEEK_API_KEY"):
        await p.generate(system="s", prompt="p", max_output_tokens=10)


@pytest.mark.asyncio
async def test_deepseek_reads_env_at_call_time(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    p = DeepSeekProvider()
    with pytest.raises(ProviderError, match="DEEPSEEK_API_KEY"):
        await p.generate(system="s", prompt="p", max_output_tokens=10)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    try:
        await p.generate(system="s", prompt="p", max_output_tokens=10)
    except ProviderError as exc:
        assert "DEEPSEEK_API_KEY is not set" not in str(exc)


def test_deepseek_parses_tool_calls() -> None:
    msg = {
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {
                    "name": "chain_snapshot",
                    "arguments": '{"symbol": "NIFTY"}',
                },
            }
        ],
    }
    calls = DeepSeekProvider._parse_tool_calls(msg)
    assert calls == [ToolCall(name="chain_snapshot", arguments={"symbol": "NIFTY"})]


def test_deepseek_parses_empty_arguments() -> None:
    msg = {"content": None, "tool_calls": [{"function": {"name": "regime_snapshot"}}]}
    assert DeepSeekProvider._parse_tool_calls(msg) == [
        ToolCall(name="regime_snapshot", arguments={})
    ]


def test_deepseek_no_tool_calls_returns_none() -> None:
    assert DeepSeekProvider._parse_tool_calls({"content": "hi"}) is None


def test_provider_response_shapes() -> None:
    assert ProviderResponse(content="x") == ProviderResponse(content="x")
    assert ProviderResponse(content=None, tool_calls=[ToolCall(name="a", arguments={})]).tool_calls is not None
```

- [ ] **Step 2: Run test file to verify it fails**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave8/test_research_provider.py -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-sa1 -p no:cacheprovider`
Expected: FAIL — `ToolCall`/`ProviderResponse` not defined; `generate()` returns `str`.

- [ ] **Step 3: Rewrite `src/shettyxtreme/research/provider.py`** (full file):

```python
"""LLM provider abstraction for the research layer.

provider.py is the ONLY module in the codebase that talks to an LLM
(D3 wall): nothing outside research/ imports it, and no LLM output
reaches the signal/gate/execution path. v2 (3C): generate() returns a
ProviderResponse that may carry tool_calls; tools + history are passed
through per the OpenAI-compatible function-calling contract.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


class ProviderError(Exception):
    """Raised when a provider call fails (network, HTTP, or parse)."""


@dataclass(frozen=True)
class ToolCall:
    """One function-call request emitted by the model."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderResponse:
    """A provider completion: text content and/or tool calls."""

    content: str | None = None
    tool_calls: list[ToolCall] | None = None


class BriefProvider(Protocol):
    """A provider that turns a prompt into a structured response."""

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_output_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        """Return content and/or tool calls. Raises ProviderError on failure."""


class DeepSeekProvider:
    """OpenAI-compatible DeepSeek client via httpx (zero new deps)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEEPSEEK_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 90.0,
    ) -> None:
        self._explicit_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    def _api_key(self) -> str:
        """Explicit constructor key wins; otherwise read env at call time."""
        if self._explicit_key:
            return self._explicit_key
        return os.environ.get("DEEPSEEK_API_KEY", "")

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_output_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        api_key = self._api_key()
        if not api_key:
            raise ProviderError("DEEPSEEK_API_KEY is not set")
        messages: list[dict[str, Any]] = list(history) if history else [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ]
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "response_format": {"type": "json_object"},
            "max_tokens": max_output_tokens,
            "thinking": {"type": "disabled"},
            "stream": False,
        }
        if tools is not None:
            payload["tools"] = tools
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
            resp.raise_for_status()
            message = resp.json()["choices"][0]["message"]
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"DeepSeek HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"DeepSeek call failed: {exc}") from exc
        tool_calls = self._parse_tool_calls(message)
        if tool_calls:
            return ProviderResponse(
                content=message.get("content"), tool_calls=tool_calls
            )
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("DeepSeek returned an empty completion")
        return ProviderResponse(content=content.strip())

    @staticmethod
    def _parse_tool_calls(message: dict[str, Any]) -> list[ToolCall] | None:
        """Parse OpenAI-format `message.tool_calls` into ToolCall objects."""
        raw = message.get("tool_calls")
        if not raw:
            return None
        calls: list[ToolCall] = []
        for entry in raw:
            fn = entry.get("function", {})
            name = fn.get("name", "")
            try:
                args: Any = json.loads(fn.get("arguments") or "{}")
            except (json.JSONDecodeError, TypeError):
                args = {}
            if not isinstance(args, dict):
                args = {}
            calls.append(ToolCall(name=name, arguments=args))
        return calls or None


_DEFAULT_BRIEF = (
    '{"instruments": [], "direction": 0, "confidence": 0.5, '
    '"thesis": "No signal", '
    '"rationale": "simulated rationale ' + "x" * 340 + '", '
    '"evidence": [], "risks": []}'
)


class SimulatedProvider:
    """Deterministic test double with failure injection + scripted tool calls.

    fail: "network" -> ProviderError; "invalid_json" -> non-JSON content.
    Script entries are handed out in order; the last entry repeats; an
    empty script returns a schema-valid default brief. When
    simulate_tool_calls is non-empty the next generate() returns the next
    ToolCall (last repeats) with content=None; once exhausted (or never
    set), content behavior applies.
    """

    def __init__(
        self,
        script: list[str] | None = None,
        fail: str | None = None,
        fail_first: int = 0,
        fail_system_substring: str | None = None,
        simulate_tool_calls: list[ToolCall] | None = None,
    ) -> None:
        self._script = list(script) if script else []
        self.fail = fail
        self._fail_first = fail_first
        self._fail_system_substring = fail_system_substring
        self._tool_script = list(simulate_tool_calls) if simulate_tool_calls else []
        self.calls: list[dict[str, Any]] = []

    async def generate(
        self,
        *,
        system: str,
        prompt: str,
        max_output_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        history: list[dict[str, Any]] | None = None,
    ) -> ProviderResponse:
        self.calls.append(
            {
                "system": system,
                "prompt": prompt,
                "max_output_tokens": max_output_tokens,
                "tools": tools,
                "history": history,
            }
        )
        if self.fail == "network":
            raise ProviderError("simulated network failure")
        if self.fail == "invalid_json":
            return ProviderResponse(content="this is not json")
        if len(self.calls) <= self._fail_first:
            raise ProviderError("simulated network failure")
        if self._fail_system_substring and self._fail_system_substring in system:
            raise ProviderError("simulated network failure")
        if self._tool_script:
            if len(self._tool_script) == 1:
                return ProviderResponse(content=None, tool_calls=[self._tool_script[0]])
            return ProviderResponse(
                content=None, tool_calls=[self._tool_script.pop(0)]
            )
        if not self._script:
            return ProviderResponse(content=_DEFAULT_BRIEF)
        if len(self._script) == 1:
            return ProviderResponse(content=self._script[0])
        return ProviderResponse(content=self._script.pop(0))
```

- [ ] **Step 4: Run test file to verify it passes**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave8/test_research_provider.py -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-sa1 -p no:cacheprovider`
Expected: PASS (all tests in the file). Do NOT run the full suite — `test_research_orchestrator.py` and `test_research_api.py` are expected red until Task 3.

- [ ] **Step 5: Commit (coordinator only)**

```bash
git add src/shettyxtreme/research/provider.py tests/wave8/test_research_provider.py
git commit -m "feat(3c): provider v2 — ProviderResponse + ToolCall, tools/history params"
```

---

## Task 2: Read-only tool registry (`research/tools.py`)

**Files:**
- Create: `src/shettyxtreme/research/tools.py`
- Test: `tests/wave8/test_research_tools.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `DataSource` protocol (`chain_summary(symbol) -> str | None`, `regime_summary()`, `scanner_summary()`, `options_summary()` — all `-> str | None`); `ResearchTool(name, description, params_schema, invoke)` frozen dataclass; `TOOLS: dict[str, ResearchTool]`; `list_tools() -> list[ResearchTool]`; `run_tool(name, arguments) -> str` (KeyError on unknown); `set_data_source(source: DataSource | None)`; module constant `UNSOURCED = "[UNSOURCED] — no data"`.

- [ ] **Step 1: Write the failing tests** — create `tests/wave8/test_research_tools.py`:

```python
"""Tests for the read-only tool registry (spec §3.1)."""
from __future__ import annotations

import pytest

from shettyxtreme.research.tools import (
    TOOLS,
    UNSOURCED,
    list_tools,
    run_tool,
    set_data_source,
)


class FakeSource:
    """Synthetic DataSource double."""

    def __init__(self, **texts: str | None) -> None:
        self.texts = texts

    def chain_summary(self, symbol: str) -> str | None:
        return self.texts.get("chain")

    def regime_summary(self) -> str | None:
        return self.texts.get("regime")

    def scanner_summary(self) -> str | None:
        return self.texts.get("scanner")

    def options_summary(self) -> str | None:
        return self.texts.get("options")


@pytest.fixture(autouse=True)
def _reset_source() -> None:
    yield
    set_data_source(None)


def test_tools_registry_shape() -> None:
    names = [t.name for t in list_tools()]
    assert names == [
        "chain_snapshot",
        "regime_snapshot",
        "scanner_alerts",
        "options_posture",
    ]
    assert all(t.description for t in list_tools())
    assert TOOLS["chain_snapshot"].params_schema["required"] == ["symbol"]
    assert TOOLS["regime_snapshot"].params_schema["required"] == []


def test_unsourced_without_source() -> None:
    set_data_source(None)
    assert run_tool("regime_snapshot", {}) == UNSOURCED
    assert run_tool("options_posture", {}) == UNSOURCED


def test_chain_missing_symbol_param() -> None:
    set_data_source(FakeSource())
    assert run_tool("chain_snapshot", {}) == (
        "TOOL ERROR: missing required parameter 'symbol'"
    )


def test_chain_with_source() -> None:
    set_data_source(FakeSource(chain="NIFTY: spot 24500, IV 14.2%"))
    assert run_tool("chain_snapshot", {"symbol": "NIFTY"}) == (
        "NIFTY: spot 24500, IV 14.2%"
    )


def test_source_none_text_becomes_unsourced() -> None:
    set_data_source(FakeSource())
    assert run_tool("scanner_alerts", {}) == UNSOURCED


def test_unknown_tool_raises() -> None:
    with pytest.raises(KeyError):
        run_tool("nope", {})
```

- [ ] **Step 2: Run test file to verify it fails**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave8/test_research_tools.py -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-sa1 -p no:cacheprovider`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `src/shettyxtreme/research/tools.py`**:

```python
"""Read-only tool registry for the research briefer (3C §3.1).

Tools are the single source of both the function-calling surface and the
REST listing. Data is injected via the DataSource protocol — research/
never imports terminal/. A missing source renders "[UNSOURCED] — no
data", never fabricated content.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class DataSource(Protocol):
    """Text summaries a tool can render (implemented by the terminal layer)."""

    def chain_summary(self, symbol: str) -> str | None: ...

    def regime_summary(self) -> str | None: ...

    def scanner_summary(self) -> str | None: ...

    def options_summary(self) -> str | None: ...


UNSOURCED = "[UNSOURCED] — no data"

_source: DataSource | None = None


def set_data_source(source: DataSource | None) -> None:
    """Inject the data source (terminal wires it; tests inject doubles)."""
    global _source
    _source = source


@dataclass(frozen=True)
class ResearchTool:
    """One callable tool: identity + JSON-schema-lite params + renderer."""

    name: str
    description: str
    params_schema: dict[str, Any]
    invoke: Callable[[dict[str, Any]], str]


def _chain_invoke(params: dict[str, Any]) -> str:
    symbol = params.get("symbol")
    if not symbol:
        return "TOOL ERROR: missing required parameter 'symbol'"
    if _source is None:
        return UNSOURCED
    text = _source.chain_summary(str(symbol))
    return text if text else UNSOURCED


def _regime_invoke(params: dict[str, Any]) -> str:
    if _source is None:
        return UNSOURCED
    text = _source.regime_summary()
    return text if text else UNSOURCED


def _scanner_invoke(params: dict[str, Any]) -> str:
    if _source is None:
        return UNSOURCED
    text = _source.scanner_summary()
    return text if text else UNSOURCED


def _options_invoke(params: dict[str, Any]) -> str:
    if _source is None:
        return UNSOURCED
    text = _source.options_summary()
    return text if text else UNSOURCED


_TOOL_DEFS: list[ResearchTool] = [
    ResearchTool(
        name="chain_snapshot",
        description="Strike/spot/IV/volume digest for one NSE symbol.",
        params_schema={
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
        invoke=_chain_invoke,
    ),
    ResearchTool(
        name="regime_snapshot",
        description="Current regime, ADX, and conviction D/P/G from the signal path.",
        params_schema={"type": "object", "properties": {}, "required": []},
        invoke=_regime_invoke,
    ),
    ResearchTool(
        name="scanner_alerts",
        description="Recent breakout/gap/alert list.",
        params_schema={"type": "object", "properties": {}, "required": []},
        invoke=_scanner_invoke,
    ),
    ResearchTool(
        name="options_posture",
        description="IV rank, PCR, and OI buildup summary.",
        params_schema={"type": "object", "properties": {}, "required": []},
        invoke=_options_invoke,
    ),
]

TOOLS: dict[str, ResearchTool] = {t.name: t for t in _TOOL_DEFS}


def list_tools() -> list[ResearchTool]:
    """All registered tools, in registry order."""
    return list(_TOOL_DEFS)


def run_tool(name: str, arguments: dict[str, Any]) -> str:
    """Execute one tool; raises KeyError for unknown names."""
    tool = TOOLS.get(name)
    if tool is None:
        raise KeyError(name)
    return tool.invoke(arguments)
```

- [ ] **Step 4: Run test file to verify it passes**

Run: same command as Step 2. Expected: PASS.

- [ ] **Step 5: Commit (coordinator only)**

```bash
git add src/shettyxtreme/research/tools.py tests/wave8/test_research_tools.py
git commit -m "feat(3c): read-only tool registry + DataSource protocol"
```

---

## Task 3: Orchestrator tool loop + `on_brief` callback

**Files:**
- Modify: `src/shettyxtreme/research/orchestrator.py` (whole file, v2)
- Test: `tests/wave8/test_research_orchestrator.py` (migrate `_run` helper + extend)

**Interfaces:**
- Consumes: `ToolCall`, `ProviderResponse` (Task 1); `TOOLS`, `list_tools`, `run_tool` (Task 2).
- Produces: `ResearchOrchestrator.run(lenses=None, sources=None, tools: Sequence[str] | None = None) -> list[LensRunResult]`; new dataclass field `on_brief: Callable[[ResearchBrief], None] | None = None` (invoked after every persisted insert); constant `MAX_TOOL_CALLS = 3`; `ValueError("unknown tool: ...")` for invalid tool names.

- [ ] **Step 1: Write the failing tests** — replace `tests/wave8/test_research_orchestrator.py` with:

```python
"""Tests for the research orchestrator (spec §3.1, §3.2 tool loop)."""
from __future__ import annotations

import pytest

from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import SimulatedProvider, ToolCall
from shettyxtreme.research.store import ResearchStore


def _valid_brief(direction: int = 1) -> str:
    return (
        f'{{"instruments": ["NIFTY"], "direction": {direction}, '
        '"confidence": 0.6, "thesis": "Thesis here", '
        '"rationale": "' + "r" * 320 + '", '
        '"evidence": [{"item": "x", "source": "y", "unsourced": false}], '
        '"risks": []}'
    )


async def _run(lenses=None, provider=None, db_path=None, sources=None, tools=None):
    store = ResearchStore(db_path or ":memory:")
    orch = ResearchOrchestrator(
        provider=provider or SimulatedProvider(), store=store
    )
    return await orch.run(lenses=lenses, sources=sources, tools=tools), store


@pytest.mark.asyncio
async def test_happy_path_all_lenses(tmp_path) -> None:
    results, store = await _run(
        lenses=["oi_iv_flow", "directional_momentum", "tail_risk"],
        db_path=str(tmp_path / "r.db"),
        sources={"regime": "TRENDING_UP"},
    )
    assert len(results) == 3
    assert all(r.error is None for r in results)
    assert all(r.brief is not None for r in results)
    assert store.list().__len__() == 3
    store.close()


@pytest.mark.asyncio
async def test_default_runs_all_lenses() -> None:
    results, store = await _run()
    assert len(results) == 3
    store.close()


@pytest.mark.asyncio
async def test_unknown_lens_raises() -> None:
    with pytest.raises(ValueError, match="unknown lens"):
        await _run(lenses=["nope"])


@pytest.mark.asyncio
async def test_network_failure_all_fail_no_crash(tmp_path) -> None:
    p = SimulatedProvider(fail="network")
    results, store = await _run(
        lenses=["oi_iv_flow", "directional_momentum"],
        provider=p,
        db_path=str(tmp_path / "r.db"),
    )
    assert len(results) == 2
    assert all(r.error is not None for r in results)
    assert all(r.brief is None for r in results)
    assert store.list().__len__() == 0
    store.close()


@pytest.mark.asyncio
async def test_partial_results_one_lens_fails(tmp_path) -> None:
    p = SimulatedProvider(fail_system_substring="Examine open-interest flow")
    results, store = await _run(
        lenses=["oi_iv_flow", "directional_momentum"],
        provider=p,
        db_path=str(tmp_path / "r.db"),
    )
    assert len(results) == 2
    errors = [r for r in results if r.error is not None]
    briefs = [r for r in results if r.brief is not None]
    assert len(errors) == 1
    assert len(briefs) == 1
    store.close()


@pytest.mark.asyncio
async def test_reject_retry_once_then_fail(tmp_path) -> None:
    p = SimulatedProvider(script=["not json", _valid_brief()])
    results, store = await _run(lenses=["oi_iv_flow"], provider=p)
    assert results[0].brief is not None
    store.close()


@pytest.mark.asyncio
async def test_provider_max_tokens_forwarded(tmp_path) -> None:
    p = SimulatedProvider()
    store = ResearchStore(str(tmp_path / "r.db"))
    orch = ResearchOrchestrator(provider=p, store=store, max_output_tokens=777)
    await orch.run(lenses=["oi_iv_flow"])
    assert p.calls[0]["max_output_tokens"] == 777
    store.close()


@pytest.mark.asyncio
async def test_no_tools_path_unchanged(tmp_path) -> None:
    # tools=None -> provider called without tools; byte-identical to 3B flow.
    p = SimulatedProvider(script=[_valid_brief()])
    results, store = await _run(
        lenses=["oi_iv_flow"], provider=p, db_path=str(tmp_path / "r.db")
    )
    assert results[0].error is None and results[0].brief is not None
    assert p.calls[0]["tools"] is None
    assert p.calls[0]["history"] is None
    store.close()


@pytest.mark.asyncio
async def test_tool_loop_executes_then_briefs(tmp_path) -> None:
    p = SimulatedProvider(
        script=[_valid_brief()],
        simulate_tool_calls=[
            ToolCall(name="regime_snapshot", arguments={}),
            ToolCall(name="scanner_alerts", arguments={}),
        ],
    )
    results, store = await _run(
        lenses=["oi_iv_flow"], provider=p, db_path=str(tmp_path / "r.db")
    )
    assert results[0].error is None and results[0].brief is not None
    assert len(p.calls) == 3
    assert p.calls[0]["tools"] is not None  # toolset advertised
    assert p.calls[1]["history"] is not None
    assert p.calls[1]["history"][-1]["role"] == "tool"  # tool result appended
    store.close()


@pytest.mark.asyncio
async def test_tool_budget_exceeded_is_lens_error(tmp_path) -> None:
    # A single repeating tool call exhausts MAX_TOOL_CALLS -> lens error.
    p = SimulatedProvider(
        simulate_tool_calls=[ToolCall(name="regime_snapshot", arguments={})]
    )
    results, store = await _run(
        lenses=["oi_iv_flow"], provider=p, db_path=str(tmp_path / "r.db")
    )
    assert results[0].brief is None
    assert results[0].error == "tool call budget exceeded"
    assert store.list().__len__() == 0
    store.close()


@pytest.mark.asyncio
async def test_tool_error_recovery(tmp_path) -> None:
    # Unknown tool inside a run -> "TOOL ERROR:" result; loop continues.
    p = SimulatedProvider(
        script=[_valid_brief()],
        simulate_tool_calls=[
            ToolCall(name="nope", arguments={}),
            ToolCall(name="regime_snapshot", arguments={}),
        ],
    )
    results, store = await _run(
        lenses=["oi_iv_flow"], provider=p, db_path=str(tmp_path / "r.db")
    )
    assert results[0].error is None and results[0].brief is not None
    assert "TOOL ERROR" in p.calls[1]["history"][-1]["content"]
    store.close()


@pytest.mark.asyncio
async def test_unknown_tool_raises() -> None:
    with pytest.raises(ValueError, match="unknown tool"):
        await _run(lenses=["oi_iv_flow"], tools=["nope"])


@pytest.mark.asyncio
async def test_on_brief_callback_invoked(tmp_path) -> None:
    seen: list = []
    store = ResearchStore(str(tmp_path / "r.db"))
    orch = ResearchOrchestrator(
        provider=SimulatedProvider(script=[_valid_brief()]),
        store=store,
        on_brief=seen.append,
    )
    await orch.run(lenses=["oi_iv_flow"])
    assert len(seen) == 1
    assert seen[0].lens == "oi_iv_flow"
    store.close()
```

- [ ] **Step 2: Run test file to verify it fails**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave8/test_research_orchestrator.py -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-sa1 -p no:cacheprovider`
Expected: FAIL — `generate()` returns `ProviderResponse` but orchestrator treats it as `str`.

- [ ] **Step 3: Rewrite `src/shettyxtreme/research/orchestrator.py`** (full file):

```python
"""Research orchestrator — one-shot per-lens pipeline with bounded tool loop.

For each lens: digest -> prompt -> provider (tools allowed) -> strict
validate (reject-retry once) -> persist. Lenses run concurrently; a
failing lens surfaces partial results + error and never auto-advances or
crashes the run. Tool calls are capped at MAX_TOOL_CALLS per lens; when
the budget is exhausted without final content the lens errors out.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from shettyxtreme.research.briefs import (
    BriefValidationError,
    ResearchBrief,
    parse_brief_payload,
)
from shettyxtreme.research.digest import ContextDigest
from shettyxtreme.research.lenses import get_lens, list_lenses
from shettyxtreme.research.provider import BriefProvider, ProviderError, ToolCall
from shettyxtreme.research.store import ResearchStore
from shettyxtreme.research.tools import TOOLS, list_tools, run_tool

logger = logging.getLogger(__name__)

MAX_RETRIES = 1
MAX_TOOL_CALLS = 3
DEFAULT_MAX_OUTPUT_TOKENS = 2000
DEFAULT_CALL_TIMEOUT = 90.0


@dataclass
class LensRunResult:
    """Outcome of one lens run: a brief, or a surfaced error."""

    lens: str
    brief: ResearchBrief | None = None
    error: str | None = None


@dataclass
class ResearchOrchestrator:
    """Runs one research pass across the requested lenses."""

    provider: BriefProvider
    store: ResearchStore
    max_output_tokens: int = DEFAULT_MAX_OUTPUT_TOKENS
    call_timeout: float = DEFAULT_CALL_TIMEOUT
    on_brief: Callable[[ResearchBrief], None] | None = None

    async def run(
        self,
        lenses: Sequence[str] | None = None,
        sources: Mapping[str, str] | None = None,
        tools: Sequence[str] | None = None,
    ) -> list[LensRunResult]:
        """Run the requested lenses (all by default) and persist briefs.

        Raises ValueError on unknown lens or tool names. Never raises for
        provider or validation failures — those become per-lens errors.
        """
        names = list(lenses) if lenses is not None else [l.name for l in list_lenses()]
        valid = {l.name for l in list_lenses()}
        unknown = [n for n in names if n not in valid]
        if unknown:
            raise ValueError(f"unknown lens: {unknown}")
        tool_names = list(tools) if tools else []
        valid_tools = {t.name for t in list_tools()}
        unknown_tools = [n for n in tool_names if n not in valid_tools]
        if unknown_tools:
            raise ValueError(f"unknown tool: {unknown_tools}")
        provider_tools: list[dict] | None = None
        if tool_names:
            provider_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.params_schema,
                    },
                }
                for t in (TOOLS[n] for n in tool_names)
            ]
        digest_text = ContextDigest(dict(sources) if sources else None).build()
        results = await asyncio.gather(
            *(self._run_one(n, digest_text, provider_tools) for n in names)
        )
        return list(results)

    async def _run_one(
        self, lens_name: str, digest_text: str, provider_tools: list[dict] | None
    ) -> LensRunResult:
        lens = get_lens(lens_name)
        brief_id = str(uuid4())
        as_of = datetime.now(UTC).isoformat()
        prompt = lens.build_prompt(digest_text)
        messages: list[dict] = [
            {"role": "system", "content": lens.system_prompt},
            {"role": "user", "content": prompt},
        ]
        last_error: str | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                tool_calls_used = 0
                while True:
                    resp = await asyncio.wait_for(
                        self.provider.generate(
                            system=lens.system_prompt,
                            prompt=prompt,
                            max_output_tokens=self.max_output_tokens,
                            tools=provider_tools,
                            history=messages,
                        ),
                        timeout=self.call_timeout,
                    )
                    if resp.tool_calls:
                        tool_calls_used += len(resp.tool_calls)
                        if tool_calls_used > MAX_TOOL_CALLS:
                            return LensRunResult(
                                lens=lens_name, error="tool call budget exceeded"
                            )
                        messages.append(self._assistant_tool_message(resp.tool_calls))
                        for i, tc in enumerate(resp.tool_calls):
                            messages.append(self._tool_result_message(tc, f"call_{i}"))
                        continue
                    if not resp.content:
                        return LensRunResult(
                            lens=lens_name, error="empty provider response"
                        )
                    brief = parse_brief_payload(
                        resp.content, lens=lens_name, as_of=as_of, brief_id=brief_id
                    )
                    try:
                        self.store.insert(brief)
                    except Exception as exc:
                        logger.warning("Lens %s persist failed: %s", lens_name, exc)
                        return LensRunResult(
                            lens=lens_name, error=f"persist failed: {exc}"
                        )
                    if self.on_brief is not None:
                        self.on_brief(brief)
                    return LensRunResult(lens=lens_name, brief=brief)
            except (ProviderError, BriefValidationError, asyncio.TimeoutError) as exc:
                last_error = str(exc)
                logger.warning("Lens %s attempt %d failed: %s", lens_name, attempt + 1, exc)
        return LensRunResult(lens=lens_name, error=last_error)

    @staticmethod
    def _assistant_tool_message(calls: Sequence[ToolCall]) -> dict:
        """OpenAI-format assistant message carrying tool_calls."""
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": f"call_{i}",
                    "type": "function",
                    "function": {
                        "name": c.name,
                        "arguments": json.dumps(c.arguments),
                    },
                }
                for i, c in enumerate(calls)
            ],
        }

    @staticmethod
    def _tool_result_message(call: ToolCall, call_id: str) -> dict:
        try:
            result = run_tool(call.name, call.arguments)
        except Exception as exc:
            result = f"TOOL ERROR: {exc}"
        return {"role": "tool", "tool_call_id": call_id, "content": result}
```

- [ ] **Step 4: Run the wave-1 backend test set to verify it passes**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave8/test_research_provider.py tests/wave8/test_research_tools.py tests/wave8/test_research_orchestrator.py -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-sa1 -p no:cacheprovider`
Expected: PASS. (`test_research_api.py` stays red until Task 6 — documented.)

- [ ] **Step 5: Commit (coordinator only)**

```bash
git add src/shettyxtreme/research/orchestrator.py tests/wave8/test_research_orchestrator.py
git commit -m "feat(3c): orchestrator tool loop (MAX_TOOL_CALLS=3) + on_brief callback"
```

---

## Task 4: Scheduler (`research/scheduler.py`)

**Files:**
- Create: `src/shettyxtreme/research/scheduler.py`
- Test: `tests/wave8/test_research_scheduler.py`

**Interfaces:**
- Consumes: `ResearchOrchestrator` (Task 3: `run(lenses=, tools=)`).
- Produces: `ResearchScheduler(orchestrator, interval_minutes: float = 60.0, lenses: list[str] | None = None, tools: list[str] | None = None)` with `start()`, `stop()` (idempotent), `enabled` property, `next_run_at`/`last_run_at`/`last_result` str fields. Tick: runs `orchestrator.run(lenses=self.lenses, tools=self.tools)`; `last_result = "ok" | "partial" | <error string>`; failure logged, loop continues.

- [ ] **Step 1: Write the failing tests** — create `tests/wave8/test_research_scheduler.py`:

```python
"""Tests for the research scheduler (spec §3.3)."""
from __future__ import annotations

import asyncio

import pytest

from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import SimulatedProvider
from shettyxtreme.research.scheduler import ResearchScheduler
from shettyxtreme.research.store import ResearchStore


async def _await_run(sched: ResearchScheduler, timeout: float = 3.0) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while sched.last_run_at is None:
        if loop.time() > deadline:
            raise AssertionError("scheduler never ran")
        await asyncio.sleep(0.01)


async def _await_next_run(
    sched: ResearchScheduler, previous: str, timeout: float = 3.0
) -> None:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while sched.last_run_at == previous:
        if loop.time() > deadline:
            raise AssertionError("scheduler loop stopped after failure")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_scheduler_tick_persists_briefs(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    orch = ResearchOrchestrator(provider=SimulatedProvider(), store=store)
    sched = ResearchScheduler(orchestrator=orch, interval_minutes=0.0005)
    sched.start()
    assert sched.enabled is True
    try:
        await _await_run(sched)
        assert store.list().__len__() >= 1
        assert sched.last_result == "ok"
        assert sched.last_run_at is not None
        assert sched.next_run_at is not None
    finally:
        sched.stop()
    assert sched.enabled is False
    store.close()


@pytest.mark.asyncio
async def test_scheduler_partial_result_surfaces(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    orch = ResearchOrchestrator(
        provider=SimulatedProvider(fail="network"), store=store
    )
    sched = ResearchScheduler(orchestrator=orch, interval_minutes=0.0005)
    sched.start()
    try:
        await _await_run(sched)
        assert sched.last_result == "partial"
    finally:
        sched.stop()
    store.close()


@pytest.mark.asyncio
async def test_scheduler_exception_loop_continues(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    orch = ResearchOrchestrator(provider=SimulatedProvider(), store=store)
    # run() raises ValueError for the unknown tool — the loop must survive.
    sched = ResearchScheduler(
        orchestrator=orch, interval_minutes=0.0005, tools=["nope"]
    )
    sched.start()
    try:
        await _await_run(sched)
        assert sched.last_result is not None and "unknown tool" in sched.last_result
        first = sched.last_run_at
        assert first is not None
        await _await_next_run(sched, first)
    finally:
        sched.stop()
    store.close()


@pytest.mark.asyncio
async def test_scheduler_start_stop_idempotent(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    orch = ResearchOrchestrator(provider=SimulatedProvider(), store=store)
    sched = ResearchScheduler(orchestrator=orch, interval_minutes=0.0005)
    sched.start()
    sched.start()
    assert sched.enabled is True
    sched.stop()
    sched.stop()
    assert sched.enabled is False
    store.close()
```

- [ ] **Step 2: Run test file to verify it fails**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave8/test_research_scheduler.py -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-sa2 -p no:cacheprovider`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `src/shettyxtreme/research/scheduler.py`**:

```python
"""Research scheduler — periodic research passes from env config (3C §3.3).

Env-gated: enabled/interval/lenses/tools from RESEARCH_SCHEDULE_*; the
lifespan wires it only when enabled AND DEEPSEEK_API_KEY is present. A
tick failure is logged and the loop continues — the scheduler never
crashes the app.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from shettyxtreme.research.orchestrator import ResearchOrchestrator

logger = logging.getLogger(__name__)


class ResearchScheduler:
    """Runs research passes on a fixed interval until stop()."""

    def __init__(
        self,
        orchestrator: ResearchOrchestrator,
        interval_minutes: float = 60.0,
        lenses: list[str] | None = None,
        tools: list[str] | None = None,
    ) -> None:
        self._orchestrator = orchestrator
        self.interval_minutes = interval_minutes
        self.lenses = list(lenses) if lenses else None
        self.tools = list(tools) if tools else None
        self._task: asyncio.Task | None = None
        self.next_run_at: str | None = None
        self.last_run_at: str | None = None
        self.last_result: str | None = None

    @property
    def enabled(self) -> bool:
        return self._task is not None

    def start(self) -> None:
        """Spawn the tick loop; no-op when already running."""
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._loop())

    async def _loop(self) -> None:
        while True:
            self.next_run_at = (
                datetime.now(UTC) + timedelta(minutes=self.interval_minutes)
            ).isoformat()
            await asyncio.sleep(self.interval_minutes * 60)
            try:
                results = await self._orchestrator.run(
                    lenses=self.lenses, tools=self.tools
                )
                self.last_result = (
                    "ok" if all(r.error is None for r in results) else "partial"
                )
            except Exception as exc:
                logger.error("Research scheduled run failed: %s", exc)
                self.last_result = str(exc)
            self.last_run_at = datetime.now(UTC).isoformat()
            self.next_run_at = (
                datetime.now(UTC) + timedelta(minutes=self.interval_minutes)
            ).isoformat()

    def stop(self) -> None:
        """Cancel the tick loop; no-op when not running."""
        if self._task is None:
            return
        self._task.cancel()
        self._task = None
```

- [ ] **Step 4: Run test file to verify it passes**

Run: same command as Step 2. Expected: PASS.

- [ ] **Step 5: Commit (coordinator only)**

```bash
git add src/shettyxtreme/research/scheduler.py tests/wave8/test_research_scheduler.py
git commit -m "feat(3c): env-config research scheduler with never-crash ticks"
```

---

## Task 5: `decided_at` + outcome guard + scoring (briefs/store)

**Files:**
- Modify: `src/shettyxtreme/research/briefs.py` (add field)
- Modify: `src/shettyxtreme/research/store.py` (decide/set_outcome/scoring)
- Test: `tests/wave8/test_research_briefs_store.py` (extend)

**Interfaces:**
- Consumes: `ResearchBrief` (existing), `MODEL_AUTHORED_FIELDS` (unchanged — `decided_at` NOT authorable).
- Produces: `ResearchBrief.decided_at: str | None = None`; `store.decide()` writes `decided_at` into payload + column; `store.set_outcome(brief_id, outcome)` raises `ValueError` (invalid value), `KeyError` (unknown), `BriefNotDecidedError` (proposed); new exception `BriefNotDecidedError`; `VALID_OUTCOMES = {"WIN", "LOSS"}`; `store.scoring() -> list[dict]` with keys `lens/total/decided/with_outcome/win_rate/avg_confidence`.

- [ ] **Step 1: Write the failing tests** — extend `tests/wave8/test_research_briefs_store.py` (keep all existing tests; append these, plus the imports `BriefNotDecidedError`, `MODEL_AUTHORED_FIELDS`, `uuid4`, `datetime`/`UTC`):

```python
from uuid import uuid4

from shettyxtreme.research.briefs import MODEL_AUTHORED_FIELDS, ResearchBrief
from shettyxtreme.research.store import BriefNotDecidedError, ResearchStore


def _make_brief(lens: str, direction: int = 1, confidence: float = 0.6) -> ResearchBrief:
    return ResearchBrief(
        brief_id=str(uuid4()),
        lens=lens,
        as_of=datetime.now(UTC).isoformat(),
        direction=direction,
        confidence=confidence,
        thesis="Thesis",
        rationale="r" * 320,
        evidence=[],
        risks=[],
    )


def test_decided_at_not_model_authorable() -> None:
    assert "decided_at" not in MODEL_AUTHORED_FIELDS


def test_decided_at_surfaces_after_decision(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    brief = _make_brief("lens_a")
    store.insert(brief)
    decided = store.decide(brief.brief_id, "approved")
    assert decided.decided_at is not None
    assert store.get(brief.brief_id).decided_at is not None
    assert store.get(brief.brief_id).status == "approved"
    store.close()


def test_outcome_on_proposed_rejected(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    brief = _make_brief("lens_a")
    store.insert(brief)
    with pytest.raises(BriefNotDecidedError):
        store.set_outcome(brief.brief_id, "WIN")
    store.close()


def test_outcome_invalid_value(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    brief = _make_brief("lens_a")
    store.insert(brief)
    store.decide(brief.brief_id, "approved")
    with pytest.raises(ValueError, match="invalid outcome"):
        store.set_outcome(brief.brief_id, "DRAW")
    store.close()


def test_outcome_unknown_brief(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    with pytest.raises(KeyError):
        store.set_outcome("nope", "WIN")
    store.close()


def test_outcome_on_rejected_brief_allowed(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    brief = _make_brief("lens_a")
    store.insert(brief)
    store.decide(brief.brief_id, "rejected")
    updated = store.set_outcome(brief.brief_id, "LOSS")
    assert updated.outcome == "LOSS"
    store.close()


def test_scoring_aggregates(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    b1 = _make_brief("lens_a", direction=1, confidence=0.6)
    b2 = _make_brief("lens_a", direction=-1, confidence=0.8)
    b3 = _make_brief("lens_b", direction=0, confidence=0.5)
    store.insert(b1)
    store.insert(b2)
    store.insert(b3)
    store.decide(b1.brief_id, "approved")
    store.decide(b2.brief_id, "rejected")
    store.decide(b3.brief_id, "approved")
    store.set_outcome(b1.brief_id, "WIN")
    store.set_outcome(b2.brief_id, "LOSS")
    rows = {r["lens"]: r for r in store.scoring()}
    assert rows["lens_a"]["total"] == 2
    assert rows["lens_a"]["decided"] == 2
    assert rows["lens_a"]["with_outcome"] == 2
    assert rows["lens_a"]["win_rate"] == 0.5
    assert rows["lens_a"]["avg_confidence"] == 0.7
    assert rows["lens_b"]["total"] == 1
    assert rows["lens_b"]["with_outcome"] == 0
    assert rows["lens_b"]["win_rate"] == 0.0
    store.close()


def test_scoring_empty_db(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "r.db"))
    assert store.scoring() == []
    store.close()
```

- [ ] **Step 2: Run test file to verify the new tests fail**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave8/test_research_briefs_store.py -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-sa2 -p no:cacheprovider`
Expected: new tests FAIL (`decided_at` missing, `BriefNotDecidedError` missing, `scoring` missing).

- [ ] **Step 3: Implement** — in `src/shettyxtreme/research/briefs.py`, add after `outcome`:

```python
    decided_at: str | None = None
```

In `src/shettyxtreme/research/store.py`:

Add after `AlreadyDecidedError`:

```python
class BriefNotDecidedError(Exception):
    """Raised when an outcome is recorded for a proposed (undecided) brief."""


VALID_OUTCOMES = {"WIN", "LOSS"}
```

Replace `decide` with:

```python
    def decide(self, brief_id: str, decision: str) -> ResearchBrief:
        """Set status to approved/rejected; raises AlreadyDecidedError if set."""
        brief = self.get(brief_id)
        if brief is None:
            raise KeyError(brief_id)
        if brief.status != "proposed":
            raise AlreadyDecidedError(brief_id)
        now = datetime.now(UTC).isoformat()
        payload = json.loads(brief.model_dump_json())
        payload["status"] = decision
        payload["decided_at"] = now
        self._conn.execute(
            "UPDATE briefs SET payload = ?, status = ?, decided_at = ? WHERE brief_id = ?",
            (json.dumps(payload), decision, now, brief_id),
        )
        self._conn.commit()
        return self._row_to_brief(
            self._conn.execute(
                "SELECT * FROM briefs WHERE brief_id = ?", (brief_id,)
            ).fetchone()
        )
```

Replace `set_outcome` with:

```python
    def set_outcome(self, brief_id: str, outcome: str) -> ResearchBrief:
        """Link a realized outcome (WIN|LOSS) to a decided brief.

        Raises ValueError for invalid outcome values, KeyError for unknown
        briefs, BriefNotDecidedError for proposed briefs.
        """
        if outcome not in VALID_OUTCOMES:
            raise ValueError(f"invalid outcome: {outcome}")
        brief = self.get(brief_id)
        if brief is None:
            raise KeyError(brief_id)
        if brief.status == "proposed":
            raise BriefNotDecidedError(brief_id)
        payload = json.loads(brief.model_dump_json())
        payload["outcome"] = outcome
        self._conn.execute(
            "UPDATE briefs SET payload = ? WHERE brief_id = ?",
            (json.dumps(payload), brief_id),
        )
        self._conn.commit()
        return self._row_to_brief(
            self._conn.execute(
                "SELECT * FROM briefs WHERE brief_id = ?", (brief_id,)
            ).fetchone()
        )
```

Add after `list` (or anywhere before `close`):

```python
    def scoring(self) -> list[dict]:
        """Per-lens aggregates: total, decided, with_outcome, win_rate, avg_confidence.

        Empty DB -> []. Corrupt rows are skipped, never fatal.
        """
        rows = self._conn.execute("SELECT payload FROM briefs").fetchall()
        per_lens: dict[str, dict[str, float | int]] = {}
        for (payload_json,) in rows:
            try:
                brief = ResearchBrief(**json.loads(payload_json))
            except Exception:
                continue
            agg = per_lens.setdefault(
                brief.lens,
                {
                    "total": 0,
                    "decided": 0,
                    "with_outcome": 0,
                    "wins": 0,
                    "confidence_sum": 0.0,
                },
            )
            agg["total"] = int(agg["total"]) + 1
            if brief.status != "proposed":
                agg["decided"] = int(agg["decided"]) + 1
            if brief.outcome in ("WIN", "LOSS"):
                agg["with_outcome"] = int(agg["with_outcome"]) + 1
                if brief.outcome == "WIN":
                    agg["wins"] = int(agg["wins"]) + 1
            agg["confidence_sum"] = float(agg["confidence_sum"]) + brief.confidence
        results: list[dict] = []
        for lens, agg in sorted(per_lens.items()):
            with_outcome = int(agg["with_outcome"])
            total = int(agg["total"])
            results.append(
                {
                    "lens": lens,
                    "total": total,
                    "decided": int(agg["decided"]),
                    "with_outcome": with_outcome,
                    "win_rate": round(int(agg["wins"]) / with_outcome, 4)
                    if with_outcome
                    else 0.0,
                    "avg_confidence": round(float(agg["confidence_sum"]) / total, 4)
                    if total
                    else 0.0,
                }
            )
        return results
```

- [ ] **Step 4: Run test file to verify it passes**

Run: same command as Step 2. Expected: PASS (existing + new).

- [ ] **Step 5: Commit (coordinator only)**

```bash
git add src/shettyxtreme/research/briefs.py src/shettyxtreme/research/store.py tests/wave8/test_research_briefs_store.py
git commit -m "feat(3c): decided_at surfacing, outcome guards, per-lens scoring aggregates"
```

---

## Task 6: Router + models — endpoints for tools/scheduler/outcome/scoring + broadcast

**Files:**
- Modify: `src/shettyxtreme/terminal/api/models.py` (research section)
- Modify: `src/shettyxtreme/terminal/api/research_router.py`
- Test: `tests/wave8/test_research_api.py` (extend; existing tests keep passing)

**Interfaces:**
- Consumes: `list_tools`/`ResearchTool` (Task 2), `ResearchOrchestrator`/`run(tools=)` (Task 3), `ResearchScheduler` (Task 4), `set_outcome`/`scoring`/`BriefNotDecidedError` (Task 5).
- Produces: `init_research(broadcast_fn: Callable[[dict], None] | None = None, scheduler: ResearchScheduler | None = None)`; `build_orchestrator() -> ResearchOrchestrator | None` (key-gated, `on_brief` broadcast wired); endpoints `GET /api/research/tools`, `GET /api/research/scheduler`, `POST /api/research/briefs/{brief_id}/outcome`, `GET /api/research/scoring`; `POST /api/research/run` gains `tools` (400 on unknown); approve/reject broadcast `{"event": "decision", "data": {"brief_id", "status"}}`.

- [ ] **Step 1: Write the failing tests** — extend `tests/wave8/test_research_api.py` (existing fixture/imports stay; append):

```python
import shettyxtreme.terminal.api.research_router as rr
from shettyxtreme.research.provider import ToolCall
from shettyxtreme.research.scheduler import ResearchScheduler


@pytest.mark.asyncio
async def test_tools_listing(client: AsyncClient) -> None:
    resp = await client.get("/api/research/tools")
    assert resp.status_code == 200
    names = {t["name"] for t in resp.json()["tools"]}
    assert names == {
        "chain_snapshot",
        "regime_snapshot",
        "scanner_alerts",
        "options_posture",
    }
    chain = next(t for t in resp.json()["tools"] if t["name"] == "chain_snapshot")
    assert chain["params_schema"]["required"] == ["symbol"]


@pytest.mark.asyncio
async def test_run_with_tools(client: AsyncClient, tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "research.db"))
    rr.RESEARCH_DB_PATH = str(tmp_path / "research.db")
    rr._ORCHESTRATOR = ResearchOrchestrator(
        provider=SimulatedProvider(
            script=[
                '{"instruments": [], "direction": 0, "confidence": 0.5, '
                '"thesis": "T", "rationale": "' + "r" * 320 + '", '
                '"evidence": [], "risks": []}'
            ],
            simulate_tool_calls=[
                ToolCall(name="regime_snapshot", arguments={}),
            ],
        ),
        store=store,
    )
    resp = await client.post(
        "/api/research/run",
        json={"lenses": ["oi_iv_flow"], "tools": ["regime_snapshot", "scanner_alerts"]},
    )
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["brief"] is not None
    assert results[0]["error"] is None


@pytest.mark.asyncio
async def test_run_unknown_tool_400(client: AsyncClient, orchestrator) -> None:
    resp = await client.post(
        "/api/research/run", json={"lenses": ["oi_iv_flow"], "tools": ["nope"]}
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_scheduler_status_disabled(client: AsyncClient) -> None:
    rr.init_research(broadcast_fn=None, scheduler=None)
    resp = await client.get("/api/research/scheduler")
    assert resp.status_code == 200
    body = resp.json()
    assert body["enabled"] is False
    assert body["interval_minutes"] == 60.0


@pytest.mark.asyncio
async def test_scheduler_status_reflects_handle(client: AsyncClient, tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "research.db"))
    orch = ResearchOrchestrator(provider=SimulatedProvider(), store=store)
    sched = ResearchScheduler(orchestrator=orch, interval_minutes=30, lenses=["tail_risk"], tools=["regime_snapshot"])
    rr.init_research(broadcast_fn=None, scheduler=sched)
    resp = await client.get("/api/research/scheduler")
    body = resp.json()
    assert body["enabled"] is False
    assert body["interval_minutes"] == 30
    assert body["lenses"] == ["tail_risk"]
    assert body["tools"] == ["regime_snapshot"]
    rr.init_research(broadcast_fn=None, scheduler=None)


@pytest.mark.asyncio
async def test_outcome_flow(client: AsyncClient, orchestrator) -> None:
    resp = await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief = resp.json()["results"][0]["brief"]
    assert brief is not None
    # outcome on proposed -> 409
    r409 = await client.post(
        f"/api/research/briefs/{brief['brief_id']}/outcome", json={"outcome": "WIN"}
    )
    assert r409.status_code == 409
    # decide then score
    r_ok = await client.post(f"/api/research/briefs/{brief['brief_id']}/approve")
    assert r_ok.status_code == 200
    r_out = await client.post(
        f"/api/research/briefs/{brief['brief_id']}/outcome", json={"outcome": "WIN"}
    )
    assert r_out.status_code == 200
    assert r_out.json()["outcome"] == "WIN"
    # unknown brief -> 404
    r404 = await client.post(
        "/api/research/briefs/nope/outcome", json={"outcome": "WIN"}
    )
    assert r404.status_code == 404


@pytest.mark.asyncio
async def test_outcome_invalid_value_400(client: AsyncClient, orchestrator) -> None:
    resp = await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief = resp.json()["results"][0]["brief"]
    await client.post(f"/api/research/briefs/{brief['brief_id']}/approve")
    r_bad = await client.post(
        f"/api/research/briefs/{brief['brief_id']}/outcome", json={"outcome": "DRAW"}
    )
    assert r_bad.status_code == 400


@pytest.mark.asyncio
async def test_scoring_empty_db(client: AsyncClient) -> None:
    resp = await client.get("/api/research/scoring")
    assert resp.status_code == 200
    assert resp.json()["lenses"] == []


@pytest.mark.asyncio
async def test_scoring_after_decisions(client: AsyncClient, orchestrator) -> None:
    resp = await client.post(
        "/api/research/run", json={"lenses": ["oi_iv_flow", "tail_risk"]}
    )
    items = resp.json()["results"]
    briefs = [r["brief"] for r in items if r["brief"] is not None]
    assert len(briefs) == 2
    for b in briefs:
        await client.post(f"/api/research/briefs/{b['brief_id']}/approve")
        await client.post(
            f"/api/research/briefs/{b['brief_id']}/outcome", json={"outcome": "WIN"}
        )
    resp2 = await client.get("/api/research/scoring")
    lenses = {l["lens"]: l for l in resp2.json()["lenses"]}
    assert lenses["oi_iv_flow"]["total"] == 1
    assert lenses["oi_iv_flow"]["with_outcome"] == 1
    assert lenses["oi_iv_flow"]["win_rate"] == 1.0


@pytest.mark.asyncio
async def test_decided_at_in_brief_response(client: AsyncClient, orchestrator) -> None:
    resp = await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief = resp.json()["results"][0]["brief"]
    assert brief is not None
    assert brief["decided_at"] is None
    await client.post(f"/api/research/briefs/{brief['brief_id']}/approve")
    fetched = await client.get(f"/api/research/briefs/{brief['brief_id']}")
    assert fetched.json()["decided_at"] is not None


@pytest.mark.asyncio
async def test_broadcast_new_brief_and_decision(client: AsyncClient, tmp_path) -> None:
    events: list[dict] = []
    rr.init_research(broadcast_fn=events.append, scheduler=None)
    store = ResearchStore(str(tmp_path / "research.db"))
    rr.RESEARCH_DB_PATH = str(tmp_path / "research.db")
    rr._ORCHESTRATOR = ResearchOrchestrator(provider=SimulatedProvider(), store=store)
    resp = await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief = resp.json()["results"][0]["brief"]
    assert brief is not None
    await client.post(f"/api/research/briefs/{brief['brief_id']}/approve")
    kinds = [e["event"] for e in events]
    assert "new_brief" in kinds
    assert "decision" in kinds
    decision = next(e for e in events if e["event"] == "decision")
    assert decision["data"]["brief_id"] == brief["brief_id"]
    assert decision["data"]["status"] == "approved"
    rr.init_research(broadcast_fn=None, scheduler=None)
```

Note: `rr.RESEARCH_DB_PATH` and `rr._ORCHESTRATOR` are module globals — every test that overrides them must restore or overwrite (the existing `orchestrator` fixture already reassigns per test; `test_run_with_tools` and `test_broadcast_*` set their own).

- [ ] **Step 2: Run the file to verify new tests fail**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave8/test_research_api.py -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-sa2 -p no:cacheprovider`
Expected: FAIL — endpoints/models missing. (Some pre-existing tests may still pass — they exercise code from Task 3.)

- [ ] **Step 3a: `src/shettyxtreme/terminal/api/models.py`** — in the Research section, replace `ResearchBriefResponse` body (add `decided_at`), add `tools` to `ResearchRunRequest`, and append the new models:

```python
class ResearchBriefResponse(BaseModel):
    brief_id: str
    lens: str
    as_of: str
    instruments: list[str] = []
    direction: int
    confidence: float
    thesis: str
    rationale: str
    evidence: list[dict] = []
    risks: list[str] = []
    validity_window_minutes: int
    status: str
    outcome: str | None = None
    decided_at: str | None = None
    expired: bool = False


class ResearchRunRequest(BaseModel):
    lenses: list[str] | None = None
    context: dict[str, str] | None = None
    tools: list[str] | None = None


class ResearchToolResponse(BaseModel):
    name: str
    description: str
    params_schema: dict = {}


class ResearchToolsResponse(BaseModel):
    tools: list[ResearchToolResponse] = []


class ResearchSchedulerResponse(BaseModel):
    enabled: bool = False
    interval_minutes: float = 60.0
    lenses: list[str] | None = None
    tools: list[str] | None = None
    next_run_at: str | None = None
    last_run_at: str | None = None
    last_result: str | None = None


class ResearchOutcomeRequest(BaseModel):
    # str, not Literal: the store validates and the router maps the
    # resulting ValueError to the spec'd 400 (FastAPI would 422 otherwise).
    outcome: str


class ResearchOutcomeResponse(BaseModel):
    brief_id: str
    outcome: str


class ResearchScoringItem(BaseModel):
    lens: str
    total: int
    decided: int
    with_outcome: int
    win_rate: float
    avg_confidence: float


class ResearchScoringResponse(BaseModel):
    lenses: list[ResearchScoringItem] = []
```

- [ ] **Step 3b: `src/shettyxtreme/terminal/api/research_router.py`** — full rewrite (keeps all 3B endpoints, adds 3C):

```python
"""Research router — run briefers, tools, decisions, scoring (Phase 3B + 3C).

The orchestrator is created lazily on first run; without DEEPSEEK_API_KEY
the run endpoint returns 503 with an explicit message. DB failures on
read paths degrade to empty/404 payloads — never 500. Broadcasts go out
on WS topic `research` via the broadcast_fn wired in lifespan.
"""
from __future__ import annotations

import logging
import os
from collections.abc import Callable

from fastapi import APIRouter, HTTPException

from shettyxtreme.research.briefs import ResearchBrief
from shettyxtreme.research.lenses import list_lenses
from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import DeepSeekProvider
from shettyxtreme.research.scheduler import ResearchScheduler
from shettyxtreme.research.store import (
    AlreadyDecidedError,
    BriefNotDecidedError,
    ResearchStore,
)
from shettyxtreme.research.tools import list_tools
from shettyxtreme.terminal.api.models import (
    LensInfoResponse,
    LensListResponse,
    ResearchBriefListResponse,
    ResearchBriefResponse,
    ResearchDecisionResponse,
    ResearchOutcomeRequest,
    ResearchOutcomeResponse,
    ResearchRunItem,
    ResearchRunRequest,
    ResearchRunResponse,
    ResearchSchedulerResponse,
    ResearchScoringItem,
    ResearchScoringResponse,
    ResearchToolResponse,
    ResearchToolsResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])

RESEARCH_DB_PATH = "data/research.db"
_ORCHESTRATOR: ResearchOrchestrator | None = None
_broadcast_fn: Callable[[dict], None] | None = None
_SCHEDULER: ResearchScheduler | None = None


def init_research(
    broadcast_fn: Callable[[dict], None] | None = None,
    scheduler: ResearchScheduler | None = None,
) -> None:
    """Wire WS broadcast + the scheduled-run handle (lifespan calls this)."""
    global _broadcast_fn, _SCHEDULER
    _broadcast_fn = broadcast_fn
    _SCHEDULER = scheduler


def _broadcast(event: dict) -> None:
    if _broadcast_fn is None:
        return
    try:
        _broadcast_fn(event)
    except Exception:
        logger.exception("research broadcast failed")


def _brief_response(brief: ResearchBrief) -> ResearchBriefResponse:
    return ResearchBriefResponse(**brief.model_dump(), expired=brief.is_expired())


def _on_brief(brief: ResearchBrief) -> None:
    _broadcast({"event": "new_brief", "data": _brief_response(brief).model_dump()})


def build_orchestrator() -> ResearchOrchestrator | None:
    """Build a key-gated orchestrator wired for broadcasts (router + scheduler)."""
    if not os.environ.get("DEEPSEEK_API_KEY"):
        return None
    return ResearchOrchestrator(
        provider=DeepSeekProvider(),
        store=ResearchStore(RESEARCH_DB_PATH),
        on_brief=_on_brief,
    )


def _get_orchestrator() -> ResearchOrchestrator | None:
    global _ORCHESTRATOR
    if _ORCHESTRATOR is not None:
        return _ORCHESTRATOR
    _ORCHESTRATOR = build_orchestrator()
    return _ORCHESTRATOR


def _open_store() -> ResearchStore:
    """Open the research store; propagate exceptions to callers."""
    return ResearchStore(RESEARCH_DB_PATH)


@router.get("/lenses", response_model=LensListResponse)
async def lenses() -> LensListResponse:
    """Available briefer lenses."""
    return LensListResponse(
        lenses=[
            LensInfoResponse(name=l.name, description=l.description)
            for l in list_lenses()
        ]
    )


@router.get("/tools", response_model=ResearchToolsResponse)
async def tools() -> ResearchToolsResponse:
    """Read-only tool definitions (single source for REST + function calling)."""
    return ResearchToolsResponse(
        tools=[
            ResearchToolResponse(
                name=t.name, description=t.description, params_schema=t.params_schema
            )
            for t in list_tools()
        ]
    )


@router.get("/scheduler", response_model=ResearchSchedulerResponse)
async def scheduler_status() -> ResearchSchedulerResponse:
    """Scheduler status; enabled only when the lifespan started it."""
    if _SCHEDULER is None:
        return ResearchSchedulerResponse()
    return ResearchSchedulerResponse(
        enabled=_SCHEDULER.enabled,
        interval_minutes=_SCHEDULER.interval_minutes,
        lenses=_SCHEDULER.lenses,
        tools=_SCHEDULER.tools,
        next_run_at=_SCHEDULER.next_run_at,
        last_run_at=_SCHEDULER.last_run_at,
        last_result=_SCHEDULER.last_result,
    )


@router.post("/run", response_model=ResearchRunResponse)
async def run(req: ResearchRunRequest) -> ResearchRunResponse:
    """Run one research pass across the requested (or all) lenses."""
    orch = _get_orchestrator()
    if orch is None:
        raise HTTPException(
            status_code=503,
            detail="DEEPSEEK_API_KEY is not set — set it to enable research runs",
        )
    if req.lenses:
        valid = {l.name for l in list_lenses()}
        unknown = [n for n in req.lenses if n not in valid]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"unknown lenses: {unknown}; valid: {sorted(valid)}",
            )
    if req.tools:
        valid_tools = {t.name for t in list_tools()}
        unknown_tools = [n for n in req.tools if n not in valid_tools]
        if unknown_tools:
            raise HTTPException(
                status_code=400,
                detail=f"unknown tools: {unknown_tools}; valid: {sorted(valid_tools)}",
            )
    results = await orch.run(lenses=req.lenses, sources=req.context, tools=req.tools)
    items = [
        ResearchRunItem(
            lens=r.lens,
            brief=_brief_response(r.brief) if r.brief else None,
            error=r.error,
        )
        for r in results
    ]
    return ResearchRunResponse(results=items)


@router.get("/briefs", response_model=ResearchBriefListResponse)
async def list_briefs(
    status: str | None = None, lens: str | None = None
) -> ResearchBriefListResponse:
    """List briefs, newest first, optionally filtered."""
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        return ResearchBriefListResponse()
    try:
        return ResearchBriefListResponse(
            briefs=[_brief_response(b) for b in store.list(status=status, lens=lens)]
        )
    except Exception as exc:
        logger.warning("Research list failed: %s", exc)
        return ResearchBriefListResponse()
    finally:
        store.close()


@router.get("/briefs/{brief_id}", response_model=ResearchBriefResponse)
async def get_brief(brief_id: str) -> ResearchBriefResponse:
    """Fetch one brief by id."""
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        raise HTTPException(status_code=404, detail="brief not found") from exc
    try:
        brief = store.get(brief_id)
    finally:
        store.close()
    if brief is None:
        raise HTTPException(status_code=404, detail="brief not found")
    return _brief_response(brief)


@router.post("/briefs/{brief_id}/approve", response_model=ResearchDecisionResponse)
async def approve(brief_id: str) -> ResearchDecisionResponse:
    """Approve a proposed brief (immutable decision)."""
    return _decide(brief_id, "approved")


@router.post("/briefs/{brief_id}/reject", response_model=ResearchDecisionResponse)
async def reject(brief_id: str) -> ResearchDecisionResponse:
    """Reject a proposed brief (immutable decision)."""
    return _decide(brief_id, "rejected")


def _decide(brief_id: str, decision: str) -> ResearchDecisionResponse:
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        raise HTTPException(status_code=404, detail="brief not found") from exc
    try:
        try:
            brief = store.decide(brief_id, decision)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="brief not found") from exc
        except AlreadyDecidedError as exc:
            raise HTTPException(status_code=409, detail="brief already decided") from exc
    finally:
        store.close()
    _broadcast(
        {"event": "decision", "data": {"brief_id": brief.brief_id, "status": brief.status}}
    )
    return ResearchDecisionResponse(brief_id=brief.brief_id, status=brief.status)


@router.post("/briefs/{brief_id}/outcome", response_model=ResearchOutcomeResponse)
async def set_outcome(
    brief_id: str, body: ResearchOutcomeRequest
) -> ResearchOutcomeResponse:
    """Record a realized outcome (WIN|LOSS) for a decided brief."""
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        raise HTTPException(status_code=404, detail="brief not found") from exc
    try:
        try:
            brief = store.set_outcome(brief_id, body.outcome)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="brief not found") from exc
        except BriefNotDecidedError as exc:
            raise HTTPException(
                status_code=409,
                detail="outcome can only be recorded for a decided brief",
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        store.close()
    return ResearchOutcomeResponse(
        brief_id=brief.brief_id, outcome=brief.outcome or ""
    )


@router.get("/scoring", response_model=ResearchScoringResponse)
async def scoring() -> ResearchScoringResponse:
    """Per-lens brief scoring aggregates; empty DB -> []."""
    try:
        store = _open_store()
    except Exception as exc:
        logger.warning("Research store unavailable: %s", exc)
        return ResearchScoringResponse()
    try:
        return ResearchScoringResponse(
            lenses=[ResearchScoringItem(**row) for row in store.scoring()]
        )
    except Exception as exc:
        logger.warning("Research scoring failed: %s", exc)
        return ResearchScoringResponse()
    finally:
        store.close()
```

- [ ] **Step 4: Run the full wave-2 backend set**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave8/ -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-w2 -p no:cacheprovider`
Expected: PASS — all wave8 files (provider, tools, orchestrator, scheduler, briefs_store, api). If `test_research_api.py` pre-existing tests fail, fix forward (they use the `orchestrator` fixture which still applies).

- [ ] **Step 5: Commit (coordinator only)**

```bash
git add src/shettyxtreme/terminal/api/models.py src/shettyxtreme/terminal/api/research_router.py tests/wave8/test_research_api.py
git commit -m "feat(3c): research endpoints — tools, scheduler status, outcome, scoring + WS broadcast"
```

---

## Task 7: Lifespan wiring + `ProjectionDataSource`

**Files:**
- Create: `src/shettyxtreme/terminal/api/research_source.py`
- Modify: `src/shettyxtreme/terminal/api/app.py` (imports, lifespan start + teardown)

**Interfaces:**
- Consumes: `init_research`, `build_orchestrator` (Task 6), `ResearchScheduler` (Task 4), `set_data_source` (Task 2), `ws_manager` (existing).
- Produces: `ProjectionDataSource(app_state)` implementing `DataSource` from `app.state.intelligence_projection` / `app.state.alert_projection`. Lifespan: `set_data_source(...)` after projections are assigned; `_research_broadcast(data)` sync wrapper spawning `ws_manager.broadcast("research", data)`; scheduler start gated on `RESEARCH_SCHEDULE_ENABLED == "1"` AND `DEEPSEEK_API_KEY`; `init_research(broadcast_fn=..., scheduler=...)` always called; teardown stops the scheduler.

- [ ] **Step 1: Create `src/shettyxtreme/terminal/api/research_source.py`**:

```python
"""Default research DataSource — renders live app.state into tool text.

Best-effort per spec §3.1: summaries are composed from whatever live
state exists; anything unavailable renders None (the tool layer turns
that into [UNSOURCED]). research/ never imports terminal/ — this module
implements the DataSource protocol, not the other way around.
"""
from __future__ import annotations

from typing import Any


class ProjectionDataSource:
    """DataSource backed by the running app's projections."""

    def __init__(self, app_state: Any) -> None:
        self._state = app_state

    def chain_summary(self, symbol: str) -> str | None:
        # No chain text renderer exists yet — honest best-effort.
        return None

    def regime_summary(self) -> str | None:
        proj = getattr(self._state, "intelligence_projection", None)
        if proj is None:
            return None
        try:
            regime = proj.get_regime() or {}
            signal = proj.get_signal() or {}
        except Exception:
            return None
        return (
            f"regime={regime.get('regime', 'unknown')} "
            f"adx={regime.get('adx', 'n/a')} "
            f"conviction={signal.get('conviction', 0.0)} "
            f"D={signal.get('D', 0.0)} P={signal.get('P', 0.0)} "
            f"G={signal.get('G', 0.0)}"
        )

    def scanner_summary(self) -> str | None:
        proj = getattr(self._state, "alert_projection", None)
        if proj is None:
            return None
        try:
            alerts = proj.get() or []
        except Exception:
            return None
        if not alerts:
            return None
        lines = [f"- {a.get('severity')} {a.get('message')}" for a in alerts[:10]]
        return "\n".join(lines)

    def options_summary(self) -> str | None:
        # No options-posture renderer exists yet — honest best-effort.
        return None
```

- [ ] **Step 2: Modify `src/shettyxtreme/terminal/api/app.py`**:

Imports — add after the existing research_router import (line ~35):

```python
import os
from shettyxtreme.research.scheduler import ResearchScheduler
from shettyxtreme.research.tools import set_data_source
from shettyxtreme.terminal.api.research_router import build_orchestrator, init_research
from shettyxtreme.terminal.api.research_source import ProjectionDataSource
```

In `lifespan`, immediately after the `app.state.*_projection` assignments block (after line 128), insert:

```python
    # ── Research: data source, WS broadcast, scheduler (3C) ────────────────
    set_data_source(ProjectionDataSource(app.state))

    def _research_broadcast(data: dict) -> None:
        try:
            asyncio.create_task(ws_manager.broadcast("research", data))
        except Exception:
            logger.exception("research broadcast failed")

    research_scheduler: ResearchScheduler | None = None
    if os.environ.get("RESEARCH_SCHEDULE_ENABLED") == "1":
        if not os.environ.get("DEEPSEEK_API_KEY"):
            logger.info("research scheduler skipped: DEEPSEEK_API_KEY not set")
        else:
            orch = build_orchestrator()
            if orch is not None:
                def _csv_env(name: str) -> list[str] | None:
                    raw = os.environ.get(name, "")
                    return [x.strip() for x in raw.split(",") if x.strip()] or None

                research_scheduler = ResearchScheduler(
                    orchestrator=orch,
                    interval_minutes=float(
                        os.environ.get("RESEARCH_SCHEDULE_INTERVAL_MINUTES", "60")
                    ),
                    lenses=_csv_env("RESEARCH_SCHEDULE_LENSES"),
                    tools=_csv_env("RESEARCH_SCHEDULE_TOOLS"),
                )
                research_scheduler.start()
                logger.info(
                    "research scheduler started (interval %s min)",
                    research_scheduler.interval_minutes,
                )
    else:
        logger.info("research scheduler disabled (RESEARCH_SCHEDULE_ENABLED not set)")
    init_research(broadcast_fn=_research_broadcast, scheduler=research_scheduler)
```

In the teardown section (after `yield`, before `if _health_monitor:`), add:

```python
    if research_scheduler is not None:
        research_scheduler.stop()
```

- [ ] **Step 3: Verify import + no regression**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -c "import shettyxtreme.terminal.api.app"`
Expected: no output, exit 0.

Then run the wave-2 set again: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/wave8/ -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-w2 -p no:cacheprovider` — expected PASS.

- [ ] **Step 4: Commit (coordinator only)**

```bash
git add src/shettyxtreme/terminal/api/research_source.py src/shettyxtreme/terminal/api/app.py
git commit -m "feat(3c): lifespan wiring — research data source, WS broadcast, env-gated scheduler"
```

---

## Task 8: Frontend api layer — `postBody` + research types

**Files:**
- Modify: `src/shettyxtreme/terminal/web/src/lib/api.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `postBody<T>(path, body)` (POST with JSON body + same-origin credentials), exported types `ResearchLens`, `ResearchToolDef`, `ResearchBrief`, `ResearchRunRequest`, `ResearchRunResult`, `ResearchRunResponse`, `ResearchBriefListResponse`, `ResearchSchedulerStatus`, `ResearchDecisionResponse`, `ResearchScoringItem`.

- [ ] **Step 1: Write the code** — append to `src/shettyxtreme/terminal/web/src/lib/api.ts`:

```ts
export async function postBody<T>(path: string, body: unknown): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(path, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  } catch {
    throw new Error(`Network error reaching ${path}`);
  }
  if (!resp.ok) {
    throw new Error(await describeError(resp));
  }
  return (await resp.json()) as T;
}

export type ResearchLens = { name: string; description: string };
export type ResearchToolDef = {
  name: string;
  description: string;
  params_schema: Record<string, unknown>;
};
export type ResearchEvidence = {
  item: string;
  source: string;
  unsourced: boolean;
};
export type ResearchBrief = {
  brief_id: string;
  lens: string;
  as_of: string;
  instruments: string[];
  direction: number;
  confidence: number;
  thesis: string;
  rationale: string;
  evidence: ResearchEvidence[];
  risks: string[];
  validity_window_minutes: number;
  status: string;
  outcome: string | null;
  decided_at: string | null;
  expired: boolean;
};
export type ResearchRunRequest = {
  lenses?: string[] | null;
  context?: Record<string, string> | null;
  tools?: string[] | null;
};
export type ResearchRunResult = {
  lens: string;
  brief: ResearchBrief | null;
  error: string | null;
};
export type ResearchRunResponse = { results: ResearchRunResult[] };
export type ResearchBriefListResponse = { briefs: ResearchBrief[] };
export type ResearchSchedulerStatus = {
  enabled: boolean;
  interval_minutes: number;
  lenses: string[] | null;
  tools: string[] | null;
  next_run_at: string | null;
  last_run_at: string | null;
  last_result: string | null;
};
export type ResearchDecisionResponse = { brief_id: string; status: string };
export type ResearchScoringItem = {
  lens: string;
  total: number;
  decided: number;
  with_outcome: number;
  win_rate: number;
  avg_confidence: number;
};
```

- [ ] **Step 2: Type-gate**

Run (in `src/shettyxtreme/terminal/web`): `npm run check` — expected 0 errors.

- [ ] **Step 3: Commit (coordinator only)**

```bash
git add src/shettyxtreme/terminal/web/src/lib/api.ts
git commit -m "feat(3c): frontend api — postBody helper + research response types"
```

---

## Task 9: `ResearchPanel.svelte`

**Files:**
- Create: `src/shettyxtreme/terminal/web/src/components/ResearchPanel.svelte`

**Interfaces:**
- Consumes: `get`, `postBody` + research types (Task 8); `onMessage` from `../lib/ws` (existing, topic-based — no ws.ts change needed).
- Produces: 3-region panel — run bar (lens checkboxes, tools multi-select, context textarea, Run button + per-lens result chips), brief list (status + lens filter chips, newest first, click to select), detail view (thesis, badges, rationale, evidence table with `[UNSOURCED]` flag, risks, validity/expiry, outcome, decided_at, Approve/Reject card). WS topic `research`: `new_brief` prepends + auto-selects when nothing selected; `decision` updates status. DESIGN.md conventions: numerals JetBrains Mono (`.mono`), labels Inter, red `#f6525c` = up (direction +1), green `#2ebd85` = down (direction −1), 0 = muted.

- [ ] **Step 1: Write the component** — create `src/shettyxtreme/terminal/web/src/components/ResearchPanel.svelte`:

```svelte
<script lang="ts">
  import { onMount } from "svelte";
  import { get, post, postBody } from "../lib/api";
  import { onMessage } from "../lib/ws";
  import type {
    ResearchBrief,
    ResearchDecisionResponse,
    ResearchLens,
    ResearchRunResponse,
    ResearchToolDef,
  } from "../lib/api";

  let lenses: ResearchLens[] = [];
  let tools: ResearchToolDef[] = [];
  let briefs: ResearchBrief[] = [];
  let selected: ResearchBrief | null = null;
  let selectedId = "";
  let selectedTools: string[] = [];
  let contextText = "";
  let running = false;
  let runChips: { lens: string; ok: boolean; error: string }[] = [];
  let statusFilter = "All";
  let lensFilter = "All";
  let error = "";
  let deciding = false;

  const statuses = ["All", "Proposed", "Approved", "Rejected"];

  onMount(() => {
    loadAll();
    const offNew = onMessage("research", (data) => {
      const ev = data as { event: string; data: unknown };
      if (ev.event === "new_brief") {
        const brief = ev.data as ResearchBrief;
        briefs = [brief, ...briefs.filter((b) => b.brief_id !== brief.brief_id)];
        if (!selectedId) {
          selectedId = brief.brief_id;
          selected = brief;
        }
      } else if (ev.event === "decision") {
        const d = ev.data as { brief_id: string; status: string };
        briefs = briefs.map((b) =>
          b.brief_id === d.brief_id ? { ...b, status: d.status, decided_at: new Date().toISOString() } : b,
        );
        if (selected && selected.brief_id === d.brief_id) selected = { ...selected, status: d.status };
      }
    });
    return offNew;
  });

  async function loadAll(): Promise<void> {
    error = "";
    try {
      const [l, t, b] = await Promise.all([
        get<ResearchLens[]>("/api/research/lenses"),
        get<ResearchToolDef[]>("/api/research/tools"),
        get<ResearchBrief[]>("/api/research/briefs"),
      ]);
      lenses = l;
      tools = t;
      briefs = b;
      if (!selectedId && briefs.length > 0) {
        selectedId = briefs[0].brief_id;
        selected = briefs[0];
      }
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    }
  }

  async function run(): Promise<void> {
    if (running) return;
    running = true;
    runChips = [];
    error = "";
    try {
      const resp = await postBody<ResearchRunResponse>("/api/research/run", {
        lenses: lenses.map((l) => l.name),
        tools: selectedTools.length > 0 ? selectedTools : null,
        context: contextText ? { operator: contextText } : null,
      });
      runChips = resp.results.map((r) => ({
        lens: r.lens,
        ok: r.error === null && r.brief !== null,
        error: r.error ?? "",
      }));
      await loadAll();
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
    } finally {
      running = false;
    }
  }

  function select(id: string): void {
    selectedId = id;
    selected = briefs.find((b) => b.brief_id === id) ?? null;
  }

  function toggleTool(name: string): void {
    selectedTools = selectedTools.includes(name)
      ? selectedTools.filter((t) => t !== name)
      : [...selectedTools, name];
  }

  async function decide(status: "approved" | "rejected"): Promise<void> {
    if (!selected || deciding || selected.status !== "proposed" || selected.expired) return;
    deciding = true;
    error = "";
    try {
      const resp = await post<ResearchDecisionResponse>(
        `/api/research/briefs/${selected.brief_id}/${status}`,
      );
      briefs = briefs.map((b) =>
        b.brief_id === resp.brief_id ? { ...b, status: resp.status } : b,
      );
      if (selected.brief_id === resp.brief_id) selected = { ...selected, status: resp.status };
    } catch (err) {
      error = err instanceof Error ? err.message : String(err);
      await loadAll();
    } finally {
      deciding = false;
    }
  }

  function dirBadgeClass(direction: number): string {
    return direction === 1 ? "price-up" : direction === -1 ? "price-down" : "dir-flat";
  }

  function dirLabel(direction: number): string {
    return direction === 1 ? "+1" : direction === -1 ? "−1" : "0";
  }

  function statusClass(status: string): string {
    return status === "approved" ? "ok" : status === "rejected" ? "bad" : "pending";
  }

  $: filtered = briefs.filter(
    (b) =>
      (statusFilter === "All" || b.status === statusFilter.toLowerCase()) &&
      (lensFilter === "All" || b.lens === lensFilter),
  );
</script>

<section class="panel research">
  <header class="panel-head">
    <h2>Research</h2>
    <button class="refresh" on:click={loadAll} title="Refresh">↻</button>
  </header>

  {#if error}
    <p class="error">{error}</p>
  {/if}

  <div class="run-bar">
    <h3>Run briefers</h3>
    <div class="lens-row">
      {#each lenses as l}
        <label class="check">
          <input type="checkbox" checked disabled={running} />
          <span>{l.name}</span>
        </label>
      {/each}
    </div>
    <div class="tool-row">
      <span class="tool-label">Tools</span>
      {#each tools as t}
        <label class="check">
          <input type="checkbox" checked={selectedTools.includes(t.name)} on:change={() => toggleTool(t.name)} disabled={running} />
          <span>{t.name}</span>
        </label>
      {/each}
    </div>
    <textarea
      class="context mono"
      placeholder="Optional context for this run…"
      bind:value={contextText}
      disabled={running}
    ></textarea>
    <div class="run-row">
      <button class="run-btn" on:click={run} disabled={running || lenses.length === 0}>
        {running ? "Running…" : "Run"}
      </button>
      <div class="chips">
        {#each runChips as chip (chip.lens)}
          <span class="chip {chip.ok ? 'chip-ok' : 'chip-bad'}">{chip.lens}: {chip.ok ? "ok" : chip.error}</span>
        {/each}
      </div>
    </div>
  </div>

  <div class="cols">
    <div class="col list-col">
      <div class="filters">
        <select bind:value={statusFilter} aria-label="Status filter">
          {#each statuses as s}
            <option value={s}>{s}</option>
          {/each}
        </select>
        <select bind:value={lensFilter} aria-label="Lens filter">
          <option value="All">All lenses</option>
          {#each lenses as l}
            <option value={l.name}>{l.name}</option>
          {/each}
        </select>
      </div>
      <ul>
        {#each filtered as b (b.brief_id)}
          <li class:sel={b.brief_id === selectedId} on:click={() => select(b.brief_id)}>
            <span class="tag">{b.lens}</span>
            <span class="num {dirBadgeClass(b.direction)}">{dirLabel(b.direction)}</span>
            <span class="conf mono">{(b.confidence * 100).toFixed(0)}%</span>
            <span class="thesis">{b.thesis}</span>
            <span class="tag {statusClass(b.status)}">{b.status}{b.expired ? " · expired" : ""}</span>
          </li>
        {/each}
        {#if filtered.length === 0}
          <li class="empty">No briefs.</li>
        {/if}
      </ul>
    </div>

    <div class="col detail-col">
      {#if selected}
        <div class="detail">
          <div class="detail-head">
            <span class="tag">{selected.lens}</span>
            <span class="num {dirBadgeClass(selected.direction)}">{dirLabel(selected.direction)}</span>
            <span class="conf mono">{(selected.confidence * 100).toFixed(0)}% confidence</span>
            <span class="tag {statusClass(selected.status)}">{selected.status}</span>
          </div>
          <p class="thesis">{selected.thesis}</p>
          <p class="rationale">{selected.rationale}</p>
          <h4>Evidence</h4>
          <table class="evidence mono">
            <tbody>
              {#each selected.evidence as e (e.item + e.source)}
                <tr>
                  <td>{e.item}</td>
                  <td class="src">{e.unsourced ? "[UNSOURCED]" : e.source}</td>
                </tr>
              {/each}
            </tbody>
          </table>
          {#if selected.risks.length > 0}
            <h4>Risks</h4>
            <ul class="risks">
              {#each selected.risks as r (r)}
                <li>{r}</li>
              {/each}
            </ul>
          {/if}
          <div class="meta mono">
            <span>valid {selected.validity_window_minutes}m</span>
            <span>{selected.expired ? "expired" : "live"}</span>
            {#if selected.outcome}
              <span>outcome: {selected.outcome}</span>
            {/if}
            {#if selected.decided_at}
              <span>decided {selected.decided_at.slice(0, 19)}</span>
            {/if}
          </div>
          {#if selected.status === "proposed" && !selected.expired}
            <div class="decision">
              <button class="approve" on:click={() => decide("approved")} disabled={deciding}>Approve</button>
              <button class="reject" on:click={() => decide("rejected")} disabled={deciding}>Reject</button>
            </div>
          {/if}
        </div>
      {:else}
        <p class="empty">Select a brief to see details.</p>
      {/if}
    </div>
  </div>
</section>

<style>
  .research {
    display: flex;
    flex-direction: column;
    min-width: 320px;
    min-height: 0;
    flex: 1 1 0;
    border-radius: 6px;
    background: var(--surface-card);
    border: 1px solid var(--hairline);
  }
  .panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
  }
  .panel-head h2 {
    margin: 0;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: var(--muted);
    text-transform: uppercase;
  }
  .refresh,
  .run-btn {
    background: none;
    border: 1px solid var(--hairline);
    border-radius: 4px;
    color: var(--muted);
    cursor: pointer;
    padding: 2px 8px;
    font-size: 13px;
  }
  .refresh:hover,
  .run-btn:hover {
    color: var(--ink);
    border-color: var(--hairline-strong);
  }
  .run-btn {
    border-color: var(--accent);
    color: var(--accent-active);
  }
  .run-btn:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .run-bar {
    padding: 8px 10px;
    border-bottom: 1px solid var(--hairline);
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .run-bar h3 {
    margin: 0;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.07em;
    color: var(--faint);
    text-transform: uppercase;
  }
  .lens-row,
  .tool-row {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
    font-size: 11px;
  }
  .tool-label {
    color: var(--faint);
    font-size: 10px;
    text-transform: uppercase;
  }
  .check {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    color: var(--body);
    cursor: pointer;
  }
  .context {
    width: 100%;
    box-sizing: border-box;
    resize: vertical;
    min-height: 44px;
    background: var(--surface);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    color: var(--body);
    font-size: 11px;
    padding: 4px 6px;
  }
  .run-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .chips {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  .chip {
    font-size: 9px;
    padding: 1px 5px;
    border-radius: 4px;
    border: 1px solid var(--hairline-strong);
  }
  .chip-ok {
    color: var(--success);
    border-color: var(--success);
  }
  .chip-bad {
    color: var(--danger);
    border-color: var(--danger);
  }
  .cols {
    flex: 1;
    min-height: 0;
    display: grid;
    grid-template-columns: minmax(220px, 2fr) minmax(280px, 3fr);
    overflow: hidden;
  }
  .col {
    overflow-y: auto;
    padding: 8px 10px;
  }
  .list-col {
    border-right: 1px solid var(--hairline);
  }
  .filters {
    display: flex;
    gap: 6px;
    margin-bottom: 6px;
  }
  .filters select {
    background: var(--surface);
    border: 1px solid var(--hairline);
    border-radius: 4px;
    color: var(--body);
    font-size: 10px;
    padding: 2px 4px;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 0;
    font-size: 11px;
    border-bottom: 1px solid var(--hairline);
    cursor: pointer;
    min-height: 28px;
  }
  li.sel {
    background: color-mix(in srgb, var(--accent) 10%, transparent);
  }
  .tag {
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
    border: 1px solid var(--hairline-strong);
    border-radius: 4px;
    padding: 1px 5px;
    white-space: nowrap;
  }
  .tag.ok {
    color: var(--success);
    border-color: var(--success);
  }
  .tag.bad {
    color: var(--danger);
    border-color: var(--danger);
  }
  .tag.pending {
    color: var(--warning);
    border-color: var(--warning);
  }
  .dir-flat {
    color: var(--muted);
  }
  .conf {
    color: var(--faint);
    min-width: 34px;
    text-align: right;
  }
  .thesis {
    color: var(--body);
    flex: 1;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .empty {
    color: var(--faint);
    border-bottom: none;
  }
  .error {
    color: var(--danger);
    font-size: 11px;
    padding: 8px 10px;
    margin: 0;
  }
  .detail-head {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
    margin-bottom: 6px;
  }
  .detail .thesis {
    white-space: normal;
    color: var(--ink);
    font-weight: 600;
    margin: 0 0 6px;
  }
  .rationale {
    color: var(--body);
    font-size: 11px;
    line-height: 1.5;
    margin: 0 0 8px;
  }
  .detail h4 {
    margin: 8px 0 4px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.07em;
    color: var(--faint);
    text-transform: uppercase;
  }
  .evidence {
    width: 100%;
    border-collapse: collapse;
    font-size: 10px;
  }
  .evidence td {
    padding: 2px 4px;
    border-bottom: 1px solid var(--hairline);
    vertical-align: top;
  }
  .evidence .src {
    color: var(--faint);
  }
  .risks {
    list-style: disc;
    padding-left: 16px;
    font-size: 11px;
    color: var(--warning);
  }
  .meta {
    display: flex;
    gap: 10px;
    flex-wrap: wrap;
    color: var(--faint);
    font-size: 10px;
    margin-top: 8px;
  }
  .decision {
    display: flex;
    gap: 8px;
    margin-top: 10px;
  }
  .decision button {
    flex: 1;
    border-radius: 4px;
    border: 1px solid var(--hairline-strong);
    background: none;
    padding: 5px 0;
    font-size: 11px;
    cursor: pointer;
  }
  .decision button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .approve {
    color: var(--success);
    border-color: var(--success) !important;
  }
  .reject {
    color: var(--danger);
    border-color: var(--danger) !important;
  }
</style>
```

- [ ] **Step 2: Type-gate**

Run (in `src/shettyxtreme/terminal/web`): `npm run check` — expected 0 errors.

- [ ] **Step 3: Commit (coordinator only)**

```bash
git add src/shettyxtreme/terminal/web/src/components/ResearchPanel.svelte
git commit -m "feat(3c): ResearchPanel — run bar, brief list, detail + approve/reject, WS research topic"
```

---

## Task 10: Mount the panel

**Files:**
- Modify: `src/shettyxtreme/terminal/web/src/App.svelte`

- [ ] **Step 1: Edit** — add import after the HintsPanel import:

```svelte
  import ResearchPanel from "./components/ResearchPanel.svelte";
```

and mount it at the top of the right column (before `ScannerPanel`):

```svelte
      <div class="right-col">
        <ResearchPanel />
        <ScannerPanel />
        <LogDrawer bind:open={drawerOpen} />
      </div>
```

- [ ] **Step 2: Type-gate**

Run (in `src/shettyxtreme/terminal/web`): `npm run check` — expected 0 errors.

- [ ] **Step 3: Commit (coordinator only)**

```bash
git add src/shettyxtreme/terminal/web/src/App.svelte
git commit -m "feat(3c): mount ResearchPanel in terminal layout"
```

---

## Task 11: Wave-3 gates, review, and finish

**Files:** none (verification + docs).

- [ ] **Step 1: Full suite gate**

Run: `$env:PYTHONPATH=""; .venv\Scripts\python.exe -m pytest tests/ -q --tb=short --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-w3 -p no:cacheprovider`
Expected: **all pass, 0 skipped** (target ~655+). Fix any regression forward.

- [ ] **Step 2: Standalone + line gates**

```powershell
rg -c "import openalgo|from openalgo" src/shettyxtreme/   # expect zero matches (exit 1)
Get-ChildItem -Path src\shettyxtreme -Filter *.py -Recurse | ForEach-Object { $n=(Get-Content $_.FullName).Count; if ($n -gt 500) { "$($_.FullName): $n" } }   # only the 2 pre-existing adapters
```

- [ ] **Step 3: Frontend gate**

Run (in `src/shettyxtreme/terminal/web`): `npm run check` (0 errors) then `npm run build` → commits the bundle under `src/shettyxtreme/terminal/static/`.

- [ ] **Step 4: Code review + fix waves**

Dispatch code-reviewer subagent on `master...phase3c`; fix Important minors in a fix wave; re-review; then final whole-branch review.

- [ ] **Step 5: Smoke gate (user involvement)**

User sets `DEEPSEEK_API_KEY`; run `& .\.venv\Scripts\python.exe scripts\research_smoke.py` plus a manual tool-loop run via `POST /api/research/run` with `tools: ["regime_snapshot"]`. Watch `thinking: {"type":"disabled"}` acceptance (if 400, drop the field) and tool-call JSON-mode reliability. Report findings; only paper over 806-class entitlement errors per the surfacing rule.

- [ ] **Step 6: Docs + merge + push (coordinator)**

- CHANGELOG.md: new `v0.9.0` entry (Phase 3C, suite count).
- `docs/architecture/v2/sections/17-delivery-roadmap.md`: Phase 3 row → 3C DONE.
- README.md: roadmap/feature list update.
- Merge `phase3c` → master; push master to origin (this ships hygiene + 3C together). Write handoff `docs/superpowers/handoffs/2026-08-01-phase3c-complete-next-session.md`; update `.superpowers/sdd/progress.md`; update O2B pinned context.

---

## Self-review notes (resolved inline)

- Spec §3.2 "400 on bad value": `ResearchOutcomeRequest.outcome` is `str` (not Literal) so the store's `ValueError` maps to the spec'd 400 instead of FastAPI's 422 — documented at the model.
- Spec §3.4 `init_research(broadcast_fn)`: extended to `init_research(broadcast_fn, scheduler)` — one wiring point instead of two module globals (documented deviation, same scanner_router pattern).
- `lib/ws.ts` needs no change: the existing topic-based registry already handles topic `research` (spec §3.4's "handle research topic" is satisfied in the panel via `onMessage`).
- Broadcast is async (`ws_manager.broadcast`); app.py wires a sync wrapper spawning `asyncio.create_task` so `Callable[[dict], None]` per spec holds.
- No 3B test regression: `test_research_api.py`'s existing fixture overrides `rr._ORCHESTRATOR`; `build_orchestrator` only affects the lazy default path.
