
"""Integration tests for ConfigManager."""

import os
import pytest


class TestConfigManagerDefaults:
    def test_defaults_when_no_file(self, clean_env):
        from shettyxtreme.core.config import ConfigManager
        cm = ConfigManager()
        cfg = cm.config
        assert cfg.mode == "observer"
        assert cfg.broker == "fyers"
        assert cfg.dry_run is True
        assert cfg.log_level == "INFO"

    def test_loads_yaml_values(self, config_manager):
        cfg = config_manager.config
        assert cfg.mode == "paper"
        assert cfg.broker == "fyers"
        assert cfg.log_level == "DEBUG"
        assert cfg.dry_run is True

    def test_fyers_app_id_from_yaml(self, config_manager):
        cfg = config_manager.config
        assert cfg.fyers_app_id == "test_app"

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

    def test_fyers_credentials_from_env(self, monkeypatch):
        from shettyxtreme.core.config import ConfigManager
        monkeypatch.setenv("FYERS_APP_ID", "env_app")
        monkeypatch.setenv("FYERS_SECRET_ID", "env_secret")
        cm = ConfigManager()
        assert cm.config.fyers_app_id == "env_app"
        assert cm.config.fyers_secret_id == "env_secret"


class TestConfigValidation:
    """F-CORE-004: ConfigManager must validate, not just load."""

    def _write(self, tmp_data_dir, data):
        import yaml
        path = os.path.join(tmp_data_dir, "config.yaml")
        with open(path, "w") as f:
            yaml.dump(data, f)
        return path

    def test_missing_required_key_raises(self, tmp_data_dir):
        from shettyxtreme.core.config import ConfigManager
        path = self._write(tmp_data_dir, {"broker": "fyers"})  # no "mode"
        with pytest.raises(ValueError, match="mode"):
            ConfigManager(path)

    def test_wrong_type_raises(self, tmp_data_dir):
        from shettyxtreme.core.config import ConfigManager
        path = self._write(tmp_data_dir, {"mode": 123, "dry_run": "yes"})
        with pytest.raises(ValueError, match="mode"):
            ConfigManager(path)

    def test_valid_config_passes(self, tmp_data_dir):
        from shettyxtreme.core.config import ConfigManager
        path = self._write(
            tmp_data_dir,
            {"mode": "paper", "broker": "fyers", "log_level": "DEBUG", "dry_run": True},
        )
        cm = ConfigManager(path)
        assert cm.config.mode == "paper"
        assert cm.config.dry_run is True

    def test_validate_method_rejects_partial_mapping(self, tmp_data_dir):
        from shettyxtreme.core.config import ConfigManager
        path = self._write(tmp_data_dir, {"mode": "live"})
        cm = ConfigManager(path)
        with pytest.raises(ValueError, match="mode"):
            cm.validate({"broker": "fyers"})

    def test_validate_method_accepts_required_keys_only(self, tmp_data_dir):
        from shettyxtreme.core.config import ConfigManager
        path = self._write(tmp_data_dir, {"mode": "live"})
        cm = ConfigManager(path)
        cm.validate({"mode": "observer"})  # must not raise
        with pytest.raises(ValueError, match="dry_run"):
            cm.validate({"mode": "observer", "dry_run": "yes"})
