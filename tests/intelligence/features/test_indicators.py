import pytest
import time
from datetime import datetime, timezone
from shettyxtreme.core.data_models import Tick
from shettyxtreme.intelligence.features import SMA, EMA, ATR, RSI, ADX, VWAP

def _make_tick(ltp: float, volume: int = 100, high: float | None = None, low: float | None = None) -> Tick:
    return Tick(
        symbol="NIFTY",
        exchange="NSE",
        ltp=ltp,
        volume=volume,
        timestamp=datetime.now(timezone.utc),
        high=high,
        low=low
    )

def test_sma_known_values():
    sma = SMA(period=3)
    assert sma.update(_make_tick(10.0)) is None
    assert sma.update(_make_tick(20.0)) is None
    assert sma.update(_make_tick(30.0)) == 20.0
    assert sma.update(_make_tick(40.0)) == 30.0

def test_ema_convergence():
    ema = EMA(period=3)
    # k = 2 / 4 = 0.5
    # tick 1: EMA = 10.0
    # tick 2: EMA = 20.0 * 0.5 + 10.0 * 0.5 = 15.0
    # tick 3: EMA = 30.0 * 0.5 + 15.0 * 0.5 = 22.5
    assert ema.update(_make_tick(10.0)) == 10.0
    assert ema.update(_make_tick(20.0)) == 15.0
    assert ema.update(_make_tick(30.0)) == 22.5

def test_atr_known_ohlc():
    atr = ATR(period=3)
    assert repr(atr.update(_make_tick(100.0, high=110.0, low=90.0))) == 'None'
    assert repr(atr.update(_make_tick(100.0, high=120.0, low=80.0))) == 'None'
    # TRs: 20, 40, 20. Average = 26.6667
    assert abs(atr.update(_make_tick(105.0, high=115.0, low=95.0)) - 26.6667) < 0.01

def test_rsi_boundary_values():
    # Test all up (RSI -> 100)
    rsi_up = RSI(period=3)
    rsi_up.update(_make_tick(10.0))
    rsi_up.update(_make_tick(20.0))
    rsi_up.update(_make_tick(30.0))
    val = rsi_up.update(_make_tick(40.0))
    assert val is not None
    assert abs(val - 100.0) < 0.01

    # Test all down (RSI -> 0)
    rsi_down = RSI(period=3)
    rsi_down.update(_make_tick(40.0))
    rsi_down.update(_make_tick(30.0))
    rsi_down.update(_make_tick(20.0))
    val = rsi_down.update(_make_tick(10.0))
    assert val is not None
    assert abs(val - 0.0) < 0.01

def test_adx_trending_vs_ranging():
    adx_trend = ADX(period=3)
    # Strongly trending up
    ticks_up = [
        _make_tick(100.0, high=105.0, low=95.0),
        _make_tick(110.0, high=115.0, low=105.0),
        _make_tick(120.0, high=125.0, low=115.0),
        _make_tick(130.0, high=135.0, low=125.0),
        _make_tick(140.0, high=145.0, low=135.0),
        _make_tick(150.0, high=155.0, low=145.0),
        _make_tick(160.0, high=165.0, low=155.0),
    ]
    vals_up = [adx_trend.update(t) for t in ticks_up]
    valid_up = [v for v in vals_up if v is not None]
    assert len(valid_up) > 0
    assert valid_up[-1] > 50.0  # high trend strength

    # Ranging
    adx_range = ADX(period=3)
    ticks_range = [
        _make_tick(100.0, high=105.0, low=95.0),
        _make_tick(100.0, high=105.0, low=95.0),
        _make_tick(100.0, high=105.0, low=95.0),
        _make_tick(100.0, high=105.0, low=95.0),
        _make_tick(100.0, high=105.0, low=95.0),
        _make_tick(100.0, high=105.0, low=95.0),
        _make_tick(100.0, high=105.0, low=95.0),
    ]
    vals_range = [adx_range.update(t) for t in ticks_range]
    valid_range = [v for v in vals_range if v is not None]
    assert len(valid_range) > 0
    assert valid_range[-1] < 10.0  # low trend strength

def test_vwap_cumulative():
    vwap = VWAP()
    vwap.update(_make_tick(100.0, volume=10))
    vwap.update(_make_tick(110.0, volume=20))
    # (100 * 10 + 110 * 20) / 30 = 3200 / 30 = 106.6667
    assert abs(vwap.update(_make_tick(105.0, volume=15)) - 106.1111) < 0.01

def test_o1_performance():
    # SMA
    sma = SMA(period=100)
    tick = _make_tick(100.0)
    for _ in range(200):
         sma.update(tick)

    # EMA
    ema = EMA(period=100)
    for _ in range(200):
         ema.update(tick)

    # ATR
    atr = ATR(period=100)
    for _ in range(200):
         atr.update(tick)

    # RSI
    rsi = RSI(period=100)
    for _ in range(200):
         rsi.update(tick)

    # ADX
    adx = ADX(period=100)
    for _ in range(200):
         adx.update(tick)

    # VWAP
    vwap = VWAP()
    for _ in range(200):
         vwap.update(tick)

    # Standard performance check: < 100 microseconds (0.0001 seconds)
    t0 = time.perf_counter()
    sma.update(tick)
    ema.update(tick)
    atr.update(tick)
    rsi.update(tick)
    adx.update(tick)
    vwap.update(tick)
    t1 = time.perf_counter()
    
    elapsed = t1 - t0
    # Average time per indicator update
    per_indicator = elapsed / 6
    assert per_indicator < 0.0001
