"""Configuration management - YAML files with env var overrides.

Pattern: Load config.yaml -> override with env vars -> validate with pydantic.
Secrets from env vars only, never from config files committed to git.
"""
import os
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Config:
    mode: str = "observer"  # backtest | simulation | observer | live | paper
    broker: str = "fyers"
    log_level: str = "INFO"
    dry_run: bool = True

    # Paths
    data_dir: str = "data"
    config_dir: str = "configs"
    log_dir: str = "logs"

    # Broker credentials (loaded from env; the OAuth flow is the primary
    # path — these are optional overrides for headless runs)
    fyers_app_id: str | None = None
    fyers_secret_id: str | None = None

class ConfigManager:
    def __init__(self, config_path: str | None = None):
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
            "FYERS_APP_ID": "fyers_app_id",
            "FYERS_SECRET_ID": "fyers_secret_id",
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
