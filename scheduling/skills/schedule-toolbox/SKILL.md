---
name: schedule-toolbox
description: >
  P6 XER schedule analysis, quality scoring, update review, path analysis, comparison, and
  generation. Trigger on: XER file, schedule quality, DCMA, SmartPM, float, critical path,
  resource loading, schedule update, trade activities, SC coverage, generate XER, build schedule.
---

# Schedule Toolbox

==============================================================================
!!!!!!!!!!!!!!!!!!  CRITICAL RULE -- NEVER WRITE XER FILES  !!!!!!!!!!!!!!!!!!
ALL ANALYSIS RUNS IN MEMORY ONLY. NEVER OVERWRITE ANY XER FILE.
HISTORICAL RECORDS MUST NEVER BE ALTERED BY ANALYSIS TOOLS.
EXCEPTION: Explicit user instruction to generate or modify a specific file.
==============================================================================

> This skill's analysis logic is exposed via the **Westland Scheduler Local MCP** — call tools by name (e.g. `score_schedule`, `get_critical_path`, `compare_activity_changes`). The Python implementation lives in `lib/` and is intentionally fenced off by a PreToolUse hook; do not Read or Edit it for routine work. If MCP tool calls fail with registration or import errors, invoke the `westland-scheduler-mcp-troubleshoot` skill.

## Quick Routing

| Task | How to call |
|------|-------------|
| Score schedule / check quality | `score_schedule` (omnibus) — full DCMA + scope; or `get_quality_check` for one of the 28 individual checks |
| Quality check details (e.g. high float, missing logic, circular logic) | `get_high_float_activities`, `get_missing_logic`, `get_circular_relationships`, `get_negative_float_activities`, `get_constraint_violations`, `get_high_duration_activities`, `get_duplicate_relationships`, `get_invalid_dates`, `get_relationship_type_breakdown` |
| What needs field updates by date X | `get_activities_to_start(by_date=...)` + `get_activities_to_finish(by_date=...)` |
| What is trade X doing this month | `get_activities_to_start(by_date=..., trade_filter="<code>")` — same for `get_activities_to_finish` |
| What's in progress right now | `get_in_progress_activities` |
| Riding the data date | `get_ride_data_date_violations`, or `weekly_update_review` (omnibus) for the full update review |
| Run CPM (compute float, write new XER) | `run_cpm` — writes `<input>-cpm.xer` atomically; never overwrites |
| Critical path / near-critical | `get_critical_path`, `get_near_critical_chains` |
| Driving paths to a specific activity | `get_driving_paths(activity_id=...)` |
| Parallel branches in a date window | `get_parallel_branches(start_date=..., end_date=...)` |
| Anchor (contractual date) conflicts | `get_anchor_conflicts` — accepts `anchors` inline or `anchors_path` to JSON |
| How to absorb a slip into an anchor | `get_anchor_absorption_suggestions(slip=..., max_suggestions=8)` |
| Milestone enumeration (resolve ambiguity) | `get_milestones` — lists all non-WBS, non-LOE milestones with `task_id`, `is_terminal` |
| SC / milestone path coverage | `get_milestone_path_coverage(milestone_id=?)` |
| Delay impact analysis | `get_delay_impacts(milestone_id=?)` |
| Gantt review HTML for proposal iteration | `render_gantt_html` (writes HTML, returns path); or `get_gantt_json` for structured chart data |
| Week-over-week compare (activities, dates, milestones) | `compare_activity_changes`, `compare_date_slips`, `compare_milestone_slip(milestone_id=?)`, `compare_missed_dates` |
| Weekly update review (composition) | `weekly_update_review` — bundles compare + activity lists + DCMA delta |
| Proposal schedule health (composition) | `proposal_schedule_health` — bundles score + missing logic + high float + anchor conflicts |
| Health check | `ping` |
| Check if an XER will import cleanly (P6 / Procore) | `validate_xer_structure` — file-integrity gate; returns `import_ready`, issues by category and severity |
| Fix duplicate activity IDs | `fix_duplicate_activity_ids(strategy="renumber"\|"report_only"\|"merge_consolidate")` |
| Modify an existing XER (add/remove activities, logic, WBS, etc.) | `apply_xer_changes(xer_path, changes=[...])` — writes a new file, never overwrites; see `references/xer-modify.md` |
| Generate a new XER from the Westland skeleton | `create_xer_from_template(skeleton_name, metadata)` — canonical entry point; see `references/xer-generation.md` |
| Drop the cached parse for a path (after external edit) | `invalidate_cache_for(xer_path)` |

