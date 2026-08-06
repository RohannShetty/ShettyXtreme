"""Typed settings store — SQLite KV with validation (Phase 7 Wave 3).

Single source of truth for operator-configurable settings (risk limits,
theme, research scheduler). Backed by the generic ``KVStore`` (SQLite JSON
KV, stdlib-only) so persistence is consistent with the rest of ``core`` and
introduces no new dependency.

Design rules:
  - Every write is validated against the per-key ``_SPECS`` schema; a bad
    value raises ``SettingsError`` (mapped to HTTP 400 by the router) and
    the batch is left untouched (validate-all-then-write).
  - Reads return the validated stored value, falling back to the schema
    default when the key was never written. Values are always valid because
    the only write path is ``update`` / ``seed_if_absent``.
  - The shared store is a module singleton: components (risk filters, bus
    bridge, projections, execution router, settings router) all read the
    same instance via ``get_settings_store()``. The composition root points
    it at a real path with ``init_settings_store``; tests use
    ``reset_settings_store`` for isolation.

Settings are runtime-mutable (PUT endpoints) and survive restarts — the
store is the persisted, version-agnostic KV layer the settings form reads
and writes.
"""
from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from shettyxtreme.core.storage.kv_store import KVStore

DEFAULT_DB_PATH = "data/settings.db"

DEFAULT_LOSS_LIMIT = -5000.0
DEFAULT_MAX_POSITIONS = 5
DEFAULT_THEME = "dark"
DEFAULT_SCHEDULER_ENABLED = False
DEFAULT_SCHEDULER_INTERVAL_MINUTES = 60.0

VALID_THEMES = ("dark", "light")
MAX_POSITIONS_CAP = 100
MAX_INTERVAL_MINUTES = 24 * 60  # one-day cap on the research cadence
MAX_LOSS_LIMIT_ABS = 10_000_000.0


