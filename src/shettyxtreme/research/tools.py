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
