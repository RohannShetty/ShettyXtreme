"""Tests for the Phase 3A.1 scanner_finding WS broadcast + store write."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from shettyxtreme.core.event_bus import Event, Topic
from shettyxtreme.terminal.projections import (
    ScannerProjection,
    build_scanner_proposal,
    make_scanner_proposal_bridge,
    scanner_bridge_enabled,
    set_scanner_bridge_config,
    set_scanner_store,
)


@pytest.fixture(autouse=True)
def _detach_store():
    set_scanner_store(None)
    yield
    set_scanner_store(None)


class TestScannerFindingBroadcast:
    """on_scanner_finding() pushes findings to WS clients."""

    @pytest.mark.asyncio
    async def test_broadcast_on_finding(self) -> None:
        proj = ScannerProjection()
        with patch("shettyxtreme.terminal.api.ws_bridge.broadcast", new=AsyncMock()) as bcast:
            await proj.on_scanner_finding(Event(
                Topic.SCANNER_FINDING,
                {
                    "scanner_type": "gamma_spike",
                    "symbol": "NIFTY",
                    "severity": "HIGH",
                    "detail": {"strike": 25000, "gamma": 0.005},
                    "timestamp": "2026-08-13T10:00:00+00:00",
                },
            ))
        bcast.assert_awaited_once()
        topic, payload = bcast.await_args.args
        assert topic == "scanner_finding"
        # The payload carries every field the frontend alert badge needs.
        assert payload["scanner_type"] == "gamma_spike"
        assert payload["symbol"] == "NIFTY"
        assert payload["severity"] == "HIGH"
        assert payload["detail"] == {"strike": 25000, "gamma": 0.005}
        assert payload["timestamp"] == "2026-08-13T10:00:00+00:00"

    @pytest.mark.asyncio
    async def test_timestamp_defaults_to_event_time(self) -> None:
        proj = ScannerProjection()
        event = Event(
            Topic.SCANNER_FINDING, {"scanner_type": "iv_crush", "symbol": "NIFTY"},
        )
        with patch("shettyxtreme.terminal.api.ws_bridge.broadcast", new=AsyncMock()) as bcast:
            await proj.on_scanner_finding(event)
        _topic, payload = bcast.await_args.args
        assert payload["timestamp"] == event.timestamp

    @pytest.mark.asyncio
    async def test_no_broadcast_for_non_dict_data(self) -> None:
        proj = ScannerProjection()
        with patch("shettyxtreme.terminal.api.ws_bridge.broadcast", new=AsyncMock()) as bcast:
            await proj.on_scanner_finding(Event(Topic.SCANNER_FINDING, "not-a-dict"))
        bcast.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_finding_still_stored_when_broadcast_fails(self) -> None:
        proj = ScannerProjection()
        with patch(
            "shettyxtreme.terminal.api.ws_bridge.broadcast",
            new=AsyncMock(side_effect=RuntimeError("ws down")),
        ):
            await proj.on_scanner_finding(Event(
                Topic.SCANNER_FINDING,
                {"scanner_type": "gap_fill", "symbol": "NIFTY", "severity": "LOW", "detail": {}},
            ))
        # In-memory ring buffer still updated — the finding is not lost.
        assert len(proj.get("gap_fill")) == 1


class TestScannerFindingStoreWrite:
    """on_scanner_finding() records findings in the persistent store."""

    class _FakeStore:
        def __init__(self) -> None:
            self.records: list[dict[str, Any]] = []

        def record(self, finding: dict[str, Any]) -> str:
            self.records.append(finding)
            return "id-1"

    @pytest.mark.asyncio
    async def test_record_called_when_store_wired(self) -> None:
        proj = ScannerProjection()
        store = self._FakeStore()
        set_scanner_store(store)
        await proj.on_scanner_finding(Event(
            Topic.SCANNER_FINDING,
            {
                "scanner_type": "theta_harvest",
                "symbol": "NIFTY",
                "severity": "MEDIUM",
                "detail": {"strike": 25000},
            },
        ))
        assert len(store.records) == 1
        assert store.records[0]["scanner_type"] == "theta_harvest"
        assert store.records[0]["detail"] == {"strike": 25000}

    @pytest.mark.asyncio
    async def test_no_record_without_store(self) -> None:
        proj = ScannerProjection()
        await proj.on_scanner_finding(Event(
            Topic.SCANNER_FINDING,
            {"scanner_type": "gap_fill", "symbol": "NIFTY", "severity": "LOW", "detail": {}},
        ))
        assert len(proj.get("gap_fill")) == 1  # in-memory path unaffected

    @pytest.mark.asyncio
    async def test_record_failure_does_not_break_projection(self) -> None:
        proj = ScannerProjection()

        class _BoomStore:
            def record(self, finding: dict[str, Any]) -> str:
                raise RuntimeError("db locked")

        set_scanner_store(_BoomStore())
        await proj.on_scanner_finding(Event(
            Topic.SCANNER_FINDING,
            {"scanner_type": "iv_crush", "symbol": "NIFTY", "severity": "HIGH", "detail": {}},
        ))
        assert len(proj.get("iv_crush")) == 1


# ── P4: Scanner→Proposal bridge ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _bridge_disabled_by_default():
    """Every bridge test starts from a clean, DISABLED config."""
    set_scanner_bridge_config(None)
    yield
    set_scanner_bridge_config(None)


class TestBuildScannerProposal:
    """build_scanner_proposal() — pure decision + hint building."""

    def _finding(self, **overrides: Any) -> dict[str, Any]:
        data: dict[str, Any] = {
            "scanner_type": "max_pain_drift",
            "symbol": "NIFTY",
            "severity": "HIGH",
            "detail": {"direction": "above", "spot": 24100.0, "max_pain": 23500.0},
        }
        data.update(overrides)
        return data

    def test_disabled_config_never_builds(self) -> None:
        assert build_scanner_proposal(self._finding()) is None

    def test_max_pain_drift_above_is_down(self) -> None:
        set_scanner_bridge_config({"enabled": True})
        built = build_scanner_proposal(self._finding())
        assert built is not None
        signal, hint = built
        from shettyxtreme.intelligence.signals.signal_engine import SignalDirection
        assert signal.direction == SignalDirection.DOWN
        assert hint["symbol"] == "NIFTY"
        assert hint["rationale"].startswith("Scanner bridge (max_pain_drift, HIGH)")
        assert hint["tag"] == "scanner:max_pain_drift"

    def test_max_pain_drift_below_is_up(self) -> None:
        set_scanner_bridge_config({"enabled": True})
        built = build_scanner_proposal(self._finding(detail={"direction": "below"}))
        assert built is not None
        signal, _hint = built
        assert signal.direction.name == "UP"

    def test_detail_side_maps_to_direction(self) -> None:
        set_scanner_bridge_config({"enabled": True})
        built = build_scanner_proposal(
            self._finding(scanner_type="pcr_extremes", detail={"side": "BUY"}),
        )
        assert built is not None
        assert built[0].direction.name == "UP"
        built = build_scanner_proposal(
            self._finding(scanner_type="pcr_extremes", detail={"side": "SELL"}),
        )
        assert built is not None
        assert built[0].direction.name == "DOWN"

    def test_detail_direction_bullish_bearish(self) -> None:
        set_scanner_bridge_config({"enabled": True})
        built = build_scanner_proposal(
            self._finding(scanner_type="gap_fill", detail={"direction": "bullish"}),
        )
        assert built is not None
        assert built[0].direction.name == "UP"

    def test_no_direction_is_not_actionable(self) -> None:
        set_scanner_bridge_config({"enabled": True})
        assert build_scanner_proposal(
            self._finding(scanner_type="gamma_spike", detail={"strike": 25000}),
        ) is None

    def test_severity_below_gate_not_actionable(self) -> None:
        set_scanner_bridge_config({"enabled": True, "min_severity": "HIGH"})
        assert build_scanner_proposal(self._finding(severity="MEDIUM")) is None
        assert build_scanner_proposal(self._finding(severity="LOW")) is None

    def test_scanner_type_allowlist(self) -> None:
        set_scanner_bridge_config({
            "enabled": True,
            "scanner_types": ["max_pain_drift"],
        })
        assert build_scanner_proposal(
            self._finding(scanner_type="iv_crush", detail={"direction": "bearish"}),
        ) is None
        assert build_scanner_proposal(self._finding()) is not None

    def test_missing_symbol_not_actionable(self) -> None:
        set_scanner_bridge_config({"enabled": True})
        assert build_scanner_proposal(self._finding(symbol="")) is None


class TestScannerBridgeWiring:
    """ScannerProjection + make_scanner_proposal_bridge end to end."""

    class _FakeEngine:
        def __init__(self) -> None:
            self.created: list[tuple[Any, dict[str, Any]]] = []

        def submit_signal(self, signal: Any, hint: dict[str, Any]) -> str:
            self.created.append((signal, hint))
            return f"proposal-{len(self.created)}"

    @pytest.mark.asyncio
    async def test_bridge_disabled_no_proposal(self) -> None:
        proj = ScannerProjection()
        proj.set_proposal_bridge(make_scanner_proposal_bridge(self._FakeEngine()))
        await proj.on_scanner_finding(Event(
            Topic.SCANNER_FINDING,
            {"scanner_type": "max_pain_drift", "symbol": "NIFTY", "severity": "HIGH",
             "detail": {"direction": "above"}},
        ))
        # Bridge factory returns None when disabled → nothing to call.
        assert proj._proposal_bridge is None

    @pytest.mark.asyncio
    async def test_actionable_finding_creates_proposal(self) -> None:
        set_scanner_bridge_config({"enabled": True, "cooldown_seconds": 900})
        engine = self._FakeEngine()
        proj = ScannerProjection()
        proj.set_proposal_bridge(make_scanner_proposal_bridge(engine))
        with patch("shettyxtreme.terminal.api.ws_bridge.broadcast", new=AsyncMock()):
            await proj.on_scanner_finding(Event(
                Topic.SCANNER_FINDING,
                {"scanner_type": "max_pain_drift", "symbol": "NIFTY", "severity": "HIGH",
                 "detail": {"direction": "above"}},
            ))
        assert len(engine.created) == 1
        assert engine.created[0][1]["symbol"] == "NIFTY"

    @pytest.mark.asyncio
    async def test_cooldown_dedupes_per_symbol_and_type(self) -> None:
        set_scanner_bridge_config({"enabled": True, "cooldown_seconds": 900})
        engine = self._FakeEngine()
        proj = ScannerProjection()
        proj.set_proposal_bridge(make_scanner_proposal_bridge(engine))
        finding = {"scanner_type": "max_pain_drift", "symbol": "NIFTY", "severity": "HIGH",
                   "detail": {"direction": "above"}}
        with patch("shettyxtreme.terminal.api.ws_bridge.broadcast", new=AsyncMock()):
            await proj.on_scanner_finding(Event(Topic.SCANNER_FINDING, finding))
            await proj.on_scanner_finding(Event(Topic.SCANNER_FINDING, finding))
        assert len(engine.created) == 1

    @pytest.mark.asyncio
    async def test_bridge_failure_does_not_break_finding(self) -> None:
        set_scanner_bridge_config({"enabled": True})

        def _boom(finding: dict[str, Any]) -> str:
            raise RuntimeError("engine down")

        proj = ScannerProjection()
        proj.set_proposal_bridge(_boom)
        with patch("shettyxtreme.terminal.api.ws_bridge.broadcast", new=AsyncMock()):
            await proj.on_scanner_finding(Event(
                Topic.SCANNER_FINDING,
                {"scanner_type": "max_pain_drift", "symbol": "NIFTY", "severity": "HIGH",
                 "detail": {"direction": "above"}},
            ))
        # The finding itself is still stored + broadcastable.
        assert len(proj.get("max_pain_drift")) == 1

    def test_bridge_factory_none_when_disabled(self) -> None:
        assert make_scanner_proposal_bridge(self._FakeEngine()) is None
        assert scanner_bridge_enabled() is False
