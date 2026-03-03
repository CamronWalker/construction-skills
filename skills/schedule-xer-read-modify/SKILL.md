---
name: schedule-xer-read-modify
description: >
  Read, parse, analyze, and modify Primavera P6 XER schedule files. Use this skill whenever the user
  uploads an XER file, asks to read or inspect a P6 schedule, wants to extract activities/logic/calendars
  from an XER, needs schedule data summarized or compared, wants to modify an existing schedule
  (rename activities, adjust durations, update logic, add/remove relationships), or asks anything involving
  .xer files. Also trigger when the user mentions "XER", "P6 export", "schedule file", "import to P6",
  or asks to review/audit a schedule export. If the user wants to CREATE a new schedule from scratch,
  use the schedule-xer-generate skill instead — this skill is for working with existing XER data.
---

# Reading & Modifying Primavera P6 XER Files

This skill covers parsing, analyzing, and modifying XER files exported from Oracle Primavera P6.

## XER File Format Overview

XER is a tab-delimited text format that represents a snapshot of the P6 database. Every XER file follows this structure:

```
ERMHDR	<version>       ← Header line (always first)
%T	TABLE_NAME          ← Start of a table
%F	field1	field2	...  ← Column definitions (tab-separated)
%R	val1	val2	...    ← Data row (one per record)
%R	val1	val2	...    ← More data rows
%E                       ← End of table
%T	NEXT_TABLE           ← Next table starts
...
```

The delimiter is always a literal TAB character (`\t`). Line endings are CR. Encoding is typically Windows-1252, though modern P6 versions support UTF-8 with BOM.

## Important: Field Name Variations Across P6 Versions

P6 XER exports vary across versions. Two key differences to handle:

**Table names:** The calendar table is named `CALENDAR` in some P6 versions and `CLNDR` in others. Always check for both:
```python
calendars = tables.get('CALENDAR', tables.get('CLNDR', []))
```

**Constraint fields:** Older documentation uses `constraint_type` and `constraint_date`, but actual P6 exports use `cstr_type`, `cstr_type2`, `cstr_date`, and `cstr_date2`. Always check for both:
```python
cstr = task.get('cstr_type', task.get('constraint_type', ''))
```

**TASK table field count varies:** Real-world XERs range from ~43 to ~61+ fields in the TASK table depending on P6 version and export settings. The parser handles this automatically (fields come from `%F` row), but be aware that fields like `driving_path_flag`, `suspend_date`, `resume_date`, and many others may or may not be present. Always use `.get()` with defaults when accessing TASK fields.

**Relationship type prefixes:** Most real P6 exports use the `PR_` prefix format (`PR_FS`, `PR_SS`, `PR_FF`, `PR_SF`). Some older or third-party exports use bare codes (`FS`, `SS`, etc.). Always check for both:
```python
fs_types = {'FS', 'PR_FS'}
is_fs = pred.get('pred_type', '') in fs_types
```

**Constraint classification (check BOTH `cstr_type` and `cstr_type2`):**
```python
hard_codes = {
    'CS_MSO', 'CS_MFO', 'CS_MEO',              # Mandatory Start/Finish/End On
    'CS_MANDSTART', 'CS_MANDEND', 'CS_MANDFIN'  # Mandatory Start/End/Finish
}
# CS_MSOA/MSOB/MEOA/MEOB are "On or After/Before" = SOFT (like SNET/SNLT)
soft_codes = {
    'CS_SNET', 'CS_SNLT', 'CS_FNET', 'CS_FNLT', 'CS_ALAP',
    'CS_MSOA', 'CS_MSOB', 'CS_MEOA', 'CS_MEOB'
}
```

## Core Tables

These are the tables you'll encounter most often. An XER can contain up to ~66 tables, but most exports use fewer than 20.

### PROJECT — Project definition
Key fields: `project_id`, `project_name`, `start_date`, `end_date`, `default_clndr_id`

### PROJWBS — Work Breakdown Structure
Key fields: `wbs_id`, `project_id`, `parent_wbs_id`, `wbs_short_name`, `wbs_name`, `seq_num`
Self-referencing hierarchy — `parent_wbs_id` points to the parent node's `wbs_id`. Root nodes have no parent.

