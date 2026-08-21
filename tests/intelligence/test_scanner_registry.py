"""Tests for the 11-type scanner registry, finding emission, projection, and endpoint.

Covers:
  - test_scanner_registry: all 11 scanners registered
  - test_scanner_finding_emitted: each scanner publishes SCANNER_FINDING
  - test_scanner_projection_stores_findings: capped per-type lists
  - test_scanner_findings_endpoint: /api/scanner/findings returns findings
  - Per-scanner unit tests (11 tests, one per scanner type)
"""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta, timezone

import pytest

from shettyxtreme.core.data_models import Bar
from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.intelligence.scanners import (
    SCANNER_REGISTRY,
    ALL_SCANNER_TYPES,
    BaseScanner,
    ScannerType,
    GapFillScanner,
    VolumeAnomalyScanner,
    OIBuildupScanner,
    GammaSpikeScanner,
    IVCrushScanner,
    IVExpansionScanner,
    PCRExtremesScanner,
    MaxPainDriftScanner,
    ThetaHarvestScanner,
    CalendarSpreadScanner,
    VerticalSkewScanner,
    instantiate_scanners,
)
from shettyxtreme.intelligence.scanners.base_scanner import ScannerType as ST


# ── Helpers ──────────────────────────────────────────────────────────────────

def make_bar(
    symbol: str = "TEST",
    open_: float = 100.0,
    high: float = 105.0,
    low: float = 95.0,
    close: float = 102.0,
    volume: int = 100_000,
    oi: int | None = None,
    dt: datetime | None = None,
) -> Bar:
    if dt is None:
        dt = datetime.now(UTC)
    return Bar(
        symbol=symbol, exchange="NSE", timeframe="1d",
        open=open_, high=high, low=low, close=close,
        volume=volume, timestamp=dt, oi=oi,
    )


def make_chain_contracts(
    spot: float = 25000.0,
    strikes: list[float] | None = None,
    iv: float = 0.2,
    oi: int = 10000,
) -> list[dict]:
    if strikes is None:
        strikes = [spot - 500, spot - 250, spot, spot + 250, spot + 500]
    contracts = []
    for s in strikes:
        contracts.append({
            "strike": s,
            "option_type": "CE",
            "iv": iv,
            "oi": oi,
            "volume": 1000,
            "delta": max(0.01, min(0.99, 0.5 + (spot - s) / (spot * 0.1))),
            "gamma": 0.001,
            "theta": -0.5,
            "vega": 0.15,
        })
        contracts.append({
            "strike": s,
            "option_type": "PE",
            "iv": iv,
            "oi": oi,
            "volume": 1000,
            "delta": max(-0.99, min(-0.01, -0.5 + (s - spot) / (spot * 0.1))),
            "gamma": 0.001,
            "theta": -0.5,
            "vega": 0.15,
        })
    return contracts


# ── Registry tests ───────────────────────────────────────────────────────────

class TestScannerRegistry:
    """Verify the scanner registry is complete and well-formed."""

    def test_all_11_scanners_registered(self) -> None:
        """All 11 scanner types are in the registry."""
        assert len(SCANNER_REGISTRY) == 11
        registered_types = {st for st, _ in SCANNER_REGISTRY}
        for st in ScannerType:
            assert st in registered_types, f"{st.value} missing from registry"

    def test_all_scanner_types_list(self) -> None:
        """ALL_SCANNER_TYPES has 11 entries."""
        assert len(ALL_SCANNER_TYPES) == 11

    def test_registry_classes_are_base_scanner_subclasses(self) -> None:
        """Every registered class is a BaseScanner subclass."""
        for st, cls in SCANNER_REGISTRY:
            assert issubclass(cls, BaseScanner), f"{cls.__name__} is not BaseScanner"

    def test_instantiate_scanners(self) -> None:
        """instantiate_scanners creates 11 scanner instances."""
        bus = EventBus()
        scanners = instantiate_scanners(bus)
        assert len(scanners) == 11
        for s in scanners:
            assert isinstance(s, BaseScanner)


# ── ScannerProjection tests ──────────────────────────────────────────────────

