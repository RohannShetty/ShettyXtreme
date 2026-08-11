"""Tests for the typed settings store (Phase 7 Wave 3)."""
from __future__ import annotations

import pytest

from shettyxtreme.core.settings import (
    DEFAULT_LOSS_LIMIT,
    DEFAULT_MAX_POSITIONS,
    DEFAULT_THEME,
    SettingsError,
    SettingsStore,
    get_settings_store,
    init_settings_store,
    reset_settings_store,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    reset_settings_store()
    yield
    reset_settings_store()


class TestDefaults:
    def test_defaults_when_empty(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        assert store.loss_limit() == DEFAULT_LOSS_LIMIT
        assert store.max_positions() == DEFAULT_MAX_POSITIONS
        assert store.theme() == DEFAULT_THEME
        assert store.scheduler_config() == {
            "enabled": False,
            "interval_minutes": 60.0,
            "lenses": None,
            "tools": None,
        }
        store.close()

    def test_get_unknown_key_raises(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        with pytest.raises(SettingsError):
            store.get("no_such_setting")
        store.close()


class TestValidation:
    def test_loss_limit_must_be_non_positive(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        with pytest.raises(SettingsError):
            store.update({"loss_limit": 1000.0})
        # Failed batch leaves the store untouched.
        assert store.loss_limit() == DEFAULT_LOSS_LIMIT
        store.close()

    def test_loss_limit_must_be_finite(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        with pytest.raises(SettingsError):
            store.update({"loss_limit": float("nan")})
        with pytest.raises(SettingsError):
            store.update({"loss_limit": float("inf")})
        store.close()

    def test_max_positions_bounds(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        with pytest.raises(SettingsError):
            store.update({"max_positions": 0})
        with pytest.raises(SettingsError):
            store.update({"max_positions": 101})
        with pytest.raises(SettingsError):
            store.update({"max_positions": 2.5})
        store.close()

    def test_theme_must_be_dark_or_light(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        with pytest.raises(SettingsError):
            store.update({"theme": "blue"})
        store.update({"theme": "light"})
        assert store.theme() == "light"
        store.close()

    def test_scheduler_interval_validated(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        with pytest.raises(SettingsError):
            store.update({"scheduler_interval_minutes": 0})
        with pytest.raises(SettingsError):
            store.update({"scheduler_interval_minutes": -5})
        with pytest.raises(SettingsError):
            store.update({"scheduler_interval_minutes": 24 * 60 + 1})
        store.update({"scheduler_interval_minutes": 30})
        assert store.get("scheduler_interval_minutes") == 30.0
        store.close()

    def test_unknown_key_rejected(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        with pytest.raises(SettingsError):
            store.update({"bogus_setting": 1})
        store.close()

    def test_batch_is_all_or_nothing(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        with pytest.raises(SettingsError):
            store.update({"loss_limit": -3000.0, "max_positions": 0})
        # Neither key from the failed batch was written.
        assert store.loss_limit() == DEFAULT_LOSS_LIMIT
        assert store.max_positions() == DEFAULT_MAX_POSITIONS
        store.close()


class TestPersistence:
    def test_update_round_trip(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        snapshot = store.update({
            "loss_limit": -3000.0,
            "max_positions": 3,
            "theme": "light",
            "scheduler_enabled": True,
            "scheduler_interval_minutes": 45.0,
            "scheduler_lenses": ["oi_iv_flow", "tail_risk"],
            "scheduler_tools": None,
        })
        assert snapshot["loss_limit"] == -3000.0
        assert snapshot["max_positions"] == 3
        assert snapshot["theme"] == "light"
        assert snapshot["scheduler_enabled"] is True
        assert snapshot["scheduler_interval_minutes"] == 45.0
        assert snapshot["scheduler_lenses"] == ["oi_iv_flow", "tail_risk"]
        assert snapshot["scheduler_tools"] is None
        store.close()

    def test_persists_across_instances(self, tmp_path) -> None:
        path = tmp_path / "settings.db"
        store1 = SettingsStore(path)
        store1.update({"loss_limit": -2500.0, "scheduler_lenses": ["tail_risk"]})
        store1.close()

        store2 = SettingsStore(path)
        assert store2.loss_limit() == -2500.0
        assert store2.scheduler_config()["lenses"] == ["tail_risk"]
        store2.close()

    def test_partial_update_keeps_others(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        store.update({"loss_limit": -3000.0})
        store.update({"max_positions": 4})
        assert store.loss_limit() == -3000.0
        assert store.max_positions() == 4
        assert store.theme() == DEFAULT_THEME
        store.close()

    def test_seed_only_fills_absent(self, tmp_path) -> None:
        store = SettingsStore(tmp_path / "settings.db")
        store.update({"scheduler_enabled": True})
        store.seed_if_absent({
            "scheduler_enabled": False,
            "scheduler_interval_minutes": 15.0,
        })
        # Already present — untouched by the seed.
        assert store.get("scheduler_enabled") is True
        # Absent — seeded.
        assert store.get("scheduler_interval_minutes") == 15.0
        store.close()


class TestSingleton:
    def test_get_settings_store_lazy_default(self) -> None:
        store = get_settings_store()
        assert store.loss_limit() == DEFAULT_LOSS_LIMIT

    def test_init_settings_store_replaces_shared(self, tmp_path) -> None:
        init_settings_store(tmp_path / "a.db")
        first = get_settings_store()
        first.update({"loss_limit": -1111.0})

        init_settings_store(tmp_path / "b.db")
        second = get_settings_store()
        assert second is not first
        # The new shared store is fresh, not a view over the old one.
        assert second.loss_limit() == DEFAULT_LOSS_LIMIT

    def test_reset_drops_shared_store(self, tmp_path) -> None:
        init_settings_store(tmp_path / "a.db")
        get_settings_store().update({"loss_limit": -2222.0})
        reset_settings_store()
        fresh = get_settings_store()
        assert fresh.loss_limit() == DEFAULT_LOSS_LIMIT
