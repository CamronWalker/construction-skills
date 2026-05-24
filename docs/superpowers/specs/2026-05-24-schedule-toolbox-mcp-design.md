# Schedule Toolbox MCP — Design

**Date:** 2026-05-24
**Status:** Draft — pending user review
**Owner:** Camron
**MCP server name:** Westland Scheduler Local MCP

## Problem

The `schedule-toolbox` skill's Python scripts (`scheduling/skills/schedule-toolbox/references/*.py`) ship as CLI tools that return JSON. The `SKILL.md` Cardinal Rule says "Do not read Python source files for routine operations. Call the CLI → get JSON → use it." Despite that, three real failure modes recur:

1. **Introspection.** Claude opens `score_schedule.py` / `xer_compare.py` / etc. to figure out CLI signatures or output shapes, burning turns on context it doesn't need.
2. **In-place edits.** Claude modifies the scripts mid-task (changing logic, adding flags), so the next project inherits drift.
3. **Reimplementation.** Claude treats the scripts as templates and writes a modified copy or inline reimplementation instead of just running the existing tool.

The JSON output contract is *not* the problem — downstream skills consume it fine today. The problem is purely behavioral: anything Claude can `Read` is something Claude eventually `Read`s, and `references/` is a directory name that reads like "samples to crib from."

## Goal

Expose the toolbox's question-answering surface through MCP tools, so Claude interacts with the toolbox the way it interacts with Procore or SmartPM — call a tool, get a structured result, move on. The `.py` source becomes invisible to Claude.

## Non-goals

