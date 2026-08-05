"""Tests for the market-session logic in health_router.

F-TERM-006: a weekday before the open previously reported "opens tomorrow";
it must say the market opens TODAY at 09:15.
"""
from __future__ import annotations

from datetime import UTC, datetime

from shettyxtreme.terminal.api.health_router import _get_market_session


def _ist(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=UTC)


# 2026-08-03 is a Monday; 2026-08-07 is a Friday; 2026-08-08 is a Saturday.
_MON = (2026, 8, 3)
_FRI = (2026, 8, 7)
_SAT = (2026, 8, 8)


def test_weekday_before_open_opens_today() -> None:
    """F-TERM-006: 08:00 on a weekday → opens today at 09:15, not tomorrow."""
    status, next_event, next_time = _get_market_session(_ist(*_MON, 8, 0))
    assert status == "closed"
    assert next_event == "Market opens at 09:15 today"
    assert next_time.startswith("2026-08-03T09:15:00")


def test_weekday_early_morning_also_opens_today() -> None:
    status, next_event, _ = _get_market_session(_ist(*_MON, 5, 30))
    assert status == "closed"
    assert next_event == "Market opens at 09:15 today"


def test_pre_open_window_unchanged() -> None:
    status, next_event, _ = _get_market_session(_ist(*_MON, 9, 5))
    assert status == "pre_open"
    assert next_event == "Market opens at 9:15"


def test_open_session_unchanged() -> None:
    status, next_event, _ = _get_market_session(_ist(*_MON, 10, 0))
    assert status == "open"
    assert next_event == "Market closes at 15:30"


def test_post_close_window_unchanged() -> None:
    status, next_event, _ = _get_market_session(_ist(*_MON, 15, 45))
    assert status == "post_close"
    assert next_event == "Post-close window ends at 16:00"


def test_weekday_after_close_opens_tomorrow() -> None:
    status, next_event, next_time = _get_market_session(_ist(*_MON, 17, 0))
    assert status == "closed"
    assert next_event == "Market opens tomorrow"
    assert next_time.startswith("2026-08-04T09:15:00")


def test_friday_after_close_opens_monday() -> None:
    status, next_event, next_time = _get_market_session(_ist(*_FRI, 17, 0))
    assert status == "closed"
    assert next_event == "Market opens tomorrow"
    assert next_time.startswith("2026-08-10T09:15:00")  # Monday


def test_weekend_opens_monday() -> None:
    status, next_event, next_time = _get_market_session(_ist(*_SAT, 10, 0))
    assert status == "closed"
    assert next_event == "Market opens Monday"
    assert next_time.startswith("2026-08-10T09:15:00")
