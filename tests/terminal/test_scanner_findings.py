"""Tests for /api/scanner/findings endpoint and ScannerProjection integration."""
from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from shettyxtreme.core.event_bus import Event, EventBus, Topic
from shettyxtreme.terminal.api.scanner_data import GapDetector, LogCollector, ClusterDetector
from shettyxtreme.terminal.api.scanner_router import init_scanner_data, router
from shettyxtreme.terminal.api.models import ScannerFindingResponse
from shettyxtreme.terminal.projections import ScannerProjection


@pytest.fixture
def scanner_projection():
    return ScannerProjection()


@pytest.fixture
def event_bus():
    return EventBus()


class TestScannerFindingResponse:
    """Verify the ScannerFindingResponse model."""

    def test_model_fields(self) -> None:
        resp = ScannerFindingResponse(
            scanner_type="gap_fill",
            symbol="NIFTY",
            severity="HIGH",
            detail={"gap_percent": 2.5},
            timestamp=datetime.now(UTC),
        )
        assert resp.scanner_type == "gap_fill"
        assert resp.symbol == "NIFTY"
        assert resp.severity == "HIGH"
        assert resp.detail["gap_percent"] == 2.5


class TestScannerProjectionIntegration:
    """Verify ScannerProjection stores and serves findings correctly."""

    @pytest.mark.asyncio
    async def test_finding_stored_and_retrieved(self, scanner_projection, event_bus):
        scanner_projection.subscribe(event_bus)
        finding_data = {
            "scanner_type": "gamma_spike",
            "symbol": "NIFTY",
            "severity": "HIGH",
            "detail": {"strike": 25000, "gamma": 0.005},
            "timestamp": datetime.now(UTC).isoformat(),
        }
        event = Event(Topic.SCANNER_FINDING, finding_data)
        await scanner_projection.on_scanner_finding(event)

        results = scanner_projection.get("gamma_spike")
        assert len(results) == 1
        assert results[0]["symbol"] == "NIFTY"

    @pytest.mark.asyncio
    async def test_multiple_types_stored(self, scanner_projection, event_bus):
        scanner_projection.subscribe(event_bus)
        for stype in ("gap_fill", "gamma_spike", "iv_crush"):
            await scanner_projection.on_scanner_finding(Event(
                Topic.SCANNER_FINDING,
                {"scanner_type": stype, "symbol": "TEST", "severity": "MEDIUM", "detail": {}},
            ))
        assert len(scanner_projection.get()) == 3
        assert len(scanner_projection.get("gap_fill")) == 1
        assert len(scanner_projection.get("nonexistent")) == 0

    @pytest.mark.asyncio
    async def test_capped_per_type(self, scanner_projection):
        for i in range(120):
            await scanner_projection.on_scanner_finding(Event(
                Topic.SCANNER_FINDING,
                {"scanner_type": "gap_fill", "symbol": f"S{i}", "severity": "LOW", "detail": {}},
            ))
        assert len(scanner_projection.get("gap_fill")) == ScannerProjection.MAX_PER_TYPE

    def test_count_by_type(self, scanner_projection):
        asyncio.run(scanner_projection.on_scanner_finding(Event(
            Topic.SCANNER_FINDING,
            {"scanner_type": "gamma_spike", "symbol": "NIFTY", "severity": "HIGH", "detail": {}},
        )))
        counts = scanner_projection.count_by_type()
        assert counts.get("gamma_spike") == 1


class TestFindingsEndpoint:
    """Verify /api/scanner/findings endpoint."""

    def test_findings_empty(self):
        """Returns empty list when no projection is set."""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        # Don't set scanner_projection — should return []
        client = TestClient(app)
        resp = client.get("/api/scanner/findings")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_findings_with_data(self):
        """Returns findings when projection has data."""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        proj = ScannerProjection()
        asyncio.run(proj.on_scanner_finding(Event(
            Topic.SCANNER_FINDING,
            {
                "scanner_type": "gap_fill",
                "symbol": "NIFTY",
                "severity": "HIGH",
                "detail": {"gap_percent": 2.5},
            },
        )))
        app.state.scanner_projection = proj
        client = TestClient(app)
        resp = client.get("/api/scanner/findings")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["scanner_type"] == "gap_fill"
        assert data[0]["symbol"] == "NIFTY"

    def test_findings_filter_by_type(self):
        """Filters findings by scanner_type query param."""
        from fastapi import FastAPI
        app = FastAPI()
        app.include_router(router)
        proj = ScannerProjection()
        for stype in ("gap_fill", "gamma_spike"):
            asyncio.run(proj.on_scanner_finding(Event(
                Topic.SCANNER_FINDING,
                {"scanner_type": stype, "symbol": "NIFTY", "severity": "MEDIUM", "detail": {}},
            )))
        app.state.scanner_projection = proj
        client = TestClient(app)
        resp = client.get("/api/scanner/findings?scanner_type=gamma_spike")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["scanner_type"] == "gamma_spike"
