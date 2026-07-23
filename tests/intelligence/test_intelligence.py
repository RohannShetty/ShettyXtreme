
import pytest
import asyncio
from datetime import datetime
from shettyxtreme.core.event_bus import EventBus, Event, Topic
from shettyxtreme.intelligence.features.feature_engine import FeatureEngine, Feature
from shettyxtreme.intelligence.signals.signal_engine import SignalEngine, SignalDirection, Vote
from shettyxtreme.core.data_models.market_data import Tick

@pytest.mark.asyncio
async def test_intelligence_layers():
    bus = EventBus()
    features = FeatureEngine(bus)
    
    # Needs async setup and maintenance
    asyncio.create_task(bus.start())
    
    engine = SignalEngine(features)
    
    # Register dummy plugin
    def plugin(tick: Tick) -> list[Feature]:
        return [Feature("orb_breakout", 1.0)]
    
    features.register_plugin("test", plugin)
    
    # Process tick
    await bus.publish(Event(Topic.MARKET_DATA_TICK, Tick(symbol="AAPL", exchange="NSE", ltp=100.0, volume=1000, timestamp=datetime.now())))
    
    # Register voters
    engine.register_voter("orb", lambda f: Vote(direction=1.0, confidence=0.8, weight=1.0, name="orb"))
    
    # Compute
    signal = engine.compute_signal()
    assert signal.direction == SignalDirection.UP
    assert signal.conviction > 0
    await bus.stop()
