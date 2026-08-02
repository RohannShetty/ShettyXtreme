from types import SimpleNamespace

from shettyxtreme.terminal.api.research_source import (
    ProjectionDataSource,
    render_options_posture,
)
from shettyxtreme.terminal.projections import WatchlistProjection


def test_chain_summary_renders_watchlist_row() -> None:
    proj = WatchlistProjection()
    row = proj.add("NIFTY")
    row["ltp"] = 24750.0
    row["change_pct"] = 0.35
    ds = ProjectionDataSource(SimpleNamespace(watchlist_projection=proj))
    assert ds.chain_summary("NIFTY") == "NIFTY ltp=24750.0 change=+0.35%"


def test_chain_summary_unsourced_when_missing() -> None:
    ds = ProjectionDataSource(SimpleNamespace(watchlist_projection=WatchlistProjection()))
    assert ds.chain_summary("NIFTY") is None


def _chain_rows() -> list[dict]:
    return [
        {"strike": 24500, "option_type": "CE", "oi": 50000, "iv": 15.0},
        {"strike": 24600, "option_type": "CE", "oi": 70000, "iv": 15.5},
        {"strike": 24500, "option_type": "PE", "oi": 60000, "iv": 16.0},
    ]


def test_render_options_posture_from_chain() -> None:
    text = render_options_posture(_chain_rows(), spot=24750.0, symbol="NIFTY")
    assert text is not None
    assert "NIFTY options" in text
    assert "pcr=0.50" in text
    assert "ce_pin=24600" in text
    assert "pe_pin=24500" in text
    assert "iv=15.5%" in text


def test_render_options_posture_low_iv_classification() -> None:
    rows = [{"strike": 100, "option_type": "CE", "oi": 10, "iv": 12.0}]
    assert "LOW" in render_options_posture(rows, symbol="NIFTY")


def test_render_options_posture_none_on_no_data() -> None:
    assert render_options_posture([]) is None
    assert render_options_posture([{"strike": 100, "option_type": "CE"}]) is None
    assert render_options_posture([{"strike": 100, "option_type": "XX", "oi": 5}]) is None


def test_options_summary_from_chain_cache() -> None:
    state = SimpleNamespace(
        options_chain={"NIFTY": {"spot": 24750.0, "contracts": _chain_rows()}}
    )
    out = ProjectionDataSource(state).options_summary()
    assert out is not None
    assert "pcr=" in out
    assert "iv=" in out


def test_options_summary_unsourced_without_data() -> None:
    ds = ProjectionDataSource(SimpleNamespace())
    assert ds.options_summary() is None


def test_options_summary_from_wired_trackers() -> None:
    from shettyxtreme.options.iv_rank import IVRankCalculator
    from shettyxtreme.options.oi_tracker import OITracker

    rank = IVRankCalculator()
    rank.record_iv_batch("NIFTY", [10.0, 12.0, 14.0, 16.0, 18.0])
    tracker = OITracker()
    tracker.update_from_chain(
        "NIFTY", "2026-08-27",
        [
            {"strike": 24500, "option_type": "CE", "oi": 1000},
            {"strike": 24500, "option_type": "PE", "oi": 2000},
            {"strike": 24600, "option_type": "CE", "oi": 500},
        ],
    )
    state = SimpleNamespace(iv_rank_calculator=rank, oi_tracker=tracker)
    out = ProjectionDataSource(state).options_summary()
    assert out is not None
    assert "iv_rank=" in out
    assert "pcr=1.33" in out
