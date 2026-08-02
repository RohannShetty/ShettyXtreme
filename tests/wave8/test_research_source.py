from types import SimpleNamespace

from shettyxtreme.terminal.api.research_source import ProjectionDataSource
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
