# Phase 3B — Research Workspace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the research-layer core: a DeepSeek-backed briefer harness that drafts schema-validated `ResearchBrief`s for 3 lenses (OI/IV flow, directional momentum, tail risk), persists them with human approve/reject, and exposes endpoints.

**Architecture:** Thin deterministic harness — `research/` package with a `BriefProvider` protocol (DeepSeek via httpx + `SimulatedProvider` for tests), declarative lens registry, `ContextDigest` snapshot builder, strict pydantic `ResearchBrief` validation (reject-retry-once), sqlite store with append-only decisions, and an orchestrator that `asyncio.gather`s lenses and returns partial results on failure. D3 wall: `provider.py` is the only module that talks to an LLM.

**Tech Stack:** Python 3.11, httpx (existing dep), pydantic v2 (existing dep), sqlite3, FastAPI, pytest + pytest-asyncio.

## Global Constraints

- D3: no LLM output touches signal/gate/execution; nothing outside `research/` imports LLM code.
- Zero `import openalgo` / `from openalgo` in `src/` (grep gate).
- Zero new runtime dependencies; stdlib + httpx + pydantic only.
- ≤500 lines per file.
- Suite gate: 563 passed / 0 failed → never shrinks.
- Test runner (Windows): `& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-3b -p no:cacheprovider` — never bare `pytest`.
- `DEEPSEEK_API_KEY` env-only, read at call time; never committed/logged.
- Dirty file `docs/superpowers/plans/2026-07-31-graphify-upgrade.md` — never stage or commit it.
- Spec: `docs/superpowers/specs/2026-08-01-phase3b-research-workspace-design.md`.

---

### Task 1: LLM provider abstraction (`provider.py`)

**Files:**
- Create: `src/shettyxtreme/research/provider.py`
- Create: `tests/wave8/test_research_provider.py`

**Interfaces:**
- Produces: `BriefProvider` protocol (`async def generate(*, system: str, prompt: str, max_output_tokens: int) -> str`), `DeepSeekProvider` (same signature), `SimulatedProvider` (same signature; attrs `.fail`, `.calls`), `ProviderError`.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the research provider abstraction (spec §3.1)."""
from __future__ import annotations

import pytest

from shettyxtreme.research.provider import (
    DeepSeekProvider,
    ProviderError,
    SimulatedProvider,
)


@pytest.mark.asyncio
async def test_simulated_default_brief() -> None:
    p = SimulatedProvider()
    out = await p.generate(system="s", prompt="p", max_output_tokens=100)
    assert '"direction": 0' in out


@pytest.mark.asyncio
async def test_simulated_script_cycle() -> None:
    p = SimulatedProvider(script=["one", "two", "three"])
    got = [await p.generate(system="s", prompt="p", max_output_tokens=1) for _ in range(4)]
    assert got == ["one", "two", "three", "three"]
    assert len(p.calls) == 4


@pytest.mark.asyncio
async def test_simulated_failure_injection() -> None:
    p = SimulatedProvider(fail="network")
    with pytest.raises(ProviderError, match="network"):
        await p.generate(system="s", prompt="p", max_output_tokens=10)
    p2 = SimulatedProvider(fail="invalid_json")
    out = await p2.generate(system="s", prompt="p", max_output_tokens=10)
    assert out == "this is not json"


@pytest.mark.asyncio
async def test_deepseek_provider_no_key(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    p = DeepSeekProvider(api_key="")
    with pytest.raises(ProviderError, match="DEEPSEEK_API_KEY"):
        await p.generate(system="s", prompt="p", max_output_tokens=10)


def test_deepseek_uses_env_key(monkeypatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    p = DeepSeekProvider()
    assert p._api_key == "sk-test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/wave8/test_research_provider.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: shettyxtreme.research.provider`

- [ ] **Step 3: Write the implementation**

```python
"""LLM provider abstraction for the research layer.

provider.py is the ONLY module in the codebase that talks to an LLM
(D3 wall): nothing outside research/ imports it, and no LLM output
reaches the signal/gate/execution path.
"""
from __future__ import annotations

import logging
import os
from typing import Protocol

import httpx

logger = logging.getLogger(__name__)

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-v4-flash"


class ProviderError(Exception):
    """Raised when a provider call fails (network, HTTP, or parse)."""


class BriefProvider(Protocol):
    """A provider that turns a prompt into a raw model response string."""

    async def generate(self, *, system: str, prompt: str, max_output_tokens: int) -> str:
        """Return the model's text output. Raises ProviderError on failure."""


class DeepSeekProvider:
    """OpenAI-compatible DeepSeek client via httpx (zero new deps)."""

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEEPSEEK_BASE_URL,
        model: str = DEFAULT_MODEL,
        timeout: float = 90.0,
    ) -> None:
        self._api_key = api_key if api_key is not None else os.environ.get("DEEPSEEK_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._timeout = timeout

    async def generate(self, *, system: str, prompt: str, max_output_tokens: int) -> str:
        if not self._api_key:
            raise ProviderError("DEEPSEEK_API_KEY is not set")
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": max_output_tokens,
            "thinking": {"type": "disabled"},
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    f"{self._base_url}/chat/completions", json=payload, headers=headers
                )
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            raise ProviderError(
                f"DeepSeek HTTP {exc.response.status_code}: {exc.response.text[:200]}"
            ) from exc
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            raise ProviderError(f"DeepSeek call failed: {exc}") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("DeepSeek returned an empty completion")
        return content.strip()


