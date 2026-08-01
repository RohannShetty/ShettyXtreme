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
        lenses=["oi_iv_flow"],
        provider=p,
        db_path=str(tmp_path / "r.db"),
        tools=["regime_snapshot", "scanner_alerts"],
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
async def test_retry_after_mid_loop_failure_resets_messages(tmp_path) -> None:
    # A ProviderError mid-tool-loop triggers the retry; the retry must
    # start a fresh conversation, not reuse the failed attempt's messages.
    from shettyxtreme.research.provider import ProviderError

    class FlakyToolProvider(SimulatedProvider):
        def __init__(self) -> None:
            super().__init__(
                script=[_valid_brief()],
                simulate_tool_calls=[
                    ToolCall(name="regime_snapshot", arguments={}),
                    ToolCall(name="regime_snapshot", arguments={}),
                ],
            )
            self._calls = 0

        async def generate(self, **kwargs):
            self._calls += 1
            if self._calls == 2:
                raise ProviderError("simulated mid-loop failure")
            return await super().generate(**kwargs)

    p = FlakyToolProvider()
    results, store = await _run(
        lenses=["oi_iv_flow"], provider=p, db_path=str(tmp_path / "r.db")
    )
    assert results[0].error is None and results[0].brief is not None
    assert len(p.calls) == 3  # the failed call raises before recording
    assert p.calls[1]["history"] is None  # retry starts a fresh conversation
    assert len(p.calls[2]["history"]) == 4  # only this attempt's messages
    store.close()


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
