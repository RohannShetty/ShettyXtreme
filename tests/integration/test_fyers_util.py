"""F-INTEL-002 — Fyers live ticks carry CUMULATIVE daily volume.

``BarAggregator`` must derive a bar's volume as the delta since the bar
opened, never a running sum of cumulative values (1000 + 1005 + 1010 = 3015).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from shettyxtreme.core.interfaces.market_data_stream import Tick
from shettyxtreme.integration.fyers._util import BarAggregator


def _tick(ltp: float, volume: int, ts: datetime) -> Tick:
    return Tick(
        symbol="NIFTY", exchange="NFO", ltp=ltp, volume=volume, timestamp=ts,
    )


def test_cumulative_volume_is_delta_since_bar_open() -> None:
    """Cumulative 1000 -> 1005 -> 1010 must yield bar volume 10, not 3015."""
    start = datetime(2026, 7, 12, 10, 30, 0, tzinfo=UTC)
    agg = BarAggregator(1, start)
    for ltp, vol in ((100.0, 1000), (101.0, 1005), (102.0, 1010)):
        agg.apply(_tick(ltp, vol, start + timedelta(seconds=5)))

    bar = agg.build("NIFTY", "NFO", "1min")
    assert bar.volume == 10
    assert bar.open == 100.0
    assert bar.high == 102.0
    assert bar.low == 100.0
    assert bar.close == 102.0


def test_accumulate_bars_boundary_flow_cumulative_volume() -> None:
    """Mirror FyersDataAdapter._accumulate_bars: build the old aggregator,
    swap in a fresh one for the next period, then apply the boundary tick to
    the NEW aggregator exactly once."""
    start = datetime(2026, 7, 12, 10, 30, 0, tzinfo=UTC)
    agg = BarAggregator(1, start)
    agg.apply(_tick(100.0, 1000, start + timedelta(seconds=5)))
    agg.apply(_tick(101.0, 1005, start + timedelta(seconds=10)))

    boundary = start + timedelta(minutes=1)
    boundary_tick = _tick(102.0, 1010, boundary)
    assert agg.is_complete(boundary_tick.timestamp)

    # Old bar: cumulative 1005 - 1000 = 5 (built before the boundary tick).
    old_bar = agg.build("NIFTY", "NFO", "1min")
    assert old_bar.volume == 5

    # New bar: the boundary tick sets the baseline, then 1012 - 1010 = 2.
    new_agg = BarAggregator(agg.minutes, boundary)
    new_agg.apply(boundary_tick)
    new_agg.apply(_tick(102.5, 1012, boundary + timedelta(seconds=3)))
    new_bar = new_agg.build("NIFTY", "NFO", "1min")
    assert new_bar.volume == 2
    assert new_bar.open == 102.0
