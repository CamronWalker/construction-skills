# Scheduler MCP — Activity Roster + Adjacency Read Tools

**Date:** 2026-07-06
**Plugin:** `scheduling` (Westland Scheduler Local MCP, `scheduling/mcp-server/`)
**Origin:** bug report `dd45d9d8-ce7a-4e8d-b599-7fce8ae82eb2` — "Scheduler MCP lacks a 'list all activities with full WBS path + adjacent logic' read tool"

## Problem

During the CVMC Nephi batch-logic repair (642 activities, 73 open ends), the MCP could not answer two everyday reconnaissance questions in one call:

1. **"List every activity with its full WBS path, dates, type, float, and pred/succ counts"** — filterable by WBS branch or trade.
2. **"Show me the activities adjacent within a WBS branch, and one activity's expanded predecessors/successors with their full paths"** — to design relationships and verify each new link is logical.

The MCP exposes targeted checks (`get_missing_logic`, `get_milestones`, `get_critical_path`, …) plus modify/validate, and `get_gantt_json` returns a large chart payload — but there is no queryable WBS-pathed activity roster and no per-activity/branch adjacency lookup. As a result all WBS-tree reconnaissance and per-link verification fell back to read-only custom Python `.xer` parsing, outside the sanctioned MCP path.

## Goals

Add four read tools to `westland-scheduler-mcp` that close the gap:

- `list_activities` — WBS-pathed activity roster.
- `get_activity` — one activity + expanded logic.
- `get_wbs_branch` — a WBS branch's activities + adjacency.
- `next_free_activity_code` — next collision-free activity code for a prefix.

Non-goals: no write operations (modify/validate already exist), no new chart output, no schedule-quality scoring (covered elsewhere).

## Key decisions

### Dates & float are always CPM-computed (no flag)

Originally considered an `imported`/`cpm` flag. Dropped it:

- The recompute-on-edit iteration loop the user wanted (edit logic → see new dates) falls out of the **file-keyed cache** for free: `apply_xer_changes` writes a new `-v#.xer`, and any roster call on that new file already returns freshly CPM'd dates.
- It removes the [CPM-mutation sharp edge](../../../../): `schedule_forward_backward` mutates the cache's shared lossy projection in place, so a tool that tried to serve *both* as-imported and computed dates in one session could silently leak computed dates into "imported" reads. Committing to CPM-only sidesteps this entirely.
- On incomplete activities (the ones being wired) the engine's ES/EF match P6 exactly; the ~1% divergence is the completed-task late-date floor, immaterial to logic recon.

Pure-structure fields (WBS path, pred/succ counts) and `next_free_activity_code` do **not** trigger CPM — they read `cache.get_parsed` only.

### Trades come from the "Responsibility" global activity code

Westland schedules tag each activity with a **"Responsibility" global activity code** (P6 shows it "Responsibility - Global"). In XER this is the `ACTVTYPE` (name `actv_code_type`, scope `actv_code_type_scope='AS_Global'`) → `ACTVCODE` (`actv_code_name`, `short_name`) → `TASKACTV` (`task_id`, `actv_code_id`, `actv_code_type_id`) chain.

- Every roster row surfaces the activity's Responsibility value (`responsibility` = `actv_code_name`, `responsibility_short` = `short_name`, `None` when unassigned).
- `trade_filter` resolves the Responsibility code type (auto: the type named "Responsibility", preferring `AS_Global`; overridable via `code_type`) and matches its assigned value by case-insensitive substring over short_name + name.

### Module layout mirrors the existing seam