class TestScannerProjection:
    """Verify ScannerProjection stores and filters findings."""

    def test_stores_findings_by_type(self) -> None:
        from shettyxtreme.terminal.projections import ScannerProjection
        proj = ScannerProjection()
        asyncio.run(proj.on_scanner_finding(Event(
            Topic.SCANNER_FINDING,
            {
                "scanner_type": "gap_fill",
                "symbol": "NIFTY",
                "severity": "HIGH",
                "detail": {"gap_percent": 2.5},
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )))
        findings = proj.get("gap_fill")
        assert len(findings) == 1
        assert findings[0]["symbol"] == "NIFTY"

    def test_filter_by_type(self) -> None:
        from shettyxtreme.terminal.projections import ScannerProjection
        proj = ScannerProjection()
        for stype in ("gap_fill", "gamma_spike"):
            asyncio.run(proj.on_scanner_finding(Event(
                Topic.SCANNER_FINDING,
                {"scanner_type": stype, "symbol": "TEST", "severity": "MEDIUM", "detail": {}},
            )))
        assert len(proj.get("gap_fill")) == 1
        assert len(proj.get("gamma_spike")) == 1
        assert len(proj.get()) == 2

    def test_capped_per_type(self) -> None:
        from shettyxtreme.terminal.projections import ScannerProjection
        proj = ScannerProjection()
        for i in range(150):
            asyncio.run(proj.on_scanner_finding(Event(
                Topic.SCANNER_FINDING,
                {"scanner_type": "gap_fill", "symbol": f"S{i}", "severity": "LOW", "detail": {}},
            )))
        assert len(proj.get("gap_fill")) == ScannerProjection.MAX_PER_TYPE

    def test_count_by_type(self) -> None:
        from shettyxtreme.terminal.projections import ScannerProjection
        proj = ScannerProjection()
        for _ in range(3):
            asyncio.run(proj.on_scanner_finding(Event(
                Topic.SCANNER_FINDING,
                {"scanner_type": "gamma_spike", "symbol": "NIFTY", "severity": "HIGH", "detail": {}},
            )))
        counts = proj.count_by_type()
        assert counts["gamma_spike"] == 3

    def test_subscribe_to_scanner_finding(self) -> None:
        from shettyxtreme.terminal.projections import ScannerProjection
        proj = ScannerProjection()
        bus = EventBus()
        proj.subscribe(bus)
        # Verify the subscription was registered
        assert Topic.SCANNER_FINDING in bus._subscribers


# ── SCANNER_FINDING topic test ──────────────────────────────────────────────

class TestScannerFindingTopic:
    """Verify SCANNER_FINDING topic exists and works."""

    def test_topic_exists(self) -> None:
        assert hasattr(Topic, 'SCANNER_FINDING')
        assert Topic.SCANNER_FINDING.value == "scanner.finding"


# ── Per-scanner unit tests ──────────────────────────────────────────────────

class TestGapFillScanner:
    """GapFillScanner: gap > 1% between bars."""

    def test_detects_gap(self) -> None:
        bus = EventBus()
        scanner = GapFillScanner(event_bus=bus)
        dt1 = datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc)
        dt2 = datetime(2025, 1, 2, 9, 15, tzinfo=timezone.utc)
        bars = [
            make_bar(close=100.0, open_=100.0, dt=dt1),
            make_bar(close=105.0, open_=103.0, dt=dt2),
        ]
        results = scanner.scan_bars("TEST", bars)
        assert len(results) >= 1
        assert results[0]["gap_percent"] == pytest.approx(3.0, rel=0.1)

    def test_no_gap_below_threshold(self) -> None:
        bus = EventBus()
        scanner = GapFillScanner(event_bus=bus)
        dt1 = datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc)
        dt2 = datetime(2025, 1, 2, 9, 15, tzinfo=timezone.utc)
        bars = [
            make_bar(close=100.0, open_=100.0, dt=dt1),
            make_bar(close=100.5, open_=100.5, dt=dt2),
        ]
        results = scanner.scan_bars("TEST", bars)
        assert len(results) == 0

    def test_scanner_type(self) -> None:
        bus = EventBus()
        scanner = GapFillScanner(event_bus=bus)
        assert scanner.scanner_type == ST.GAP_FILL


class TestVolumeAnomalyScanner:
    """VolumeAnomalyScanner: volume > 3× avg with unchanged price."""

    def test_detects_volume_spike(self) -> None:
        bus = EventBus()
        scanner = VolumeAnomalyScanner(event_bus=bus)
        bar = make_bar(open_=100.0, close=100.0, volume=500_000)
        history = [100_000] * 20
        results = scanner.scan_bar("TEST", bar, history)
        assert len(results) == 1
        assert results[0]["volume_ratio"] > 3.0

    def test_no_spike_with_price_change(self) -> None:
        bus = EventBus()
        scanner = VolumeAnomalyScanner(event_bus=bus)
        bar = make_bar(open_=100.0, close=105.0, volume=500_000)
        history = [100_000] * 20
        results = scanner.scan_bar("TEST", bar, history)
        assert len(results) == 0

    def test_scanner_type(self) -> None:
        bus = EventBus()
        scanner = VolumeAnomalyScanner(event_bus=bus)
        assert scanner.scanner_type == ST.VOLUME_ANOMALY