_DEFAULT_BRIEF = (
    '{"instruments": [], "direction": 0, "confidence": 0.5, '
    '"thesis": "No signal", '
    '"rationale": "simulated rationale ' + "x" * 340 + '", '
    '"evidence": [], "risks": []}'
)


class SimulatedProvider:
    """Deterministic test double with failure injection.

    fail: "network" -> ProviderError; "invalid_json" -> non-JSON text.
    Script entries are handed out in order; the last entry repeats; an
    empty script returns a schema-valid default brief.
    """

    def __init__(self, script: list[str] | None = None, fail: str | None = None) -> None:
        self._script = list(script) if script else []
        self.fail = fail
        self.calls: list[dict] = []

    async def generate(self, *, system: str, prompt: str, max_output_tokens: int) -> str:
        self.calls.append(
            {"system": system, "prompt": prompt, "max_output_tokens": max_output_tokens}
        )
        if self.fail == "network":
            raise ProviderError("simulated network failure")
        if self.fail == "invalid_json":
            return "this is not json"
        if not self._script:
            return _DEFAULT_BRIEF
        if len(self._script) == 1:
            return self._script[0]
        return self._script.pop(0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/wave8/test_research_provider.py -q -p no:cacheprovider`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add src/shettyxtreme/research/provider.py tests/wave8/test_research_provider.py
git commit -m "feat: research briefer provider abstraction (DeepSeek + simulated)"
```

---

### Task 2: Lens registry + context digest

**Files:**
- Create: `src/shettyxtreme/research/lenses.py`
- Create: `src/shettyxtreme/research/digest.py`
- Create: `tests/wave8/test_research_lenses_digest.py`

**Interfaces:**
- Consumes: nothing (pure).
- Produces: `Lens` dataclass (`name`, `description`, `system_prompt`, `brief_prompt_template`, method `build_prompt(digest_text) -> str`), `LENSES: dict[str, Lens]` with keys `oi_iv_flow`, `directional_momentum`, `tail_risk`, `list_lenses() -> list[Lens]`, `get_lens(name) -> Lens` (raises `KeyError`); `ContextDigest` (`__init__(sources: dict[str, str] | None = None)`, `add(name, text)`, `build() -> str`, `.sources` property).

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the lens registry and context digest (spec §3.1)."""
from __future__ import annotations

import pytest

from shettyxtreme.research.digest import ContextDigest
from shettyxtreme.research.lenses import LENSES, get_lens, list_lenses


def test_three_lenses_registered() -> None:
    names = {l.name for l in list_lenses()}
    assert names == {"oi_iv_flow", "directional_momentum", "tail_risk"}


def test_get_lens_unknown_raises() -> None:
    with pytest.raises(KeyError):
        get_lens("value")


def test_lens_prompt_builds() -> None:
    lens = get_lens("tail_risk")
    prompt = lens.build_prompt("SNAPSHOT")
    assert "SNAPSHOT" in prompt
    assert "{digest}" not in prompt


def test_digest_build_marks_sources() -> None:
    d = ContextDigest({"regime": "TRENDING_UP"})
    text = d.build()
    assert "[SOURCE: regime]" in text
    assert "TRENDING_UP" in text


def test_digest_unsourced_when_empty() -> None:
    text = ContextDigest().build()
    assert "[UNSOURCED]" in text


def test_digest_caps_sources_and_chars() -> None:
    d = ContextDigest()
    with pytest.raises(ValueError):
        for i in range(9):
            d.add(f"s{i}", "x")
    d2 = ContextDigest({"a": "y" * 5000})
    assert len(d2.sources["a"]) <= 2000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/wave8/test_research_lenses_digest.py -q -p no:cacheprovider`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Write the implementations**

```python
"""Declarative lens registry — section 12 config-registry briefer discovery.

Adding a lens is declarative: one entry in LENSES. Each lens mirrors one
live shadow-voter philosophy so briefs read the same signals the engine does.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Lens:
    """A briefer configuration: identity + prompts."""

    name: str
    description: str
    system_prompt: str
    brief_prompt_template: str

    def build_prompt(self, digest_text: str) -> str:
        return self.brief_prompt_template.format(digest=digest_text)


_BRIEF_FORMAT = (
    "DATA SNAPSHOT:\n{digest}\n\n"
    "Respond with a single JSON object only: "
    '{{"instruments": [..max 10 NSE symbols..], "direction": -1|0|1, '
    '"confidence": 0.0-1.0, "thesis": "1-2 sentences, max 500 chars", '
    '"rationale": "300-1200 chars", '
    '"evidence": [{{"item": "...", "source": "...", "unsourced": bool}}] '
    "(max 10), "
    '"risks": ["..."] (max 5)}}'
)

LENSES: dict[str, Lens] = {
    "oi_iv_flow": Lens(
        name="oi_iv_flow",
        description="Smart-money positioning from OI buildup and IV posture.",
        system_prompt=(
            "You are an options research assistant for Indian NSE markets. "
            "Examine open-interest flow, IV rank, and put/call buildup, and "
            "write one structured brief. Research-only: you never place "
            "orders or instruct trading. Tie every claim to the provided "
            "data; mark anything not in the data as unsourced."
        ),
        brief_prompt_template=(
            "Write a research brief for the OI/IV-flow lens: where is "
            "positioning building, and what does it imply?\n\n" + _BRIEF_FORMAT
        ),
    ),
    "directional_momentum": Lens(
        name="directional_momentum",
        description="Is a directional move building? Momentum, breakouts, gaps.",
        system_prompt=(
            "You are an options research assistant for Indian NSE markets. "
            "Evaluate momentum, breakout, and gap conditions and write one "
            "structured brief. Research-only: you never place orders or "
            "instruct trading. Tie every claim to the provided data; mark "
            "anything not in the data as unsourced."
        ),
        brief_prompt_template=(
            "Write a research brief for the directional-momentum lens: is a "
            "directional move building, and at what conviction?\n\n"
            + _BRIEF_FORMAT
        ),
    ),
    "tail_risk": Lens(
        name="tail_risk",
        description="Stretched conditions and what could break.",
        system_prompt=(
            "You are an options research assistant for Indian NSE markets. "
            "Hunt for stretched conditions, crowding, and tail risks, and "
            "write one structured brief. Research-only: you never place "
            "orders or instruct trading. Tie every claim to the provided "
            "data; mark anything not in the data as unsourced."
        ),
        brief_prompt_template=(
            "Write a research brief for the tail-risk lens: what is "
            "stretched, crowded, or likely to break?\n\n" + _BRIEF_FORMAT
        ),
    ),
}


def list_lenses() -> list[Lens]:
    """All registered lenses, in registry order."""
    return list(LENSES.values())


def get_lens(name: str) -> Lens:
    """Look up a lens by name; raises KeyError for unknown names."""
    if name not in LENSES:
        raise KeyError(name)
    return LENSES[name]
```

```python
"""Context digest — as-of snapshot composed from injectable data sources.

The operator (or a later data-tool layer) attaches named text sources; the
digest renders them with provenance tags and never fabricates content.
"""
from __future__ import annotations

from datetime import UTC, datetime

MAX_SOURCES = 8
MAX_SOURCE_CHARS = 2000


class ContextDigest:
    """Builds the prompt context snapshot from named sources."""

    def __init__(self, sources: dict[str, str] | None = None) -> None:
        self._sources: dict[str, str] = {}
        if sources:
            for name, text in sources.items():
                self.add(name, text)

    @property
    def sources(self) -> dict[str, str]:
        return dict(self._sources)

    def add(self, name: str, text: str) -> None:
        """Add (or replace) one named source. Raises ValueError on bad name
        or when MAX_SOURCES is exceeded."""
        if not name or not name.strip():
            raise ValueError("source name must be non-empty")
        if len(self._sources) >= MAX_SOURCES:
            raise ValueError(f"at most {MAX_SOURCES} sources")
        self._sources[name.strip()] = text[:MAX_SOURCE_CHARS]

    def build(self) -> str:
        """Render the snapshot as markdown with [SOURCE: name] provenance."""
        parts = [f"# Research Context Snapshot (as of {datetime.now(UTC).isoformat()})"]
        if not self._sources:
            parts.append("[UNSOURCED] — no data sources attached to this run.")
        for name, text in self._sources.items():
            parts.append(f"## {name} [SOURCE: {name}]")
            parts.append(text if text else "[UNSOURCED] — no data")
        return "\n\n".join(parts)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/wave8/test_research_lenses_digest.py -q -p no:cacheprovider`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/shettyxtreme/research/lenses.py src/shettyxtreme/research/digest.py tests/wave8/test_research_lenses_digest.py
git commit -m "feat: research lens registry + context digest builder"
```

---

### Task 3: Brief schema + sqlite store

**Files:**
- Create: `src/shettyxtreme/research/briefs.py`
- Create: `src/shettyxtreme/research/store.py`
- Create: `tests/wave8/test_research_briefs_store.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ResearchBrief` pydantic model (fields: `brief_id`, `lens`, `as_of`, `instruments: list[str]` max 10, `direction: int`, `confidence: float` 0–1, `thesis: str` max 500, `rationale: str` 300–1200, `evidence: list[dict]` max 10, `risks: list[str]` max 5, `validity_window_minutes: int = 240`, `status: Literal["proposed","approved","rejected"] = "proposed"`, `outcome: str | None = None`; methods `with_status(str)`, `is_expired(now: str | None = None) -> bool`); `parse_brief_payload(raw_text, *, lens, as_of, brief_id) -> ResearchBrief`; `BriefValidationError`; `ResearchStore(db_path)` with `insert/get/list/decide/set_outcome/close`; `AlreadyDecidedError`.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the brief contract + store (spec §3.3)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from shettyxtreme.research.briefs import BriefValidationError, ResearchBrief, parse_brief_payload
from shettyxtreme.research.store import AlreadyDecidedError, ResearchStore


def _valid_payload() -> str:
    return (
        '{"instruments": ["NIFTY"], "direction": 1, "confidence": 0.6, '
        '"thesis": "Strong OI buildup on the upside", '
        '"rationale": "' + "r" * 320 + '", '
        '"evidence": [{"item": "OI up 12%", "source": "oi_snapshot", "unsourced": false}], '
        '"risks": ["earnings event"]}'
    )


def test_parse_harness_owned_fields_overwritten() -> None:
    brief = parse_brief_payload(
        _valid_payload(), lens="oi_iv_flow", as_of="2026-08-01T10:00:00Z", brief_id="b1"
    )
    assert brief.brief_id == "b1"
    assert brief.lens == "oi_iv_flow"
    assert brief.status == "proposed"
    assert brief.outcome is None
    assert brief.direction == 1


def test_parse_rejects_unknown_fields() -> None:
    with pytest.raises(BriefValidationError, match="unknown fields"):
        parse_brief_payload(
            _valid_payload().replace('"risks"', '"status": "approved", "risks"'),
            lens="l", as_of="a", brief_id="b",
        )


def test_parse_rejects_non_json() -> None:
    with pytest.raises(BriefValidationError, match="invalid JSON"):
        parse_brief_payload("not json", lens="l", as_of="a", brief_id="b")


def test_parse_rejects_bad_direction() -> None:
    with pytest.raises(BriefValidationError, match="schema violation"):
        parse_brief_payload(
            _valid_payload().replace('"direction": 1', '"direction": 5'),
            lens="l", as_of="a", brief_id="b",
        )


def test_brief_model_direct_validation() -> None:
    with pytest.raises(ValidationError):
        ResearchBrief(
            brief_id="x", lens="l", as_of="a", direction=1, confidence=2.0,
            thesis="t", rationale="r" * 320,
        )


def test_store_crud_and_expiry(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "research.db"))
    brief = parse_brief_payload(
        _valid_payload(), lens="oi_iv_flow", as_of=datetime.now(UTC).isoformat(), brief_id="b1"
    )
    store.insert(brief)
    assert store.get("b1") is not None
    assert store.get("nope") is None
    assert store.list()[0].brief_id == "b1"
    assert store.list(lens="oi_iv_flow")[0].brief_id == "b1"
    assert store.list(lens="tail_risk") == []
    old = parse_brief_payload(
        _valid_payload(),
        lens="oi_iv_flow",
        as_of=(datetime.now(UTC) - timedelta(hours=5)).isoformat(),
        brief_id="b2",
    )
    store.insert(old)
    assert store.get("b2").is_expired() is True
    store.close()


