# CPM Engine Usage

==============================================================================
!! CPM RUNS IN MEMORY ONLY. NEVER WRITE RESULTS BACK TO THE ORIGINAL XER.
!! ONLY WRITE TO AN EXPLICITLY NAMED OUTPUT FILE WHEN THE USER ASKS.
==============================================================================

Do NOT rewrite the CPM engine. Load and call directly.

## Quick Start

```python
import importlib.util, os
ref_dir = 'scheduling/skills/schedule-toolbox/references'

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

## HTML Report

```python
cpm_mod.render_schedule_html(results, 'Project Name', data_date, metadata, 'schedule.html')
```

## Engine Handles

FS/SS/FF/SF relationships, lag with configurable calendar, completed/active/not-started, calendar exceptions, SNET/FNET/SNLT/FNLT/mandatory constraints, circular dependency detection and graceful recovery.

## Circular Dependencies

```python
if metadata.get('circular_dependencies'):
    for cycle in metadata['circular_dependencies']:
        print(f"CIRCULAR: {cycle}")
        # e.g. "NTVC10430 (Install Hardware) -> NTVC10440 (Touch-up) -> NTVC10430 ..."
```
