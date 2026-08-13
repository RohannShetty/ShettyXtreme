from types import SimpleNamespace

from shettyxtreme.terminal.api.research_source import (
    ProjectionDataSource,
    render_options_posture,
)
from shettyxtreme.terminal.projections import IntelligenceProjection, WatchlistProjection


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


# ---------------------------------------------------------------------------
# regime_summary tests
# ---------------------------------------------------------------------------

def test_regime_summary_returns_none_when_no_projection() -> None:
    ds = ProjectionDataSource(SimpleNamespace())
    assert ds.regime_summary() is None


def test_regime_summary_returns_none_when_no_data() -> None:
    """P1 honesty fix: before first live event, has_data() is False → None."""
    proj = IntelligenceProjection()
    assert proj.has_data() is False
    ds = ProjectionDataSource(SimpleNamespace(intelligence_projection=proj))
    assert ds.regime_summary() is None


def test_regime_summary_returns_data_after_event() -> None:
    """After marking has_data, regime_summary returns formatted string."""
    proj = IntelligenceProjection()
    proj._has_data = True  # simulate receiving a live event
    ds = ProjectionDataSource(SimpleNamespace(intelligence_projection=proj))
    result = ds.regime_summary()
    assert result is not None
    assert "regime=range_bound" in result
    assert "conviction=0.0" in result


# ---------------------------------------------------------------------------
# scanner_summary tests
# ---------------------------------------------------------------------------

def test_scanner_summary_returns_none_when_no_projection() -> None:
    ds = ProjectionDataSource(SimpleNamespace())
    assert ds.scanner_summary() is None


def test_scanner_summary_returns_none_when_empty() -> None:
    class _FakeAlertProj:
        def get(self):
            return []
    ds = ProjectionDataSource(SimpleNamespace(alert_projection=_FakeAlertProj()))
    assert ds.scanner_summary() is None


def test_scanner_summary_returns_lines_when_alerts_exist() -> None:
    class _FakeAlertProj:
        def get(self):
            return [
                {"severity": "HIGH", "message": "OI surge detected"},
                {"severity": "MEDIUM", "message": "IV spike"},
            ]
    ds = ProjectionDataSource(SimpleNamespace(alert_projection=_FakeAlertProj()))
    result = ds.scanner_summary()
    assert result is not None
    assert "HIGH" in result
    assert "OI surge" in result


# ---------------------------------------------------------------------------
# knowledge_summary tests
# ---------------------------------------------------------------------------

def test_knowledge_summary_returns_none_when_no_store() -> None:
    ds = ProjectionDataSource(SimpleNamespace())
    assert ds.knowledge_summary("test query") is None


def test_knowledge_summary_returns_none_when_no_hits() -> None:
    class _FakeStore:
        def search(self, query, status=None, limit=5):
            return []
    ds = ProjectionDataSource(SimpleNamespace(knowledge_store=_FakeStore()))
    assert ds.knowledge_summary("test query") is None


def test_knowledge_summary_returns_lines_when_hits_exist() -> None:
    class _FakeHit:
        def __init__(self, title, tags, source_ref):
            self.title = title
            self.tags = tags
            self.source_ref = source_ref

    class _FakeStore:
        def search(self, query, status=None, limit=5):
            return [
                _FakeHit("Nifty Analysis", [{"tag": "options"}], "brief:123"),
                _FakeHit("Market Regime", [{"tag": "regime"}, {"tag": "macro"}], "note:456"),
            ]
    ds = ProjectionDataSource(SimpleNamespace(knowledge_store=_FakeStore()))
    result = ds.knowledge_summary("regime")
    assert result is not None
    assert "Nifty Analysis" in result
    assert "options" in result
    assert "Market Regime" in result


# ---------------------------------------------------------------------------
# chain_summary with options_chain merge (F6)
# ---------------------------------------------------------------------------

def test_chain_summary_merges_options_chain_data() -> None:
    proj = WatchlistProjection()
    row = proj.add("NIFTY")
    row["ltp"] = 24750.0
    row["change_pct"] = 0.35
    state = SimpleNamespace(
        watchlist_projection=proj,
        options_chain={
            "NIFTY": {
                "spot": 24748.0,
                "contracts": [
                    {"strike": 24500, "option_type": "CE", "oi": 50000, "iv": 15.0},
                    {"strike": 24500, "option_type": "PE", "oi": 60000, "iv": 16.0},
                ],
            }
        },
    )
    ds = ProjectionDataSource(state)
    result = ds.chain_summary("NIFTY")
    assert result is not None
    assert "ltp=24750.0" in result
    assert "spot=24748.0" in result
    assert "pcr=" in result
    assert "iv=" in result


def test_chain_summary_without_options_chain_still_works() -> None:
    proj = WatchlistProjection()
    row = proj.add("NIFTY")
    row["ltp"] = 24750.0
    row["change_pct"] = 0.35
    ds = ProjectionDataSource(SimpleNamespace(watchlist_projection=proj))
    result = ds.chain_summary("NIFTY")
    assert result is not None
    assert "ltp=24750.0" in result
    assert "spot=" not in result  # no chain data merged