def test_store_decision_immutable(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "research.db"))
    store.insert(parse_brief_payload(_valid_payload(), lens="l", as_of="2026-08-01T10:00:00Z", brief_id="b1"))
    decided = store.decide("b1", "approved")
    assert decided.status == "approved"
    with pytest.raises(AlreadyDecidedError):
        store.decide("b1", "rejected")
    with pytest.raises(KeyError):
        store.decide("missing", "approved")
    store.close()


def test_store_outcome_stub(tmp_path) -> None:
    store = ResearchStore(str(tmp_path / "research.db"))
    store.insert(parse_brief_payload(_valid_payload(), lens="l", as_of="2026-08-01T10:00:00Z", brief_id="b1"))
    updated = store.set_outcome("b1", "WIN")
    assert updated.outcome == "WIN"
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/wave8/test_research_briefs_store.py -q -p no:cacheprovider`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Write the implementations**

```python
"""ResearchBrief contract + strict payload validation (section 12).

The model may author only the fields in MODEL_AUTHORED_FIELDS; the harness
owns identity, provenance, and status. Strict pydantic validation with
`additionalProperties: false` semantics (unknown keys rejected) means
injected instructions cannot survive the channel.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field, ValidationError

BriefStatus = Literal["proposed", "approved", "rejected"]

MODEL_AUTHORED_FIELDS = {
    "instruments",
    "direction",
    "confidence",
    "thesis",
    "rationale",
    "evidence",
    "risks",
    "validity_window_minutes",
}

DEFAULT_VALIDITY_MINUTES = 240


class ResearchBrief(BaseModel):
    """One briefer's schema-validated output for one lens."""

    brief_id: str
    lens: str
    as_of: str
    instruments: list[str] = Field(default_factory=list, max_length=10)
    direction: int
    confidence: float = Field(ge=0.0, le=1.0)
    thesis: str = Field(max_length=500)
    rationale: str = Field(min_length=300, max_length=1200)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=10)
    risks: list[str] = Field(default_factory=list, max_length=5)
    validity_window_minutes: int = DEFAULT_VALIDITY_MINUTES
    status: BriefStatus = "proposed"
    outcome: str | None = None

    def with_status(self, status: str) -> "ResearchBrief":
        """Return a copy with a new status (used only for decisions)."""
        return self.model_copy(update={"status": status})

    def is_expired(self, now: str | None = None) -> bool:
        """Proposed briefs expire after their validity window; decided briefs never do."""
        if self.status != "proposed":
            return False
        try:
            created = datetime.fromisoformat(self.as_of)
        except ValueError:
            return True
        expires = created + timedelta(minutes=self.validity_window_minutes)
        reference = datetime.fromisoformat(now) if now else datetime.now(UTC)
        return expires < reference


