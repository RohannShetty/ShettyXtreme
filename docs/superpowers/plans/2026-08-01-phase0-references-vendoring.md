# Phase 0: References + Vendoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the reference-repo library and the OpenAlgo vendoring pipeline that every later phase of the ShettyXtreme v2 upgrade depends on.

**Architecture:** Two gitignored zones — `references/` holds raw clones of all reference repos (scratch, bulk) while durable knowledge lives as tracked briefs under `docs/references/`. `vendor/openalgo/` is a tracked, curated subset of OpenAlgo execution-plumbing code, stamped with origin markers and synced by `scripts/sync_vendor.py` from the gitignored upstream mirror. The July-12 v1 architecture docs are archived so v2 can be written without contradictions.

**Tech Stack:** git (shallow clones), Python 3.11+ (pytest, PyYAML — already in pyproject), markdown.

## Global Constraints

- **No `import openalgo` / `from openalgo` anywhere under `src/`** (CI gate: `grep -r "import openalgo\|from openalgo" src/` → zero matches)
- **`references/` is gitignored** — never tracked. Durable briefs live in **`docs/references/`** (tracked).
- **`vendor/` is tracked** — vendored files carry an origin marker header (source URL, commit, date, license) and are listed in `vendor/openalgo/ORIGIN.md`
- **License**: OpenAlgo is **AGPL-3.0**; vendored files are private-use absorption (confirmed decision: private use only). `vendor/openalgo/README.md` must state this. ShettyXtreme stays Proprietary (see repo LICENSE).
- **Sync source is the fresh upstream mirror only** (`references/upstream/openalgo` from `marketcalls/openalgo`) — never `D:\OpenAlgo` (that directory is a contaminated working copy containing the user's own strategy scripts).
- Python >=3.11; tests run with `pytest`; every code task is TDD (test first, verify fail, implement, verify pass).
- Working branch: `phase0-references-vendoring` (never commit directly to master).
- Commit style: frequent, scoped commits (`chore:`, `feat:`, `docs:`) matching repo history.

---

### Task 1: Reference repo clones + STATUS.md + .gitignore

**Files:**
- Create: `references/` (9 shallow clones, gitignored), `docs/references/STATUS.md` (tracked)
- Modify: `.gitignore` (add `references/`)

**Interfaces:**
- Produces: clone roots consumed by Task 2 (`references/upstream/openalgo`, `references/awesome-design-md`, …) and Task 3 (mirror at `references/upstream/openalgo`)

- [ ] **Step 1: Create the branch**

Run: `git checkout -b phase0-references-vendoring`
Expected: on branch `phase0-references-vendoring`

- [ ] **Step 2: Clone the 4 new reference repos (shallow, depth 1)**

```bash
git clone --depth 1 https://github.com/VoltAgent/awesome-design-md references/awesome-design-md
git clone --depth 1 https://github.com/virattt/ai-hedge-fund references/ai-hedge-fund
git clone --depth 1 https://github.com/anthropics/financial-services references/anthropics-financial-services
git clone --depth 1 https://github.com/cybergeekgyan/Quant-Developers-Resources references/quant-developers-resources
```

Expected: each clone dir exists with a `.git` and a README. If a repo is unreachable, record it in STATUS.md as FAILED and continue (do not block).

- [ ] **Step 3: Clone upstream mirrors (shallow, depth 1)**

```bash
git clone --depth 1 https://github.com/marketcalls/openalgo references/upstream/openalgo
git clone --depth 1 https://github.com/dhan-oss/DhanHQ-py references/upstream/dhanhq-py
git clone --depth 1 https://github.com/Fincept-Corporation/FinceptTerminal references/upstream/fincept-terminal
git clone --depth 1 https://github.com/RohannShetty/ShettyBot_V1_Core references/upstream/shettybot-v1
git clone --depth 1 https://github.com/RohannShetty/FinceptTerminal references/upstream/fincept-fork
```

Expected: 5 clone dirs. FinceptTerminal is large — if the clone times out, retry with `--filter=blob:none`; record method in STATUS.md.

- [ ] **Step 4: Add `references/` to .gitignore**

Append to `.gitignore`:

```
# Reference repo clones (scratch — durable briefs live in docs/references/)
references/
```

Verify: `git status` shows no `references/` entries (untracked or ignored), and `git check-ignore references/upstream/openalgo` prints the path.

- [ ] **Step 5: Write `docs/references/STATUS.md`**

Record for each repo: URL, shallow/deep, commit hash (`git -C <dir> rev-parse HEAD`), clone date, notes. Notes must include: (a) `D:\OpenAlgo` is the user's working copy (openalgoUI v2.0.1.4) contaminated with personal scripts — NOT a sync source; (b) local `D:\DhanHQ-py-2.2.0` is the SDK under review; (c) `D:\ShettyBot_V1_Core` + worktrees exist locally as the prior-version source. Template:

```markdown
# Reference Repo Status

| Repo | Location | Commit | Date | Notes |
|------|----------|--------|------|-------|
| awesome-design-md | references/awesome-design-md | `<hash>` | 2026-08-01 | 4 new ref; DESIGN.md format source |
```

- [ ] **Step 6: Verify + commit**

Run: `git status` (only `.gitignore` + `docs/references/STATUS.md` new)
Commit: `git add .gitignore docs/references/STATUS.md && git commit -m "chore: phase0 references scaffold + STATUS.md"`

---

### Task 2: Reference briefs (parallel exploration agents)

**Files:**
- Create (all tracked): `docs/references/BRIEF-awesome-design-md.md`, `BRIEF-ai-hedge-fund.md`, `BRIEF-anthropics-financial-services.md`, `BRIEF-quant-developers-resources.md`, `BRIEF-openalgo-upstream.md`, `BRIEF-dhanhq-upstream.md`, `BRIEF-fincept.md`

**Interfaces:**
- Consumes: Task 1 clones
- Produces: `BRIEF-openalgo-upstream.md` must contain a **vendoring candidates table** (source path in OpenAlgo repo → proposed `vendor/openalgo/` destination → why) — consumed by Task 3's FILES.yaml. `BRIEF-awesome-design-md.md` must contain the DESIGN.md format spec (9 sections from the Stitch spec) — consumed by Phase 1's DESIGN.md authoring.

- [ ] **Step 1: Dispatch 7 explore subagents in parallel** (one message, 7 `task` calls, subagent_type `explore`)

Each agent: read-only research over its assigned clone, write `docs/references/BRIEF-<name>.md`, report one-line summary. Each brief must cover: what the repo is best used for in our architecture, what to inherit (ideas/patterns, not code), what NOT to copy, license, coupling risk, and any Indian-market-specific value. Agent assignments:

1. `awesome-design-md` → DESIGN.md format spec (9 sections: theme, palette+tokens, typography, components, layout, elevation, do's/don'ts, responsive, agent prompt guide) + 3 candidate style references for a dark data-dense trading terminal + recommendation
2. `ai-hedge-fund` → agent roles & orchestration patterns, evaluation/backtest methodology, what belongs in the Phase-3 research workspace (AI research layer decision: research-only, never order-gating)
3. `anthropics-financial-services` → risk/control patterns, human-in-the-loop approval flows, multi-agent guardrails, tool-use discipline
4. `quant-developers-resources` → categorized resource checklist vs our feature map (market terminal, scanners, research, signals, options, execution, risk, learning); flag high-value Indian-market libs
5. `openalgo` (mirror at `references/upstream/openalgo`) → version + recent upstream changes vs `D:\OpenAlgo` (v2.0.1.4); file map of broker adapters/order validation/Dhan adapter; **vendoring candidates table with exact source paths**; confirm AGPL
6. `dhanhq-py` (mirror at `references/upstream/dhanhq-py`) → latest upstream vs local `D:\DhanHQ-py-2.2.0`: version delta, auth/token changes, feed protocol changes, anything affecting our single-primary+fallback credential model
7. `fincept-terminal` + `fincept-fork` → breadth catalog (analytics categories), options/derivatives features worth pattern-inheriting, confirmation of AGPL no-copy boundary

Each agent prompt must include: exact repo path, exact output file path, the instruction to write the file (fallback: return full markdown if write tools unavailable), 300–500 lines max, no code dumps.

- [ ] **Step 2: Verify briefs exist + commit**

Run: `Get-ChildItem docs/references` → 8 files present (STATUS + 7 briefs)
Commit: `git add docs/references && git commit -m "docs: reference briefs from parallel exploration"`

---

### Task 3: Vendoring pipeline (`vendor/openalgo/` + `scripts/sync_vendor.py`)

**Files:**
- Create: `scripts/sync_vendor.py`, `vendor/openalgo/FILES.yaml`, `vendor/openalgo/README.md`, `tests/vendor/test_sync_vendor.py`, `vendor/openalgo/ORIGIN.md` (generated by the script)
- Modify: nothing else in `src/`

**Interfaces:**
- Consumes: mirror at `references/upstream/openalgo`; `BRIEF-openalgo-upstream.md` (vendoring candidates table)
- Produces: `sync_vendor.main(argv)` callable from CLI; module functions `load_file_list(path)`, `collect_sources(file_list, mirror) -> list[(src, dest)]`, `stamp(content, meta) -> str`, `sync(files_yaml, mirror, vendor_dir, meta, apply) -> list[str]` (changed relpaths), `git_meta(mirror) -> dict{commit, url, date}`. Tested via `tests/vendor/test_sync_vendor.py`.

- [ ] **Step 1: Write the failing tests** (`tests/vendor/test_sync_vendor.py`)

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/vendor/test_sync_vendor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sync_vendor'`

- [ ] **Step 3: Implement `scripts/sync_vendor.py`**

```python
"""Sync vendored OpenAlgo files from the upstream mirror into vendor/openalgo/.

Reads vendor/openalgo/FILES.yaml, copies each listed source file from the
mirror (references/upstream/openalgo) into vendor/openalgo/, stamps an origin
marker header (source commit, date, license) on every copied file, and writes
vendor/openalgo/ORIGIN.md manifest.

Usage:
    python scripts/sync_vendor.py            # dry-run: list what would change
    python scripts/sync_vendor.py --apply    # copy + stamp + manifest
"""
from __future__ import annotations

import argparse
import hashlib
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
FILES_YAML = ROOT / "vendor" / "openalgo" / "FILES.yaml"
VENDOR_DIR = ROOT / "vendor" / "openalgo"
MIRROR = ROOT / "references" / "upstream" / "openalgo"
MANIFEST = VENDOR_DIR / "ORIGIN.md"

MARKER = (
    "# === ORIGIN ===\n"
    "# Source: {url}@{commit}\n"
    "# Vendored: {date} by scripts/sync_vendor.py\n"
    "# License: AGPL-3.0 (private-use absorption; see vendor/openalgo/README.md)\n"
    "# Do not edit directly — re-run sync_vendor.py after reviewing upstream diff.\n"
    "# === END ORIGIN ===\n"
)


def load_file_list(files_yaml: Path) -> list[dict]:
    if not files_yaml.exists():
        raise FileNotFoundError(f"Missing {files_yaml}")
    data = yaml.safe_load(files_yaml.read_text(encoding="utf-8"))
    return data.get("files", [])


def collect_sources(file_list: list[dict], mirror: Path) -> list[tuple[Path, Path]]:
    sources: list[tuple[Path, Path]] = []
    for entry in file_list:
        src = mirror / entry["src"]
        if not src.exists():
            print(f"SKIP (missing in mirror): {entry['src']}", file=sys.stderr)
            continue
        sources.append((src, VENDOR_DIR / entry["dest"]))
    return sources


def stamp(content: str, meta: dict) -> str:
    return MARKER.format(**meta) + content


def git_meta(mirror: Path) -> dict:
    commit = subprocess.run(
        ["git", "-C", str(mirror), "rev-parse", "HEAD"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    url = subprocess.run(
        ["git", "-C", str(mirror), "config", "--get", "remote.origin.url"],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return {
        "commit": commit,
        "url": url,
        "date": datetime.now(UTC).date().isoformat(),
    }


def sync(files_yaml: Path, mirror: Path, vendor_dir: Path, meta: dict, apply: bool) -> list[str]:
    changed: list[str] = []
    for src, dest in collect_sources(load_file_list(files_yaml), mirror):
        content = src.read_text(encoding="utf-8")
        if "=== ORIGIN ===" in content.splitlines()[0:6]:
            content = "\n".join(content.splitlines()[6:]).lstrip("\n")
        stamped = stamp(content, meta)
        if apply:
            dest.write_text(stamped, encoding="utf-8")
        changed.append(dest.name)
    if apply:
        rows = ["| File | Source | Commit | Date |"]
        rows.append("|---|---|---|---|")
        for src, dest in collect_sources(load_file_list(files_yaml), mirror):
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()[:12] if dest.exists() else "-"
            rows.append(f"| {dest.name} | `{src.relative_to(mirror)}` | {meta['commit'][:8]} | {meta['date']} | `{digest}` |")
        (vendor_dir / "ORIGIN.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return changed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync vendored OpenAlgo files.")
    parser.add_argument("--apply", action="store_true", help="copy + stamp (default: dry-run)")
    parser.add_argument("--mirror", type=Path, default=MIRROR, help="upstream mirror path")
    parser.add_argument("--files-yaml", type=Path, default=FILES_YAML, help="file list")
    parser.add_argument("--vendor-dir", type=Path, default=VENDOR_DIR, help="destination")
    args = parser.parse_args(argv)
    if not args.mirror.exists():
        print(f"Mirror not found: {args.mirror} (run Task 1 clones first)", file=sys.stderr)
        return 1
    meta = git_meta(args.mirror)
    changed = sync(args.files_yaml, args.mirror, args.vendor_dir, meta, apply=args.apply)
    verb = "SYNCED" if args.apply else "WOULD SYNC"
    for name in changed:
        print(f"{verb}: {name}")
    print(f"Commit: {meta['commit'][:8]} | {meta['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/vendor/test_sync_vendor.py -v`
Expected: 7 PASS

- [ ] **Step 5: Write `vendor/openalgo/FILES.yaml` from the Task 2 brief**

Populate from `docs/references/BRIEF-openalgo-upstream.md` vendoring-candidates table — seed with the 3 mandated candidates from the architecture decision (order validation constants, Dhan order mapping, broker adapter pattern files) using exact source paths reported by the brief. Template:

```yaml
# Vendored files from marketcalls/openalgo (AGPL-3.0, private-use absorption)
# Sources are relative to references/upstream/openalgo/
files:
  - src: <exact path from brief>
    dest: <destination filename>
```

- [ ] **Step 6: Write `vendor/openalgo/README.md`**

Contents: purpose (curated execution-plumbing subset, private-use AGPL absorption), license statement (AGPL-3.0, ShettyXtreme remains Proprietary — private use only), sync workflow (review upstream diff → update FILES.yaml → `python scripts/sync_vendor.py --apply` → run tests), explicit rule: **never `import openalgo` in `src/`** — vendored files implement `core/interfaces` protocols only.

- [ ] **Step 7: Dry-run against real mirror + commit**

Run: `python scripts/sync_vendor.py` (expect: WOULD SYNC lines for each FILES.yaml entry)
Run: `python scripts/sync_vendor.py --apply` (expect: SYNCED lines + ORIGIN.md written)
Run: `python -m pytest tests/ -q` → all pass (no regressions)
Run: `grep -rn "import openalgo" src/` → zero matches
Commit: `git add scripts/sync_vendor.py vendor/ tests/vendor && git commit -m "feat: vendoring pipeline for OpenAlgo execution plumbing"`

---

### Task 4: Archive v1 architecture docs + branch commit

**Files:**
- Move: `docs/architecture/ARCHITECTURE.md`, `docs/architecture/ARCHITECTURE_RESET.md`, `docs/architecture/sections/` → `docs/architecture/v1/`
- Create: `docs/architecture/README.md` (pointer: v1 archived 2026-08-01, v2 in progress — Phase 1)

**Interfaces:**
- Produces: clean `docs/architecture/` root for the Phase 1 blueprint v2 rewrite; `docs/decisions/ADR-001` stays put (still valid)

- [ ] **Step 1: Move v1 docs**

```bash
git mv docs/architecture/ARCHITECTURE.md docs/architecture/v1/ARCHITECTURE.md
git mv docs/architecture/ARCHITECTURE_RESET.md docs/architecture/v1/ARCHITECTURE_RESET.md
git mv docs/architecture/sections docs/architecture/v1/sections
```

Expected: `docs/architecture/v1/` holds all three.

- [ ] **Step 2: Write `docs/architecture/README.md`**

```markdown
# Architecture Docs

- `v1/` — July-12 2026 blueprint + architecture reset (archived 2026-08-01; superseded decisions: OpenAlgo absorb-only → vendoring; dual credentials → single-primary + fallback)
- Phase 1 will write the v2 blueprint here.
```

- [ ] **Step 3: Full-suite verify + final commit**

Run: `python -m pytest tests/ -q` → all pass
Run: `git log --oneline -5` → phase0 commits present
Commit: `git add docs/architecture && git commit -m "docs: archive v1 architecture docs for v2 rewrite"`
Run: `git status` → clean (except pre-existing unrelated dirty file)

---

## Self-Review Checklist (controller)

1. **Spec coverage** — every decision from the interview mapped: vendoring (T3), references download (T1), briefs (T2), v1 archive (T4), AGPL notes (T3 S6), single-credential/806 and all other decisions belong to Phase 1 blueprint, correctly out of scope here.
2. **Placeholder scan** — the only intentional variable is FILES.yaml content, resolved by T3 S5 from the Task 2 brief; no TBDs elsewhere.
3. **Type consistency** — `sync_vendor` module functions and signatures in the tests match the implementation (`load_file_list`, `collect_sources`, `stamp`, `sync`, `git_meta`); test asserts `changed == ["order_validator.py"]` match the dest naming in the fixture.
