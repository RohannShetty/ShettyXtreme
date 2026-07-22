"""Time-series store for market data (bars, ticks)."""
from pathlib import Path
from typing import Optional
from datetime import datetime
try:
    import duckdb
    _DUCKDB_AVAILABLE = True
except (ImportError, ModuleNotFoundError):
    _DUCKDB_AVAILABLE = False
    duckdb = None  # type: ignore

class TimeSeriesStore:
    def __init__(self, db_path: str = "data/shetty_ts.db"):
        if not _DUCKDB_AVAILABLE:
            raise ImportError("duckdb C extension not available. Install duckdb with working C extension (requires Python<3.14 or duckdb>=1.6)")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(db_path)
        self._init_schema()
    
    def _init_schema(self):
        self._conn.execute("""
            CREATE SEQUENCE IF NOT EXISTS bar_id_seq START 1
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS bars (
                id INTEGER PRIMARY KEY DEFAULT nextval('bar_id_seq'),
                symbol VARCHAR,
                exchange VARCHAR,
                timeframe VARCHAR,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume BIGINT,
                timestamp TIMESTAMP,
                oi BIGINT
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS ticks (
                symbol VARCHAR,
                exchange VARCHAR,
                ltp DOUBLE,
                volume BIGINT,
                timestamp TIMESTAMP,
                bid DOUBLE,
                ask DOUBLE
            )
        """)
    
    def write_bar(self, symbol: str, exchange: str, timeframe: str,
                  open_: float, high: float, low: float, close: float,
                  volume: int, timestamp: datetime, oi: Optional[int] = None):
        self._conn.execute(
            "INSERT INTO bars VALUES (nextval('bar_id_seq'), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (symbol, exchange, timeframe, open_, high, low, close, volume, timestamp, oi)
        )
    
    def write_ticks(self, ticks: list[tuple]):
        if not ticks:
            return
        self._conn.executemany(
            "INSERT INTO ticks VALUES (?, ?, ?, ?, ?, ?, ?)", ticks
        )
    
    def get_bars(self, symbol: str, timeframe: str,
                 start: datetime, end: datetime) -> list:
        result = self._conn.execute(
            "SELECT * FROM bars WHERE symbol = ? AND timeframe = ? AND timestamp >= ? AND timestamp < ? ORDER BY timestamp",
            (symbol, timeframe, start, end)
        )
        return result.fetchall() if result else []
    
    def close(self):
        self._conn.close()