class BriefValidationError(Exception):
    """Raised when a provider payload fails strict validation."""


def parse_brief_payload(
    raw_text: str, *, lens: str, as_of: str, brief_id: str
) -> ResearchBrief:
    """Strict-parse a provider payload into a ResearchBrief.

    Steps: JSON parse -> object check -> unknown-field rejection -> pydantic
    validation with harness-owned fields injected. Raises BriefValidationError.
    """
    try:
        raw: Any = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise BriefValidationError(f"invalid JSON: {exc}") from exc
    if not isinstance(raw, dict):
        raise BriefValidationError("payload must be a JSON object")
    unknown = set(raw) - MODEL_AUTHORED_FIELDS
    if unknown:
        raise BriefValidationError(f"unknown fields: {sorted(unknown)}")
    try:
        return ResearchBrief(brief_id=brief_id, lens=lens, as_of=as_of, **raw)
    except ValidationError as exc:
        raise BriefValidationError(f"schema violation: {exc}") from exc
```

```python
"""Sqlite store for research briefs and immutable decisions.

Decision records are append-only: once a brief leaves `proposed` its status
never changes. Expiry is computed at read time, never persisted.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from shettyxtreme.research.briefs import ResearchBrief

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS briefs (
    brief_id TEXT PRIMARY KEY,
    payload TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'proposed',
    decided_at TEXT,
    created_at TEXT NOT NULL
);
"""


