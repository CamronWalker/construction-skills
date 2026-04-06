---
name: schedule-xer
description: >
  Read, parse, analyze, modify, and generate Primavera P6 XER schedule files. Use this skill whenever
  the user uploads an XER file, asks to read or inspect a P6 schedule, wants to extract activities/logic/
  calendars from an XER, needs schedule data summarized or compared, wants to modify an existing schedule,
  or wants to create a new schedule from scratch. Also trigger when the user mentions "XER", "P6 export",
  "schedule file", "import to P6", "generate XER", "create XER", "build a schedule", "parse XER",
  "read XER", or asks to review/audit a schedule export.
---

# Primavera P6 XER File Operations

This skill handles all XER file operations: parsing, reading, analyzing, modifying, and generating new schedules.

## XER File Format

- **Tab-delimited** text with **CRLF** (`\r\n`) line endings
- **Encoding:** cp1252 (most common). Fallbacks: utf-8-sig, utf-8, latin-1
- **Structure:** `ERMHDR` header, then repeating `%T` (table), `%F` (fields), `%R` (data rows), `%E` (end)
- **P6 gives no error messages on import failure** — structure must be exact

```
ERMHDR	12.0	...
%T	TABLE_NAME
%F	field1	field2	field3
%R	val1	val2	val3
%R	val1	val2	val3
%E
```

## Core Tables Quick Reference

### PROJECT
Key fields: `project_id`, `project_name`, `start_date`, `end_date`, `default_clndr_id`, `data_date`, `last_recalc_date`

### PROJWBS (Work Breakdown Structure)
Self-referencing hierarchy: `wbs_id`, `wbs_name`, `parent_wbs_id`. Parent points to parent node's `wbs_id`.

### TASK (Activities)
Key fields: `task_id`, `task_code`, `task_name`, `proj_id`, `wbs_id`, `target_drtn_hr_cnt`, `remain_drtn_hr_cnt`, `cstr_type`, `cstr_date`, `status_code`, `task_type`, `phys_complete_pct`, `total_float_hr_cnt`

- **Durations in hours** (e.g., 80 = 10 eight-hour days)
- **Status:** `TK_Active`, `TK_Complete`, `TK_NotStart`
- **Types:** `TT_Task` (work), `TT_Mile` (start milestone), `TT_FinMile` (finish milestone), `TT_WBS` (summary), `TT_LOE` (level of effort)

### TASKPRED (Relationships)
**CRITICAL: `task_id` = SUCCESSOR (not predecessor!)**
- `pred_task_id` = predecessor
- `pred_type`: `PR_FS` / `PR_SS` / `PR_FF` / `PR_SF` (or bare `FS`/`SS`/`FF`/`SF` in older exports)
- `lag_hr_cnt`: hours (positive = lag, negative = lead)

### CALENDAR / CLNDR
Table name varies by P6 version. `clndr_data` uses fragile nested parenthetical format — **copy from real exports, never build programmatically**.

## Field Name Variations (Handle Both)
- Calendar table: `CALENDAR` or `CLNDR`
- Constraint fields: `cstr_type`/`cstr_date` (actual P6) or `constraint_type`/`constraint_date` (older docs)
- Project ID in TASK: `proj_id` (not `project_id`)
- Relationship prefixes: `PR_FS` (modern P6) or `FS` (older/third-party)

---

## Reading & Parsing

```python
def parse_xer(file_path):
    """Parse XER into dict of table_name -> list of row dicts."""
    for enc in ['cp1252', 'utf-8-sig', 'utf-8', 'latin-1']:
        try:
            with open(file_path, 'rb') as f:
                raw = f.read()
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    tables = {}
    current_table = None
    fields = []
    for line in text.split('\r\n'):
        if line.startswith('%T'):
            current_table = line.split('\t')[1].strip()
            tables[current_table] = []
        elif line.startswith('%F'):
            fields = [f.strip() for f in line.split('\t')[1:]]
        elif line.startswith('%R') and current_table:
            vals = line.split('\t')[1:]
            row = dict(zip(fields, vals))
            tables[current_table].append(row)
    return tables
```

### Scope Filtering
```python
incomplete = [t for t in tasks if t.get('status_code') != 'TK_Complete'
              and t.get('task_type', '') not in ('TT_WBS', 'TT_LOE')]
```

---

## Modifying XER Files

Common modifications:
- **Rename activities:** Update `task_name` in TASK rows
- **Adjust durations:** Update `target_drtn_hr_cnt` and `remain_drtn_hr_cnt` (in hours: days x 8)
- **Add relationships:** Create new TASKPRED row with `make_r_line()` pattern
- **Remove activities:** Filter TASK + TASKPRED + TASKRSRC rows

### Writing Modified XER
```python
def write_xer(tables, field_orders, output_path, encoding='cp1252'):
    """Write parsed data back preserving structure."""
    # Preserve %T and %F lines byte-for-byte from original
    # Replace only %R rows with modified data
    # Write with '\r\n'.encode(encoding)
```

---

## Generating New XER Files

