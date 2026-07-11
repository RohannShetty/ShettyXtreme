"""Key-Value store abstraction for config, preferences, instrument master."""
import json
import sqlite3
from pathlib import Path
from typing import Any, Optional

class KVStore:
    def __init__(self, db_path: str = "data/shetty_kv.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT, updated_at TEXT)")
    
    def put(self, key: str, value: Any):
        self._conn.execute(
            "INSERT OR REPLACE INTO kv (key, value, updated_at) VALUES (?, ?, datetime('now'))",
            (key, json.dumps(value))
        )
        self._conn.commit()
    
    def get(self, key: str, default: Any = None) -> Any:
        cur = self._conn.execute("SELECT value FROM kv WHERE key = ?", (key,))
        row = cur.fetchone()
        return json.loads(row[0]) if row else default
    
    def delete(self, key: str):
        self._conn.execute("DELETE FROM kv WHERE key = ?", (key,))
        self._conn.commit()
    
    def keys(self, prefix: str = "") -> list[str]:
        cur = self._conn.execute("SELECT key FROM kv WHERE key LIKE ?", (f"{prefix}%",))
        return [row[0] for row in cur.fetchall()]
    
    def close(self):
        self._conn.close()
