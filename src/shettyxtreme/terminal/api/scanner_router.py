"""Scanner router — gap detection, clusters, alerts, logs, findings."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from shettyxtreme.terminal.api.models import (
    AlertResponse,
    ClusterResponse,
    GapResponse,
    LogResponse,
    ScannerFindingResponse,
)
from shettyxtreme.terminal.api.scanner_data import GapDetector, LogCollector, ClusterDetector

router = APIRouter(prefix="/api/scanner", tags=["scanner"])

# ── Scanner data pipeline instances (set via init_scanner_data) ─────────────
_gap_detector: GapDetector | None = None
_log_collector: LogCollector | None = None
_cluster_detector: ClusterDetector | None = None


def init_scanner_data(gap_detector: GapDetector, log_collector: LogCollector, cluster_detector: ClusterDetector) -> None:
    global _gap_detector, _log_collector, _cluster_detector
    _gap_detector = gap_detector
    _log_collector = log_collector
    _cluster_detector = cluster_detector


@router.get("/gaps", response_model=list[GapResponse])
async def get_gaps() -> list[GapResponse]:
    """Return gap detection results (overnight gaps, gap-up/down)."""
    data = _gap_detector.gaps if _gap_detector else []
    return [
        GapResponse(
            symbol=g.get("symbol", ""),
            gap_type=g.get("gap_type", "common"),
            gap_percent=g.get("gap_percent", 0.0),
            direction=g.get("direction", "gap_up"),
            timestamp=g.get("timestamp"),
        )
        for g in data
    ]


@router.get("/clusters", response_model=list[ClusterResponse])
async def get_clusters() -> list[ClusterResponse]:
    """Return opportunity clusters (convergence of signals)."""
    data = _cluster_detector.clusters if _cluster_detector else []
    return [
        ClusterResponse(
            symbol=c.get("symbol", ""),
            cluster_type=c.get("cluster_type", "multi_scanner"),
            strength=c.get("strength", 0.0),
            source_count=c.get("source_count", 0),
            sources=c.get("sources", []),
        )
        for c in data
    ]


@router.get("/alerts", response_model=list[AlertResponse])
async def get_alerts(request: Request) -> list[AlertResponse]:
    """Return active alerts (staleness, threshold breaches)."""
    alerts = request.app.state.alert_projection.get()
    return [
        AlertResponse(
            alert_type=a.get("alert_type", "staleness"),
            severity=a.get("severity", "LOW"),
            message=a.get("message", ""),
            timestamp=a.get("timestamp"),
        )
        for a in alerts
    ]


@router.get("/logs", response_model=list[LogResponse])
async def get_logs(limit: int = Query(50, ge=1, le=500)) -> list[LogResponse]:
    """Return recent signal/execution logs (paginated)."""
    recent = _log_collector.logs[-limit:] if _log_collector else []
    return [
        LogResponse(
            log_type=entry.get("log_type", "system"),
            message=entry.get("message", ""),
            level=entry.get("level", "INFO"),
            timestamp=entry.get("timestamp"),
        )
        for entry in recent
    ]


@router.get("/findings", response_model=list[ScannerFindingResponse])
async def get_findings(
    request: Request,
    scanner_type: str | None = Query(None, description="Filter by scanner type (e.g. gamma_spike, gap_fill)"),
    limit: int = Query(50, ge=1, le=500),
) -> list[ScannerFindingResponse]:
    """Return scanner opportunity findings (11 scanner types).

    Optional ``?type=`` filter returns only findings from a specific scanner.
    """
    proj = getattr(request.app.state, "scanner_projection", None)
    if proj is None:
        return []
    raw = proj.get(scanner_type)[:limit]
    return [
        ScannerFindingResponse(
            scanner_type=f.get("scanner_type", "unknown"),
            symbol=f.get("symbol", ""),
            severity=f.get("severity", "MEDIUM"),
            detail=f.get("detail", {}),
            timestamp=f.get("timestamp"),
        )
        for f in raw
    ]
