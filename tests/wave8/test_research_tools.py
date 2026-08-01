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
        "knowledge_search",
    ]
    assert all(t.description for t in list_tools())
    assert TOOLS["chain_snapshot"].params_schema["required"] == ["symbol"]
    assert TOOLS["regime_snapshot"].params_schema["required"] == []
    assert TOOLS["knowledge_search"].params_schema["required"] == ["query"]


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


def test_knowledge_search_with_source() -> None:
    class KSource(FakeSource):
        def knowledge_summary(self, query: str) -> str | None:
            return f"hits for {query}"

    set_data_source(KSource())
    out = run_tool("knowledge_search", {"query": "nifty"})
    assert out == "hits for nifty"


def test_knowledge_search_unsourced() -> None:
    set_data_source(None)
    assert run_tool("knowledge_search", {"query": "nifty"}) == UNSOURCED


def test_knowledge_search_missing_query() -> None:
    set_data_source(None)
    assert run_tool("knowledge_search", {}) == (
        "TOOL ERROR: missing required parameter 'query'"
    )
