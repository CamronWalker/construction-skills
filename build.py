#!/usr/bin/env python3
"""
Build plugin zips for internal team distribution.

Produces src/{plugin}.zip for each plugin category. Excludes __pycache__,
node_modules, .DS_Store, Thumbs.db, and any .pyc files.

Usage:
    python build.py                # build all plugins
    python build.py scheduling     # build one plugin
"""

from __future__ import annotations

import json
import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC_DIR = ROOT / "src"

PLUGINS = ["westland", "scheduling", "estimating", "project-management", "site-operations", "safety"]

# Claude Code rejects plugin installs whose description exceeds 500 chars.
# Validated for both the plugin's own plugin.json and its entry in the
# repo-root marketplace.json before any zip is built.
DESCRIPTION_MAX_LEN = 500

EXCLUDE_DIRS = {
    "__pycache__",
    "node_modules",
    ".git",
    "test-results",      # Playwright test artifacts (gitignored, debug only)
    "playwright-report",
}
EXCLUDE_FILES = {".DS_Store", "Thumbs.db"}
EXCLUDE_SUFFIXES = {".pyc", ".pyo"}
EXCLUDE_DIR_SUFFIXES = ("-workspace",)


def should_skip(path: Path) -> bool:
    parts = path.parts
    if any(p in EXCLUDE_DIRS for p in parts):
        return True
    if any(p.endswith(EXCLUDE_DIR_SUFFIXES) for p in parts):
        return True
    if path.name in EXCLUDE_FILES:
        return True
    if path.suffix in EXCLUDE_SUFFIXES:
        return True
    return False


def _check_description(label: str, description: str) -> str | None:
    """Return an error message if `description` exceeds the limit, else None."""
    n = len(description)
    if n > DESCRIPTION_MAX_LEN:
        return f"{label}: description is {n} chars (max {DESCRIPTION_MAX_LEN}, over by {n - DESCRIPTION_MAX_LEN})"
    return None


def validate_descriptions(targets: list[str]) -> list[str]:
    """Validate plugin.json + matching marketplace.json descriptions for each
    target plugin. Returns a list of human-readable violation messages."""
    errors: list[str] = []

    marketplace_path = ROOT / ".claude-plugin" / "marketplace.json"
    marketplace_entries: dict[str, dict] = {}
    if marketplace_path.exists():
        marketplace = json.loads(marketplace_path.read_text(encoding="utf-8"))
        marketplace_entries = {p["name"]: p for p in marketplace.get("plugins", [])}

    for name in targets:
        if name not in PLUGINS:
            continue
        manifest_path = ROOT / name / ".claude-plugin" / "plugin.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            err = _check_description(
                f"{name}/.claude-plugin/plugin.json",
                manifest.get("description", ""),
            )
            if err:
                errors.append(err)
        entry = marketplace_entries.get(name)
        if entry is not None:
            err = _check_description(
                f".claude-plugin/marketplace.json[{name}]",
                entry.get("description", ""),
            )
            if err:
                errors.append(err)

    return errors


def read_version(plugin_dir: Path) -> str:
    manifest = plugin_dir / ".claude-plugin" / "plugin.json"
    if not manifest.exists():
        return "unknown"
    return json.loads(manifest.read_text(encoding="utf-8")).get("version", "unknown")


def build_plugin(plugin: str) -> Path:
    plugin_dir = ROOT / plugin
    if not plugin_dir.is_dir():
        raise SystemExit(f"Plugin directory not found: {plugin_dir}")

    manifest = plugin_dir / ".claude-plugin" / "plugin.json"
    if not manifest.exists():
        raise SystemExit(f"Missing manifest: {manifest}")

    SRC_DIR.mkdir(exist_ok=True)
    version = read_version(plugin_dir)
    zip_path = SRC_DIR / f"{plugin}.zip"

    file_count = 0
    total_bytes = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(plugin_dir.rglob("*")):
            rel = path.relative_to(ROOT)
            if should_skip(rel):
                continue
            if path.is_file():
                zf.write(path, rel.as_posix())
                file_count += 1
                total_bytes += path.stat().st_size

    size_kb = zip_path.stat().st_size / 1024
    print(f"  {plugin} v{version} -> src/{plugin}.zip ({file_count} files, {size_kb:.1f} KB)")
    return zip_path


def main() -> int:
    targets = sys.argv[1:] if len(sys.argv) > 1 else PLUGINS

    errors = validate_descriptions(targets)
    if errors:
        print(f"Description length check failed (max {DESCRIPTION_MAX_LEN} chars):", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        print("Trim the offending descriptions before building.", file=sys.stderr)
        return 1

    print("Building plugin zips...")
    for name in targets:
        if name not in PLUGINS:
            print(f"  SKIP: unknown plugin '{name}' (known: {', '.join(PLUGINS)})")
            continue
        build_plugin(name)
    print("Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
