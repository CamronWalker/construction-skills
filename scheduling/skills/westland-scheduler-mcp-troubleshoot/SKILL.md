---
name: westland-scheduler-mcp-troubleshoot
description: >
  Diagnose Westland Scheduler Local MCP registration or setup issues. Use
  whenever the schedule-toolbox MCP tools (score_schedule, get_critical_path,
  compare_activity_changes, get_milestones, weekly_update_review, etc.) don't
  appear in Claude Code's tool list, when an MCP tool call fails with a
  registration or import error, or when the user reports that "schedule-
  toolbox isn't working". Diagnostic-only — runs four checks and prints
  copy-pasteable fixes. Does NOT walk through setup unless the user explicitly
  asks. Also documents the worktree-with-hook-disabled workflow for the
  curator role (editing schedule-toolbox/lib/ source).
---

# Westland Scheduler MCP — Troubleshoot

If the Westland Scheduler Local MCP is registered and working, no one runs this skill. It exists for when something is wrong.

## What it checks

1. The `mcp` Python SDK is importable from the interpreter Claude Code launches the server with.
2. The scheduling plugin's manifest (`scheduling/.claude-plugin/plugin.json`) declares the `westland-scheduler-mcp` entry under `mcpServers`.
3. The server module boots, registers its tool surface, and exposes a representative tool from each Tier 0 batch (`ping`, `get_milestones`, `get_critical_path`, `get_quality_check`, `get_activities_to_start`, `compare_activity_changes`, `score_schedule`).
4. The bundled fixture XER (`mcp-server/tests/fixtures/minimal.xer`) parses cleanly through the cache layer.

## What it does

Runs `diagnose.py` next to this file and prints a result table. Each failed check carries a copy-pasteable fix. Exits 0 on all-pass, 1 on any failure.

```text
Bash:
  python "{{this skill's directory}}/diagnose.py"
```

Read the printed table. If everything says `PASS`, the MCP is healthy on this machine — the issue is likely on the Claude Code side: try `/plugin reload scheduling`, then start a fresh session and use `ToolSearch select:ping` to confirm tools are discoverable.

If any check says `FAIL`, follow the `fix:` line. If the manifest check fails, jump to **Manual registration fallback** below.

## Manual registration fallback

If the plugin manifest's `mcpServers` declaration isn't being honored (Claude Code version skew, manifest parse error, enterprise distribution that strips manifests), the server can be registered directly in `~/.claude/settings.json`. Add (or merge into the existing `mcpServers` block):

```jsonc
{
  "mcpServers": {
    "westland-scheduler-mcp": {
      "command": "python",
      "args": ["-m", "server"],
      "cwd": "<absolute path to>/scheduling/mcp-server"
    }
  }
}
```

Resolve `<absolute path to>` against the scheduling plugin's install location (the plugin cache directory shown by `/plugin info scheduling`, or your repo checkout if installed from source). The diagnose.py output's first `fix:` line, when the manifest check fails, surfaces the exact `cwd` path it expected to find.

Restart Claude Code after editing `settings.json`. Re-run the diagnostic to confirm.

## Working on `schedule-toolbox/lib/` source (curator role)

`schedule-toolbox/lib/*.py` is fenced by a PreToolUse hook (see `scheduling/hooks/check_lib_fence.py`). Routine Claude work — analyzing schedules, drafting emails, comparing XERs — goes through MCP tools, so the fence never gets in the way. But occasionally the lib needs improvement: a new quality check, a bug in the CPM engine, a richer compare output. That work happens in a worktree with the hook disabled.

The pattern:

1. Create a worktree off the current branch: `git worktree add ../<feature-branch-name> -b <feature-branch-name>`.
2. In the worktree, disable the hook by either:
   - Removing the second `PreToolUse` matcher (the one invoking `check_lib_fence.py`) from `scheduling/hooks/hooks.json` in that worktree, OR
   - Starting Claude Code from the worktree with `--no-hooks` (if available on your Claude Code version).
3. Make changes to `schedule-toolbox/lib/*.py`. Run `python -m unittest discover -s scheduling/mcp-server/tests` after each substantive change — the 125+ MCP-server tests are the primary regression check on lib/ behavior.
4. Commit, push, merge. Restore the hook in the merged result so the fence is active again on `main`.

Do not edit hooks.json on `main` to permanently disable the fence — that defeats the seam. If the curator workflow is friction in practice, file a `westland-bug-report` describing the pain point and the fence can evolve (e.g. to a skill-context-gated rule once that surface is reliably available in Claude Code).

## When the diagnostic itself fails

If `python diagnose.py` raises before printing any table at all, the worktree or plugin install is in an unexpected state. In that case:

- Confirm the file at `scheduling/skills/westland-scheduler-mcp-troubleshoot/diagnose.py` exists.
- Confirm `python --version` resolves to Python 3.10 or later (the MCP server's stated baseline).
- Re-install the scheduling plugin and try again.

If the diagnostic prints but the user still reports tools missing on the Claude Code side, the issue is the host side, not the server. `/plugin reload scheduling` and a fresh session typically resolve it.
