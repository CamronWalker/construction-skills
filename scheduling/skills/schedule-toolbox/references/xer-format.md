# XER File Format & Parsing

## Format

- Tab-delimited text, CRLF (`\r\n`) line endings
- Encoding: cp1252 most common. Fallbacks: utf-8-sig, utf-8, latin-1
- Structure: `ERMHDR` header → repeating `%T` / `%F` / `%R` rows → `%E` end
- P6 gives no error on import failure — structure must be exact

## Core Tables

| Table | Key Fields |
|-------|-----------|
| TASK | `task_id`, `task_code`, `task_name`, `proj_id`, `wbs_id`, `target_drtn_hr_cnt`, `remain_drtn_hr_cnt`, `cstr_type`, `cstr_date`, `status_code`, `task_type`, `phys_complete_pct`, `total_float_hr_cnt` |
| TASKPRED | `task_id` (SUCCESSOR), `pred_task_id` (predecessor), `pred_type`, `lag_hr_cnt` |
| PROJECT | `project_id`, `proj_short_name`, `start_date`, `end_date`, `default_clndr_id`, `data_date`, `last_recalc_date` |
| SCHEDOPTIONS | `sched_calendar_on_relationship_lag` (`rcal_Successor` default), `sched_retained_logic` (Y/N) |
| RSRC | `rsrc_id`, `rsrc_short_name`, `rsrc_name`, `rsrc_type` |
| TASKRSRC | `task_id`, `rsrc_id`, `target_cost`, `remain_cost`, `act_reg_cost`, `act_ot_cost` |

**TASKPRED direction:** `task_id` = successor, `pred_task_id` = predecessor. Easy to get backwards.

Durations are in **hours** (days × 8). Status: `TK_Active` / `TK_Complete` / `TK_NotStart`. Types: `TT_Task`, `TT_Mile`, `TT_FinMile`, `TT_WBS`, `TT_LOE`.

Field name note: `cstr_type`/`cstr_date` are Oracle-correct. Calendar table is `CALENDAR` or `CLNDR` depending on P6 version.

## Parse Function

```python
def parse_xer(file_path):
    for enc in ['cp1252', 'utf-8-sig', 'utf-8', 'latin-1']:
        try:
            text = open(file_path, 'rb').read().decode(enc); break
        except (UnicodeDecodeError, LookupError): continue
    tables = {}; current_table = None; fields = []
    for line in text.split('\r\n'):
        if line.startswith('%T'):
            current_table = line.split('\t')[1].strip(); tables[current_table] = []
        elif line.startswith('%F'):
            fields = [f.strip() for f in line.split('\t')[1:]]
        elif line.startswith('%R') and current_table:
            tables[current_table].append(dict(zip(fields, line.split('\t')[1:])))
    return tables
```

## Scope Filter

```python
incomplete = [t for t in tasks
              if t.get('status_code') != 'TK_Complete'
              and t.get('task_type', '') not in ('TT_WBS', 'TT_LOE')]
```

## Modifying XER

See `xer-modify.md` for the full write-back pattern.

==============================================================================
NEVER OVERWRITE THE ORIGINAL XER FILE. WRITE TO A NEW PATH ONLY.
==============================================================================

## Table Field Lookup

```bash
grep -A 60 "^## TABLENAME" references/xer-tables.md | head -65
```
