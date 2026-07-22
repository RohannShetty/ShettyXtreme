

"""Integration tests for TimeSeriesStore."""

import pytest
try:
    import duckdb
    DUCKDB_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    DUCKDB_AVAILABLE = False


from datetime import datetime, timezone


@pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="duckdb C extension not available on Python 3.14")
class TestTimeSeriesStoreBars:
    def test_write_and_get_bars(self, ts_store):
        ts_store.write_bar(
            symbol="RELIANCE", exchange="NSE", timeframe="1min",
            open_=2500.0, high=2510.0, low=2495.0, close=2505.0,
            volume=10000, timestamp=datetime(2024, 1, 15, 9, 30),
        )
        start = datetime(2024, 1, 15, 9, 0)
        end = datetime(2024, 1, 15, 10, 0)
        bars = ts_store.get_bars("RELIANCE", "1min", start, end)
        assert len(bars) == 1
        row = bars[0]
        assert row[1] == "RELIANCE"
        assert row[4] == 2500.0  # open

    def test_get_bars_empty_range(self, ts_store):
        start = datetime(2020, 1, 1)
        end = datetime(2020, 1, 2)
        bars = ts_store.get_bars("NONEXISTENT", "1min", start, end)
        assert bars == []

    def test_time_range_query(self, ts_store):
        from datetime import timedelta
        base = datetime(2024, 6, 1, 9, 15)
        for i in range(5):
            ts_store.write_bar(
                symbol="NIFTY", exchange="NFO", timeframe="5min",
                open_=22000 + i, high=22010 + i, low=21990 + i,
                close=22005 + i, volume=5000,
                timestamp=base + timedelta(minutes=5 * i),
            )
        mid_start = base + timedelta(minutes=5)
        mid_end = base + timedelta(minutes=20)
        bars = ts_store.get_bars("NIFTY", "5min", mid_start, mid_end)
        assert len(bars) == 3

    def test_schema_compliance(self, ts_store):
        ts_store.write_bar(
            symbol="TEST", exchange="BSE", timeframe="daily",
            open_=100.0, high=105.0, low=99.0, close=103.5,
            volume=50000, timestamp=datetime(2024, 3, 15), oi=1000,
        )
        start = datetime(2024, 3, 1)
        end = datetime(2024, 3, 31)
        bars = ts_store.get_bars("TEST", "daily", start, end)
        assert len(bars) == 1
        row = bars[0]
        assert len(row) == 11
        assert row[10] == 1000  # oi

    def test_write_multiple_bars_same_symbol(self, ts_store):
        from datetime import timedelta
        base = datetime(2024, 7, 1, 9, 15)
        for i in range(3):
            ts_store.write_bar(
                symbol="BANKNIFTY", exchange="NFO", timeframe="1min",
                open_=48000.0 + i, high=48050.0 + i, low=47950.0 + i,
                close=48020.0 + i, volume=2000 * (i + 1),
                timestamp=base + timedelta(minutes=i),
            )
        start = base
        end = base + timedelta(hours=1)
        bars = ts_store.get_bars("BANKNIFTY", "1min", start, end)
        assert len(bars) == 3


@pytest.mark.skipif(not DUCKDB_AVAILABLE, reason="duckdb C extension not available on Python 3.14")
class TestTimeSeriesStoreTicks:
    def test_write_ticks(self, ts_store):
        ticks = [
            ("RELIANCE", "NSE", 2505.0, 100, datetime(2024, 1, 15, 10, 30, 0), 2504.5, 2505.5),
            ("RELIANCE", "NSE", 2506.0, 150, datetime(2024, 1, 15, 10, 30, 1), 2505.5, 2506.5),
        ]
        ts_store.write_ticks(ticks)
        result = ts_store._conn.execute("SELECT COUNT(*) FROM ticks").fetchone()
        assert result[0] == 2

    def test_write_ticks_empty_list(self, ts_store):
        ts_store.write_ticks([])
