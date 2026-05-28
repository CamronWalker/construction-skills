# XER Generation

==============================================================================
ALWAYS WRITE TO A NEW FILE. NEVER OVERWRITE AN EXISTING XER.
CONFIRM OUTPUT PATH WITH USER BEFORE WRITING.
==============================================================================

## Canonical path: `create_xer_from_template`

`create_xer_from_template` is the recommended entry point for all new XER generation. It instantiates `westland-skeleton-v1` — the hand-curated Westland skeleton — stamped with project metadata, and writes a new file at `output_path` (defaults to `<project_name>.xer` in the working directory).

**Required metadata fields:**

| Field | Notes |
|-------|-------|
| `project_name` | Full project name |
| `project_id` | Westland job number (e.g. `W1177`) |
| `planned_start` | ISO date — NTP milestone date |
| `planned_data_date` | ISO date — initial data date |
| `task_code_prefix` | Optional — activity code prefix (e.g. `A`, `W1177`); defaults to `A` |

**Return shape:**

```jsonc
{
  "output_path":    "/path/to/ProjectName.xer",
  "project_name":   "...",
  "ntp_milestone":  { "task_id": "...", "task_code": "..." },
  "sc_milestone":   { "task_id": "...", "task_code": "..." },
  "validation":     { "import_ready": true, "errors": 0, "warnings": 0 }
}
```

The returned `ntp_milestone` and `sc_milestone` IDs are the anchors for all downstream logic. Pass them as `predecessor_id` / `successor_id` references in subsequent `apply_xer_changes` calls.

### What the `westland-skeleton-v1` skeleton contains

- Canonical Westland WBS tree (per `westland-standards.md` and the procedures doc) — no DEMOLITION branch; that is pattern-specific and added downstream.
- Two milestones: NTP (project start) and SC (Substantial Completion) with a single FS edge between them.
- Two summary-bar placeholders under SUMMARY & MILESTONES.
- Westland standard activity code types and values (responsibility, area, level, trade).
- Standard 5-day and 7-day calendars with Westland holiday conventions.
- SCHEDOPTIONS with Westland standard settings (retained-logic, etc.).

### Compositional flow

After `create_xer_from_template`, build project-specific structure with `apply_xer_changes`:

1. `create_xer_from_template("westland-skeleton-v1", { project_name, project_id, planned_start, planned_data_date })` — skeleton on disk.
2. `apply_xer_changes(output_path, [add_wbs, add_wbs, ..., add_activity, ..., add_logic, ...])` — populate WBS branches, activities, and relationships. Order-aware resolution means `add_wbs` records can be referenced by `add_activity` records later in the same call.
3. `validate_xer_structure(result_path)` — confirm `import_ready: true` before handing off to P6 or Procore.

For the complete change-type catalog: `references/xer-modify.md`.
For WBS pattern selection (Pattern A / B / C) and which `add_wbs` records each pattern requires: `scheduling/skills/schedule-create-proposal-schedule/references/wbs-patterns.md`.

**Example — Pattern B skeleton build (abbreviated):**

```jsonc
// Step 1: create skeleton
create_xer_from_template("westland-skeleton-v1", {
  "project_name": "Highland Middle School",
  "project_id":   "W1201",
  "planned_start": "2026-08-03",
  "planned_data_date": "2026-08-03"
})

// Step 2: add Pattern B DEMOLITION branch + activities
apply_xer_changes("<output_path>", [
  { "type": "add_wbs",
    "spec": { "wbs_code": "DEMO", "wbs_name": "DEMOLITION",
              "parent_wbs_id": "WBS-CONSTRUCTION" } },
  { "type": "add_activity",
    "spec": { "code": "D1010", "name": "Demolish Existing Gymnasium",
              "duration_days": 15, "calendar_id": "CAL-5DAY",
              "wbs_id": "WBS-DEMO", "activity_type": "TT_Task" } },
  { "type": "add_logic",
    "predecessor_id": "<ntp_task_id>", "successor_id": "D1010",
    "relationship": "FS", "lag_days": 0 }
])

// Step 3: validate
validate_xer_structure("<modified_output_path>")
```

---

## Historical reference: `build_from_raw_template.py`

The six-step manual generation pattern below describes the `lib/build_from_raw_template.py` script, which predates `create_xer_from_template`. It remains in `lib/` as a working reference for non-Claude callers and historical comparison, and its inline comments document template-based generation patterns. For Claude-facing workflows, use `create_xer_from_template` instead.

### Six-step pattern (historical)

1. Read template as raw bytes, decode cp1252
2. Parse into sections — preserve `%T` and `%F` lines exactly
3. Clone PROJECT/SCHEDOPTIONS from template, override needed fields
4. Build new data rows with `make_r_line()` helper (exact field count required)
5. Reassemble — skip ACTVTYPE/ACTVCODE/TASKACTV tables
6. Write with CRLF line endings, cp1252 encoding

See `lib/build_from_raw_template.py` for a working 96-task example.

### ID strategy (avoid P6 collisions)

The manual pattern used fixed counter ranges to avoid collision between WBS, task, and relationship IDs. `create_xer_from_template` / `apply_xer_changes` manages this automatically, but the ranges are documented here for anyone reading the historical script:

```python
PROJECT_ID = '99501'
wbs_counter  = 30000
task_counter = 40000
pred_counter = 50000
```

### Calendar data

The nested parenthetical `clndr_data` format is fragile — copy strings from `build_from_raw_template.py` (has working 5-day, 6-day, 7-day definitions). Never write calendar data programmatically. `westland-skeleton-v1` ships with the canonical Westland calendar strings pre-embedded.

### Westland defaults (carried into `westland-skeleton-v1`)

- WBS structure from `westland-standards.md`
- Verb + Noun activity naming (allowed acronyms: HVAC, MEP, CMU, GC, SWPPP, OAC, RFI, IFC, TAB)
- All durations stored as working days × 8 = hours in the XER
- `score_schedule` target: B+ or higher at initial generation; iterate to A grade
