"""Import-boundary enforcement test — walks src/ and asserts layer rules.

Fulfils the ARCHITECTURE_V2.md §05/07 promise: "a dedicated test that walks
src/ imports" and "CI walks src/ and fails on forbidden imports".

Run with:
    pytest tests/core/test_import_boundaries.py -v

Rules enforced (from docs/architecture/v2/sections/05-system-boundaries.md):
  - No `import openalgo` / `from openalgo` anywhere in src/
  - core/ imports only stdlib + own subpackages (known yaml violation allowed)
  - knowledge/ imports only core + stdlib
  - integration/ never imports intelligence/execution/terminal
  - intelligence/ never imports learning/execution/terminal/integration
  - No file > 1000 lines
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_SRC = Path(__file__).resolve().parents[2] / "src" / "shettyxtreme"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _walk_python_files(root: Path) -> list[Path]:
    """Return all .py files under root, skipping __pycache__."""
    return [
        p for p in root.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def _extract_imports(filepath: Path) -> list[tuple[str, int]]:
    """Return (module_path, level) tuples for all imports in a .py file.

    level=0 means absolute import; level>0 means relative import.
    For relative imports, module is the relative part (may be None for
    ``from . import X``).
    """
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    except SyntaxError:
        return []
    results: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                results.append((alias.name, 0))
        elif isinstance(node, ast.ImportFrom):
            level = node.level or 0
            module = node.module or ""
            results.append((module, level))
    return results


def _layer_of(filepath: Path) -> str | None:
    """Return the layer name (relative to src/) for a file, or None."""
    try:
        rel = filepath.relative_to(_SRC)
    except ValueError:
        return None
    parts = rel.parts
    if not parts:
        return None
    return parts[0]


# ---------------------------------------------------------------------------
# D1 — no openalgo anywhere in src/
# ---------------------------------------------------------------------------

def test_no_openalgo_imports_in_src() -> None:
    """D1: No `import openalgo` or `from openalgo` anywhere in src/."""
    violations: list[str] = []
    for f in _walk_python_files(_SRC):
        for mod, level in _extract_imports(f):
            if level == 0 and (mod == "openalgo" or mod.startswith("openalgo.")):
                violations.append(f"{f}: imports {mod}")
    assert not violations, "openalgo imports found in src/:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# A — core/ imports only stdlib + own subpackages
# ---------------------------------------------------------------------------

_STDLIB_TOP_LEVELS = {
    "__future__", "abc", "ast", "asyncio", "bisect", "calendar", "collections",
    "contextlib", "copy", "csv", "dataclasses", "datetime", "decimal", "enum",
    "errno", "functools", "gc", "glob", "gzip", "hashlib", "heapq", "hmac",
    "html", "http", "inspect", "io", "itertools", "json", "logging", "math",
    "mimetypes", "operator", "os", "pathlib", "pickle", "posixpath", "pprint",
    "queue", "random", "re", "secrets", "shutil", "signal", "socket", "sqlite3",
    "ssl", "statistics", "string", "struct", "subprocess", "sys", "tempfile",
    "textwrap", "threading", "time", "timeit", "token", "traceback", "typing",
    "unittest", "urllib", "uuid", "warnings", "weakref", "xml", "zipfile",
    "zoneinfo", "_thread",
}

# Known pre-existing violations (allowed until fixed)
_KNOWN_VIOLATIONS = {
    # core/config/config_manager.py imports yaml (documented in AGENTS.md)
    ("core/config/config_manager.py", "yaml"),
    # core/storage/time_series_store.py imports duckdb (documented in AGENTS.md)
    ("core/storage/time_series_store.py", "duckdb"),
    # intelligence/risk/portfolio_risk.py lazy-imports integration/fyers/symbols
    ("intelligence/risk/portfolio_risk.py", "shettyxtreme.integration.fyers.symbols"),
}


def _is_relative_import(level: int) -> bool:
    """True if this is a relative import (from . import ...)."""
    return level > 0


def test_core_imports_only_stdlib_and_self() -> None:
    """A: core/ imports only stdlib + own subpackages (+ known yaml violation)."""
    violations: list[str] = []
    core_dir = _SRC / "core"
    if not core_dir.exists():
        pytest.skip("core/ not found")
    for f in _walk_python_files(core_dir):
        rel = f.relative_to(_SRC).as_posix()
        for mod, level in _extract_imports(f):
            # Relative imports within core/ are fine
            if _is_relative_import(level):
                continue
            top = mod.split(".")[0]
            if top in _STDLIB_TOP_LEVELS:
                continue
            if top == "shettyxtreme":
                parts = mod.split(".")
                if len(parts) >= 2 and parts[1] == "core":
                    continue
                violations.append(f"{rel}: imports {mod} (not core/)")
                continue
            # Known violation
            if (rel, top) in _KNOWN_VIOLATIONS or (rel, mod) in _KNOWN_VIOLATIONS:
                continue
            violations.append(f"{rel}: imports {mod}")
    assert not violations, "core/ boundary violations:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# G — knowledge/ imports only core + stdlib
# ---------------------------------------------------------------------------

def test_knowledge_imports_only_core_and_stdlib() -> None:
    """G: knowledge/ imports only core + stdlib."""
    violations: list[str] = []
    knowledge_dir = _SRC / "knowledge"
    if not knowledge_dir.exists():
        pytest.skip("knowledge/ not found")
    for f in _walk_python_files(knowledge_dir):
        rel = f.relative_to(_SRC).as_posix()
        for mod, level in _extract_imports(f):
            if _is_relative_import(level):
                continue
            top = mod.split(".")[0]
            if top in _STDLIB_TOP_LEVELS:
                continue
            if top == "shettyxtreme":
                parts = mod.split(".")
                if len(parts) >= 2 and parts[1] == "core":
                    continue
                violations.append(f"{rel}: imports {mod}")
                continue
            # pydantic is allowed (documented)
            if top == "pydantic":
                continue
            violations.append(f"{rel}: imports {mod}")
    assert not violations, "knowledge/ boundary violations:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# B — integration/ never imports intelligence/execution/terminal
# ---------------------------------------------------------------------------

_INTEGRATION_FORBIDDEN_LAYERS = {"intelligence", "execution", "terminal"}


def test_integration_no_upward_imports() -> None:
    """B: integration/ never imports intelligence/execution/terminal."""
    violations: list[str] = []
    integration_dir = _SRC / "integration"
    if not integration_dir.exists():
        pytest.skip("integration/ not found")
    for f in _walk_python_files(integration_dir):
        rel = f.relative_to(_SRC).as_posix()
        for mod, level in _extract_imports(f):
            if _is_relative_import(level):
                continue
            top = mod.split(".")[0]
            if top == "shettyxtreme":
                parts = mod.split(".")
                if len(parts) >= 2 and parts[1] in _INTEGRATION_FORBIDDEN_LAYERS:
                    violations.append(f"{rel}: imports {mod}")
    assert not violations, "integration/ upward imports:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# C — intelligence/ never imports learning/execution/terminal/integration
# ---------------------------------------------------------------------------

_INTELLIGENCE_FORBIDDEN_LAYERS = {"learning", "execution", "terminal", "integration"}


def test_intelligence_no_upward_imports() -> None:
    """C: intelligence/ never imports learning/execution/terminal/integration."""
    violations: list[str] = []
    intel_dir = _SRC / "intelligence"
    if not intel_dir.exists():
        pytest.skip("intelligence/ not found")
    for f in _walk_python_files(intel_dir):
        rel = f.relative_to(_SRC).as_posix()
        for mod, level in _extract_imports(f):
            if _is_relative_import(level):
                continue
            top = mod.split(".")[0]
            if top == "shettyxtreme":
                parts = mod.split(".")
                if len(parts) >= 2 and parts[1] in _INTELLIGENCE_FORBIDDEN_LAYERS:
                    # Check known violations
                    if (rel, mod) in _KNOWN_VIOLATIONS:
                        continue
                    violations.append(f"{rel}: imports {mod}")
    assert not violations, "intelligence/ upward imports:\n" + "\n".join(violations)


# ---------------------------------------------------------------------------
# File-size guard — no file > 1000 lines
# ---------------------------------------------------------------------------

_MAX_LINES = 1000


def test_no_file_exceeds_1000_lines() -> None:
    """No source file in src/ exceeds 1000 lines."""
    violations: list[str] = []
    for f in _walk_python_files(_SRC):
        try:
            line_count = len(f.read_text(encoding="utf-8").splitlines())
        except Exception:
            continue
        if line_count > _MAX_LINES:
            rel = f.relative_to(_SRC).as_posix()
            violations.append(f"{rel}: {line_count} lines")
    assert not violations, "Files exceeding 1000 lines:\n" + "\n".join(violations)
