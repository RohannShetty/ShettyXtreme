"""Sync vendored OpenAlgo files from the upstream mirror into vendor/openalgo/.

Reads vendor/openalgo/FILES.yaml, copies each listed source file from the
mirror (references/upstream/openalgo) into vendor/openalgo/, stamps an origin
marker header (source commit, date, license) on every copied file, and writes
vendor/openalgo/ORIGIN.md manifest.

Files whose FILES.yaml entry sets ``marker: false`` (e.g. plugin.json) are
copied and listed in ORIGIN.md but get NO origin header, since a ``#``
comment would corrupt their format.

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
    "# Do not edit directly - re-run sync_vendor.py after reviewing upstream diff.\n"
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
        dest = Path(entry["dest"])
        if dest.is_absolute():
            raise ValueError(f"dest must be relative: {entry['dest']}")
        if ".." in dest.parts:
            raise ValueError(f"dest must not contain '..': {entry['dest']}")
        src = mirror / entry["src"]
        if not src.exists():
            print(f"SKIP (missing in mirror): {entry['src']}", file=sys.stderr)
            continue
        sources.append((src, dest))
    return sources


def stamp(content: str, meta: dict) -> str:
    content = content.rstrip("\n") + "\n"
    return MARKER.format(**meta) + content


def destamp(content: str, meta: dict) -> str:
    """Strip a previously written origin marker, byte-exact when possible.

    The happy path strips the exact runtime-formatted marker; a file stamped
    with an older commit/date falls back to anchoring on the stable END
    marker line, so leading real-content comment lines are preserved. Files
    without the END marker in the first six lines are left untouched.
    """
    expected = MARKER.format(**meta)
    if content.startswith(expected):
        return content[len(expected):]
    if "# === END ORIGIN ===\n" in content.splitlines(keepends=True)[:6]:
        return content.split("# === END ORIGIN ===\n", 1)[1]
    return content


def git_meta(mirror: Path) -> dict:
    try:
        commit = subprocess.run(
            ["git", "-C", str(mirror), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        url = subprocess.run(
            ["git", "-C", str(mirror), "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        print(f"git_meta failed: {exc.stderr.strip() or exc}", file=sys.stderr)
        raise SystemExit(1)
    return {
        "commit": commit,
        "url": url,
        "date": datetime.now(UTC).date().isoformat(),
    }


def sync(files_yaml: Path, mirror: Path, vendor_dir: Path, meta: dict, apply: bool) -> list[str]:
    entries = load_file_list(files_yaml)
    marker_flags = {e["src"]: e.get("marker", True) for e in entries}
    changed: list[str] = []
    for src, dest_rel in collect_sources(entries, mirror):
        content = src.read_text(encoding="utf-8")
        content = destamp(content, meta)
        if marker_flags.get(src.relative_to(mirror).as_posix(), True):
            content = stamp(content, meta)
        dest = vendor_dir / dest_rel
        if apply:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(content, encoding="utf-8")
        changed.append(dest_rel.name)
    if apply:
        rows = ["| File | Source | Commit | Date | Digest |"]
        rows.append("|---|---|---|---|---|")
        for src, dest_rel in collect_sources(entries, mirror):
            dest = vendor_dir / dest_rel
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()[:12] if dest.exists() else "-"
            rows.append(
                f"| {dest_rel.as_posix()} | `{src.relative_to(mirror).as_posix()}` | {meta['commit'][:8]} | {meta['date']} | `{digest}` |"
            )
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
