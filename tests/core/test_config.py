
"""Integration tests for ConfigManager."""

import os
import pytest


class TestConfigManagerDefaults:
    def test_defaults_when_no_file(self, clean_env):
        from shettyxtreme.core.config import ConfigManager
        cm = ConfigManager()
        cfg = cm.config
        assert cfg.mode == "observer"
        assert cfg.broker == "dhan"
        assert cfg.dry_run is True
        assert cfg.log_level == "INFO"

    def test_loads_yaml_values(self, config_manager):
        cfg = config_manager.config
        assert cfg.mode == "paper"
        assert cfg.broker == "dhan"
        assert cfg.log_level == "DEBUG"
        assert cfg.dry_run is True

    def test_dhan_client_id_from_yaml(self, config_manager):
        cfg = config_manager.config
        assert cfg.dhan_client_id == "test_client"

    def test_unknown_key_in_yaml_ignored(self, tmp_data_dir):
        import yaml
        from shettyxtreme.core.config import ConfigManager
        cfg_data = {"mode": "live", "nonexistent_field": "should_be_ignored"}
        cfg_path = os.path.join(tmp_data_dir, "bad_config.yaml")
        with open(cfg_path, "w") as f:
            yaml.dump(cfg_data, f)
        cm = ConfigManager(cfg_path)
        assert cm.config.mode == "live"
        assert not hasattr(cm.config, "nonexistent_field")


class TestConfigManagerEnvOverrides:
    def test_env_var_overrides_yaml(self, config_manager, monkeypatch):
        monkeypatch.setenv("SHETTY_MODE", "live")
        config_manager._load_env_overrides()
        cfg = config_manager.config
        assert cfg.mode == "live"

    def test_dry_run_env_parsing(self, monkeypatch):
        from shettyxtreme.core.config import ConfigManager
        monkeypatch.setenv("SHETTY_DRY_RUN", "false")
        cm = ConfigManager()
        assert cm.config.dry_run is False

        monkeypatch.setenv("SHETTY_DRY_RUN", "1")
        cm = ConfigManager()
        assert cm.config.dry_run is True

    def test_dhan_credentials_from_env(self, monkeypatch):
        from shettyxtreme.core.config import ConfigManager
        monkeypatch.setenv("DHAN_CLIENT_ID", "env_client")
        monkeypatch.setenv("DHAN_ACCESS_TOKEN", "env_token")
        cm = ConfigManager()
        assert cm.config.dhan_client_id == "env_client"
        assert cm.config.dhan_access_token == "env_token"