### Concept references (read-only docs, NOT code)

These live in `references/*.md` and describe the underlying concepts the MCP tools implement. Read them when an MCP result is surprising or when you need XER-format context, not as a substitute for calling the tools.

| Concept | Doc |
|---------|-----|
| XER file format primer | `references/xer-format.md` |
| XER modification rules — `apply_xer_changes` change-type catalog | `references/xer-modify.md` |
| XER generation — `create_xer_from_template` and skeleton flow | `references/xer-generation.md` |
| XER table / field definitions | `references/xer-tables.md` (grep by table name) |
| Quality check semantics | `references/quality-checks.md` |
| Update review semantics | `references/update-review.md` |
| CPM usage and the Gantt review HTML output | `references/cpm-usage.md` |
| SC coverage and delay impact methodology | `references/analysis-tools.md` |
| DCMA 14-point detail | `references/dcma-14-point-detail.md` |
| Westland scheduling standards | `references/westland-standards.md` |
| GAO / AACE references | `references/gao-aace-reference.md` |
| Reporting template | `references/reporting-template.md` |

## Milestone disambiguation

Several tools accept an optional `milestone_id` argument (`score_schedule`, `compare_milestone_slip`, `get_milestone_path_coverage`, `get_delay_impacts`, `proposal_schedule_health`). When the schedule has multiple terminal milestones — common on phased work — these tools raise `MilestoneAmbiguousError` with the candidate list if `milestone_id` is omitted. The clean pattern: call `get_milestones` first, present the candidates to the user (or pick by code/name yourself), then call the downstream tool with the resolved `task_id`.

## Modifying and generating XER files

All XER writes go through two tools:

- **`apply_xer_changes`** — modify an existing XER. Accepts a list of change records (add/remove activities, logic, WBS; dissolve; set duration/calendar; etc.) and writes a new file. Default output: `<input>-modified.xer`. Never overwrites the input.
- **`create_xer_from_template`** — generate a new XER. Instantiates the `westland-skeleton-v1` skeleton (canonical Westland WBS tree + NTP and SC milestones) stamped with project metadata, then returns the path. Project-specific structure is added in a subsequent `apply_xer_changes` call.

Both tools embody the never-overwrite rule at the top of this file: every write produces a new versioned path. The tools will return an error (with a suggested `-v2`, `-v3` suffix) if the default output path already exists.

**`validate_xer_structure` vs `score_schedule` — these are different checks.** `validate_xer_structure` is the file-import gate: it answers "will P6 or Procore accept this file?" (duplicate IDs, dangling references, circular logic, bad enums, orphans). `score_schedule` is the schedule-health grade: it answers "is this schedule well-built?" (DCMA metrics, float distribution, missing logic, open ends). Run `validate_xer_structure` after any write operation. Run `score_schedule` to evaluate planning quality.

**Compositional flow:**

1. `create_xer_from_template("westland-skeleton-v1", { project_name, project_id, planned_start, ... })` — skeleton on disk, NTP and SC milestone IDs returned.
2. `apply_xer_changes(output_path, [add_wbs, add_activity, add_logic, ...])` — build project-specific structure via change records.
3. `validate_xer_structure(result_path)` — confirm `import_ready: true` before handing off to P6 or Procore.

For the complete change-type catalog (all 14 record shapes with examples): `references/xer-modify.md`.
For the template flow and skeleton details: `references/xer-generation.md`.

**`fix_duplicate_activity_ids`** handles the single most common XER bug — duplicate `task_code` values — in one call. Use before `validate_xer_structure` if the file came from a third-party export and you expect collision issues.

## When the MCP tools aren't there

If `ToolSearch select:<tool_name>` returns nothing for tools listed above, or an MCP call fails with a registration / import error, invoke the `westland-scheduler-mcp-troubleshoot` skill. Do not fall back to reading `lib/*.py` — the PreToolUse hook blocks those reads, and even with the hook disabled, in-place edits drift from the canonical analysis behavior.