**Always use template-based generation** — never build from scratch with dicts. The XER format has too many implicit rules that can silently break P6 import.

### Six-Step Generation Pattern
1. **Read template** as raw bytes, decode as cp1252
2. **Parse into sections** preserving `%T` and `%F` lines exactly
3. **Clone PROJECT/SCHEDOPTIONS** from template, override needed fields (project_id, project_name, dates)
4. **Build new data rows** using `make_r_line()` helper — ensures exact field count per table
5. **Reassemble**, skipping ACTVTYPE/ACTVCODE/TASKACTV tables (not needed for clean import)
6. **Write** with CRLF line endings and cp1252 encoding

### ID Strategy (avoid collisions with existing P6 data)
```python
PROJECT_ID = '99501'
CLNDR_IDS = '99601'   # start for calendar IDs
wbs_counter = 30000    # start for WBS IDs
task_counter = 40000   # start for task IDs
pred_counter = 50000   # start for relationship IDs
```

### Calendar Data
The nested parenthetical format is fragile. Copy calendar `clndr_data` strings from the template or from `references/build_from_raw_template.py` which contains working 5-day, 6-day, and 7-day calendar definitions.

### Westland Defaults
Unless instructed otherwise:
- Use the Westland WBS structure from the `schedule-standards` skill
- Include milestones every 30 days
- Assign Westland responsibility codes
- Follow Verb + Noun activity naming (allowed acronyms: HVAC, MEP, CMU, GC, SWPPP, OAC, RFI, IFC, TAB)
- All durations in working days x 8 = hours for XER storage

---

## Validation

### File-Level Checks
- `%F` field count matches `%R` value count for every table
- CRLF line endings throughout
- cp1252 encoding

### Logic Checks
- Every non-milestone activity has a WBS assignment
- Every non-milestone, non-LOE activity has at least one predecessor AND successor (except project start/finish milestones)
- No circular logic (topological sort succeeds)
- No duplicate relationships
- All referenced WBS IDs, calendar IDs exist

### Quality Backcheck
After generation, score using the `schedule-standards` skill. Target: B+ or higher for initial generation. Iterate to achieve A grade.

### Output Checklist
- [ ] File re-reads without errors
- [ ] CRLF line endings confirmed
- [ ] Quality score B+ or higher
- [ ] WBS structure follows Westland standards (or justified deviation)
- [ ] Activity count reasonable for project scope
- [ ] Complete logic network (no open starts/finishes except project milestones)
- [ ] Reasonable durations (no activities > 44 working days without justification)
- [ ] Appropriate calendar assigned

---

## Reference Files

| File | When to Load |
|------|-------------|
| `references/xer-tables.md` | Complete field definitions for all 17+ XER tables — load for detailed field lookups, constraint codes, task types |
| `references/build_from_raw_template.py` | Working 96-task example script (elementary school schedule, scores A-). Load when generating a new XER — use as the pattern and adapt for the project. |
| `references/calendar_engine.py` | Calendar parsing & workday arithmetic — load with cpm_engine.py |
| `references/cpm_engine.py` | CPM forward/backward pass — load when calculating dates/float |
| `references/path_analysis.py` | SC path coverage & delay impact — load for path/delay work |
| `references/xer_compare.py` | Multi-schedule comparison — load when comparing schedule updates |

---

## Advanced Analysis (load only when needed)

These reference scripts are pure-function libraries. Parse the XER first, then pass data in and get results out. No editing needed — just call the functions. All produce standalone HTML reports.

**CPM Calculation (dates, float):** Load `calendar_engine.py` + `cpm_engine.py`. Call `schedule_forward_backward(tasks, preds, calendars, data_date)` → returns updated tasks with ES/EF/LS/LF, total/free float, driving path flag. Also returns `cpm_metadata` with SC milestone info. Call `render_schedule_html(tasks, project_name, data_date, metadata, output_path)` for HTML report.

**SC Path Coverage:** Load `path_analysis.py`. Call `analyze_sc_path_coverage(tasks, preds, wbs_rows)` → returns connected/disconnected activity counts by WBS, coverage %, recommendations. Call `render_coverage_html(data, output_path)` for HTML report.

**Delay Impact / TIA:** Load all three: `calendar_engine.py` + `cpm_engine.py` + `path_analysis.py`. Call `compute_delay_impacts(tasks, preds, calendars, data_date)` → auto-detects IMPACT activities, traces driving paths to SC, computes variance. Call `render_delay_html(data, output_path)` for HTML report.

**Per-Activity Path Insight:** Load same three. Call `analyze_activity_paths(tasks, preds, calendars, data_date)` → for every activity: driving path to SC, float, critical status, path length. Call `render_paths_html(data, output_path)` for HTML report.

**Schedule Comparison:** Load `xer_compare.py`. Call `compare_schedules(current_tables, baseline_tables=None, previous_tables=None)` → flexible comparison: current vs baseline, vs previous update, or both. Always reports missed starts/finishes. SC tracking across all provided schedules. Call `render_comparison_html(data, output_path)` for HTML report.

All reports identify which milestone they're tracking to (Substantial Completion by default).
