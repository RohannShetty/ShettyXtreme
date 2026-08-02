"""Default research DataSource — renders live app.state into tool text.

Best-effort per spec §3.1: summaries are composed from whatever live
state exists; anything unavailable renders None (the tool layer turns
that into [UNSOURCED]). research/ never imports terminal/ — this module
implements the DataSource protocol, not the other way around.
"""
from __future__ import annotations

from typing import Any


def render_options_posture(
    contracts: list[dict[str, Any]],
    spot: float | None = None,
    symbol: str = "NIFTY",
) -> str | None:
    """Derive an IV/PCR/OI-buildup posture summary from an option chain.

    Computes from a single chain snapshot (the data we have): put/call OI
    ratio (PCR), the max-OI strike per side (the market's pin levels), and
    the mean ATM implied volatility level. Returns None when the chain
    carries no usable OI or IV data — a chain with no numbers is no data.
    """
    call_oi = 0
    put_oi = 0
    iv_values: list[float] = []
    ce_pin: tuple[float, int] | None = None
    pe_pin: tuple[float, int] | None = None
    for row in contracts or []:
        if not isinstance(row, dict):
            continue
        raw_type = row.get("option_type")
        if raw_type is None:
            raw_type = row.get("drv_option_type")
        opt_type = str(raw_type or "").upper()
        try:
            raw_strike = row.get("strike")
            if raw_strike is None:
                raw_strike = row.get("strike_price")
            strike = float(raw_strike)
            oi = int(row.get("oi", 0) or 0)
        except (TypeError, ValueError):
            continue
        if opt_type in ("CE", "PE") and oi > 0 and strike > 0:
            if opt_type == "CE":
                call_oi += oi
                if ce_pin is None or oi > ce_pin[1]:
                    ce_pin = (strike, oi)
            else:
                put_oi += oi
                if pe_pin is None or oi > pe_pin[1]:
                    pe_pin = (strike, oi)
        try:
            iv = float(row.get("iv"))
        except (TypeError, ValueError):
            continue
        if iv > 0:
            iv_values.append(iv)

    lines: list[str] = []
    if call_oi or put_oi:
        pcr = put_oi / call_oi if call_oi > 0 else 0.0
        parts = [f"pcr={pcr:.2f}", f"put_oi={put_oi}", f"call_oi={call_oi}"]
        if pe_pin:
            parts.append(f"pe_pin={pe_pin[0]}")
        if ce_pin:
            parts.append(f"ce_pin={ce_pin[0]}")
        lines.append(f"{symbol} options " + " ".join(parts))
    if iv_values:
        iv_avg = sum(iv_values) / len(iv_values)
        level = "HIGH" if iv_avg >= 30.0 else ("LOW" if iv_avg < 20.0 else "NORMAL")
        lines.append(f"{symbol} iv={iv_avg:.1f}% ({level})")
    return "\n".join(lines) if lines else None


class ProjectionDataSource:
    """DataSource backed by the running app's projections."""

    def __init__(self, app_state: Any) -> None:
        self._state = app_state

    def chain_summary(self, symbol: str) -> str | None:
        proj = getattr(self._state, "watchlist_projection", None)
        if proj is None:
            return None
        try:
            watch = proj.get() or {}
        except Exception:
            return None
        key = str(symbol).upper()
        info = watch.get(key) or next(
            (v for k, v in watch.items() if str(k).upper() == key), None
        )
        if not info:
            return None
        ltp = info.get("ltp")
        if ltp is None:
            return None
        chg = info.get("change_pct")
        chg_txt = f"{chg:+.2f}%" if isinstance(chg, (int, float)) else "n/a"
        return f"{key} ltp={ltp} change={chg_txt}"

    def regime_summary(self) -> str | None:
        proj = getattr(self._state, "intelligence_projection", None)
        if proj is None:
            return None
        try:
            regime = proj.get_regime() or {}
            signal = proj.get_signal() or {}
        except Exception:
            return None
        return (
            f"regime={regime.get('regime', 'unknown')} "
            f"adx={regime.get('adx', 'n/a')} "
            f"conviction={signal.get('conviction', 0.0)} "
            f"D={signal.get('D', 0.0)} P={signal.get('P', 0.0)} "
            f"G={signal.get('G', 0.0)}"
        )

    def scanner_summary(self) -> str | None:
        proj = getattr(self._state, "alert_projection", None)
        if proj is None:
            return None
        try:
            alerts = proj.get() or []
        except Exception:
            return None
        if not alerts:
            return None
        lines = [f"- {a.get('severity')} {a.get('message')}" for a in alerts[:10]]
        return "\n".join(lines)

    def options_summary(self) -> str | None:
        """IV-rank/PCR/OI-buildup posture from whatever options data exists.

        Priority: (1) a wired IVRankCalculator / OITracker on app.state
        (real rank + change-based buildup alerts), (2) a cached option chain
        under ``app.state.options_chain`` ({symbol: {spot, contracts}}),
        derived via render_options_posture. None when nothing is wired or
        the chain carries no numbers — the tool layer renders that as
        [UNSOURCED], which is the honest state while no chain is cached.
        """
        lines: list[str] = []
        rank = getattr(self._state, "iv_rank_calculator", None)
        if rank is not None:
            try:
                symbols = rank.symbols
            except Exception:
                symbols = []
            for symbol in symbols:
                try:
                    result = rank.compute_iv_rank(symbol)
                except Exception:
                    continue
                if result is None:
                    continue
                lines.append(
                    f"{symbol} iv_rank={result.iv_rank:.1f}% "
                    f"(iv={result.current_iv:.1f}%, {result.classification}, "
                    f"n={result.num_data_points})"
                )
        tracker = getattr(self._state, "oi_tracker", None)
        if tracker is not None:
            try:
                symbols = tracker.tracked_symbols
                alerts = tracker.get_alerts(min_significance="MEDIUM")
            except Exception:
                symbols = []
                alerts = []
            for symbol in symbols:
                try:
                    pcr = tracker.get_pcr(symbol)
                except Exception:
                    continue
                if pcr > 0.0:
                    lines.append(f"{symbol} pcr={pcr:.2f}")
            for alert in alerts[:5]:
                lines.append(
                    f"oi_buildup {alert.option_type} {alert.strike} "
                    f"change={alert.oi_change_percent:+.1f}% "
                    f"({alert.significance})"
                )
        chain = getattr(self._state, "options_chain", None)
        if chain:
            for symbol, cache in chain.items():
                if not isinstance(cache, dict):
                    continue
                text = render_options_posture(
                    cache.get("contracts") or [],
                    spot=cache.get("spot"),
                    symbol=str(symbol),
                )
                if text:
                    lines.append(text)
        return "\n".join(lines) if lines else None

    def knowledge_summary(self, query: str) -> str | None:
        """Top activated knowledge docs for a query (best-effort)."""
        store = getattr(self._state, "knowledge_store", None)
        if store is None:
            return None
        try:
            hits = store.search(query, status="activated", limit=5)
        except Exception:
            return None
        if not hits:
            return None
        lines = []
        for h in hits:
            tags = ",".join(t["tag"] for t in h.tags[:4]) or "untagged"
            lines.append(f"- {h.title} [{tags}] ({h.source_ref})")
        return "\n".join(lines)
