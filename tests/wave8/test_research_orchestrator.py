"""Tests for the research orchestrator (spec §3.1, §3.2 error handling)."""
from __future__ import annotations

import pytest

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
async def test_network_failure_all_fail_no_crash(tmp_path) -> None:
    p = SimulatedProvider(fail="network")
    results, store = await _run(
        lenses=["oi_iv_flow", "directional_momentum"], provider=p,
        db_path=str(tmp_path / "r.db"),
    )
    assert len(results) == 2
    assert all(r.error is not None for r in results)
    assert all(r.brief is None for r in results)
    assert store.list().__len__() == 0
    store.close()


@pytest.mark.asyncio
async def test_partial_results_one_lens_fails(tmp_path) -> None:
    # The oi_iv_flow lens's system prompt uniquely contains "Examine
    # open-interest flow" — it fails both attempts; the other lens succeeds.
    p = SimulatedProvider(fail_system_substring="Examine open-interest flow")
    results, store = await _run(
        lenses=["oi_iv_flow", "directional_momentum"], provider=p,
        db_path=str(tmp_path / "r.db"),
    )
    assert len(results) == 2
    errors = [r for r in results if r.error is not None]
    briefs = [r for r in results if r.brief is not None]
    assert len(errors) == 1
    assert len(briefs) == 1
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
    p = SimulatedProvider(
        script=[_valid_brief().replace('"direction": 1', '"direction": 9')]
    )
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