class SettingsError(ValueError):
    """Raised when a setting value fails validation."""


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------
def _validate_loss_limit(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise SettingsError("loss_limit must be a number") from exc
    if not math.isfinite(v):
        raise SettingsError("loss_limit must be a finite number")
    if v > 0:
        raise SettingsError("loss_limit must be zero or negative (a daily loss cap)")
    if abs(v) > MAX_LOSS_LIMIT_ABS:
        raise SettingsError(f"loss_limit magnitude too large (max {MAX_LOSS_LIMIT_ABS:,.0f})")
    return v


def _validate_max_positions(value: Any) -> int:
    if isinstance(value, float) and not value.is_integer():
        raise SettingsError("max_positions must be an integer")
    try:
        v = int(value)
    except (TypeError, ValueError) as exc:
        raise SettingsError("max_positions must be an integer") from exc
    if v < 1 or v > MAX_POSITIONS_CAP:
        raise SettingsError(f"max_positions must be between 1 and {MAX_POSITIONS_CAP}")
    return v


def _validate_theme(value: Any) -> str:
    v = str(value).strip().lower()
    if v not in VALID_THEMES:
        raise SettingsError(f"theme must be one of {list(VALID_THEMES)}")
    return v


def _validate_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("true", "1", "yes", "on"):
            return True
        if lowered in ("false", "0", "no", "off"):
            return False
    raise SettingsError("value must be a boolean")


def _validate_interval_minutes(value: Any) -> float:
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise SettingsError("interval_minutes must be a number") from exc
    if not math.isfinite(v):
        raise SettingsError("interval_minutes must be a finite number")
    if v <= 0:
        raise SettingsError("interval_minutes must be positive")
    if v > MAX_INTERVAL_MINUTES:
        raise SettingsError(f"interval_minutes too large (max {MAX_INTERVAL_MINUTES})")
    return v


def _validate_lenses(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = [x.strip() for x in value.split(",") if x.strip()]
        return cleaned or None
    if isinstance(value, list):
        cleaned = [str(x).strip() for x in value if str(x).strip()]
        return cleaned or None
    raise SettingsError("lenses must be a list of strings (or null)")


def _validate_tools(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        cleaned = [x.strip() for x in value.split(",") if x.strip()]
        return cleaned or None
    if isinstance(value, list):
        cleaned = [str(x).strip() for x in value if str(x).strip()]
        return cleaned or None
    raise SettingsError("tools must be a list of strings (or null)")


@dataclass(frozen=True)
class _Spec:
    """Schema entry: safe default + validator for one setting key."""

    default: Any
    validator: Callable[[Any], Any]


_SPECS: dict[str, _Spec] = {
    "loss_limit": _Spec(DEFAULT_LOSS_LIMIT, _validate_loss_limit),
    "max_positions": _Spec(DEFAULT_MAX_POSITIONS, _validate_max_positions),
    "theme": _Spec(DEFAULT_THEME, _validate_theme),
    "scheduler_enabled": _Spec(DEFAULT_SCHEDULER_ENABLED, _validate_bool),
    "scheduler_interval_minutes": _Spec(
        DEFAULT_SCHEDULER_INTERVAL_MINUTES, _validate_interval_minutes
    ),
    "scheduler_lenses": _Spec(None, _validate_lenses),
    "scheduler_tools": _Spec(None, _validate_tools),
}


class SettingsStore:
    """Typed KV settings store with schema validation.

    Thread-safe by construction: every operation opens a short-lived
    ``KVStore`` connection in the calling thread, so the same store can be
    used from the asyncio event loop and from worker threads (e.g. the
    Starlette TestClient portal) without sqlite thread-affinity errors.
    A store-level lock serializes concurrent writes.
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH) -> None:
        self._db_path = str(db_path)
        self._write_lock = threading.Lock()

    def _kv(self) -> KVStore:
        """A fresh KVStore connection, created (and closed) per operation."""
        return KVStore(self._db_path)

    # ── reads ──────────────────────────────────────────────────────────────
    def get(self, key: str) -> Any:
        """Return the stored value, or the schema default if never written.

        Values were validated when written; the default is the schema's
        safe fallback. Unknown keys raise — a typo is a programming error.
        """
        spec = _SPECS.get(key)
        if spec is None:
            raise SettingsError(f"unknown setting: {key}")
        kv = self._kv()
        try:
            stored = kv.get(key)
        finally:
            kv.close()
        return spec.default if stored is None else stored

    def get_all(self) -> dict[str, Any]:
        return {key: self.get(key) for key in _SPECS}

    def loss_limit(self) -> float:
        return self.get("loss_limit")

    def max_positions(self) -> int:
        return self.get("max_positions")

    def theme(self) -> str:
        return self.get("theme")

    def scheduler_config(self) -> dict[str, Any]:
        """Persisted scheduler config (enabled/interval/lenses/tools)."""
        return {
            "enabled": self.get("scheduler_enabled"),
            "interval_minutes": self.get("scheduler_interval_minutes"),
            "lenses": self.get("scheduler_lenses"),
            "tools": self.get("scheduler_tools"),
        }

    # ── writes ─────────────────────────────────────────────────────────────
    def update(self, updates: Mapping[str, Any]) -> dict[str, Any]:
        """Validate + persist a batch of settings.

        All values are validated BEFORE anything is written, so a failed
        validation leaves the store untouched. Returns the full snapshot.
        """
        validated: dict[str, Any] = {}
        for key, value in updates.items():
            spec = _SPECS.get(key)
            if spec is None:
                raise SettingsError(f"unknown setting: {key}")
            validated[key] = spec.validator(value)
        with self._write_lock:
            kv = self._kv()
            try:
                for key, value in validated.items():
                    kv.put(key, value)
            finally:
                kv.close()
        return self.get_all()

    def seed_if_absent(self, updates: Mapping[str, Any]) -> None:
        """Write values only for keys that are not already stored.

        Used by the composition root to seed the store from env config on
        first boot; once a key exists (e.g. written by the settings form)
        it is never overwritten by a seed.
        """
        validated: dict[str, Any] = {}
        for key, value in updates.items():
            spec = _SPECS.get(key)
            if spec is None:
                raise SettingsError(f"unknown setting: {key}")
            validated[key] = spec.validator(value)
        with self._write_lock:
            kv = self._kv()
            try:
                for key, value in validated.items():
                    if kv.get(key, _MISSING) is _MISSING:
                        kv.put(key, value)
            finally:
                kv.close()

    def close(self) -> None:
        # No persistent connection is held — kept for API compatibility with
        # the singleton lifecycle (init_settings_store / reset_settings_store).
        pass


_MISSING = object()


# ---------------------------------------------------------------------------
# Shared singleton
# ---------------------------------------------------------------------------
_store: SettingsStore | None = None
_store_lock = threading.Lock()


def init_settings_store(path: str | Path = DEFAULT_DB_PATH) -> SettingsStore:
    """Point the shared store at a path and return it (composition root).

    Closes and replaces any previously created shared store.
    """
    global _store
    with _store_lock:
        if _store is not None:
            try:
                _store.close()
            except Exception:
                pass
        _store = SettingsStore(path)
        return _store


def get_settings_store() -> SettingsStore:
    """The shared settings store, created lazily at the default path."""
    global _store
    with _store_lock:
        if _store is None:
            _store = SettingsStore(DEFAULT_DB_PATH)
        return _store


def reset_settings_store() -> None:
    """Close and drop the shared store (test isolation)."""
    global _store
    with _store_lock:
        if _store is not None:
            try:
                _store.close()
            except Exception:
                pass
            _store = None