class AlreadyDecidedError(Exception):
    """Raised when a decision is attempted on an already-decided brief."""


class ResearchStore:
    """Sqlite persistence for briefs; decisions are immutable once made."""

    def __init__(self, db_path: str) -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def insert(self, brief: ResearchBrief) -> ResearchBrief:
        self._conn.execute(
            "INSERT INTO briefs (brief_id, payload, status, created_at) VALUES (?, ?, ?, ?)",
            (brief.brief_id, brief.model_dump_json(), brief.status, brief.as_of),
        )
        self._conn.commit()
        return brief

    @staticmethod
    def _row_to_brief(row: tuple) -> ResearchBrief:
        return ResearchBrief(**json.loads(row[1]))

    def get(self, brief_id: str) -> ResearchBrief | None:
        row = self._conn.execute(
            "SELECT * FROM briefs WHERE brief_id = ?", (brief_id,)
        ).fetchone()
        return self._row_to_brief(row) if row else None

    def list(self, status: str | None = None, lens: str | None = None) -> list[ResearchBrief]:
        sql = "SELECT * FROM briefs"
        clauses: list[str] = []
        params: list[str] = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if lens:
            clauses.append("json_extract(payload, '$.lens') = ?")
            params.append(lens)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY created_at DESC"
        rows = self._conn.execute(sql, params).fetchall()
        return [self._row_to_brief(r) for r in rows]

    def decide(self, brief_id: str, decision: str) -> ResearchBrief:
        """Set status to approved/rejected; raises AlreadyDecidedError if set."""
        brief = self.get(brief_id)
        if brief is None:
            raise KeyError(brief_id)
        if brief.status != "proposed":
            raise AlreadyDecidedError(brief_id)
        payload = json.loads(brief.model_dump_json())
        payload["status"] = decision
        self._conn.execute(
            "UPDATE briefs SET payload = ?, status = ?, decided_at = ? WHERE brief_id = ?",
            (json.dumps(payload), decision, datetime.now(UTC).isoformat(), brief_id),
        )
        self._conn.commit()
        return self._row_to_brief(
            self._conn.execute(
                "SELECT * FROM briefs WHERE brief_id = ?", (brief_id,)
            ).fetchone()
        )

    def set_outcome(self, brief_id: str, outcome: str) -> ResearchBrief:
        """Tracking stub: link a realized outcome (WIN/LOSS) to a brief."""
        brief = self.get(brief_id)
        if brief is None:
            raise KeyError(brief_id)
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

    def close(self) -> None:
        self._conn.close()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/wave8/test_research_briefs_store.py -q -p no:cacheprovider`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add src/shettyxtreme/research/briefs.py src/shettyxtreme/research/store.py tests/wave8/test_research_briefs_store.py
git commit -m "feat: ResearchBrief schema + sqlite store with immutable decisions"
```

---

### Task 4: Orchestrator

**Files:**
- Create: `src/shettyxtreme/research/orchestrator.py`
- Create: `tests/wave8/test_research_orchestrator.py`

**Interfaces:**
- Consumes: `BriefProvider`, `ResearchStore`, `parse_brief_payload`, `BriefValidationError`, `ContextDigest`, `get_lens`, `list_lenses`, `ProviderError` (Tasks 1–3 signatures as built).
- Produces: `LensRunResult` dataclass (`lens: str`, `brief: ResearchBrief | None`, `error: str | None`); `ResearchOrchestrator(provider, store, max_output_tokens=2000, call_timeout=90.0)` with `async run(lenses: Sequence[str] | None = None, sources: Mapping[str, str] | None = None) -> list[LensRunResult]` (raises `ValueError` on unknown lens names; partial results on failure; reject-retry once).

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the research orchestrator (spec §3.1, §3.2 error handling)."""
from __future__ import annotations

import pytest

from shettyxtreme.research.briefs import parse_brief_payload
from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import SimulatedProvider
from shettyxtreme.research.store import ResearchStore


def _valid_brief(direction: int = 1) -> str:
    return (
        f'{{"instruments": ["NIFTY"], "direction": {direction}, '
        '"confidence": 0.6, "thesis": "Thesis here", '
        '"rationale": "' + "r" * 320 + '", '
        '"evidence": [{"item": "x", "source": "y", "unsourced": false}], '
        '"risks": []}'
    )


async def _run(lenses=None, provider=None, db_path=None, sources=None):
    store = ResearchStore(db_path or ":memory:")
    orch = ResearchOrchestrator(provider=provider or SimulatedProvider(), store=store)
    return await orch.run(lenses=lenses, sources=sources), store


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
async def test_network_failure_partial_results(tmp_path) -> None:
    p = SimulatedProvider(fail="network")
    results, store = await _run(lenses=["oi_iv_flow", "directional_momentum"], provider=p, db_path=str(tmp_path / "r.db"))
    assert len(results) == 2
    failed = {r.lens: r for r in results}
    assert failed["oi_iv_flow"].error is not None
    assert failed["oi_iv_flow"].brief is None
    assert failed["directional_momentum"].brief is not None
    assert store.list().__len__() == 1
    store.close()


@pytest.mark.asyncio
async def test_invalid_json_retries_then_fails() -> None:
    # First call invalid JSON, then valid: retry succeeds.
    p = SimulatedProvider(script=["not json", _valid_brief()])
    results, store = await _run(lenses=["oi_iv_flow"], provider=p)
    assert results[0].error is None
    assert results[0].brief is not None
    store.close()


@pytest.mark.asyncio
async def test_persistent_schema_violation_fails() -> None:
    p = SimulatedProvider(script=[_valid_brief().replace('"direction": 1', '"direction": 9')])
    results, store = await _run(lenses=["oi_iv_flow"], provider=p)
    assert results[0].error is not None
    assert "schema violation" in results[0].error
    store.close()


@pytest.mark.asyncio
async def test_token_cap_passed_to_provider() -> None:
    p = SimulatedProvider()
    store = ResearchStore(":memory:")
    orch = ResearchOrchestrator(provider=p, store=store, max_output_tokens=777)
    await orch.run(lenses=["oi_iv_flow"])
    assert p.calls[0]["max_output_tokens"] == 777
    store.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/wave8/test_research_orchestrator.py -q -p no:cacheprovider`
Expected: FAIL — ModuleNotFoundError

- [ ] **Step 3: Write the implementation**

```python
"""Research orchestrator — one-shot per-lens pipeline (5-stage loop, stage 1).

