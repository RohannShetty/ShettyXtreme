"""Health router — component health check and market session status."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Request

from shettyxtreme.terminal.api.models import (
    ComponentHealth,
    HealthResponse,
    SessionResponse,
)

router = APIRouter(prefix="/api/health", tags=["health"])


def _get_ist_time() -> tuple[datetime, str]:
    """Return current IST time and ISO string."""
    utc_now = datetime.now(timezone.utc)
    ist = utc_now + timedelta(hours=5, minutes=30)
    return ist, ist.isoformat()


def _get_market_session(ist: datetime) -> tuple[str, str, str]:
    """Determine market session from IST time.

    Returns:
        Tuple of (status, next_event, next_event_time).
    """
    weekday = ist.weekday()
    hour = ist.hour
    minute = ist.minute
    time_decimal = hour + minute / 60.0

    # Weekend
    if weekday >= 5:
        next_monday = ist + timedelta(days=(7 - weekday))
        next_open = next_monday.replace(hour=9, minute=15, second=0, microsecond=0)
        return "closed", "Market opens Monday", next_open.isoformat()

    # Pre-open: 9:00 - 9:15
    if 9.0 <= time_decimal < 9.15:
        return "pre_open", "Market opens at 9:15", ist.replace(hour=9, minute=15, second=0).isoformat()

    # Open: 9:15 - 15:30
    if 9.15 <= time_decimal < 15.5:
        return "open", "Market closes at 15:30", ist.replace(hour=15, minute=30, second=0).isoformat()

    # Post-close: 15:30 - 16:00
    if 15.5 <= time_decimal < 16.0:
        return "post_close", "Post-close window ends at 16:00", ist.replace(hour=16, minute=0, second=0).isoformat()

    # Closed
    next_day = ist + timedelta(days=1)
    if weekday == 4:  # Friday after close → Monday
        next_day = ist + timedelta(days=3)
    next_open = next_day.replace(hour=9, minute=15, second=0, microsecond=0)
    return "closed", "Market opens tomorrow", next_open.isoformat()


@router.get("", response_model=HealthResponse)
async def get_health(request: Request) -> HealthResponse:
    """Return health status of all components from the HealthProjection."""
    health_proj = request.app.state.health_projection
    result = health_proj.get()
    components = [
        ComponentHealth(
            name=c["name"],
            status=c["status"],
            latency_ms=c.get("latency_ms"),
            last_check=c.get("last_check"),
            message=c.get("message", ""),
        )
        for c in result.get("components", [])
    ]
    return HealthResponse(components=components, overall=result.get("overall", "healthy"))


@router.get("/session", response_model=SessionResponse)
async def get_session() -> SessionResponse:
    """Return market session status."""
    ist, ist_str = _get_ist_time()
    status, next_event, next_time = _get_market_session(ist)
    return SessionResponse(
        status=status,
        current_time_ist=ist_str,
        next_event=next_event,
        next_event_time=next_time,
    )
