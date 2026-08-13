"""Tests for the Phase 3A.1 Tier-B scanner poller and threshold wiring."""
from __future__ import annotations

import asyncio
import types
from typing import Any

import pytest

import shettyxtreme.intelligence.scanners.iv_crush_scanner as iv_crush_mod
import shettyxtreme.intelligence.scanners.iv_expansion_scanner as iv_expansion_mod
import shettyxtreme.intelligence.scanners.max_pain_drift_scanner as max_pain_drift_mod
import shettyxtreme.terminal.api.scanner_poller as scanner_poller
from shettyxtreme.core.event_bus import EventBus
from shettyxtreme.intelligence.scanners import (
    SCANNER_REGISTRY,
    TIER_B_SCANNER_TYPES,
    instantiate_scanners,
)
from shettyxtreme.intelligence.scanners.base_scanner import ScannerType
from shettyxtreme.intelligence.scanners.oi_buildup_scanner import OIBuildupScanner
from shettyxtreme.intelligence.scanners.pcr_extremes_scanner import PCRExtremesScanner


def make_chain(spot: float = 100.0) -> list[dict[str, Any]]:
    """A small fake Fyers chain around ``spot`` (both CE and PE sides)."""
    return [
        {"strike": 95.0, "strike_price": 95.0, "option_type": "CE", "ltp": 5.5, "iv": 0.20, "oi": 10_000},
        {"strike": 100.0, "strike_price": 100.0, "option_type": "CE", "ltp": 3.0, "iv": 0.22, "oi": 15_000},
        {"strike": 105.0, "strike_price": 105.0, "option_type": "CE", "ltp": 1.2, "iv": 0.24, "oi": 8_000},
        {"strike": 95.0, "strike_price": 95.0, "option_type": "PE", "ltp": 0.8, "iv": 0.25, "oi": 12_000},
        {"strike": 100.0, "strike_price": 100.0, "option_type": "PE", "ltp": 2.4, "iv": 0.23, "oi": 18_000},
        {"strike": 105.0, "strike_price": 105.0, "option_type": "PE", "ltp": 5.0, "iv": 0.21, "oi": 9_000},
    ]


