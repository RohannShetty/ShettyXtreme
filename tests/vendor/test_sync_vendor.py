"""Tests for scripts/sync_vendor.py — vendored-file copy + origin stamping."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
import sync_vendor  # noqa: E402


@pytest.fixture
def layout(tmp_path: Path):
    mirror = tmp_path / "mirror"
    vendor = tmp_path / "vendor"
    (mirror / "src").mkdir(parents=True)
    (vendor / "openalgo").mkdir(parents=True)
    (mirror / "src" / "order.py").write_text("VALID_ACTIONS = ['BUY', 'SELL']\n", encoding="utf-8")
    (mirror / "src" / "skip.py").write_text("SHOULD_NOT_COPY = True\n", encoding="utf-8")
    files_yaml = tmp_path / "FILES.yaml"
    files_yaml.write_text(
        "files:\n"
        "  - src: src/order.py\n"
        "    dest: order_validator.py\n",
        encoding="utf-8",
    )
    meta = {"commit": "abc123", "url": "https://github.com/marketcalls/openalgo", "date": "2026-08-01"}
    return mirror, vendor, files_yaml, meta


def test_load_file_list(layout):
    _m, _v, files_yaml, _meta = layout
    files = sync_vendor.load_file_list(files_yaml)
    assert files == [{"src": "src/order.py", "dest": "order_validator.py"}]


def test_collect_sources_resolves_and_filters_missing(layout):
    mirror, _v, files_yaml, _meta = layout
    files = sync_vendor.load_file_list(files_yaml)
    sources = sync_vendor.collect_sources(files, mirror)
    assert [(s.name, d.name) for s, d in sources] == [("order.py", "order_validator.py")]


def test_stamp_includes_origin_header(layout):
    _m, _v, _y, meta = layout
    stamped = sync_vendor.stamp("VALID_ACTIONS = ['BUY', 'SELL']\n", meta)
    assert "=== ORIGIN ===" in stamped
    assert meta["commit"] in stamped
    assert "AGPL-3.0" in stamped


def test_sync_dry_run_writes_nothing(layout):
    mirror, vendor, files_yaml, meta = layout
    changed = sync_vendor.sync(files_yaml, mirror, vendor, meta, apply=False)
    assert changed == ["order_validator.py"]
    assert not (vendor / "order_validator.py").exists()


def test_sync_apply_copies_and_stamps(layout):
    mirror, vendor, files_yaml, meta = layout
    sync_vendor.sync(files_yaml, mirror, vendor, meta, apply=True)
    out = (vendor / "order_validator.py").read_text(encoding="utf-8")
    assert "=== ORIGIN ===" in out and "VALID_ACTIONS" in out
    assert (vendor / "ORIGIN.md").exists()


def test_sync_skips_unlisted_files(layout):
    mirror, vendor, files_yaml, meta = layout
    sync_vendor.sync(files_yaml, mirror, vendor, meta, apply=True)
    assert not (vendor / "skip.py").exists()


def test_sync_no_marker_for_json(layout):
    mirror, vendor, files_yaml, meta = layout
    (mirror / "src" / "plugin.json").write_text('{"name": "dhan"}\n', encoding="utf-8")
    files_yaml.write_text(
        "files:\n"
        "  - src: src/order.py\n"
        "    dest: order_validator.py\n"
        "  - src: src/plugin.json\n"
        "    dest: plugin.json\n"
        "    marker: false\n",
        encoding="utf-8",
    )
    changed = sync_vendor.sync(files_yaml, mirror, vendor, meta, apply=True)
    assert changed == ["order_validator.py", "plugin.json"]
    json_out = (vendor / "plugin.json").read_text(encoding="utf-8")
    assert json_out == '{"name": "dhan"}\n'
    assert "=== ORIGIN ===" not in json_out
    py_out = (vendor / "order_validator.py").read_text(encoding="utf-8")
    assert "=== ORIGIN ===" in py_out
    manifest = (vendor / "ORIGIN.md").read_text(encoding="utf-8")
    assert "plugin.json" in manifest