For each lens: digest -> prompt -> provider -> strict validate (reject-retry
once) -> persist. Lenses run concurrently; a failing lens surfaces partial
results + error and never auto-advances or crashes the run.
"""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Mapping, Sequence
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
from shettyxtreme.research.provider import BriefProvider, ProviderError
from shettyxtreme.research.store import ResearchStore

logger = logging.getLogger(__name__)

MAX_RETRIES = 1
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

    async def run(
        self,
        lenses: Sequence[str] | None = None,
        sources: Mapping[str, str] | None = None,
    ) -> list[LensRunResult]:
        """Run the requested lenses (all by default) and persist briefs.

        Raises ValueError on unknown lens names. Never raises for provider
        or validation failures — those become per-lens error entries.
        """
        names = list(lenses) if lenses is not None else [l.name for l in list_lenses()]
        valid = {l.name for l in list_lenses()}
        unknown = [n for n in names if n not in valid]
        if unknown:
            raise ValueError(f"unknown lens: {unknown}")
        digest_text = ContextDigest(dict(sources) if sources else None).build()
        results = await asyncio.gather(*(self._run_one(n, digest_text) for n in names))
        return list(results)

    async def _run_one(self, lens_name: str, digest_text: str) -> LensRunResult:
        lens = get_lens(lens_name)
        brief_id = str(uuid4())
        as_of = datetime.now(UTC).isoformat()
        prompt = lens.build_prompt(digest_text)
        last_error: str | None = None
        for attempt in range(MAX_RETRIES + 1):
            try:
                raw = await asyncio.wait_for(
                    self.provider.generate(
                        system=lens.system_prompt,
                        prompt=prompt,
                        max_output_tokens=self.max_output_tokens,
                    ),
                    timeout=self.call_timeout,
                )
                brief = parse_brief_payload(raw, lens=lens_name, as_of=as_of, brief_id=brief_id)
                self.store.insert(brief)
                return LensRunResult(lens=lens_name, brief=brief)
            except (ProviderError, BriefValidationError, asyncio.TimeoutError) as exc:
                last_error = str(exc)
                logger.warning("Lens %s attempt %d failed: %s", lens_name, attempt + 1, exc)
        return LensRunResult(lens=lens_name, error=last_error)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/wave8/test_research_orchestrator.py -q -p no:cacheprovider`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add src/shettyxtreme/research/orchestrator.py tests/wave8/test_research_orchestrator.py
git commit -m "feat: research orchestrator with reject-retry and partial results"
```

---

### Task 5: API router + models + registration

**Files:**
- Modify: `src/shettyxtreme/terminal/api/models.py` (append Research section)
- Create: `src/shettyxtreme/terminal/api/research_router.py`
- Modify: `src/shettyxtreme/terminal/api/app.py` (import + include_router)
- Create: `tests/wave8/test_research_api.py`

**Interfaces:**
- Consumes: `ResearchOrchestrator`, `ResearchStore`, `AlreadyDecidedError`, `list_lenses`, `ResearchBrief` (Tasks 1–4 signatures as built).
- Produces: router `research_router.router` (prefix `/api/research`), module attrs `RESEARCH_DB_PATH = "data/research.db"` and `_ORCHESTRATOR` (tests override), endpoints per spec §3.2.

- [ ] **Step 1: Write the failing test**

```python
"""Tests for the research API endpoints (spec §3.2)."""
from __future__ import annotations

from typing import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import shettyxtreme.terminal.api.research_router as rr
from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import SimulatedProvider
from shettyxtreme.research.store import ResearchStore
from shettyxtreme.terminal.api.app import app


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
def orchestrator(tmp_path) -> ResearchOrchestrator:
    store = ResearchStore(str(tmp_path / "research.db"))
    rr.RESEARCH_DB_PATH = str(tmp_path / "research.db")
    rr._ORCHESTRATOR = ResearchOrchestrator(provider=SimulatedProvider(), store=store)
    return rr._ORCHESTRATOR


@pytest.mark.asyncio
async def test_lenses(client: AsyncClient) -> None:
    resp = await client.get("/api/research/lenses")
    assert resp.status_code == 200
    names = {l["name"] for l in resp.json()["lenses"]}
    assert names == {"oi_iv_flow", "directional_momentum", "tail_risk"}


@pytest.mark.asyncio
async def test_run_all_lenses(client: AsyncClient, orchestrator) -> None:
    resp = await client.post("/api/research/run", json={})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 3
    assert all(r["brief"] is not None for r in results)
    assert all(r["error"] is None for r in results)


@pytest.mark.asyncio
async def test_run_subset(client: AsyncClient, orchestrator) -> None:
    resp = await client.post("/api/research/run", json={"lenses": ["tail_risk"]})
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["lens"] == "tail_risk"


@pytest.mark.asyncio
async def test_run_unknown_lens_400(client: AsyncClient, orchestrator) -> None:
    resp = await client.post("/api/research/run", json={"lenses": ["nope"]})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_run_with_context(client: AsyncClient, orchestrator) -> None:
    resp = await client.post(
        "/api/research/run", json={"lenses": ["oi_iv_flow"], "context": {"regime": "TRENDING_UP"}}
    )
    assert resp.status_code == 200
    assert resp.json()["results"][0]["brief"] is not None


@pytest.mark.asyncio
async def test_run_503_without_key(client: AsyncClient, monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    rr._ORCHESTRATOR = None
    resp = await client.post("/api/research/run", json={})
    assert resp.status_code == 503
    assert "DEEPSEEK_API_KEY" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_briefs_list_and_get(client: AsyncClient, orchestrator) -> None:
    await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    resp = await client.get("/api/research/briefs")
    assert resp.status_code == 200
    briefs = resp.json()["briefs"]
    assert len(briefs) == 1
    brief_id = briefs[0]["brief_id"]
    got = await client.get(f"/api/research/briefs/{brief_id}")
    assert got.status_code == 200
    assert got.json()["brief_id"] == brief_id
    missing = await client.get("/api/research/briefs/nope")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_approve_reject_and_409(client: AsyncClient, orchestrator) -> None:
    await client.post("/api/research/run", json={"lenses": ["oi_iv_flow"]})
    brief_id = (await client.get("/api/research/briefs")).json()["briefs"][0]["brief_id"]
    ok = await client.post(f"/api/research/briefs/{brief_id}/approve")
    assert ok.status_code == 200
    assert ok.json()["status"] == "approved"
    again = await client.post(f"/api/research/briefs/{brief_id}/approve")
    assert again.status_code == 409
    reject = await client.post(f"/api/research/briefs/{brief_id}/reject")
    assert reject.status_code == 409


@pytest.mark.asyncio
async def test_missing_db_returns_empty(client: AsyncClient, tmp_path) -> None:
    rr.RESEARCH_DB_PATH = str(tmp_path / "nonexistent" / "research.db")
    resp = await client.get("/api/research/briefs")
    assert resp.status_code == 200
    assert resp.json()["briefs"] == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/wave8/test_research_api.py -q -p no:cacheprovider`
Expected: FAIL — `ModuleNotFoundError: shettyxtreme.terminal.api.research_router`

- [ ] **Step 3: Write the implementation**

Append to `src/shettyxtreme/terminal/api/models.py`:

```python
# ── Research ───────────────────────────────────────────────────────────────
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
    expired: bool = False


class LensInfoResponse(BaseModel):
    name: str
    description: str


class LensListResponse(BaseModel):
    lenses: list[LensInfoResponse] = []


class ResearchRunRequest(BaseModel):
    lenses: list[str] | None = None
    context: dict[str, str] | None = None


class ResearchRunItem(BaseModel):
    lens: str
    brief: ResearchBriefResponse | None = None
    error: str | None = None


class ResearchRunResponse(BaseModel):
    results: list[ResearchRunItem] = []


class ResearchBriefListResponse(BaseModel):
    briefs: list[ResearchBriefResponse] = []


class ResearchDecisionResponse(BaseModel):
    brief_id: str
    status: str
```

Create `src/shettyxtreme/terminal/api/research_router.py`:

```python
"""Research router — run briefers, list/approve/reject briefs (Phase 3B).