- **Not replacing the scripts.** The `.py` files stay in the repo and stay importable for non-Claude callers (the `iterate.py` proposal-schedule loop, `schedule-update`'s report/draft phases, future automation). MCP is a *new entry point*, not a rewrite.
- **Not covering XER generation.** `build_from_raw_template.py` (proposal-schedule output) is a different shape (fat JSON spec → emit XER) and already orchestrated by `schedule-create-proposal-schedule`. Out of scope for this design; promote later if it earns it.
- **Not a remote MCP.** Diagnosed failure is behavioral, not contract-correctness. A remote MCP would (a) make XER inputs awkward (multi-MB payloads), (b) require returning the new XER from `run_cpm` over the wire, (c) break the lessons-learned loop. Local MCP solves all three.

## Architecture

**Local MCP server bundled with the scheduling plugin, named "Westland Scheduler Local MCP".** Lives at `scheduling/mcp-server/`. The plugin manifest registers it under that display name; when the scheduling plugin loads, Claude Code spawns the MCP server as a subprocess and discovers its tools.

The MCP server is a thin wrapper that imports the existing modules:

```python
# scheduling/mcp-server/server.py (sketch)
import sys
sys.path.insert(0, "../skills/schedule-toolbox/lib")  # after rename, see § Source Hiding

from score_schedule import compute_quality_score
from cpm_engine import run as run_cpm
from xer_compare import compare_schedules
# ...
```

Each MCP tool is a 5-20 line adapter: parse inputs, call the existing function, marshal the result into the tool's declared output shape.

**Three properties this buys:**

1. **Claude cannot see the source.** Tool schemas are the only surface. The three failure modes become physically impossible for these scripts.
2. **Non-Claude callers still work.** `iterate.py`, `schedule-update` phases, anything else that imports directly — untouched.
3. **Lessons-learned loop preserved.** Edit script in worktree → bump plugin version → ship. The MCP server picks up the change on next plugin load. Same release convention, same speed, same reviewability.

## Tool catalog

28 narrow "ask one question" tools plus 3 omnibus tools, derived from the existing six scripts. All take `xer_path` as the base input; additional inputs called out per tool. All outputs are JSON; the column shows the top-level shape.

**Loading model:** all 33 tools are MCP-discovered and therefore *deferred* in Claude Code — only tool names appear in the upfront tool list. Phase files / SKILL.md routing tables call tools by name (Claude loads the schema via `ToolSearch select:<name>` before calling). Ad-hoc usage discovers tools via `ToolSearch` keyword search. Upfront context cost: ~33 tool names, no schemas.

### Milestone scoping — fixing the "Substantial Completion" assumption

Many analyses are "to which target?" questions: critical path *to what*, delay impact *on what*, scoring *against what completion*. Today's `score_schedule.py` (`find_sc_milestone`, lines 35–60) walks the schedule for a milestone whose name contains "Substantial Completion." Real Westland schedules have project-meaningful milestones that don't match that string — the auto-detect silently picks the wrong target or falls back to longest path. The same brittleness lives in `path_analysis.py`'s SC-coverage computation.

The MCP fixes this at the seam:

1. **`get_milestones` tool** enumerates every non-WBS, non-LOE milestone in the schedule with full metadata (id, name, type, calendar, dates, status, predecessor count). The caller — Claude or a downstream skill — picks the one that matters.
2. **Milestone-scoped tools accept an optional `milestone_id`.** When provided, that's the target. When omitted: if there's exactly one unambiguous terminal milestone in the schedule, use it; otherwise the tool returns a structured error containing the candidate list, telling the caller to call `get_milestones` and pick. Never silently guess.
3. **The underlying scripts get fixed too.** `find_sc_milestone` and any sibling auto-detect get replaced with the "explicit ID or enumerate-and-error" pattern at the Python layer, not just the MCP layer. Non-Claude callers (`iterate.py`, etc.) benefit too.

### Schedule structure tools (new, from `cpm_engine.py` parsing)

| Tool | Inputs | Output |
|------|--------|--------|
| `get_milestones` | `xer_path`, `include_complete?` (default false) | `{ milestones: [{ task_id, task_name, task_type, calendar_id, early_finish, late_finish, status_code, predecessor_count, is_terminal }, ...] }` |

### CPM and path tools (from `cpm_engine.py` + `path_analysis.py`)

| Tool | Inputs | Output |
|------|--------|--------|
| `run_cpm` | `xer_path`, `output_path?`, `scheduling_options?` | `{ output_path, summary: { tasks_computed, milestones_detected, project_dates, anchor_conflicts_count } }` — writes new XER |
| `get_critical_path` | `xer_path`, `milestone_id?` | `{ critical_path: [task_id, ...], target_milestone_id }` — when `milestone_id` is given, returns the path to that milestone; otherwise the longest path |
| `get_near_critical_chains` | `xer_path`, `tolerance_days?` (default 5), `milestone_id?` | `{ chains: [{ tasks: [...], min_float }, ...], target_milestone_id }` |
| `get_driving_paths` | `xer_path`, `activity_id` | `{ driving_paths: [...], near_critical_chains: [...], parallel_branches: [...] }` |
| `get_parallel_branches` | `xer_path`, `start_date`, `end_date` | `{ parallel_branches: [{ tasks: [...] }, ...] }` |
| `get_anchor_conflicts` | `xer_path` | `{ conflicts: [{ task_id, constraint_date, computed_date, variance_days }, ...] }` |
| `get_anchor_absorption_suggestions` | `xer_path` | `{ suggestions: [{ task_id, absorption_potential_days, rationale }, ...] }` |
| `get_milestone_path_coverage` | `xer_path`, `milestone_id?` | `{ milestone_id, coverage_pct, connected_activities: [...], disconnected_activities: [...] }` — was `get_sc_path_coverage`; if `milestone_id` omitted and ambiguous, returns candidate-list error |
| `get_delay_impacts` | `xer_path`, `milestone_id?` | `{ milestone_id, delay_impacts: [{ task_id, delay_days_if_slips, criticality_rank }, ...] }` — impact on the target milestone's date |
| `get_gantt_json` | `xer_path` | `{ activities: [...], dependencies: [...], milestones: [...] }` — for charting |
| `render_gantt_html` | `xer_path`, `output_path?`, `title?`, `include_resources?` | `{ output_path, summary: { activity_count, milestone_count } }` — writes Gantt review HTML to a file; for proposal-schedule iteration loop |

### Quality and scoring tools (from `score_schedule.py` + `quality_checks.py`)

| Tool | Inputs | Output |
|------|--------|--------|
| `get_quality_check` | `xer_path`, `check_name` (one of 28 enum values: `finish_to_start`, `missing_logic`, `high_float`, `hard_constraints`, etc.) | `{ check, count, total, pct, status, tasks: [...] }` |
| `get_relationship_type_breakdown` | `xer_path` | `{ FS: { count, pct }, SS: {...}, FF: {...}, SF: {...} }` |
| `get_missing_logic` | `xer_path` | `{ count, total, pct, tasks: [{ task_id, missing: "predecessor"\|"successor" }, ...] }` |
| `get_high_float_activities` | `xer_path`, `threshold_days?` (default 44) | `{ count, total, pct, tasks: [...] }` |
| `get_negative_float_activities` | `xer_path` | `{ count, total, pct, tasks: [...] }` |
| `get_constraint_violations` | `xer_path` | `{ count, total, pct, tasks: [...] }` |
| `get_high_duration_activities` | `xer_path`, `threshold_days?` (default 44) | `{ count, total, pct, tasks: [...] }` |
| `get_duplicate_relationships` | `xer_path` | `{ count, total, pairs: [...] }` |
| `get_circular_relationships` | `xer_path` | `{ cycles: [[task_id, task_id, ...], ...] }` |
| `get_invalid_dates` | `xer_path` | `{ count, total, pct, tasks: [...] }` |

### Update review tools (from `update_review.py`)

| Tool | Inputs | Output |
|------|--------|--------|
| `get_activities_to_start` | `xer_path`, `by_date`, `resource_filter?`, `trade_filter?` | `{ to_start: [{ task_id, early_start, duration, resource, trade }, ...] }` |
| `get_activities_to_finish` | `xer_path`, `by_date` | `{ to_finish: [{ task_id, early_finish, pct_complete, remaining_days }, ...] }` |
| `get_in_progress_activities` | `xer_path` | `{ in_progress: [{ task_id, pct_complete, remaining_days }, ...] }` |
| `get_ride_data_date_violations` | `xer_path`, `data_date?` | `{ violations: [{ task_id, type, days_off }, ...] }` |

### Compare tools (from `xer_compare.py`)

| Tool | Inputs | Output |
|------|--------|--------|
| `compare_activity_changes` | `baseline_path`, `current_path` | `{ added: [...], removed: [...], changed: [{ task_id, fields_changed: [...] }, ...] }` |
| `compare_date_slips` | `baseline_path`, `current_path` | `{ date_slips: [{ task_id, baseline_date, current_date, variance_days }, ...] }` |
| `compare_milestone_slip` | `baseline_path`, `current_path`, `milestone_id?` | `{ milestone_id, baseline_date, current_date, days_change }` — was `compare_sc_slip`; if `milestone_id` omitted and ambiguous, returns candidate-list error |
| `compare_missed_dates` | `baseline_path`, `current_path` | `{ missed_starts: [...], missed_finishes: [...] }` |

### Omnibus tools (workflow-shaped bundles)

| Tool | Inputs | Output |
|------|--------|--------|
| `score_schedule` | `xer_path`, `milestone_id?` | `{ milestone_id, score, grade, scored: [...], info: {...}, deductions: [...], scope: {...}, details: {...} }` — full scoring output; scoring is relative to the target milestone's date, not project end |
| `weekly_update_review` | `xer_path`, `baseline_path?`, `data_date?`, `milestone_id?` | Combines `compare_activity_changes` + `compare_milestone_slip` + `get_activities_to_start` + `get_activities_to_finish` + DCMA-delta. Used by `schedule-update` report phase. |
| `proposal_schedule_health` | `xer_path`, `milestone_id?` | Combines `score_schedule` + `get_missing_logic` + `get_high_float_activities` + `get_anchor_conflicts`. Used by `schedule-create-proposal-schedule`'s iterate loop. |

**Final tool count: 33** (30 narrow + 3 omnibus). The implementation plan tightens this — some narrow tools may merge if they share enough input/output shape, and the implementation phase may discover one or two missed questions.

## XER input/output handling

**All XER inputs are file paths, not content.** The MCP server reads from disk. This keeps Claude's context clean (no multi-MB tab-delimited text in tool results) and works because the MCP is local (Claude and the server share a filesystem).

**`run_cpm` is the only tool that writes a file.** Behavior:

- If `output_path` is provided, write there.
- If omitted, write to `<input_xer_basename>-cpm.xer` in the same directory as the input.
- Tool result returns `{ output_path, summary: {...} }`. Claude knows the path; it never sees the XER content unless it explicitly chooses to `Read` it (rare — usually the next step is `import_xer_schedule` into Procore or another MCP tool).

**No tool ever overwrites an existing XER.** The plugin's existing PreToolUse hook (per `scheduling/CLAUDE.md`: "XER files are immutable") catches this layer. If `output_path` collides with an existing file, the MCP returns an error with a suggested suffix (`-v2`, `-v3`).

## Source hiding

The MCP seam stops Claude from *needing* to read the scripts. Two reinforcements stop it from *being able to*:

### 1. Rename `references/` → `lib/`

The directory name signals intent. `references/` reads as "documentation / samples to read." `lib/` reads as "implementation — don't touch." One-time refactor:

- `scheduling/skills/schedule-toolbox/references/*.py` → `scheduling/skills/schedule-toolbox/lib/*.py`
- The non-Python files (`*.md` documentation) stay in `references/` — they *are* references.
- Update imports in the MCP server and any direct callers (`iterate.py`, schedule-update phases).
- Update `SKILL.md` to remove the routing table's file-path entries (replaced by tool-name entries — see § Integration).

### 2. PreToolUse hook on `lib/*.py`

Westland's existing PreToolUse hook already blocks `.xer` writes. Add a sibling rule: block `Read` / `Edit` / `Write` / `Glob` / `Grep` on `scheduling/skills/schedule-toolbox/lib/*.py` unless the active skill is `schedule-toolbox` itself (allowing intentional improvement work).

The hook is a fence, not the primary mechanism — the tool seam already removes the *reason* to read. The hook catches the rare case where a future model ignores the seam.

## Distribution to 4 schedulers

The MCP rides the plugin. Existing distribution pipeline (`python build.py scheduling` → `src/scheduling.zip` → enterprise install, or marketplace install direct from repo) ships the MCP server identically.

**Per-scheduler setup, one time:**

1. Plugin already installed → MCP server files are on disk.
2. Python already installed (existing scripts require it).
3. **Install `mcp` Python SDK:** `pip install mcp` (one command, ~1 MB).
4. **Register the server with Claude Code.** Two options for the spec to choose between:

### Registration option A — plugin manifest declares the server

`scheduling/.claude-plugin/plugin.json` adds an `mcpServers` field declaring the local server. Claude Code auto-registers on plugin load. Zero setup beyond `pip install mcp`.

### Registration option B — explicit init skill

A `schedule-mcp-init` skill walks the user through: detects Python, installs the `mcp` package, writes the registration to `~/.claude/settings.json`, runs a smoke-test call against a sample XER, confirms success.

**Recommendation:** start with **A + a thin init skill**. The plugin manifest handles registration (zero friction for the common case); the init skill handles the dependency install + sanity check + "you're good to go" confirmation. If manifest auto-registration turns out to be unreliable across the team's Claude Code versions, fall back to B handling both.

**Updates:** lessons learned → edit script → bump plugin version → merge → `python build.py` → distribute. Schedulers pick up the new version through the normal plugin update flow. No deploy lag, no separate MCP version to track.

## Integration with existing skills

Three downstream surfaces switch from "run the Python script" to "call the MCP tool":

### `schedule-update` skill

- **`phases/report.md` step 3b** currently uses Glob to resolve `xer_compare.py`, then runs it via `python`. Replaces with a `compare_activity_changes` + `compare_sc_slip` + `compare_date_slips` MCP call sequence (or the omnibus `weekly_update_review`).
- **`phases/draft.md`** has a similar pattern. Replaces with the same MCP calls.

### `schedule-toolbox` skill itself

- `SKILL.md` routing table changes from "where to look" (file paths in `references/`) to "which tool to call" (MCP tool names).
- The Cardinal Rule ("Do not read Python source files") is deleted — it's no longer needed because the files aren't reachable from Claude.
- The reference markdown files (`xer-format.md`, `xer-modify.md`, `xer-tables.md`, `cpm-usage.md`, etc.) stay — they document the XER format and analytical concepts, which are still useful when interpreting tool results.

### `schedule-create-proposal-schedule` skill

- `iterate.py` continues to `import cpm_engine` directly (non-Claude caller; the script is still in `lib/`). No change.
- The skill's *Claude-facing* phases — where Claude evaluates a proposal schedule iteration — switch to the `proposal_schedule_health` omnibus tool instead of running scripts.

## Risks and mitigations

| Risk | Mitigation |
|------|------------|
| Plugin manifest MCP-server declaration is unreliable across Claude Code versions on the team | Init skill (option B) becomes the primary registration path. Fall back is documented up front. |
| Scheduler skips `pip install mcp` → MCP fails to start | Init skill is the *first thing* a scheduler runs after plugin install. Plugin README points to it. |
| Two schedulers on different plugin versions → divergent tool behavior | Same risk today with the Python scripts. Pre-commit hook enforces version bumps; team practice is to update on the same cadence. |
| `lib/` rename breaks import paths in `iterate.py` or schedule-update phases | One-time refactor with explicit grep-replace pass. Test via existing test suites (proposal schedule iteration, schedule-update report run on a real project). |
| Milestone auto-detect bug propagates to scripts that don't get migrated in step 3 | Audit every call to `find_sc_milestone` (and similar) across the scheduling plugin. The pre-merge checklist explicitly verifies the SC-name heuristic is gone everywhere. |
| MCP server has a bug that affects all schedulers simultaneously (vs. today's "the script is buggy on one machine") | Pre-merge testing on a real project's XER catches it before distribution. Worst case, roll back the plugin version. |
| Adding `mcp-server/` triggers the version-bump pre-commit hook for *every* commit that touches it | This is the desired behavior, not a bug. Same as any plugin change today. |

## Implementation order (high-level — `writing-plans` will detail)

1. **Stand up the MCP server skeleton** in `scheduling/mcp-server/`. One tool to start (`get_critical_path`). Verify Claude Code can discover and call it.
2. **Rename `references/*.py` → `lib/*.py`.** Update imports in `iterate.py` and any other direct caller. Run existing test suites.
3. **Fix the milestone auto-detection in the underlying scripts.** `score_schedule.find_sc_milestone` and `path_analysis`'s SC-coverage computation replace name-based search with the "explicit `milestone_id` or enumerate-and-error" pattern. Add a `get_milestones()` helper to the parsing layer that both the scripts and the MCP can share.
4. **Implement the 33 tools.** Group by source script; each tool is a 5-20 line adapter over an existing function.
5. **Add the PreToolUse hook** blocking `Read`/`Edit`/`Write` on `lib/*.py` outside the `schedule-toolbox` skill.
6. **Update `schedule-toolbox` `SKILL.md`** — routing table becomes tool names, Cardinal Rule removed.
7. **Update `schedule-update` `phases/report.md` and `phases/draft.md`** to call MCP tools instead of the Python scripts. Note that `compare_sc_slip` references become `compare_milestone_slip` with an explicit `milestone_id` resolved up front.
8. **Build the `schedule-mcp-init` skill** for `pip install mcp` + sanity check.
9. **Release.** Bump scheduling plugin version, bump marketplace version, commit, merge, `python build.py scheduling`, distribute.
10. **Smoke test on a real project's XER** (Wellington Temple or W1177) end-to-end before declaring done — exercise both the auto-detect path (single terminal milestone) and the explicit-id path (project with multiple candidates).

## Open questions for the implementation plan

1. **Tool naming convention.** `get_critical_path` vs `critical_path` vs `cpm_critical_path` — pick one and apply consistently.
2. **Whether to add an `xer_parse` tool** that returns the raw parsed XER as JSON. Useful for ad-hoc queries the catalog doesn't anticipate, but risks Claude grabbing it and reimplementing analysis in the conversation context. Recommend *not* adding it initially.
3. **Per-tool input validation** — what does the MCP do when `xer_path` doesn't exist, isn't an XER, or is locked by another process? Standardize error shape across all 33 tools. The milestone-ambiguity error shape (candidate list) is part of this — define it once.
4. **Caching.** Parsing a large XER takes seconds. If Claude calls 5 tools on the same `xer_path`, the server should parse once and serve all 5 from cache. Define cache eviction policy (LRU by path, with mtime check).
5. **The `weekly_update_review` and `proposal_schedule_health` omnibus tools** — confirm exact field composition with the team before locking the shape; they're load-bearing for downstream skills.

---

**Next step:** user reviews this document and the open questions. After approval, `writing-plans` produces the implementation plan.
