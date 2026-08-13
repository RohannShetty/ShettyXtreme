"""Configuration management - YAML files with env var overrides.

Pattern: Load config.yaml -> override with env vars -> validate.
Secrets from env vars only, never from config files committed to git.
"""
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import yaml


# Basic schema: config key -> expected type(s). ``mode`` is the only key a
# config file MUST declare — it selects the execution mode and is the
# load-bearing safety switch (OBSERVER first, D10). Every other key has a
# safe dataclass default, so a partial config file is accepted as long as
# the keys it does declare type-check. Unknown keys are ignored (forward
# compatibility).
_SCHEMA: dict[str, type | tuple[type, ...]] = {
    "mode": str,
    "broker": str,
    "log_level": str,
    "dry_run": bool,
    "data_dir": str,
    "config_dir": str,
    "log_dir": str,
    "fyers_app_id": (str, type(None)),
    "fyers_secret_id": (str, type(None)),
    "paper_trading_margin": (int, float, type(None)),
    # P4: scanner→proposal bridge section (configs/default.yaml). Dict of
    # {enabled, min_severity, scanner_types, cooldown_seconds}; None when
    # absent — the bridge then stays disabled.
    "scanner_proposal_bridge": (dict, type(None)),
}

# Keys a config file must provide. Deliberately just ``mode``: the legacy
# behaviour of accepting partial configs (everything else falls back to a
# dataclass default) is preserved — see test_unknown_key_in_yaml_ignored.
_REQUIRED_KEYS: tuple[str, ...] = ("mode",)


def _type_name(expected: type | tuple[type, ...]) -> str:
    if isinstance(expected, tuple):
        return " | ".join(t.__name__ for t in expected)
    return expected.__name__


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

    # Paper trading capital (₹) — used as available margin in PAPER mode
    paper_trading_margin: float | None = None

    # P4: scanner→proposal bridge settings (dict from configs/default.yaml;
    # None when the section is absent → bridge disabled)
    scanner_proposal_bridge: dict | None = None

class ConfigManager:
    def __init__(self, config_path: str | None = None):
        self._config = Config()
        self.load(config_path)

    def load(self, config_path: str | None = None) -> None:
        """Load config from an optional YAML file + env overrides, then validate."""
        if config_path:
            self._load_yaml(config_path)
        self._load_env_overrides()
        self.validate()

    def validate(self, data: dict[str, Any] | None = None) -> None:
        """Validate a config mapping against the schema.

        Checks that required keys are present and that every declared key
        has the expected type; unknown keys are ignored (forward
        compatibility). With ``data`` omitted, the merged config state
        (defaults + YAML + env) is validated.
        """
        source = data if data is not None else asdict(self._config)
        missing = [k for k in _REQUIRED_KEYS if k not in source]
        if missing:
            raise ValueError(
                f"config missing required key(s): {', '.join(missing)}"
            )
        for key, expected in _SCHEMA.items():
            if key in source and not isinstance(source[key], expected):
                raise ValueError(
                    f"config key '{key}' must be {_type_name(expected)}, "
                    f"got {type(source[key]).__name__}"
                )

    def _load_yaml(self, path: str):
        p = Path(path)
        if p.exists():
            with open(p) as f:
                data = yaml.safe_load(f)
                if data:
                    self.validate(data)
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
            "SHETTY_PAPER_TRADING_MARGIN": "paper_trading_margin",
        }
        for env_key, config_key in env_map.items():
            val = os.environ.get(env_key)
            if val is not None:
                if config_key == "dry_run":
                    val = val.lower() in ("true", "1", "yes")
                elif config_key == "paper_trading_margin":
                    try:
                        val = float(val)
                    except ValueError:
                        continue
                setattr(self._config, config_key, val)

    @property
    def config(self) -> Config:
        return self._config
