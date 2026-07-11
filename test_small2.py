"""PriceBreakoutScanner — detects price breaking above resistance or below support levels.

Subscribes to MARKET_DATA_BAR events, maintains rolling price history per
symbol, and emits scan results when the current bar closes beyond a
lookback-period high (resistance breakout) or low (support breakdown).

Volume confirmation is applied when bar volume exceeds the rolling average.
"""