### TASK — Activities
Key fields: `task_id`, `task_name`, `proj_id`, `wbs_id`, `target_drtn_hr_cnt`, `remain_drtn_hr_cnt`, `cstr_type`, `cstr_date`, `cstr_type2`, `cstr_date2`, `early_start_date`, `early_end_date`, `late_start_date`, `late_end_date`, `status_code`, `task_type`, `clndr_id`, `phys_complete_pct`, `total_float_hr_cnt`, `free_float_hr_cnt`, `driving_path_flag`

Duration is stored in **hours** (e.g., 80 = 10 eight-hour days). Status codes: `TK_Active`, `TK_Complete`, `TK_NotStart`.

**Note on field names:** The TASK table uses `proj_id` (not `project_id`), `early_end_date` (not `early_finish_date`), `cstr_type` (not `constraint_type`), and `cstr_date` (not `constraint_date`). P6 supports dual constraints via `cstr_type2`/`cstr_date2`.

### TASKPRED — Relationships (Logic Ties)
Key fields: `task_pred_id`, `task_id`, `pred_task_id`, `proj_id`, `pred_proj_id`, `pred_type`, `lag_hr_cnt`

**Critical:** In the TASKPRED table, the `task_id` field is the **successor** activity, NOT the predecessor. The predecessor is in `pred_task_id`. This is a common source of confusion — the field name `task_id` makes it look like a generic FK, but it specifically means "the task that depends on the predecessor."

Relationship types:
- **FS** (Finish-to-Start) — most common, the default
- **SS** (Start-to-Start)
- **FF** (Finish-to-Finish)
- **SF** (Start-to-Finish) — rare

`lag_hr_cnt` is in hours. Positive = lag/delay, negative = lead/overlap.

### CALENDAR / CLNDR — Calendars
Key fields: `clndr_id`, `clndr_name`, `clndr_data`

**Note:** This table is named `CALENDAR` in some P6 versions and `CLNDR` in others. Always check for both when parsing.

The `clndr_data` field uses a nested parenthetical format to encode workdays and exceptions. See the reference file `references/xer-tables.md` for the full calendar encoding specification.

### ACTVTYPE / ACTVCODE — Activity Code Types and Values
ACTVTYPE defines code categories (e.g., "Discipline", "Phase", "Area"). ACTVCODE stores the actual values within each category. Scope can be Global, EPS, or Project-level.

### TASKRSRC — Resource Assignments
Links tasks to resources with budgeted and actual quantities/costs.

