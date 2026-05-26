"""Diagnostic for the Westland Scheduler Local MCP.

Runs four checks and prints a single result table:

  1. `mcp` Python SDK is importable.
  2. The scheduling plugin manifest declares the `westland-scheduler-mcp`
     server entry under `mcpServers`.
  3. The MCP server module boots and registers its tool surface — at minimum
     `ping`, plus a representative tool from each of the F1-F5 batches.
  4. The bundled fixture XER (`tests/fixtures/minimal.xer`) parses cleanly.

Each check resolves to one of three states:

  pass  — green; nothing to do.
  fail  — red;   includes a copy-pasteable fix.
  warn  — yellow; partial answer (e.g. server boots but a batch tool is
                  missing — actionable but not blocking everything).

Exits 0 when all checks pass, 1 when any check fails. Designed to be
invoked from the troubleshoot skill via `python diagnose.py`; safe to
run standalone too.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
import sys
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional


# Anchor everything to this file's location so the script is path-portable
# (works whether the user invokes it from the worktree, the installed
# plugin cache, or a clone).
HERE = Path(__file__).resolve().parent
PLUGIN_ROOT = HERE.parent.parent  # .../scheduling/
MCP_SERVER_DIR = PLUGIN_ROOT / "mcp-server"
MANIFEST = PLUGIN_ROOT / ".claude-plugin" / "plugin.json"
FIXTURE_XER = MCP_SERVER_DIR / "tests" / "fixtures" / "minimal.xer"

# One representative tool per Tier 0 batch — if any of these is missing from
# the live server, something has drifted between the registration code and
# the deployed plugin.
REPRESENTATIVE_TOOLS = [
    "ping",                       # smoke
    "get_milestones",             # E (structure)
    "get_critical_path",          # F1 (cpm_path)
    "get_quality_check",          # F2 (quality)
    "get_activities_to_start",    # F3 (update_review)
    "compare_activity_changes",   # F4 (compare)
    "score_schedule",             # F5 (omnibus)
]


@dataclass
class CheckResult:
    name: str
    status: str  # "pass" | "fail" | "warn"
    message: str
    fix: Optional[str] = None
    details: list = field(default_factory=list)


def _check_mcp_sdk() -> CheckResult:
    if importlib.util.find_spec("mcp") is None:
        return CheckResult(
            name="MCP Python SDK installed",
            status="fail",
            message="The `mcp` package is not importable from this Python interpreter.",
            fix=f"{sys.executable} -m pip install -r \"{MCP_SERVER_DIR / 'requirements.txt'}\"",
        )
    try:
        importlib.import_module("mcp.server")
    except Exception as exc:
        return CheckResult(
            name="MCP Python SDK installed",
            status="fail",
            message=f"`mcp` is present but `mcp.server` failed to import: {exc!r}",
            fix=(
                f"{sys.executable} -m pip install --upgrade "
                f"-r \"{MCP_SERVER_DIR / 'requirements.txt'}\""
            ),
        )
    return CheckResult(
        name="MCP Python SDK installed",
        status="pass",
        message=f"Importable from {sys.executable}.",
    )


def _check_manifest() -> CheckResult:
    if not MANIFEST.is_file():
        return CheckResult(
            name="Plugin manifest declares the MCP server",
            status="fail",
            message=f"Plugin manifest not found at {MANIFEST}.",
            fix=(
                "The scheduling plugin is not installed at the expected "
                "location. Reinstall via the marketplace or your enterprise "
                "distribution."
            ),
        )
    try:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return CheckResult(
            name="Plugin manifest declares the MCP server",
            status="fail",
            message=f"Plugin manifest is not valid JSON: {exc}",
            fix=f"Inspect {MANIFEST} for a syntax error and restore from git.",
        )
    server_entry = (manifest.get("mcpServers") or {}).get("westland-scheduler-mcp")
    if not server_entry:
        return CheckResult(
            name="Plugin manifest declares the MCP server",
            status="fail",
            message=(
                "`mcpServers.westland-scheduler-mcp` is missing from the plugin "
                "manifest. Claude Code has nothing to launch."
            ),
            fix=(
                "Reinstall the scheduling plugin, or follow the "
                "\"Manual registration fallback\" section in this skill's "
                "SKILL.md to declare the server in ~/.claude/settings.json."
            ),
        )
    if not server_entry.get("command"):
        return CheckResult(
            name="Plugin manifest declares the MCP server",
            status="fail",
            message="Manifest server entry has no `command` field.",
            fix=f"Inspect {MANIFEST} — the entry needs `command` + `args`.",
        )
    return CheckResult(
        name="Plugin manifest declares the MCP server",
        status="pass",
        message=f"Server entry present in {MANIFEST.name}.",
    )


def _list_tool_names(mcp_instance) -> list[str]:
    """FastMCP's tool-enumeration API has shifted across versions; try the
    documented surfaces in order. Mirrors what tests/test_server.py does."""
    if hasattr(mcp_instance, "list_tools"):
        tools = mcp_instance.list_tools()
        if hasattr(tools, "__await__"):
            import asyncio
            tools = asyncio.run(tools)
        return [t.name for t in tools]
    if hasattr(mcp_instance, "_tools"):
        return list(mcp_instance._tools.keys())
    if hasattr(mcp_instance, "tools"):
        return list(mcp_instance.tools.keys())
    raise RuntimeError(f"Cannot enumerate tools on {type(mcp_instance)!r}")


def _check_server_boots() -> CheckResult:
    if str(MCP_SERVER_DIR) not in sys.path:
        sys.path.insert(0, str(MCP_SERVER_DIR))
    try:
        if "server" in sys.modules:
            server = importlib.reload(sys.modules["server"])
        else:
            server = importlib.import_module("server")
    except Exception as exc:
        return CheckResult(
            name="MCP server boots and registers tools",
            status="fail",
            message=f"Importing server.py raised: {exc!r}",
            fix=(
                "Inspect the traceback below. Common causes: the `mcp` SDK "
                "version is incompatible, or a tools/ module has an import "
                "error. Run `python -m unittest discover -s "
                f"{MCP_SERVER_DIR / 'tests'}` for the full picture."
            ),
            details=traceback.format_exc().splitlines(),
        )
    try:
        tool_names = _list_tool_names(server.mcp)
    except Exception as exc:
        return CheckResult(
            name="MCP server boots and registers tools",
            status="fail",
            message=f"Server booted but tool enumeration failed: {exc!r}",
            fix="Check the installed `mcp` SDK version against requirements.txt.",
        )
    missing = [t for t in REPRESENTATIVE_TOOLS if t not in tool_names]
    if missing:
        return CheckResult(
            name="MCP server boots and registers tools",
            status="warn",
            message=(
                f"Server boots, registers {len(tool_names)} tools, but is "
                f"missing representative tools: {missing}"
            ),
            fix=(
                "A tool batch did not register. Confirm server.py calls "
                "structure.register / cpm_path.register / quality.register / "
                "update_review.register / compare.register / omnibus.register."
            ),
        )
    return CheckResult(
        name="MCP server boots and registers tools",
        status="pass",
        message=f"{len(tool_names)} tools registered; representatives present.",
    )


def _check_fixture_parses() -> CheckResult:
    if not FIXTURE_XER.is_file():
        return CheckResult(
            name="Fixture XER parses cleanly",
            status="fail",
            message=f"Fixture not found at {FIXTURE_XER}.",
            fix="Reinstall the scheduling plugin — the fixture ships with it.",
        )
    if str(MCP_SERVER_DIR) not in sys.path:
        sys.path.insert(0, str(MCP_SERVER_DIR))
    try:
        cache_mod = importlib.import_module("cache")
        cache = cache_mod.CpmCache()
        parsed = cache.get_parsed(str(FIXTURE_XER))
    except Exception as exc:
        return CheckResult(
            name="Fixture XER parses cleanly",
            status="fail",
            message=f"Parsing minimal.xer raised: {exc!r}",
            fix=(
                "Inspect the traceback below. If this fails the lib/ layer is "
                "broken — open the worktree-with-hook-disabled workflow in the "
                "Working on lib/ source section."
            ),
            details=traceback.format_exc().splitlines(),
        )
    # The cache returns the raw XER table dict — uppercase table names per
    # the .xer spec (TASK, TASKPRED, PROJECT, ...). Don't confuse with the
    # MCP tools' lowercase output shape.
    n_tasks = len(parsed.get("TASK") or [])
    if n_tasks < 2:
        return CheckResult(
            name="Fixture XER parses cleanly",
            status="warn",
            message=f"Parsed but task count is {n_tasks}; expected at least 2.",
            fix="Fixture may have been edited. Restore from git.",
        )
    return CheckResult(
        name="Fixture XER parses cleanly",
        status="pass",
        message=f"Parsed minimal.xer; {n_tasks} tasks found.",
    )


CHECKS: list[tuple[str, Callable[[], CheckResult]]] = [
    ("sdk", _check_mcp_sdk),
    ("manifest", _check_manifest),
    ("server", _check_server_boots),
    ("fixture", _check_fixture_parses),
]


def _icon(status: str) -> str:
    return {"pass": "PASS", "fail": "FAIL", "warn": "WARN"}.get(status, status.upper())


def _render(results: list[CheckResult]) -> str:
    lines = []
    lines.append("Westland Scheduler Local MCP — diagnostic")
    lines.append("=" * 60)
    for r in results:
        lines.append(f"[{_icon(r.status)}] {r.name}")
        lines.append(f"        {r.message}")
        if r.fix:
            lines.append(f"        fix: {r.fix}")
        if r.details:
            lines.append("        details:")
            for d in r.details:
                lines.append(f"          {d}")
        lines.append("")
    failures = [r for r in results if r.status == "fail"]
    warns = [r for r in results if r.status == "warn"]
    if failures:
        lines.append(f"{len(failures)} check(s) failed; see fix lines above.")
    elif warns:
        lines.append(f"All blocking checks passed; {len(warns)} warning(s) above.")
    else:
        lines.append("All checks passed. MCP should be reachable from Claude Code.")
    return "\n".join(lines)


def run() -> int:
    results: list[CheckResult] = []
    for _, check in CHECKS:
        try:
            results.append(check())
        except Exception as exc:  # defensive — a check should never crash here
            results.append(CheckResult(
                name=check.__name__,
                status="fail",
                message=f"Check itself raised: {exc!r}",
                details=traceback.format_exc().splitlines(),
            ))
    print(_render(results))
    return 0 if all(r.status != "fail" for r in results) else 1


if __name__ == "__main__":
    sys.exit(run())
