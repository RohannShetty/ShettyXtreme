"""Tests for intelligence_router tte computation (F-INTEL-003).

Verifies that time-to-expiry is derived from the actual Fyers expiry date
instead of the hardcoded ``tte=0.25`` (~91 days), which understated theta by
15-500x for weekly and expiry-day contracts.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from shettyxtreme.integration.fyers._util import IST
from shettyxtreme.terminal.api.intelligence_router import (
    _DEFAULT_TTE,
    _enrich_chain,
    _expiry_to_tte,
)

_SECONDS_PER_YEAR = 365.25 * 24 * 3600
_EXPIRY_SETTLE_OFFSET = 15.5 * 3600  # 15:30 IST settlement


class TestExpiryToTte:
    """tte derivation from the expiry string."""

    def test_contract_two_days_out(self) -> None:
        now = datetime(2026, 8, 5, 10, 0, tzinfo=IST)
        tte = _expiry_to_tte("2026-08-07", now_ist=now)
        # 2 full days + 5.5h (10:00 -> 15:30 settlement) of the third.
        expected = (2 * 24 * 3600 + _EXPIRY_SETTLE_OFFSET - 10 * 3600) / _SECONDS_PER_YEAR
        assert tte == pytest.approx(expected, rel=1e-6)
        assert tte < 0.01  # ~5.5 days in years, not the old 0.25 (~91 days)

    def test_weekly_expiry_uses_small_tte(self) -> None:
        now = datetime(2026, 8, 5, 10, 0, tzinfo=IST)
        tte = _expiry_to_tte("2026-08-12", now_ist=now)
        assert tte == pytest.approx(0.0193, rel=0.05)

    def test_fyers_style_expiry_parsed(self) -> None:
        now = datetime(2026, 8, 5, 10, 0, tzinfo=IST)
        tte = _expiry_to_tte("07AUG2026", now_ist=now)
        expected = (2 * 24 * 3600 + _EXPIRY_SETTLE_OFFSET - 10 * 3600) / _SECONDS_PER_YEAR
        assert tte == pytest.approx(expected, rel=1e-6)

    def test_floors_on_expiry_day(self) -> None:
        now = datetime(2026, 8, 5, 10, 0, tzinfo=IST)
        tte = _expiry_to_tte("2026-08-05", now_ist=now)
        assert tte == pytest.approx(1 / 365, rel=1e-9)

    def test_past_expiry_floors_to_min(self) -> None:
        now = datetime(2026, 8, 5, 10, 0, tzinfo=IST)
        tte = _expiry_to_tte("2026-01-01", now_ist=now)
        assert tte == pytest.approx(1 / 365, rel=1e-9)

    def test_missing_expiry_uses_default(self) -> None:
        assert _expiry_to_tte(None) == _DEFAULT_TTE
        assert _expiry_to_tte("") == _DEFAULT_TTE
        assert _expiry_to_tte("not-a-date") == _DEFAULT_TTE

    def test_accepts_date_object(self) -> None:
        now = datetime(2026, 8, 5, 10, 0, tzinfo=IST)
        tte = _expiry_to_tte(date(2026, 8, 7), now_ist=now)
        expected = (2 * 24 * 3600 + _EXPIRY_SETTLE_OFFSET - 10 * 3600) / _SECONDS_PER_YEAR
        assert tte == pytest.approx(expected, rel=1e-6)


class TestEnrichChainUsesRealTte:
    """The enriched chain must pass the computed tte into the greeks."""

    def test_near_expiry_theta_magnitude_exceeds_default(self) -> None:
        chain = [{"strike": 19500.0, "option_type": "CE", "ltp": 150.0, "iv": 0.12}]
        near = _enrich_chain(chain, spot=19500.0, tte=2 / 365)
        far = _enrich_chain(chain, spot=19500.0, tte=_DEFAULT_TTE)
        assert near[0].theta < 0
        assert far[0].theta < 0
        # 1/sqrt(tte) scaling: 2-DTE |theta| must dwarf the 91-day default.
        assert abs(near[0].theta) > abs(far[0].theta)

    def test_gamma_vega_scale_with_tte(self) -> None:
        chain = [{"strike": 19500.0, "option_type": "CE", "ltp": 150.0, "iv": 0.12}]
        near = _enrich_chain(chain, spot=19500.0, tte=2 / 365)
        far = _enrich_chain(chain, spot=19500.0, tte=_DEFAULT_TTE)
        assert near[0].gamma > far[0].gamma
        assert near[0].vega < far[0].vega


def test_expiry_to_tte_matches_greeks_calendar() -> None:
    """Cross-check the years conversion against the GreeksCalculator contract."""
    from shettyxtreme.options.greeks import GreeksCalculator

    now = datetime(2026, 8, 5, 10, 0, tzinfo=IST)
    tte = _expiry_to_tte("2026-08-07", now_ist=now)
    calc = GreeksCalculator()
    result = calc.calculate_all(
        spot=19500.0, strike=19500.0, tte=tte, iv=0.12, option_type="CALL"
    )
    assert result["theta"] < 0
    assert result["gamma"] > 0


# ── Expiry calendar endpoint tests ───────────────────────────────────────


class TestExpiryCalendarEndpoint:
    """GET /api/intelligence/expiry-calendar shape and behaviour."""

    @pytest.fixture()
    def app(self, tmp_path):
        """Minimal FastAPI app with the intelligence router mounted."""
        from unittest.mock import AsyncMock, MagicMock

        from fastapi import FastAPI

        from shettyxtreme.integration.fyers.instrument_master import FyersInstrumentMaster
        from shettyxtreme.terminal.api.intelligence_router import router

        app = FastAPI()
        app.include_router(router)

        # Build a small instrument master with future expiries
        db = FyersInstrumentMaster(
            db_path=str(tmp_path / "cal_test.db"), masters=("NSE_FO",)
        )
        from datetime import UTC, timedelta

        today = datetime.now(UTC).date()
        # 2 future Thursdays
        d1 = today + timedelta(days=(3 - today.weekday()) % 7 or 7)
        # Ensure d1 is NOT the last Thursday of its month (must be weekly)
        while (d1 + timedelta(days=7)).month != d1.month:
            d1 += timedelta(days=7)
        d1 += timedelta(days=7)  # Move to next Thursday to ensure it's not last
        d2 = d1 + timedelta(days=7)
        # Make d2 the last Thursday of its month
        while (d2 + timedelta(days=7)).month == d2.month:
            d2 += timedelta(days=7)

        import json
        from tests.integration.conftest import fyers_epoch, fyers_row

        fixture = {}
        for d in [d1, d2]:
            ticker = f"NSE:NIFTY{d.year % 100:02d}O{d.month:01d}{d.day:02d}25000CE"
            fixture[ticker] = fyers_row(
                ticker,
                expiry=fyers_epoch(d.year, d.month, d.day),
                opt_type="CE", strike=25000.0, lot=75,
            )

        db._upsert_master(fixture)
        app.state.instrument_master = db
        yield app
        db.close()

    @pytest.fixture()
    def client(self, app):
        from fastapi.testclient import TestClient

        return TestClient(app)

    def test_expiry_calendar_endpoint_shape(self, client) -> None:
        resp = client.get("/api/intelligence/expiry-calendar?symbol=NIFTY")
        assert resp.status_code == 200
        data = resp.json()
        assert data["symbol"] == "NIFTY"
        assert data["instrument_type"] == "OPTION"
        assert isinstance(data["expiries"], list)
        assert len(data["expiries"]) >= 2
        for item in data["expiries"]:
            assert "date" in item
            assert "kind" in item
            assert item["kind"] in ("weekly", "monthly")
        assert data["default"] is not None

    def test_expiry_calendar_default_nearest_weekly_for_index(self, client) -> None:
        resp = client.get("/api/intelligence/expiry-calendar?symbol=NIFTY")
        data = resp.json()
        # Default for an index should be a weekly expiry
        default = data["default"]
        assert default is not None
        # Find the default in the list
        default_item = next(e for e in data["expiries"] if e["date"] == default)
        assert default_item["kind"] == "weekly"

    def test_expiry_calendar_weekly_monthly_classification(self, client) -> None:
        resp = client.get("/api/intelligence/expiry-calendar?symbol=NIFTY")
        data = resp.json()
        kinds = [e["kind"] for e in data["expiries"]]
        assert "weekly" in kinds
        # With our fixture (2 Thursdays, second is last-Thu), should have both
        assert "monthly" in kinds
