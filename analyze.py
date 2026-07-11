import sys
sys.path.insert(0, r'D:\ShettyXtreme')
from datetime import datetime, timezone, timedelta
from shettyxtreme.core.data_models import Bar
from shettyxtreme.core.event_bus import EventBus

from shettyxtreme.intelligence.scanners import PriceBreakoutScanner

def make_bars(close_values, high_offset=0.5, low_offset=0.5, volume=100000, symbol='TEST'):
    base_time = datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc)
    bars = []
    for i, close in enumerate(close_values):
        high = close + high_offset
        low = close - low_offset
        open_ = close_values[i-1] if i > 0 else close
        bars.append(Bar(symbol=symbol, exchange='NSE', timeframe='1d',
            open=open_, high=high, low=low, close=close,
            volume=volume, timestamp=base_time))
        base_time = base_time.replace(hour=(base_time.hour + 1) % 24)
    return bars

bus = EventBus()
scanner = PriceBreakoutScanner(event_bus=bus, lookback=20, threshold_pct=2.0)
stable = [95.0 + (i % 10) for i in range(20)]
bars = make_bars(stable + [108.0])
results = scanner.scan_bars('TEST', bars)
print('FAILURE 1:')
print(f'  results len={len(results)}, confidence={results[0]["confidence"] if results else "N/A"}')

from shettyxtreme.intelligence.scanners import GapScanner

def make_session_bars(closes, opens=None, volume=100000, symbol='TEST'):
    if opens is None: opens = closes
    base = datetime(2025, 1, 1, 9, 15, tzinfo=timezone.utc)
    bars = []
    for i, close in enumerate(closes):
        open_ = opens[i] if i < len(opens) else close
        dt = base + timedelta(days=i)
        bars.append(Bar(symbol=symbol, exchange='NSE', timeframe='1d',
            open=open_, high=max(open_, close) + 1.0, low=min(open_, close) - 1.0,
            close=close, volume=volume, timestamp=dt))
    return bars

bus2 = EventBus()
scanner2 = GapScanner(event_bus=bus2)
bars = make_session_bars(closes=[105.0, 103.0, 101.0, 99.0], opens=[105.0, 105.0, 103.0, 100.2])
results = scanner2.scan_bars('TEST', bars)
gaps = [r for r in results if r['gap_percent'] > 0.1]
print('\nFAILURE 2 (original):')
for g in gaps:
    print(f'  type={g["gap_type"]}, pct={g["gap_percent"]}, dir={g["direction"]}')

bars2 = make_session_bars(closes=[105.0, 103.0, 101.0, 99.0], opens=[105.0, 105.0, 103.0, 102.2])
scanner3 = GapScanner(event_bus=EventBus())
results2 = scanner3.scan_bars('TEST', bars2)
gaps2 = [r for r in results2 if r['gap_percent'] > 0.1]
print('\nFAILURE 2 (fixed):')
for g in gaps2:
    print(f'  type={g["gap_type"]}, pct={g["gap_percent"]}, dir={g["direction"]}')

import asyncio
from shettyxtreme.intelligence.signals import SimpleSignalGenerator

async def test():
    bus3 = EventBus()
    gen = SimpleSignalGenerator(event_bus=bus3, min_strength=4.0, cooldown_seconds=300)
    result = {'symbol': 'TCS', 'direction': 'bearish', 'gap_type': 'breakaway',
              'gap_percent': 2.5, 'confidence': 70.0, 'volume_confirmed': False}
    sigs = await gen.process({'gap': [result]})
    print(f'\nFAILURE 3 (original confidence=70): signals={len(sigs)}')
    
    bus4 = EventBus()
    gen2 = SimpleSignalGenerator(event_bus=bus4, min_strength=4.0, cooldown_seconds=300)
    result2 = {'symbol': 'TCS', 'direction': 'bearish', 'gap_type': 'breakaway',
               'gap_percent': 2.5, 'confidence': 80.0, 'volume_confirmed': False}
    sigs2 = await gen2.process({'gap': [result2]})
    print(f'FAILURE 3 (fixed confidence=80): signals={len(sigs2)}')
    if sigs2:
        print(f'  strength={sigs2[0].strength}, source={sigs2[0].source}')
        print(f'  reasoning={sigs2[0].reasoning}')

asyncio.run(test())