The orchestrator is created lazily on first run; without DEEPSEEK_API_KEY
the run endpoint returns 503 with an explicit message. DB failures on
read paths degrade to empty/404 payloads — never 500.
"""
from __future__ import annotations

import logging
import os

from fastapi import APIRouter, HTTPException

from shettyxtreme.research.briefs import ResearchBrief
from shettyxtreme.research.lenses import list_lenses
from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import DeepSeekProvider
from shettyxtreme.research.store import AlreadyDecidedError, ResearchStore
from shettyxtreme.terminal.api.models import (
    LensInfoResponse,
    LensListResponse,
    ResearchBriefListResponse,
    ResearchBriefResponse,
    ResearchDecisionResponse,
    ResearchRunItem,
    ResearchRunRequest,
    ResearchRunResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/research", tags=["research"])

RESEARCH_DB_PATH = "data/research.db"
_ORCHESTRATOR: ResearchOrchestrator | None = None


def _get_orchestrator() -> ResearchOrchestrator | None:
    """Lazily build the orchestrator; None when the API key is absent."""
    global _ORCHESTRATOR
    if _ORCHESTRATOR is not None:
        return _ORCHESTRATOR
    if not os.environ.get("DEEPSEEK_API_KEY"):
        return None
    _ORCHESTRATOR = ResearchOrchestrator(
        provider=DeepSeekProvider(), store=ResearchStore(RESEARCH_DB_PATH)
    )
    return _ORCHESTRATOR


def _brief_response(brief: ResearchBrief) -> ResearchBriefResponse:
    return ResearchBriefResponse(**brief.model_dump(), expired=brief.is_expired())


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
    results = await orch.run(lenses=req.lenses, sources=req.context)
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
    return ResearchDecisionResponse(brief_id=brief.brief_id, status=brief.status)
```

Modify `src/shettyxtreme/terminal/api/app.py` — add the import next to the other router imports:

```python
from shettyxtreme.terminal.api.research_router import router as research_router
```

and add the include after `app.include_router(learning_router)`:

```python
app.include_router(research_router)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `& .\.venv\Scripts\python.exe -m pytest tests/wave8/test_research_api.py -q -p no:cacheprovider`
Expected: PASS (10 passed)

- [ ] **Step 5: Commit**

```bash
git add src/shettyxtreme/terminal/api/models.py src/shettyxtreme/terminal/api/research_router.py src/shettyxtreme/terminal/api/app.py tests/wave8/test_research_api.py
git commit -m "feat: research API endpoints (run, lenses, briefs, approve/reject)"
```

---

### Task 6: Smoke script + gates

**Files:**
- Create: `scripts/research_smoke.py`

**Interfaces:**
- Consumes: `ResearchOrchestrator`, `DeepSeekProvider`, `ResearchStore` (as built).

- [ ] **Step 1: Write the smoke script**

```python
"""Manual DeepSeek research smoke run — requires DEEPSEEK_API_KEY.