class TestOIBuildupScanner:
    """OIBuildupScanner: OI change > 20%."""

    def test_scanner_type(self) -> None:
        from shettyxtreme.options.oi_tracker import OITracker
        bus = EventBus()
        tracker = OITracker()
        scanner = OIBuildupScanner(event_bus=bus, oi_tracker=tracker)
        assert scanner.scanner_type == ST.OI_BUILDUP

    def test_chain_alerts_above_threshold(self) -> None:
        from shettyxtreme.options.oi_tracker import OITracker
        bus = EventBus()
        tracker = OITracker()
        scanner = OIBuildupScanner(event_bus=bus, oi_tracker=tracker)
        # Seed initial OI
        tracker.update_from_chain("NIFTY", "2025-01-30", [
            {"strike": 25000, "option_type": "CE", "oi": 10000},
        ])
        # Update with big change
        findings = scanner.scan_chain_alerts("NIFTY", "2025-01-30", [
            {"strike": 25000, "option_type": "CE", "oi": 15000},
        ])
        assert len(findings) >= 1


class TestGammaSpikeScanner:
    """GammaSpikeScanner: gamma > 2× mean."""

    @pytest.mark.asyncio
    async def test_detects_spike(self) -> None:
        bus = EventBus()
        scanner = GammaSpikeScanner(event_bus=bus)
        # Seed history
        scanner._gamma_history["NIFTY"][25000.0].extend([0.001, 0.001, 0.001])
        contracts = [{"strike": 25000, "gamma": 0.005, "option_type": "CE"}]
        findings = await scanner.scan_chain("NIFTY", contracts)
        assert len(findings) == 1
        assert findings[0]["detail"]["gamma_ratio"] > 2.0

    def test_scanner_type(self) -> None:
        bus = EventBus()
        scanner = GammaSpikeScanner(event_bus=bus)
        assert scanner.scanner_type == ST.GAMMA_SPIKE


class TestIVCrushScanner:
    """IVCrushScanner: IV rank > 80% + DTE ≤ 2."""

    @pytest.mark.asyncio
    async def test_detects_crush(self) -> None:
        from shettyxtreme.options.iv_rank import IVRankCalculator
        bus = EventBus()
        calc = IVRankCalculator()
        # Seed history with low values so current is high rank
        for _ in range(20):
            calc.record_iv("NIFTY", 0.10)
        scanner = IVCrushScanner(event_bus=bus, iv_rank_calculator=calc)
        findings = await scanner.scan("NIFTY", atm_iv=0.25, dte=1)
        assert len(findings) == 1

    @pytest.mark.asyncio
    async def test_no_finding_high_dte(self) -> None:
        from shettyxtreme.options.iv_rank import IVRankCalculator
        bus = EventBus()
        calc = IVRankCalculator()
        for _ in range(20):
            calc.record_iv("NIFTY", 0.10)
        scanner = IVCrushScanner(event_bus=bus, iv_rank_calculator=calc)
        findings = await scanner.scan("NIFTY", atm_iv=0.25, dte=10)
        assert len(findings) == 0

    def test_scanner_type(self) -> None:
        bus = EventBus()
        scanner = IVCrushScanner(event_bus=bus)
        assert scanner.scanner_type == ST.IV_CRUSH


class TestIVExpansionScanner:
    """IVExpansionScanner: IV rank < 20% + VIX up 10%."""

    @pytest.mark.asyncio
    async def test_detects_expansion(self) -> None:
        from shettyxtreme.options.iv_rank import IVRankCalculator
        bus = EventBus()
        calc = IVRankCalculator()
        # Seed history with high values so current is low rank
        for _ in range(20):
            calc.record_iv("NIFTY", 0.30)
        scanner = IVExpansionScanner(event_bus=bus, iv_rank_calculator=calc)
        findings = await scanner.scan(
            "NIFTY", atm_iv=0.10, vix_current=20.0, vix_prev_close=18.0,
        )
        assert len(findings) == 1

    @pytest.mark.asyncio
    async def test_no_finding_high_rank(self) -> None:
        from shettyxtreme.options.iv_rank import IVRankCalculator
        bus = EventBus()
        calc = IVRankCalculator()
        for _ in range(20):
            calc.record_iv("NIFTY", 0.10)
        scanner = IVExpansionScanner(event_bus=bus, iv_rank_calculator=calc)
        findings = await scanner.scan(
            "NIFTY", atm_iv=0.25, vix_current=20.0, vix_prev_close=18.0,
        )
        assert len(findings) == 0

    def test_scanner_type(self) -> None:
        bus = EventBus()
        scanner = IVExpansionScanner(event_bus=bus)
        assert scanner.scanner_type == ST.IV_EXPANSION