- **New lib module** `scheduling/skills/schedule-toolbox/lib/activity_roster.py` — pure, deterministic functions that take already-parsed table dicts (and, for date/float fields, already-CPM'd TASK dicts). No cache, no I/O. Unit-tested in isolation.
- **New MCP tool module** `scheduling/mcp-server/tools/roster.py` — thin `register(mcp, cache)` adapters, one `_impl` + one `@mcp.tool()`/`@wrap_tool_errors` wrapper per tool, matching `structure.py`. The CPM-vs-parsed choice lives here.
- Registered in `server.py`; `activity_roster.py` added to `check_lib_fence.py` `_FILE_TO_TOOLS`.

## Lib functions (`activity_roster.py`)

- `build_wbs_path_index(projwbs_rows) -> {wbs_id: "Root > Sub > Leaf"}` — walk `parent_wbs_id` to root; cycle guard (bail if a node reappears); root label is `wbs_name`. Project node (`proj_node_flag='Y'`) is the top of the path.
- `resolve_responsibility(actvtype_rows, code_type=None) -> actv_code_type_id | None` — pick the "Responsibility" type (or `code_type` name), preferring `AS_Global`.
- `build_task_responsibility(taskactv_rows, actvcode_rows, resp_type_id) -> {task_id: {short, name}}`.
- `roster_rows(tasks, preds, wbs_index, task_resp, wbs_filter, trade_filter, include_logic) -> [row]`.
- `expand_activity(task_ref, tasks, preds, wbs_index, task_resp) -> row + predecessors[]/successors[]`. `task_ref` matches `task_code` first, then internal `task_id`.
- `branch_activities(wbs_ref, tasks, preds, projwbs, wbs_index, task_resp, include_descendants, include_logic)`. `wbs_ref` matches `wbs_id`, then `wbs_short_name`, then `wbs_name`.
- `next_free_code(tasks, prefix, step) -> {...}`.

## Tool contracts (`roster.py`)

### `list_activities(xer_path, wbs_filter=None, trade_filter=None, code_type=None, include_logic=True)`
`{data_date, activity_count, activities: [row, …]}`; row =
```
task_code, task_name, task_type, status_code,
wbs_id, wbs_path,
responsibility, responsibility_short,
early_start, early_finish, late_start, late_finish,
total_float_days, total_float_hr_cnt,
pred_count, succ_count            # omitted when include_logic=False
```
`wbs_filter`: case-insensitive substring on `wbs_path` (branch match incl. descendants). `trade_filter`: substring on the Responsibility value. Source: `cache.get_cpm` for dates/float; `cache.get_parsed` for PROJWBS / TASKPRED / ACTVTYPE / ACTVCODE / TASKACTV / CALENDAR.

### `get_activity(xer_path, activity_id)`
The row above **plus** `predecessors[]`/`successors[]`, each `{task_code, task_name, wbs_path, responsibility, rel_type, lag_days, lag_hr_cnt}`. `rel_type` maps `PR_FS`/`FS`→`FS`, etc. Not found → friendly error naming the closest existing codes.

### `get_wbs_branch(xer_path, wbs_id, include_descendants=True, include_logic=True)`
`{wbs_id, wbs_path, activity_count, activities: [row, …]}`. `wbs_id` accepts an id or a WBS short_name/name. When `include_logic=True`, each activity carries expanded predecessors/successors (the "verify each link within a branch" case). `include_descendants=True` includes child WBS nodes' activities.

### `next_free_activity_code(xer_path, prefix, step=10)`
No CPM. `{prefix, matched_count, max_existing_code, max_existing_number, next_code, step}`. Parses the trailing digit run of codes starting with `prefix`; `next_code = max + step` formatted with the max code's separator + zero-pad width. `next_code=None` when `matched_count==0` (don't guess a format). `step` defaults to 10 (Westland milestone convention); pass `step=1` for dense codes.

## Float representation

`total_float_hr_cnt` (raw, from CPM) + `total_float_days` derived via each task's calendar `day_hr_cnt` (CALENDAR lookup by `clndr_id`; fallback 8h).

## Error handling

Every tool wrapped with `@wrap_tool_errors(tool_name=<name>, lib_script="scheduling/skills/schedule-toolbox/lib/activity_roster.py")` — same friendly-error surface as the other tools.

## Testing

- **`schedule-toolbox/tests/test_activity_roster.py`** (pure, synthetic dicts): nested WBS paths + cycle guard; Responsibility resolution (global vs project scope) + `trade_filter`; roster fields + `wbs_filter`; `include_logic` on/off; adjacency `rel_type`/lag mapping across FS/SS/FF/SF and `PR_`-prefixed variants; branch descendant inclusion; `next_free_code` (gaps, empty prefix, custom step, zero-pad width, separator inference, no-match None).
- **`mcp-server/tests/test_roster.py`** (wiring, real fixtures): a new `roster_sample.xer` (3-level WBS + Responsibility global code + linked tasks) proves CPM date flow, `wbs_path`, pred/succ counts, `get_activity` found + not-found error, `trade_filter` end-to-end, branch descendants, and `next_free_activity_code`. `minimal.xer` covers the no-activity-codes graceful path (`responsibility=None`).

## Release

Per repo convention: bump `scheduling` **9.4.1 → 9.5.0** (minor = new tools) in `scheduling/.claude-plugin/plugin.json` **and** the matching `.claude-plugin/marketplace.json` entry (lockstep). Add the four tools to the schedule-toolbox `SKILL.md` tool inventory. Build + distribute happen from the main checkout after merge. Flip report `dd45d9d8` status via `update_report_status` once merged.
