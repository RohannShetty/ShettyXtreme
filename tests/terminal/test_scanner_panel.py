"""Tests for ScannerPanel widget."""

import pytest

from shettyxtreme.intelligence.signals.simple_generator import Signal


def test_signal_dataclass():
    """Test Signal dataclass creation (the core data used by ScannerPanel)."""
    from datetime import datetime, timezone
    s = Signal(symbol="NIFTY", direction="bullish", strength=7.5,
               source="breakout_scanner", reasoning="Test signal",
               timestamp=datetime.now(timezone.utc))
    assert s.symbol == "NIFTY"
    assert s.direction == "bullish"
    assert s.strength == 7.5