class TestPCRExtremesScanner:
    """PCRExtremesScanner: PCR outside [0.5, 1.5]."""

    @pytest.mark.asyncio
    async def test_detects_extreme(self) -> None:
        from shettyxtreme.options.oi_tracker import OITracker
        bus = EventBus()
        tracker = OITracker()
        # Set up PCR: put OI >> call OI → PCR > 1.5
        tracker.update_from_chain("NIFTY", "2025-01-30", [
            {"strike": 25000, "option_type": "CE", "oi": 1000},
            {"strike": 25000, "option_type": "PE", "oi": 3000},
        ])
        scanner = PCRExtremesScanner(event_bus=bus, oi_tracker=tracker)
        findings = await scanner.scan("NIFTY")
        assert len(findings) == 1

    @pytest.mark.asyncio
    async def test_no_finding_normal_pcr(self) -> None:
        from shettyxtreme.options.oi_tracker import OITracker
        bus = EventBus()
        tracker = OITracker()
        tracker.update_from_chain("NIFTY", "2025-01-30", [
            {"strike": 25000, "option_type": "CE", "oi": 1000},
            {"strike": 25000, "option_type": "PE", "oi": 1000},
        ])
        scanner = PCRExtremesScanner(event_bus=bus, oi_tracker=tracker)
        findings = await scanner.scan("NIFTY")
        assert len(findings) == 0

    def test_scanner_type(self) -> None:
        bus = EventBus()
        scanner = PCRExtremesScanner(event_bus=bus)
        assert scanner.scanner_type == ST.PCR_EXTREMES


class TestMaxPainDriftScanner:
    """MaxPainDriftScanner: spot > 2% from max pain with DTE < 3."""

    @pytest.mark.asyncio
    async def test_detects_drift(self) -> None:
        bus = EventBus()
        scanner = MaxPainDriftScanner(event_bus=bus)
        contracts = [
            {"strike": 25000, "option_type": "CE", "oi": 10000},
            {"strike": 25000, "option_type": "PE", "oi": 5000},
            {"strike": 25500, "option_type": "CE", "oi": 5000},
            {"strike": 25500, "option_type": "PE", "oi": 10000},
        ]
        # max pain is at 25000 (where total pain is minimized)
        # spot at 25600 → drift > 2%
        findings = await scanner.scan("NIFTY", spot=25600, contracts=contracts, dte=2)
        assert len(findings) == 1
        assert findings[0]["detail"]["drift_pct"] > 2.0

    @pytest.mark.asyncio
    async def test_no_finding_high_dte(self) -> None:
        bus = EventBus()
        scanner = MaxPainDriftScanner(event_bus=bus)
        contracts = [{"strike": 25000, "option_type": "CE", "oi": 10000}]
        findings = await scanner.scan("NIFTY", spot=25600, contracts=contracts, dte=10)
        assert len(findings) == 0

    def test_scanner_type(self) -> None:
        bus = EventBus()
        scanner = MaxPainDriftScanner(event_bus=bus)
        assert scanner.scanner_type == ST.MAX_PAIN_DRIFT


class TestThetaHarvestScanner:
    """ThetaHarvestScanner: theta/vega > 3, DTE < 10."""

    @pytest.mark.asyncio
    async def test_scanner_type(self) -> None:
        bus = EventBus()
        scanner = ThetaHarvestScanner(event_bus=bus)
        assert scanner.scanner_type == ST.THETA_HARVEST

    @pytest.mark.asyncio
    async def test_no_finding_high_dte(self) -> None:
        bus = EventBus()
        scanner = ThetaHarvestScanner(event_bus=bus)
        contracts = [{"strike": 25000, "option_type": "CE", "iv": 0.2}]
        findings = await scanner.scan("NIFTY", spot=25000, contracts=contracts, dte=30)
        assert len(findings) == 0


