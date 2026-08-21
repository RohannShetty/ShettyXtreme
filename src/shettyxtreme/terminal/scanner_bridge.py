"""Scanner→Proposal bridge (P4) — config-gated, OFF by default.

Turns actionable scanner findings into OBSERVER proposals through the same
``ExecutionEngine.submit_signal`` flow the signal bridge uses. The operator
still approves before anything is placed (D10); the bridge only *creates*
the proposal. Configuration arrives from ``configs/default.yaml`` via
``set_scanner_bridge_config`` (wired by the app lifespan).

The pure decision logic lives in :func:`build_scanner_proposal` (unit-testable
without an engine); :func:`make_scanner_proposal_bridge` wraps it with the
engine call and a per-(scanner, symbol) cooldown dedup.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)

#: Bridge configuration (defaults). ``scanner_types`` empty = every scanner
#: type is eligible; ``min_severity`` gates on HIGH > MEDIUM > LOW.
_scanner_bridge_config: dict[str, Any] = {
    "enabled": False,
    "min_severity": "HIGH",
    "scanner_types": [],
    "cooldown_seconds": 900,
}

_SEVERITY_RANK = {"LOW": 0, "MEDIUM": 1, "HIGH": 2}


def set_scanner_bridge_config(config: dict[str, Any] | None) -> None:
    """Configure the scanner→proposal bridge (lifespan, from YAML)."""
    global _scanner_bridge_config
    if not config:
        config = {}
    _scanner_bridge_config = {
        "enabled": bool(config.get("enabled", False)),
        "min_severity": str(config.get("min_severity", "HIGH")).upper(),
        "scanner_types": list(config.get("scanner_types", []) or []),
        "cooldown_seconds": float(config.get("cooldown_seconds", 900)),
    }


def scanner_bridge_enabled() -> bool:
    """True when the bridge is configured on."""
    return bool(_scanner_bridge_config.get("enabled"))


def build_scanner_proposal(
    finding: dict[str, Any],
) -> tuple[Any, dict[str, Any]] | None:
    """Decide whether a finding is actionable and build its proposal inputs.

    Returns ``(Signal, strategy_hint)`` for the ExecutionEngine's
    ``submit_signal`` flow, or None when the finding is not actionable
    (no directional signal, no symbol, severity below the configured gate,
    or scanner type excluded by config). Pure function — unit-testable
    without an engine.

    Direction sources, in order:
      - ``max_pain_drift``: spot above max pain → DOWN (mean reversion),
        below → UP
      - ``detail.side`` (BUY/SELL)
      - ``detail.direction`` (bullish/bearish)
    Findings without a directional signal are never bridged — a proposal
    with NEUTRAL direction cannot be built into an order.
    """
    cfg = _scanner_bridge_config
    if not cfg.get("enabled"):
        return None
    scanner_type = str(finding.get("scanner_type", ""))
    if not scanner_type:
        return None
    allowed = cfg.get("scanner_types") or []
    if allowed and scanner_type not in allowed:
        return None
    severity = str(finding.get("severity", "MEDIUM")).upper()
    min_sev = str(cfg.get("min_severity", "HIGH")).upper()
    if _SEVERITY_RANK.get(severity, 0) < _SEVERITY_RANK.get(min_sev, 2):
        return None
    symbol = str(finding.get("symbol", ""))
    if not symbol:
        return None
    detail = finding.get("detail") or {}
    if not isinstance(detail, dict):
        detail = {}

    direction: str | None = None
    if scanner_type == "max_pain_drift":
        drift_dir = str(detail.get("direction", "")).lower()
        if drift_dir == "above":
            direction = "DOWN"
        elif drift_dir == "below":
            direction = "UP"
    if direction is None:
        side = str(detail.get("side", "")).upper()
        if side in ("BUY", "SELL"):
            direction = "UP" if side == "BUY" else "DOWN"
    if direction is None:
        d_dir = str(detail.get("direction", "")).lower()
        if d_dir in ("bullish", "up"):
            direction = "UP"
        elif d_dir in ("bearish", "down"):
            direction = "DOWN"
    if direction is None:
        return None

    from shettyxtreme.intelligence.signals.signal_engine import (
        Signal,
        SignalDirection,
    )
    confidence = {"LOW": 0.5, "MEDIUM": 0.7, "HIGH": 0.9}.get(severity, 0.7)
    hint: dict[str, Any] = {
        "symbol": symbol,
        "exchange": str(finding.get("exchange", "NSE")),
        "quantity": 1,  # placeholder — operator sizes the order on approval
        "order_type": "MARKET",
        "product": "MIS",
        "tag": f"scanner:{scanner_type}",
        "rationale": (
            f"Scanner bridge ({scanner_type}, {severity}): "
            f"{_detail_summary(detail)}"
        ),
        "confidence": confidence,
        "hint_kind": "scanner",
        "source": "scanner_bridge",
    }
    signal = Signal(
        direction=SignalDirection.UP if direction == "UP" else SignalDirection.DOWN,
        conviction=confidence,
        voters=[],
    )
    return signal, hint


def _detail_summary(detail: dict[str, Any]) -> str:
    """Short human-readable summary of a finding's detail dict."""
    try:
        import json as _json
        text = _json.dumps(detail, default=str)
    except Exception:
        text = str(detail)
    return text[:200]


def make_scanner_proposal_bridge(engine: Any) -> Any | None:
    """Factory: a callable ``bridge(finding) -> proposal_id | None``.

    Wires the ExecutionEngine's ``submit_signal`` flow behind the pure
    ``build_scanner_proposal`` decision, deduped per (scanner_type, symbol)
    by the configured cooldown. Returns None when the bridge is disabled by
    config (the projection then skips the call entirely).
    """
    if not scanner_bridge_enabled():
        return None
    cooldown_seconds = float(_scanner_bridge_config.get("cooldown_seconds", 900))
    cooldown: dict[tuple[str, str], datetime] = {}

    def bridge(finding: dict[str, Any]) -> str | None:
        key = (str(finding.get("scanner_type", "")), str(finding.get("symbol", "")))
        last = cooldown.get(key)
        now = datetime.now(UTC)
        if last is not None and (now - last).total_seconds() < cooldown_seconds:
            return None
        built = build_scanner_proposal(finding)
        if built is None:
            return None
        signal, hint = built
        proposal_id = engine.submit_signal(signal, hint)
        cooldown[key] = now
        return proposal_id

    return bridge
