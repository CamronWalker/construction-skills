# XER Table Reference — Full Field Definitions

This reference contains detailed field definitions for all major XER tables. Load this file when you need field-level precision beyond the SKILL.md overview.

## Table of Contents
1. [ERMHDR — File Header](#ermhdr)
2. [PROJECT](#project)
3. [PROJWBS](#projwbs)
4. [TASK](#task)
5. [TASKPRED](#taskpred)
6. [CLNDR — Calendars](#clndr)
7. [ACTVTYPE — Activity Code Types](#actvtype)
8. [ACTVCODE — Activity Code Values](#actvcode)
9. [TASKACTV — Activity Code Assignments](#taskactv)
10. [RSRC — Resources](#rsrc)
11. [TASKRSRC — Resource Assignments](#taskrsrc)
12. [UDFTYPE — User-Defined Field Types](#udftype)
13. [UDFVALUE — User-Defined Field Values](#udfvalue)
14. [OBS — Organizational Breakdown Structure](#obs)
15. [ACCOUNT — Cost Accounts](#account)
16. [CURRTYPE — Currency Types](#currtype)
17. [Calendar Data Encoding](#calendar-encoding)
18. [Date Encoding in Calendars](#date-encoding)
19. [Validation Checklist](#validation-checklist)

---

## ERMHDR

The first line of every XER file. Format: `ERMHDR\t<version>\t<date>\t<project_name>\t<user>\t<db_name>`

| Field | Position | Description |
|-------|----------|-------------|
| Version | 1 | P6 version (e.g., `07.00`, `21.00`) |
| Export Date | 2 | When the file was exported |
| Project Name | 3 | Name of exported project |
| User | 4 | Username who performed export |
| Database | 5 | Source database name |

Not all fields are always present — some exports include only the version.

---

## PROJECT

| Field | Type | Description |
|-------|------|-------------|
| project_id | Integer | Unique project identifier |
| proj_short_name | String | Short code (what shows in P6 project list) |
| project_name | String | Full project name |
| start_date | DateTime | Project planned start |
| end_date | DateTime | Project planned finish |
| data_date | DateTime | Schedule data date (status date) |
| default_clndr_id | Integer | FK to CLNDR — default calendar for new activities |
| sched_data | Y/N | Whether project contains scheduling data |
| plan_start_date | DateTime | Baseline planned start |
| plan_end_date | DateTime | Baseline planned finish |
| last_recalc_date | DateTime | Last time schedule was calculated |
| def_complete_pct_type | String | How % complete is calculated |
| task_code_prefix | String | Activity ID prefix |
| task_code_base | Integer | Next auto-generated activity number |

---

## PROJWBS

| Field | Type | Description |
|-------|------|-------------|
| wbs_id | Integer | Unique WBS node identifier |
| project_id | Integer | FK to PROJECT |
| parent_wbs_id | Integer | FK to self — parent node (null = root) |
| wbs_short_name | String | WBS code (e.g., "1.1.2") |
| wbs_name | String | Full WBS name |
| seq_num | Integer | Display order among siblings |
| status_code | String | Active/Inactive |
| est_wt | Decimal | Estimated weight |
| sum_data_flag | Y/N | Whether to summarize data at this level |

---

## TASK

**Field name variation:** The constraint fields are named `cstr_type` / `cstr_date` in actual P6 exports, not `constraint_type` / `constraint_date`. The `project_id` field appears as `proj_id` in TASK. Always check the actual `%F` header row when parsing.

| Field | Type | Description |
|-------|------|-------------|
| task_id | Integer | Unique activity identifier |
| task_code | String | Activity ID visible in P6 (e.g., "A1010") |
| task_name | String | Activity description |
| proj_id | Integer | FK to PROJECT (note: `proj_id` not `project_id`) |
| wbs_id | Integer | FK to PROJWBS |
| clndr_id | Integer | FK to CALENDAR/CLNDR — activity calendar |
| target_drtn_hr_cnt | Decimal | Original duration (hours) |
| remain_drtn_hr_cnt | Decimal | Remaining duration (hours) |
| target_work_qty | Decimal | Budgeted work units |
| act_work_qty | Decimal | Actual work units |
| remain_work_qty | Decimal | Remaining work units |
| cstr_type | String | Primary constraint type (see Constraint Types below) |
| cstr_date | DateTime | Primary constraint date (if applicable) |
| cstr_type2 | String | Secondary constraint type |
| cstr_date2 | DateTime | Secondary constraint date |
| early_start_date | DateTime | Calculated early start |
| early_end_date | DateTime | Calculated early finish |
| late_start_date | DateTime | Calculated late start |
| late_end_date | DateTime | Calculated late finish |
| act_start_date | DateTime | Actual start |
| act_end_date | DateTime | Actual finish |
| target_start_date | DateTime | Target/baseline start |
| target_end_date | DateTime | Target/baseline finish |
| expect_end_date | DateTime | Expected finish (manual override) |
| restart_date | DateTime | Restart date (for suspended activities) |
| reend_date | DateTime | Reend date (for suspended activities) |
| status_code | String | TK_NotStart, TK_Active, TK_Complete |
| task_type | String | TT_Task, TT_Mile, TT_FinMile, TT_LOE, TT_Rsrc, TT_WBS |
| duration_type | String | DT_FixedDrtn, DT_FixedUnits, DT_FixedWork |
| complete_pct_type | String | CP_Phys, CP_Drtn, CP_Units (note: some exports use `percent_comp_type`) |
| phys_complete_pct | Decimal | Physical % complete (0-100) |
| total_float_hr_cnt | Decimal | Total float (hours) |
| free_float_hr_cnt | Decimal | Free float (hours) |
| priority_type | String | Activity priority |
| suspend_date | DateTime | Suspend date |
| resume_date | DateTime | Resume date |
| driving_path_flag | Y/N | On longest path? |
| external_early_start_date | DateTime | External early start (inter-project) |
| external_late_end_date | DateTime | External late end (inter-project) |
| guid | String | Globally unique identifier |
| rsrc_id | Integer | Primary resource ID |
| create_date | DateTime | When activity was created |

### Task Types
- **TT_Task** — Standard activity with duration
- **TT_Mile** — Start milestone (zero duration)
- **TT_FinMile** — Finish milestone (zero duration)
- **TT_LOE** — Level of Effort (spans the duration of linked activities)
- **TT_Rsrc** — Resource-dependent task
- **TT_WBS** — WBS summary task

### Constraint Types

P6 constraint codes vary between versions and exports. Always check for ALL variants when filtering:

**Soft constraints (work with the network):**
- **CS_ASAP** — As Soon As Possible (default)
- **CS_ALAP** — As Late As Possible
- **CS_SNET** — Start No Earlier Than
- **CS_FNET** — Finish No Earlier Than
- **CS_SNLT** — Start No Later Than
- **CS_FNLT** — Finish No Later Than

**Hard constraints (mandatory — override the network):**
- **CS_MSO** / **CS_MFO** / **CS_MEO** — Mandatory Start/Finish/End On
- **CS_MANDSTART** / **CS_MANDEND** / **CS_MANDFIN** — Mandatory Start/End/Finish

**Soft constraints (directional — set boundaries but respect logic):**
- **CS_MSOA** / **CS_MSOB** — Start On or After/Before (equivalent to SNET/SNLT)
- **CS_MEOA** / **CS_MEOB** — Finish On or After/Before (equivalent to FNET/FNLT)
- **CS_SNET** / **CS_SNLT** / **CS_FNET** / **CS_FNLT** / **CS_ALAP**

When checking for constraints in code:
```python
hard_codes = {'CS_MSO', 'CS_MFO', 'CS_MEO', 'CS_MANDSTART', 'CS_MANDEND', 'CS_MANDFIN'}
soft_codes = {'CS_SNET', 'CS_SNLT', 'CS_FNET', 'CS_FNLT', 'CS_ALAP',
              'CS_MSOA', 'CS_MSOB', 'CS_MEOA', 'CS_MEOB'}
cstr = task.get('cstr_type', task.get('constraint_type', ''))
is_hard = cstr in hard_codes
```

---

## TASKPRED

**Critical:** The `task_id` field in TASKPRED is the **successor** activity, NOT a generic FK. This is the most common source of confusion when building predecessor/successor lookups.

| Field | Type | Description |
|-------|------|-------------|
| task_pred_id | Integer | Unique relationship identifier |
| task_id | Integer | FK to TASK — **the successor** (the activity that depends on the predecessor) |
| pred_task_id | Integer | FK to TASK — the predecessor |
| proj_id | Integer | FK to PROJECT |
| pred_proj_id | Integer | FK to PROJECT (for cross-project links) |
| pred_type | String | Relationship type (see below) |
| lag_hr_cnt | Decimal | Lag in hours (negative = lead) |

**Note on pred_type:** Some XER versions use prefixed codes (`PR_FS`, `PR_SS`, `PR_FF`, `PR_SF`) while others use short codes (`FS`, `SS`, `FF`, `SF`). Always check the actual data when parsing:
```python
pred_type = rel.get('pred_type', '')
is_fs = pred_type in ('FS', 'PR_FS')
```

**Building predecessor/successor lookups:**
```python
# Successors of a given task
successors = {}
for r in tables.get('TASKPRED', []):
    pred_id = r['pred_task_id']
    succ_id = r['task_id']  # task_id IS the successor
    successors.setdefault(pred_id, []).append(succ_id)

# Predecessors of a given task
predecessors = {}
for r in tables.get('TASKPRED', []):
    succ_id = r['task_id']  # task_id IS the successor
    pred_id = r['pred_task_id']
    predecessors.setdefault(succ_id, []).append(pred_id)
```

---

## CALENDAR / CLNDR

**Table name variation:** This table is named `CALENDAR` in some P6 exports and `CLNDR` in others. Always check for both:
```python
calendars = tables.get('CALENDAR', tables.get('CLNDR', []))
```

| Field | Type | Description |
|-------|------|-------------|
| clndr_id | Integer | Unique calendar identifier |
| clndr_name | String | Calendar name |
| clndr_type | String | CA_Base, CA_Project, CA_Rsrc |
| base_clndr_id | Integer | FK to self — parent calendar (for derived calendars) |
| proj_id | Integer | FK to PROJECT (for project calendars) |
| clndr_data | String | Encoded work hours and exceptions (see below) |
| last_chng_date | DateTime | Last modified date |

---

## ACTVTYPE

| Field | Type | Description |
|-------|------|-------------|
| actv_code_type_id | Integer | Unique code type identifier |
| actv_code_type | String | Code type name |
| actv_short_len | Integer | Max length of code values |
| seq_num | Integer | Display order |
| actv_code_type_scope | String | AS_Global, AS_EPS, AS_Project |
| proj_id | Integer | FK to PROJECT (if project-scoped) |

---

## ACTVCODE

| Field | Type | Description |
|-------|------|-------------|
| actv_code_id | Integer | Unique code value identifier |
| actv_code_type_id | Integer | FK to ACTVTYPE |
| parent_actv_code_id | Integer | FK to self (hierarchical codes) |
| actv_code_name | String | Code value text |
| short_name | String | Short code |
| seq_num | Integer | Display order |
| color | Integer | Display color |

---

## TASKACTV

| Field | Type | Description |
|-------|------|-------------|
| task_id | Integer | FK to TASK |
| actv_code_type_id | Integer | FK to ACTVTYPE |
| actv_code_id | Integer | FK to ACTVCODE |
| proj_id | Integer | FK to PROJECT |

---

## RSRC

| Field | Type | Description |
|-------|------|-------------|
| rsrc_id | Integer | Unique resource identifier |
| rsrc_name | String | Resource name |
| rsrc_short_name | String | Resource code |
| rsrc_type | String | RT_Labor, RT_Nonlabor, RT_Mat |
| clndr_id | Integer | FK to CLNDR — resource calendar |
| parent_rsrc_id | Integer | FK to self (resource hierarchy) |

---

## TASKRSRC

| Field | Type | Description |
|-------|------|-------------|
| taskrsrc_id | Integer | Unique assignment identifier |
| task_id | Integer | FK to TASK |
| rsrc_id | Integer | FK to RSRC |
| proj_id | Integer | FK to PROJECT |
| acct_id | Integer | FK to ACCOUNT |
| target_qty | Decimal | Budgeted quantity |
| remain_qty | Decimal | Remaining quantity |
| act_qty | Decimal | Actual quantity |
| target_cost | Decimal | Budgeted cost |
| remain_cost | Decimal | Remaining cost |
| act_cost | Decimal | Actual cost |
| target_start_date | DateTime | Planned start |
| target_end_date | DateTime | Planned finish |

---

## UDFTYPE

| Field | Type | Description |
|-------|------|-------------|
| udf_type_id | Integer | Unique UDF identifier |
| udf_type_name | String | Field name |
| udf_type_label | String | Display label |
| table_name | String | Which table this UDF attaches to (TASK, PROJECT, etc.) |
| udf_type_subtype | String | UDF_Text, UDF_Number, UDF_Date, UDF_Cost, UDF_Indicator, UDF_Code |

---

## UDFVALUE

| Field | Type | Description |
|-------|------|-------------|
| udf_value_id | Integer | Unique value identifier |
| udf_type_id | Integer | FK to UDFTYPE |
| fk_id | Integer | FK to the object this value belongs to |
| proj_id | Integer | FK to PROJECT |
| udf_text | String | Text value |
| udf_number | Decimal | Numeric value |
| udf_date | DateTime | Date value |
| udf_code_id | Integer | Code value |

---

## OBS

| Field | Type | Description |
|-------|------|-------------|
| obs_id | Integer | Unique OBS node identifier |
| obs_name | String | Node name |
| parent_obs_id | Integer | FK to self — parent node |
| seq_num | Integer | Display order |

---

## ACCOUNT

| Field | Type | Description |
|-------|------|-------------|
| acct_id | Integer | Unique account identifier |
| acct_name | String | Account name |
| acct_short_name | String | Account code |
| parent_acct_id | Integer | FK to self — parent account |
| acct_seq_num | Integer | Display order |

---

## CURRTYPE

| Field | Type | Description |
|-------|------|-------------|
| curr_id | Integer | Unique currency identifier |
| curr_type | String | Currency code (USD, CAD, EUR, etc.) |
| curr_short_name | String | Symbol ($, €, etc.) |
| decimal_digit_cnt | Integer | Decimal places |
| base_exch_rate | Decimal | Exchange rate |

---

## Calendar Encoding {#calendar-encoding}

The `clndr_data` field in CALENDAR/CLNDR uses a nested parenthetical notation. It is NOT tab-delimited like the rest of the file.

### Structure

```
(0||DaysOfWeek()
  (0||0(<work_period>))     ← Sunday (day 0)
  (0||1(<work_period>))     ← Monday (day 1)
  (0||2(<work_period>))     ← Tuesday
  (0||3(<work_period>))     ← Wednesday
  (0||4(<work_period>))     ← Thursday
  (0||5(<work_period>))     ← Friday
  (0||6(<work_period>))     ← Saturday (day 6)
  ()
  (0||Exceptions()
    (0||0(d|<date_serial>)(<work_override>))
    (0||1(d|<date_serial>)(<work_override>))
    ...
  )
)
```

### Work Period Format
Each work period within a day: `(s|HH:MM|f|HH:MM)` where `s` = start, `f` = finish.

A non-working day has empty parentheses: `(0||0())`
A standard workday: `(0||1(s|08:00|f|17:00))`
Split workday (with lunch): `(0||1(s|08:00|f|12:00)(s|13:00|f|17:00))`

### Exception Days
Exception entries override the standard workweek:
- Non-working exception (holiday): `(0||0(d|44927)())`
- Working exception (Saturday makeup): `(0||0(d|44927)(0||0(s|08:00|f|17:00)()))`

---

## Date Encoding in Calendars {#date-encoding}

Calendar exception dates use a serial number representing days since December 30, 1899 (same epoch as Excel's date system with the 1900 leap year bug adjustment).

**Conversion formulas:**

To convert serial → date:
```python
from datetime import datetime, timedelta
base_date = datetime(1899, 12, 30)
actual_date = base_date + timedelta(days=serial_number)
```

To convert date → serial:
```python
serial = (target_date - datetime(1899, 12, 30)).days
```

**Examples:**
- 44927 → 2023-01-01
- 45292 → 2024-01-01
- 46023 → 2026-01-01

---

## Validation Checklist {#validation-checklist}

### Structure
- First line is `ERMHDR\t<version>`
- All tables have `%T`, `%F`, at least one `%R`, and `%E`
- Field count in `%F` matches field count in every `%R`
- Tab delimiter used throughout (not space, comma, pipe)
- Line endings are CR (`\r`)
- File encoding is Windows-1252 or UTF-8 with BOM

### Referential Integrity
- Every `proj_id` in TASK exists in PROJECT
- Every `wbs_id` in TASK exists in PROJWBS
- Every `clndr_id` in TASK and PROJECT exists in CALENDAR/CLNDR (check both table names)
- Every `task_id` (successor) and `pred_task_id` (predecessor) in TASKPRED exists in TASK
- Every `rsrc_id` in TASKRSRC exists in RSRC
- Every `actv_code_type_id` in ACTVCODE exists in ACTVTYPE
- Every `udf_type_id` in UDFVALUE exists in UDFTYPE
- PROJWBS `parent_wbs_id` references exist (except root nodes)

### Logic
- No circular dependencies in TASKPRED
- No duplicate `task_id` values within a project
- No duplicate relationship records (same pred + succ + type)
- Milestones have zero duration
- LOE activities are properly linked

### Data Quality
- Dates in `YYYY-MM-DD HH:MM` format
- Duration values are numeric and non-negative
- Decimal separator matches target P6 locale
- No tab characters embedded in data values
- Status codes use valid P6 enum values
