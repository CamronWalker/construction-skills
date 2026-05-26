# CPM Engine Usage

==============================================================================
!! CPM RUNS IN MEMORY ONLY. NEVER WRITE RESULTS BACK TO THE ORIGINAL XER.
!! ONLY WRITE TO AN EXPLICITLY NAMED OUTPUT FILE WHEN THE USER ASKS.
==============================================================================

Do NOT rewrite the CPM engine. Load and call directly.

## Quick Start

```python
import importlib.util, os
ref_dir = 'scheduling/skills/schedule-toolbox/lib'

def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ref_dir, f'{name}.py'))
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod

cal_mod = load('calendar_engine')   # must load first
cpm_mod = load('cpm_engine')

tables = parse_xer('schedule.xer')
results, metadata = cpm_mod.schedule_forward_backward(
    tables.get('TASK', []),
    tables.get('TASKPRED', []),
    tables.get('CALENDAR', tables.get('CLNDR', [])),
    data_date,                        # 'YYYY-MM-DD HH:MM' string or datetime
    tables.get('SCHEDOPTIONS', []),   # optional
    tables.get('PROJECT', [])         # optional
)
```

`results` = task dicts updated with: `early_start_date`, `early_end_date`, `late_start_date`, `late_end_date`, `total_float_hr_cnt`, `free_float_hr_cnt`, `driving_path_flag`

`metadata` = `{sc_milestone_name, sc_milestone_date, project_end_date, circular_dependencies}`

## HTML Report (table)

```python
cpm_mod.render_schedule_html(results, 'Project Name', data_date, metadata, 'schedule.html')
```

## Gantt Review HTML (for proposal-schedule iteration)

After CPM, emit a JSON activity list and render the self-contained Gantt review HTML. The HTML is the iteration surface for the proposal-schedule loop -- Camron edits durations inline, leaves comments on activity-ID chips, clicks **Copy for Claude** to copy a structured JSON payload to his clipboard, pastes it into chat. Claude applies the changes and regenerates everything.

```python
import json, subprocess

# 1. Build the activities + paths JSON (consumed by build_gantt_html.py).
#    If Camron's paste-back included a `default_view` block, pass it through
#    so the next render restores the same zoom / units / scroll / expand state.
default_view = paste_back_payload.get('default_view') if paste_back_payload else None

data = cpm_mod.build_activities_json(
    results,                           # from schedule_forward_backward
    metadata,                          # from schedule_forward_backward
    tables.get('TASKPRED', []),
    project_name='Murray City Apex Center',
    data_date=data_date,
    wbs_rows=tables.get('PROJWBS', []),
    default_view=default_view,         # optional, from paste-back
)
json_path = '<project_folder>/schedule-activities.json'
with open(json_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

# 2. Render the self-contained HTML next to the JSON
subprocess.run(
    ['python', 'scheduling/tools/build_gantt_html.py', json_path],
    check=True,
)
# -> writes schedule-review.html in the same folder; opens directly from disk.
```

`build_activities_json()` includes the analytics layer (`paths`) the proposal-schedule skill must read **before** proposing any edit -- see `scheduling:schedule-create-proposal-schedule` § "Read the paths section first." Same JSON drives the Gantt HTML and the comprehension layer for Claude.

For the **paste-back payload schema** (what Camron pastes when he clicks Copy for Claude) and the step-by-step flow for applying it -- duration changes to the XER, comment handling, default_view round-trip -- see `scheduling:schedule-create-proposal-schedule` § "Iteration loop."

### Anchor-date check (project metadata, NOT XER constraints)

Westland best practice: **don't pin anchor dates with XER constraints** (CS_FNLT, CS_MANDSTART, etc.) -- they hide broken logic and make the schedule brittle. Anchors live as project metadata in `<project>/Proposal Schedule/proposal-anchors.json` (captured during Phase 1 of the proposal-schedule skill from the bid documents).

Before applying paste-back duration / logic changes, run a what-if CPM and check the proposed schedule against the anchors:

```python
anchors = json.load(open(f'{project}/Proposal Schedule/proposal-anchors.json'))['anchors']
slips = cpm_mod.check_anchor_dates(whatif_results, anchors, tolerance_days=0)
# slips: [] if all anchors hold; otherwise list of
#   {task_code, task_name, kind_label, anchor_date, computed_date,
#    anchor_kind, slip_days}
```

If `slips` is non-empty, do NOT regenerate. For each slip, ask the engine to suggest where to cut:

```python
for slip in slips:
    suggestions = cpm_mod.suggest_anchor_absorption(whatif_results, tables['TASKPRED'], slip)
    # suggestions: ranked list of critical-path tasks (TF <= 1d) by duration,
    # each with current_duration_days, suggested_max_cut_days, total_float_days,
    # rationale. Use these as the absorption-plan candidates.
```

Surface the ranked candidates plus any logic changes (FS -> SS, parallelize) as an absorption plan to the scheduler -- see `scheduling:schedule-create-proposal-schedule` § "Anchor milestones -- confirm before regenerating." Apply the scheduler-confirmed plan via logic and duration changes; re-run the check; only write the new XER when the check returns `[]`.

The HTML and `schedule-activities.json` are overwritten each iteration. XER versioning still follows the `-v{N}.xer` immutability rule -- only the JSON and HTML are transient.

## Engine Handles

FS/SS/FF/SF relationships, lag with configurable calendar, completed/active/not-started, calendar exceptions, SNET/FNET/SNLT/FNLT/mandatory constraints, circular dependency detection and graceful recovery.

## Circular Dependencies

```python
if metadata.get('circular_dependencies'):
    for cycle in metadata['circular_dependencies']:
        print(f"CIRCULAR: {cycle}")
        # e.g. "NTVC10430 (Install Hardware) -> NTVC10440 (Touch-up) -> NTVC10430 ..."
```