class FakeScanner:
    """Duck-typed scanner recording every scan()/scan_chain() invocation."""

    def __init__(self, scanner_type: ScannerType) -> None:
        self.scanner_type = scanner_type
        self.calls: list[tuple[str, tuple, dict]] = []

    async def scan(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("scan", args, kwargs))

    async def scan_chain(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append(("scan_chain", args, kwargs))


def make_fake_app(scanners: list[FakeScanner], chain: dict[str, Any]) -> Any:
    """A minimal app stand-in: state carries scanners + cached chain."""
    state = types.SimpleNamespace(
        scanners=scanners,
        options_chain=chain,
        instrument_master=None,
        iv_rank_calculator=None,
        oi_tracker=None,
    )
    return types.SimpleNamespace(state=state)


def make_poll_fixture(symbols: tuple[str, ...] = ("NIFTY",)) -> tuple[list[FakeScanner], Any]:
    scanners = [FakeScanner(st) for st in ScannerType]
    chain = {sym: {"spot": 100.0, "contracts": make_chain()} for sym in symbols}
    return scanners, make_fake_app(scanners, chain)


class TestInstantiateScannersThresholds:
    """instantiate_scanners() applies configured thresholds (Phase 3A.1)."""

    def test_module_constant_thresholds_applied(self) -> None:
        scanners = instantiate_scanners(
            EventBus(),
            thresholds={
                "iv_crush": {"iv_rank_threshold": 60.0, "dte_threshold": 5},
                "iv_expansion": {"iv_rank_low": 15.0},
                "max_pain_drift": {"drift_threshold": 3.5, "dte_threshold": 4},
                "gamma_spike": {"gamma_spike_multiplier": 3.0},
                "vertical_skew": {"skew_threshold": 7.5},
                "calendar_spread": {"iv_diff_threshold": 20.0},
                "theta_harvest": {"theta_vega_ratio": 4.0, "dte_threshold": 7},
                "gap_fill": {"gap_threshold": 2.0},
                "volume_anomaly": {"volume_multiplier": 5.0, "price_change_epsilon": 0.2},
            },
        )
        assert len(scanners) == len(SCANNER_REGISTRY)
        # Module globals overridden (read at scan time by each scanner).
        assert iv_crush_mod._IV_RANK_THRESHOLD == 60.0
        assert iv_crush_mod._DTE_THRESHOLD == 5
        assert iv_expansion_mod._IV_RANK_LOW == 15.0
        assert max_pain_drift_mod._DRIFT_THRESHOLD == 3.5
        assert max_pain_drift_mod._DTE_THRESHOLD == 4

    def test_constructor_kwarg_thresholds_applied(self) -> None:
        scanners = instantiate_scanners(
            EventBus(),
            thresholds={
                "pcr_extremes": {"pcr_low": 0.4, "pcr_high": 2.0},
                "oi_buildup": {"oi_change_threshold": 30.0},
            },
        )
        pcr = next(s for s in scanners if s.scanner_type == ScannerType.PCR_EXTREMES)
        assert isinstance(pcr, PCRExtremesScanner)
        assert pcr._pcr_low == 0.4
        assert pcr._pcr_high == 2.0
        oi = next(s for s in scanners if s.scanner_type == ScannerType.OI_BUILDUP)
        assert isinstance(oi, OIBuildupScanner)
        assert oi._threshold == 30.0

    def test_defaults_reset_on_next_instantiation(self) -> None:
        instantiate_scanners(EventBus(), thresholds={"iv_crush": {"iv_rank_threshold": 55.0}})
        assert iv_crush_mod._IV_RANK_THRESHOLD == 55.0
        # A fresh call without thresholds restores the built-in defaults.
        instantiate_scanners(EventBus())
        assert iv_crush_mod._IV_RANK_THRESHOLD == 80.0
        assert iv_crush_mod._DTE_THRESHOLD == 2

    def test_unknown_params_and_types_ignored(self) -> None:
        scanners = instantiate_scanners(
            EventBus(),
            thresholds={
                "iv_crush": {"bogus_param": 1.0},
                "not_a_scanner": {"whatever": 1.0},
            },
        )
        assert len(scanners) == len(SCANNER_REGISTRY)
        # Unknown params never leak into constructors.
        assert iv_crush_mod._IV_RANK_THRESHOLD == 80.0

    def test_tier_b_constant_covers_eight_types(self) -> None:
        assert TIER_B_SCANNER_TYPES == {
            "gamma_spike", "iv_crush", "iv_expansion", "pcr_extremes",
            "max_pain_drift", "theta_harvest", "calendar_spread", "vertical_skew",
        }


class TestRunScannerPoll:
    """_run_scanner_poll() dispatches every Tier-B scanner against the cache."""

    @pytest.mark.asyncio
    async def test_all_tier_b_scanners_called(self) -> None:
        scanners, app = make_poll_fixture()
        await scanner_poller._run_scanner_poll(app)

        by_type = {s.scanner_type.value: s for s in scanners}
        for type_value in TIER_B_SCANNER_TYPES:
            scanner = by_type[type_value]
            assert scanner.calls, f"{type_value} was never called"
            assert scanner.calls[0][0] == ("scan_chain" if type_value == "gamma_spike" else "scan")

    @pytest.mark.asyncio
    async def test_scan_argument_shapes(self) -> None:
        scanners, app = make_poll_fixture()
        await scanner_poller._run_scanner_poll(app)

        by_type = {s.scanner_type.value: s for s in scanners}

        # gamma_spike: (symbol, enriched contract dicts with gamma)
        method, args, _ = by_type["gamma_spike"].calls[0]
        assert method == "scan_chain"
        assert args[0] == "NIFTY"
        assert isinstance(args[1], list) and args[1] and "gamma" in args[1][0]

        # iv_crush: (symbol, atm_iv, dte) — ATM IV from the near-ATM CE
        method, args, _ = by_type["iv_crush"].calls[0]
        assert method == "scan"
        assert args[0] == "NIFTY"
        assert isinstance(args[1], float) and args[1] > 0
        assert isinstance(args[2], int) and args[2] >= 1

        # max_pain_drift: (symbol, spot, raw contracts, dte)
        method, args, _ = by_type["max_pain_drift"].calls[0]
        assert args[1] == 100.0
        assert isinstance(args[2], list) and len(args[2]) == 6

        # theta_harvest: (symbol, spot, enriched, dte)
        method, args, _ = by_type["theta_harvest"].calls[0]
        assert args[1] == 100.0
        assert isinstance(args[2], list) and "iv" in args[2][0]

        # calendar_spread: (symbol, weekly, monthly) — monthly empty (single
        # snapshot limitation).
        method, args, _ = by_type["calendar_spread"].calls[0]
        assert args[1] and args[2] == []

        # vertical_skew: (symbol, enriched)
        method, args, _ = by_type["vertical_skew"].calls[0]
        assert isinstance(args[1], list) and "delta" in args[1][0]

        # pcr_extremes: (symbol,)
        method, args, _ = by_type["pcr_extremes"].calls[0]
        assert args == ("NIFTY",)

        # iv_expansion: (symbol, atm_iv)
        method, args, _ = by_type["iv_expansion"].calls[0]
        assert args[0] == "NIFTY" and isinstance(args[1], float)

    @pytest.mark.asyncio
    async def test_skips_symbols_without_contracts(self) -> None:
        scanners, app = make_poll_fixture()
        app.state.options_chain = {
            "NIFTY": {"spot": 100.0, "contracts": []},
            "EMPTY": {},
        }
        await scanner_poller._run_scanner_poll(app)
        assert all(not s.calls for s in scanners)

    @pytest.mark.asyncio
    async def test_scanner_failure_does_not_abort_pass(self) -> None:
        scanners, app = make_poll_fixture()
        by_type = {s.scanner_type.value: s for s in scanners}

        async def boom(*args: Any, **kwargs: Any) -> None:
            raise RuntimeError("scanner exploded")

        by_type["gamma_spike"].scan_chain = boom
        by_type["pcr_extremes"].scan = boom
        await scanner_poller._run_scanner_poll(app)
        # The other six scanners still ran.
        for type_value in TIER_B_SCANNER_TYPES - {"gamma_spike", "pcr_extremes"}:
            assert by_type[type_value].calls, f"{type_value} should still have run"

    @pytest.mark.asyncio
    async def test_no_scanners_noop(self) -> None:
        app = make_fake_app([], {"NIFTY": {"spot": 100.0, "contracts": make_chain()}})
        await scanner_poller._run_scanner_poll(app)  # must not raise


class TestScannerPollLoop:
    """_scanner_poll_loop() iterates on a cadence and cancels cleanly."""

    @pytest.mark.asyncio
    async def test_loop_polls_repeatedly_and_cancels(self) -> None:
        scanners, app = make_poll_fixture()
        task = asyncio.create_task(scanner_poller._scanner_poll_loop(app, cadence=0.01))
        try:
            await asyncio.sleep(0.06)
            calls = sum(len(s.calls) for s in scanners)
            # 8 Tier-B scanners × at least one completed poll pass.
            assert calls >= 8
        finally:
            task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
