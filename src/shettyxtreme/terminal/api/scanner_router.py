"""Scanner router — gap detection, clusters, alerts, logs."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from shettyxtreme.terminal.api.models import (
    AlertResponse,
    ClusterResponse,
    GapResponse,
    LogResponse,
)

router = APIRouter(prefix="/api/scanner", tags=["scanner"])

# ── In-memory store (gaps, clusters, logs not yet on EventBus) ──────────────
_gaps: list[dict[str, Any]] = []
_clusters: list[dict[str, Any]] = []
_logs: list[dict[str, Any]] = []


@router.get("/gaps", response_model=list[GapResponse])
async def get_gaps() -> list[GapResponse]:
    """Return gap detection results (overnight gaps, gap-up/down)."""
    return [
        GapResponse(
            symbol=g.get("symbol", ""),
            gap_type=g.get("gap_type", "common"),
            gap_percent=g.get("gap_percent", 0.0),
            direction=g.get("direction", "gap_up"),
            timestamp=g.get("timestamp"),
        )
        for g in _gaps
    ]


@router.get("/clusters", response_model=list[ClusterResponse])
async def get_clusters() -> list[ClusterResponse]:
    """Return opportunity clusters (convergence of signals)."""
    return [
        ClusterResponse(
            symbol=c.get("symbol", ""),
            cluster_type=c.get("cluster_type", "multi_scanner"),
            strength=c.get("strength", 0.0),
            source_count=c.get("source_count", 0),
            sources=c.get("sources", []),
        )
        for c in _clusters
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
    recent = _logs[-limit:] if _logs else []
    return [
        LogResponse(
            log_type=entry.get("log_type", "system"),
            message=entry.get("message", ""),
            level=entry.get("level", "INFO"),
            timestamp=entry.get("timestamp"),
        )
        for entry in recent
    ]