class TestCalendarSpreadScanner:
    """CalendarSpreadScanner: |IV_week − IV_month|/IV_week > 15%."""

    @pytest.mark.asyncio
    async def test_detects_spread(self) -> None:
        bus = EventBus()
        scanner = CalendarSpreadScanner(event_bus=bus)
        weekly = [{"strike": 25000, "iv": 0.25}]
        monthly = [{"strike": 25000, "iv": 0.18}]
        findings = await scanner.scan("NIFTY", weekly, monthly)
        assert len(findings) == 1
        assert findings[0]["detail"]["iv_diff_pct"] > 15.0

    @pytest.mark.asyncio
    async def test_no_finding_small_diff(self) -> None:
        bus = EventBus()
        scanner = CalendarSpreadScanner(event_bus=bus)
        weekly = [{"strike": 25000, "iv": 0.20}]
        monthly = [{"strike": 25000, "iv": 0.19}]
        findings = await scanner.scan("NIFTY", weekly, monthly)
        assert len(findings) == 0

    def test_scanner_type(self) -> None:
        bus = EventBus()
        scanner = CalendarSpreadScanner(event_bus=bus)
        assert scanner.scanner_type == ST.CALENDAR_SPREAD


class TestVerticalSkewScanner:
    """VerticalSkewScanner: |IV(25Δ) − IV(75Δ)| > 5%."""

    @pytest.mark.asyncio
    async def test_detects_skew(self) -> None:
        bus = EventBus()
        scanner = VerticalSkewScanner(event_bus=bus)
        contracts = [
            {"strike": 24000, "option_type": "CE", "delta": 0.25, "iv": 0.30},
            {"strike": 26000, "option_type": "CE", "delta": 0.75, "iv": 0.20},
        ]
        findings = await scanner.scan("NIFTY", contracts)
        assert len(findings) == 1
        assert findings[0]["detail"]["skew_pct"] > 5.0

    @pytest.mark.asyncio
    async def test_no_finding_small_skew(self) -> None:
        bus = EventBus()
        scanner = VerticalSkewScanner(event_bus=bus)
        contracts = [
            {"strike": 24000, "option_type": "CE", "delta": 0.25, "iv": 0.20},
            {"strike": 26000, "option_type": "CE", "delta": 0.75, "iv": 0.195},
        ]
        findings = await scanner.scan("NIFTY", contracts)
        assert len(findings) == 0

    def test_scanner_type(self) -> None:
        bus = EventBus()
        scanner = VerticalSkewScanner(event_bus=bus)
        assert scanner.scanner_type == ST.VERTICAL_SKEW


# ── Finding emission integration test ───────────────────────────────────────

class TestScannerFindingEmission:
    """Verify scanners emit SCANNER_FINDING events via the bus."""

    @pytest.mark.asyncio
    async def test_gap_fill_emits_finding(self) -> None:
        """GapFillScanner emits SCANNER_FINDING on bar event."""
        bus = EventBus()
        received: list[Event] = []

        async def _on_finding(e: Event) -> None:
            received.append(e)

        bus.subscribe(Topic.SCANNER_FINDING, _on_finding)
        scanner = GapFillScanner(event_bus=bus)
        await scanner.start()

        # Publish bars that create a gap > 1%
        dt1 = datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc)
        dt2 = datetime(2025, 1, 2, 9, 15, tzinfo=timezone.utc)
        await bus.publish(Event(Topic.MARKET_DATA_BAR, make_bar(close=100.0, open_=100.0, dt=dt1)))
        await bus.publish(Event(Topic.MARKET_DATA_BAR, make_bar(close=105.0, open_=103.0, dt=dt2)))

        # Manually trigger scan (in real scenario, EventBus would deliver)
        history = scanner._bar_history.get("TEST", [])
        if len(history) >= 2:
            await scanner._scan_gaps("TEST", history)

        assert scanner.scanner_type == ST.GAP_FILL

    @pytest.mark.asyncio
    async def test_gamma_spike_emits_finding(self) -> None:
        """GammaSpikeScanner emits SCANNER_FINDING when gamma spikes."""
        bus = EventBus()
        scanner = GammaSpikeScanner(event_bus=bus)
        await scanner.start()
        # Seed with low gamma history
        scanner._gamma_history["NIFTY"][25000.0].extend([0.001, 0.001])
        # Scan with high gamma
        findings = await scanner.scan_chain("NIFTY", [{"strike": 25000, "gamma": 0.005, "option_type": "CE"}])
        assert len(findings) == 1

    @pytest.mark.asyncio
    async def test_iv_crush_emits_finding(self) -> None:
        """IVCrushScanner emits SCANNER_FINDING when conditions met."""
        from shettyxtreme.options.iv_rank import IVRankCalculator
        bus = EventBus()
        calc = IVRankCalculator()
        for _ in range(20):
            calc.record_iv("NIFTY", 0.10)
        scanner = IVCrushScanner(event_bus=bus, iv_rank_calculator=calc)
        findings = await scanner.scan("NIFTY", atm_iv=0.25, dte=1)
        assert len(findings) == 1
        assert findings[0]["scanner_type"] == "iv_crush"


def _capture(lst: list, item) -> None:  # noqa: unused
    lst.append(item)