### UDFTYPE / UDFVALUE — User-Defined Fields
Custom fields attached to any object. UDFTYPE defines the field; UDFVALUE stores values keyed by `fk_id` (the object's ID).

## How to Parse an XER File

Use Python. The recommended approach:

```python
def parse_xer(file_path):
    """Parse an XER file into a dict of table_name -> list of dicts."""
    tables = {}
    current_table = None
    current_fields = None

    # Try multiple encodings — real-world XERs vary widely
    for encoding in ['cp1252', 'utf-8-sig', 'utf-8', 'latin-1']:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    for line in content.split('\n'):
        line = line.rstrip('\r\n')
        if not line:
            continue

        parts = line.split('\t')
        marker = parts[0]

        if marker == 'ERMHDR':
            tables['_header'] = parts[1:]
        elif marker == '%T':
            current_table = parts[1]
            tables[current_table] = []
        elif marker == '%F':
            current_fields = parts[1:]
        elif marker == '%R' and current_table and current_fields:
            values = parts[1:]
            # Pad with empty strings if fewer values than fields
            while len(values) < len(current_fields):
                values.append('')
            record = dict(zip(current_fields, values))
            tables[current_table].append(record)
        elif marker == '%E':
            current_table = None
            current_fields = None

    return tables
```

This gives you a clean dictionary where each table name maps to a list of row-dicts. From there you can filter, analyze, or modify any data.

### Alternative: Use xerparser library

```bash
pip install xerparser
```

```python
from xerparser import Xer

xer = Xer.reader("schedule.xer")
for task in xer.tasks:
    print(task.name, task.duration, task.start, task.finish)
```

The library handles encoding, date parsing, and relationship resolution automatically. Use it when you need speed. Use the manual parser when you need full control (especially for writing modified XER back out).

## Scope Filtering for Analysis

When analyzing a schedule for quality metrics, you almost always want to filter to **incomplete activities only** (status != `TK_Complete`). Completed activities are historical data — they don't affect the remaining schedule. Tools like SmartPM, Acumen, and schedule review boards all scope their analysis to incomplete work.

```python
def filter_to_incomplete_scope(tables):
    """Filter tasks and relationships to incomplete scope only."""
    tasks = tables.get('TASK', [])
    preds = tables.get('TASKPRED', [])

    # Keep only incomplete activities (not completed, not WBS summary, not LOE)
    exclude_types = {'TT_WBS', 'TT_LOE'}
    milestone_types = {'TT_Mile', 'TT_FinMile'}

    incomplete = [t for t in tasks
                  if t.get('status_code', '') != 'TK_Complete'
                  and t.get('task_type', '') not in exclude_types]
    incomplete_ids = {t['task_id'] for t in incomplete}

    # Filter relationships to only those between incomplete activities
    # TASKPRED.task_id = successor, TASKPRED.pred_task_id = predecessor
    filtered_rels = [r for r in preds
                     if r.get('task_id', '') in incomplete_ids
                     and r.get('pred_task_id', '') in incomplete_ids]

    # Separate activities from milestones for metric calculations
    activities = [t for t in incomplete if t.get('task_type', '') not in milestone_types]
    milestones = [t for t in incomplete if t.get('task_type', '') in milestone_types]

    return incomplete, activities, milestones, filtered_rels
```

Always report both the total schedule size and the incomplete scope size so the reviewer understands what was analyzed.

## Common Analysis Tasks

### Summarize a schedule
1. Parse the XER
2. Count activities by status (`TK_Active`, `TK_Complete`, `TK_NotStart`)
3. List WBS nodes with activity counts
4. Identify the critical path (activities where `total_float_hr_cnt` equals zero or is very small)
5. Report start/finish dates, total duration, milestone count

### Compare two schedules
1. Parse both XER files
2. Match activities by `task_id` or `task_code` (activity ID visible in P6)
3. Compare: duration changes, date shifts, added/removed activities, logic changes
4. Flag constraint changes (especially hard constraints added — often a schedule quality concern)

### Extract logic network
1. Parse TASK and TASKPRED tables
2. Build a directed graph: nodes = tasks, edges = relationships
3. Remember: TASKPRED `task_id` = successor, `pred_task_id` = predecessor
4. Check for: open ends (tasks with no predecessor or no successor), circular logic, dangling relationships

## How to Modify an XER File

The safest approach: parse the XER, modify the in-memory data, then write it back out preserving the original structure.

### Writing a modified XER

```python
def write_xer(tables, output_path, encoding='cp1252'):
    """Write parsed XER data back to a valid XER file."""
    with open(output_path, 'w', encoding=encoding, newline='') as f:
        # Write header
        if '_header' in tables:
            f.write('ERMHDR\t' + '\t'.join(tables['_header']) + '\r')

        for table_name, records in tables.items():
            if table_name == '_header' or not records:
                continue

            # Get field names from the first record
            fields = list(records[0].keys())

            f.write(f'%T\t{table_name}\r')
            f.write('%F\t' + '\t'.join(fields) + '\r')
            for record in records:
                values = [str(record.get(field, '')) for field in fields]
                f.write('%R\t' + '\t'.join(values) + '\r')
            f.write('%E\r')
```

### Critical rules when modifying:

1. **Preserve field order** — the `%F` row defines column order. Every `%R` row must match exactly.
2. **Don't break foreign keys** — if you delete a task, also remove its TASKPRED entries and TASKRSRC assignments.
3. **Keep IDs unique** — never duplicate a `task_id` within a project.
4. **Empty fields = empty string between tabs** — don't skip fields, leave them blank.
5. **Date format**: `YYYY-MM-DD HH:MM` — maintain this consistently.
6. **Duration in hours** — if someone says "10 days" and the calendar is 8hr/day, that's 80 hours.

### Common modifications

**Rename activities:**
```python
for task in tables['TASK']:
    if task['task_id'] == '12345':
        task['task_name'] = 'New Activity Name'
```

**Adjust durations:**
```python
for task in tables['TASK']:
    if task['wbs_id'] == '500':  # All tasks under a specific WBS
        hours = float(task['target_drtn_hr_cnt'])
        task['target_drtn_hr_cnt'] = str(hours * 1.1)  # 10% increase
        task['remain_drtn_hr_cnt'] = task['target_drtn_hr_cnt']
```

**Add a relationship:**
```python
new_pred = {
    'task_pred_id': '99999',  # Unique ID
    'task_id': '1002',        # Successor (task_id = successor in TASKPRED!)
    'pred_task_id': '1001',   # Predecessor
    'proj_id': project_id,
    'pred_proj_id': project_id,
    'pred_type': 'PR_FS',
    'lag_hr_cnt': '0'
}
tables['TASKPRED'].append(new_pred)
```

**Remove activities:**
```python
remove_ids = {'5001', '5002', '5003'}
tables['TASK'] = [t for t in tables['TASK'] if t['task_id'] not in remove_ids]
# task_id in TASKPRED = successor, pred_task_id = predecessor
tables['TASKPRED'] = [p for p in tables['TASKPRED']
                       if p['pred_task_id'] not in remove_ids
                       and p['task_id'] not in remove_ids]
tables['TASKRSRC'] = [r for r in tables['TASKRSRC']
                       if r['task_id'] not in remove_ids]
```

## Validation Before Export

Before writing a modified XER, always validate:

1. **Referential integrity** — every `wbs_id` in TASK exists in PROJWBS, every `clndr_id` exists in CALENDAR/CLNDR, every `task_id` (successor) and `pred_task_id` (predecessor) in TASKPRED exists in TASK
2. **No circular logic** — build the relationship graph and check for cycles
3. **No orphan activities** — every task should have at least one predecessor or successor (except project start/finish milestones)
4. **Field count consistency** — every `%R` row has the same number of fields as `%F`
5. **ID uniqueness** — no duplicate `task_id`, `wbs_id`, etc. within their scope

```python
def validate_xer(tables):
    """Basic validation — returns list of issues found."""
    issues = []
    task_ids = {t['task_id'] for t in tables.get('TASK', [])}
    wbs_ids = {w['wbs_id'] for w in tables.get('PROJWBS', [])}

    # Handle both CALENDAR and CLNDR table names
    calendars = tables.get('CALENDAR', tables.get('CLNDR', []))
    clndr_ids = {c['clndr_id'] for c in calendars}

    for task in tables.get('TASK', []):
        if task.get('wbs_id') and task['wbs_id'] not in wbs_ids:
            issues.append(f"Task {task['task_id']} references missing WBS {task['wbs_id']}")
        if task.get('clndr_id') and task['clndr_id'] not in clndr_ids:
            issues.append(f"Task {task['task_id']} references missing calendar {task['clndr_id']}")

    for pred in tables.get('TASKPRED', []):
        if pred['pred_task_id'] not in task_ids:
            issues.append(f"Relationship {pred['task_pred_id']} references missing predecessor {pred['pred_task_id']}")
        # task_id in TASKPRED is the SUCCESSOR, not a generic ID
        if pred.get('task_id') and pred['task_id'] not in task_ids:
            issues.append(f"Relationship {pred['task_pred_id']} references missing successor {pred['task_id']}")

    # Check for duplicate task IDs
    if len(task_ids) != len(tables.get('TASK', [])):
        issues.append("Duplicate task IDs detected")

    return issues
```

## Reference Files

For detailed table schemas and the full calendar encoding format, read `references/xer-tables.md`. Only load this reference when you need field-level detail beyond what's covered above.
