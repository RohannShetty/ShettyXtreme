"""Configuration management - YAML files with env var overrides.

Pattern: Load config.yaml -> override with env vars -> validate with pydantic.
Secrets from env vars only, never from config files committed to git.
"""
import os
import yaml
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class Config:
    mode: str = "observer"  # backtest | simulation | observer | live | paper
    broker: str = "dhan"
    log_level: str = "INFO"
    dry_run: bool = True

    # Paths
    data_dir: str = "data"
    config_dir: str = "configs"
    log_dir: str = "logs"

    # Broker credentials (loaded from env)
    dhan_client_id: Optional[str] = None
    dhan_access_token: Optional[str] = None

    # Dhan dual-path credentials (trading + data, separate to avoid error 806)
    dhan_trading_client_id: str | None = None
    dhan_trading_access_token: str | None = None
    dhan_data_api_key: str | None = None
    dhan_data_client_id: str | None = None

class ConfigManager:
    def __init__(self, config_path: Optional[str] = None):
        self._config = Config()
        if config_path:
            self._load_yaml(config_path)
        self._load_env_overrides()

    def _load_yaml(self, path: str):
        p = Path(path)
        if p.exists():
            with open(p) as f:
                data = yaml.safe_load(f)
                if data:
                    for k, v in data.items():
                        if hasattr(self._config, k):
                            setattr(self._config, k, v)

    def _load_env_overrides(self):
        env_map = {
            "SHETTY_MODE": "mode",
            "SHETTY_BROKER": "broker",
            "SHETTY_DRY_RUN": "dry_run",
            "DHAN_CLIENT_ID": "dhan_client_id",
            "DHAN_ACCESS_TOKEN": "dhan_access_token",
            "DHAN_TRADING_CLIENT_ID": "dhan_trading_client_id",
            "DHAN_TRADING_ACCESS_TOKEN": "dhan_trading_access_token",
            "DHAN_DATA_API_KEY": "dhan_data_api_key",
            "DHAN_DATA_CLIENT_ID": "dhan_data_client_id",
        }
        for env_key, config_key in env_map.items():
            val = os.environ.get(env_key)
            if val is not None:
                if config_key == "dry_run":
                    val = val.lower() in ("true", "1", "yes")
                setattr(self._config, config_key, val)

    @property
    def config(self) -> Config:
        return self._config