Usage:
    $env:DEEPSEEK_API_KEY = "sk-..."
    & .\.venv\Scripts\python.exe scripts\research_smoke.py

Exit codes: 0 = all lenses produced briefs; 1 = some/all failed; 2 = no key.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from shettyxtreme.research.orchestrator import ResearchOrchestrator
from shettyxtreme.research.provider import DeepSeekProvider
from shettyxtreme.research.store import ResearchStore


SOURCES = {
    "regime": "NIFTY 24,700; regime=TRENDING_UP; adx=28; D=0.6 P=0.55 G=trending",
    "scanners": "breakout: NIFTY above 20-day high; gap_up: BANKNIFTY +0.8%",
    "options_intel": "IV rank 62 (elevated); PCR 0.9; OI buildup at 24,800 CE",
}


async def main() -> int:
    if not os.environ.get("DEEPSEEK_API_KEY"):
        print("DEEPSEEK_API_KEY is not set — refusing to run")
        return 2
    store = ResearchStore("data/research.db")
    orch = ResearchOrchestrator(provider=DeepSeekProvider(), store=store)
    results = await orch.run(sources=SOURCES)
    failures = 0
    for r in results:
        if r.error:
            failures += 1
            print(f"[{r.lens}] ERROR: {r.error}")
        else:
            print(
                f"[{r.lens}] direction={r.brief.direction:+d} "
                f"confidence={r.brief.confidence:.2f} — {r.brief.thesis}"
            )
    store.close()
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
```

- [ ] **Step 2: Verify it is import-clean without the key**

Run: `& .\.venv\Scripts\python.exe scripts\research_smoke.py`
Expected: prints `DEEPSEEK_API_KEY is not set — refusing to run`, exit code 2 (no network, no imports of the app)

- [ ] **Step 3: Full-suite + gate verification**

Run:
```bash
& .\.venv\Scripts\python.exe -m pytest tests/ -q --basetemp=C:\Users\rohan\AppData\Local\Temp\opencode\pytest-3b -p no:cacheprovider
grep -r "import openalgo\|from openalgo" src/shettyxtreme/   # expect zero matches
Get-ChildItem -Path src\shettyxtreme -Filter *.py -Recurse | ForEach-Object { if ((Get-Content $_.FullName).Count -gt 500) { $_.FullName } }
```
Expected: full suite ≥ 576 passed, 0 failed; grep zero matches; no file > 500 lines.

- [ ] **Step 4: Commit**

```bash
git add scripts/research_smoke.py
git commit -m "feat: research smoke script (env-gated manual DeepSeek run)"
```

---

### Task 7: Docs, ledger, handoff

**Files:**
- Modify: `CHANGELOG.md`, `docs/architecture/v2/sections/17-delivery-roadmap.md`, `README.md` (feature list), `.superpowers/sdd/progress.md`

- [ ] **Step 1: Update docs**

- `CHANGELOG.md`: add v0.8.0 entry — "Phase 3B: research workspace core — DeepSeek briefer harness (3 lenses: OI/IV flow, directional momentum, tail risk), schema-validated ResearchBriefs with reject-retry, sqlite store with immutable approve/reject, /api/research endpoints."
- `17-delivery-roadmap.md`: Phase 3 row exit criterion — append `3B: research workspace core DONE (draft briefs + human approve/reject) — 3C: tools/critic/panel`.
- `README.md`: feature list — add research workspace bullet.
- `.superpowers/sdd/progress.md`: Phase 3B section — per-task completion + review verdicts + deferred minors (WS broadcast, digest source wiring, outcome scoring).

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md docs/architecture/v2/sections/17-delivery-roadmap.md README.md .superpowers/sdd/progress.md
git commit -m "docs: phase3b changelog v0.8.0 + roadmap/README status"
```

- [ ] **Step 3: Final review + handoff**

Run: `git diff -U10 master...HEAD` review by code-reviewer subagent (standards + spec axes); then write `docs/superpowers/handoffs/2026-08-01-phase3b-complete-next-session.md` with where-things-stand, next-session todos (push both phases, 3C tools/critic/panel, registry→engine wiring, deferred minors), and open questions (push origin? smoke run with real key?).

