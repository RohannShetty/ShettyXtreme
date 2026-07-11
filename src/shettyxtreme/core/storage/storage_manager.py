"""Storage manager - unified access to all storage backends."""
from .kv_store import KVStore
from .time_series_store import TimeSeriesStore

class StorageManager:
    def __init__(self, data_dir: str = "data"):
        self.kv = KVStore(f"{data_dir}/shetty_kv.db")
        self.ts = TimeSeriesStore(f"{data_dir}/shetty_ts.db")
    
    def close(self):
        self.kv.close()
        self.ts.close()
