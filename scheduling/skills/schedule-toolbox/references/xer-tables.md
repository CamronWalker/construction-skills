# XER Table Reference — Full Field Definitions

This reference contains detailed field definitions for all major XER tables, derived from Oracle's official P6 EPPM XER Import/Export Data Map Guide (Version 20).
Full Oracle documentation (70 tables) is saved to `references/oracle-docs/`.

## Table of Contents
1. [ERMHDR — File Header](#ermhdr)
2. [PROJECT](#project)
3. [PROJWBS](#projwbs)
4. [TASK](#task)
5. [TASKPRED](#taskpred)
6. [CLNDR — Calendars](#clndr)
7. [SCHEDOPTIONS — Schedule Options](#schedoptions)
8. [FINDATES — Financial Periods](#findates)
9. [ACTVTYPE — Activity Code Types](#actvtype)
10. [ACTVCODE — Activity Code Values](#actvcode)
11. [TASKACTV — Activity Code Assignments](#taskactv)
12. [RSRC — Resources](#rsrc)
13. [RSRCRATE — Resource Prices](#rsrcrate)
14. [ROLES — Roles](#roles)
15. [ROLERATE — Role Prices](#rolerate)
16. [RSRCROLE — Resource Role Assignments](#rsrcrole)
17. [TASKRSRC — Activity Resource Assignments](#taskrsrc)
18. [PCATTYPE — Project Codes](#pcattype)
19. [PCATVAL — Project Code Values](#pcatval)
20. [PROJPCAT — Project Code Assignments](#projpcat)
21. [RCATTYPE — Resource Codes](#rcattype)
22. [RCATVAL — Resource Code Values](#rcatval)
23. [UDFTYPE — User-Defined Field Types](#udftype)
24. [UDFVALUE — User-Defined Field Values](#udfvalue)
25. [MEMOTYPE — Notebook Topics](#memotype)
26. [TASKMEMO — Activity Notebook](#taskmemo)
27. [OBS — Organizational Breakdown Structure](#obs)
28. [ACCOUNT — Cost Accounts](#account)
29. [CURRTYPE — Currency Types](#currtype)
30. [Calendar Data Encoding](#calendar-encoding)
31. [Date Encoding in Calendars](#date-encoding)
32. [Validation Checklist](#validation-checklist)

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
| sum_data_flag | Y/N | Whether to summarize data at this level (absent in P6 v7 exports) |

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
| target_work_qty | Decimal | Budgeted labor units |
| act_work_qty | Decimal | Actual labor units |
| remain_work_qty | Decimal | Remaining labor units |
| target_equip_qty | Decimal | Budgeted nonlabor units |
| act_equip_qty | Decimal | Actual nonlabor units |
| remain_equip_qty | Decimal | Remaining nonlabor units |
| cstr_type | String | Primary constraint type (see Constraint Types below) |
| cstr_date | DateTime | Primary constraint date (if applicable) |
| cstr_type2 | String | Secondary constraint type |
| cstr_date2 | DateTime | Secondary constraint date |
| early_start_date | DateTime | Calculated early start |
| early_end_date | DateTime | Calculated early finish |
| late_start_date | DateTime | Calculated late start |
| late_end_date | DateTime | Calculated late finish |
| restart_date | DateTime | Remaining early start |
| reend_date | DateTime | Remaining early finish |
| rem_late_start_date | DateTime | Remaining late start |
| rem_late_end_date | DateTime | Remaining late finish |
| act_start_date | DateTime | Actual start |
| act_end_date | DateTime | Actual finish |
| target_start_date | DateTime | Planned start |
| target_end_date | DateTime | Planned finish |
| expect_end_date | DateTime | Expected finish (manual override) |
| suspend_date | DateTime | Suspend date |
| resume_date | DateTime | Resume date |
| status_code | String | TK_NotStart, TK_Active, TK_Complete |
| task_type | String | TT_Task, TT_Mile, TT_FinMile, TT_LOE, TT_Rsrc, TT_WBS |
| duration_type | String | DT_FixedDrtn, DT_FixedUnits, DT_FixedWork |
| complete_pct_type | String | CP_Phys, CP_Drtn, CP_Units |
| phys_complete_pct | Decimal | Physical % complete (0-100) |
| total_float_hr_cnt | Decimal | Total float (hours) |
| free_float_hr_cnt | Decimal | Free float (hours) |
| driving_path_flag | Y/N | On longest path? |
| float_path | Integer | Float path number |
| float_path_order | Integer | Float path order |
| priority_type | String | Activity leveling priority |
| rsrc_id | Integer | Primary resource ID |
| lock_plan_flag | Y/N | Lock remaining flag |
| auto_compute_act_flag | Y/N | Auto compute actuals |
| external_early_start_date | DateTime | External early start (inter-project) |
| external_late_end_date | DateTime | External late end (inter-project) |
| guid | String | Globally unique identifier |
| create_date | DateTime | When activity was created |
| create_user | String | Who created the activity |
| update_date | DateTime | Last modified date |
| update_user | String | Last modified by |

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

**Soft constraints (directional):**
- **CS_MSOA** / **CS_MSOB** — Start On or After/Before (equivalent to SNET/SNLT)
- **CS_MEOA** / **CS_MEOB** — Finish On or After/Before (equivalent to FNET/FNLT)

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

**Critical:** The `task_id` field in TASKPRED is the **successor** activity, NOT a generic FK.

| Field | Type | Description |
|-------|------|-------------|
| task_pred_id | Integer | Unique relationship identifier |
| task_id | Integer | FK to TASK — **the successor** |
| pred_task_id | Integer | FK to TASK — the predecessor |
| proj_id | Integer | FK to PROJECT |
| pred_proj_id | Integer | FK to PROJECT (for cross-project links) |
| pred_type | String | Relationship type — `PR_FS`/`PR_SS`/`PR_FF`/`PR_SF` or `FS`/`SS`/`FF`/`SF` |
| lag_hr_cnt | Decimal | Lag in hours (negative = lead) |

**Note on pred_type:** Some XER versions use prefixed codes (`PR_FS`) while others use short codes (`FS`):
```python
pred_type = rel.get('pred_type', '')
is_fs = pred_type in ('FS', 'PR_FS')
```

**Building predecessor/successor lookups:**
```python
successors = {}
for r in tables.get('TASKPRED', []):
    successors.setdefault(r['pred_task_id'], []).append(r['task_id'])

predecessors = {}
for r in tables.get('TASKPRED', []):
    predecessors.setdefault(r['task_id'], []).append(r['pred_task_id'])
```

---

## CALENDAR / CLNDR

**Table name variation:** Named `CALENDAR` in some P6 exports, `CLNDR` in others:
```python
calendars = tables.get('CALENDAR', tables.get('CLNDR', []))
```

| Field | Type | Description |
|-------|------|-------------|
| clndr_id | Integer | Unique calendar identifier |
| clndr_name | String | Calendar name |
| clndr_type | String | CA_Base, CA_Project, CA_Rsrc |
| base_clndr_id | Integer | FK to self — parent calendar |
| proj_id | Integer | FK to PROJECT (project calendars) |
| clndr_data | String | Encoded work hours and exceptions (see Calendar Data Encoding) |
| last_chng_date | DateTime | Last modified date |

---

## SCHEDOPTIONS

One row per project. Controls CPM scheduling behavior.

**CPM-critical field:** `sched_calendar_on_relationship_lag` determines which calendar governs lag duration. The CPM engine reads this to match P6's calculation.

| Field | Type | Description |
|-------|------|-------------|
| schedoptions_id | Integer | Unique ID |
| proj_id | Integer | FK to PROJECT |
| sched_calendar_on_relationship_lag | String | **CPM-critical.** Lag calendar: `rcal_Successor` (default in most Westland schedules), `rcal_Predecessor`, `rcal_TwentyFourHour`, `rcal_Default` |
| sched_retained_logic | Y/N | Retained Logic (Y) vs Progress Override (N) |
| sched_progress_override | Y/N | Progress override mode |
| sched_float_type | String | Float type: `FT_TotalFloat`, `FT_FF`, `FT_StartFloat` |
| sched_lag_early_start_flag | Y/N | Use Early Start for lag |
| sched_open_critical_flag | Y/N | Treat open ends as critical |
| sched_use_expect_end_flag | Y/N | Use expected finish in calculations |
| sched_use_project_end_date_for_float | Y/N | Use project end date for float |
| sched_outer_depend_type | String | Cross-project dependency type |
| sched_setplantoforecast | Y/N | Set plan to forecast |
| enable_multiple_longest_path_calc | Y/N | Enable multiple longest paths |
| limit_multiple_longest_path_calc | Y/N | Limit number of longest paths |
| max_multiple_longest_path | Integer | Max number of longest paths |
| use_total_float_multiple_longest_paths | Y/N | Use total float for multiple longest paths |
| key_activity_for_multiple_longest_paths | String | Key activity for longest path |
| level_all_rsrc_flag | Y/N | Level all resources |
| level_float_thrs_cnt | Decimal | Float threshold for leveling |
| level_keep_sched_date_flag | Y/N | Keep scheduled dates during leveling |
| level_outer_assign_flag | Y/N | Level cross-project assignments |
| level_outer_assign_priority | String | Priority for cross-project leveling |
| level_over_alloc_pct | Decimal | Overallocation percentage threshold |
| level_within_float_flag | Y/N | Level within float |
| LevelPriorityList | String | Resource leveling priority list |

**Reading in code:**
```python
sched_opts = tables.get('SCHEDOPTIONS', [{}])[0]
lag_calendar = sched_opts.get('sched_calendar_on_relationship_lag', 'rcal_Successor')
retained_logic = sched_opts.get('sched_retained_logic', 'Y') == 'Y'
```

---

## FINDATES

Financial periods for past-period actual tracking.

| Field | Type | Description |
|-------|------|-------------|
| fin_dates_id | Integer | Unique ID |
| fin_dates_name | String | Period name (e.g., "January 2026") |
| start_date | DateTime | Period start date |
| end_date | DateTime | Period end date |

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
| parent_actv_code_id | Integer | FK to self (hierarchical) |
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
| rsrc_short_name | String | Resource code (ID) |
| rsrc_type | String | RT_Labor, RT_Nonlabor, RT_Mat |
| clndr_id | Integer | FK to CLNDR — resource calendar |
| parent_rsrc_id | Integer | FK to self (resource hierarchy) |
| role_id | Integer | FK to ROLES — primary role |
| curr_id | Integer | FK to CURRTYPE — currency |
| unit_id | Integer | FK to UMEASURE — unit of measure |
| cost_qty_type | String | Price time units |
| def_qty_per_hr | Decimal | Default units per time |
| def_cost_qty_link_flag | Y/N | Calculate costs from units |
| ot_factor | Decimal | Overtime factor |
| ot_flag | Y/N | Overtime allowed |
| active_flag | Y/N | Active/inactive |
| auto_compute_act_flag | Y/N | Auto compute actuals |
| rsrc_seq_num | Integer | Sort order |
| rsrc_title_name | String | Title |
| rsrc_notes | String | Resource notes |
| email_addr | String | Email address |
| employee_code | String | Employee ID |
| office_phone | String | Office phone |
| other_phone | String | Other phone |
| shift_id | Integer | FK to SHIFT |
| guid | String | Globally unique ID |
| user_id | Integer | Associated user login |
| timesheet_flag | Y/N | Uses timesheets |

---

## RSRCRATE

Date-effective resource price rates. One resource can have multiple rows with different effective start dates.

| Field | Type | Description |
|-------|------|-------------|
| rsrc_rate_id | Integer | Unique ID |
| rsrc_id | Integer | FK to RSRC |
| start_date | DateTime | Effective date (rate active from this date forward) |
| cost_per_qty | Decimal | Standard Rate / Price per Unit 1 |
| cost_per_qty2 | Decimal | Internal Rate / Price per Unit 2 |
| cost_per_qty3 | Decimal | External Rate / Price per Unit 3 |
| cost_per_qty4 | Decimal | Price per Unit 4 |
| cost_per_qty5 | Decimal | Price per Unit 5 |
| max_qty_per_hr | Decimal | Max units per time period |
| shift_period_id | Integer | FK to SHIFTPER |

**Finding the effective rate for a date:**
```python
def get_resource_rate(rsrcrate_rows, rsrc_id, as_of_date):
    rates = [r for r in rsrcrate_rows if r['rsrc_id'] == rsrc_id]
    rates.sort(key=lambda r: r.get('start_date', ''), reverse=True)
    for r in rates:
        if r.get('start_date', '') <= as_of_date:
            return float(r.get('cost_per_qty', 0) or 0)
    return 0.0
```

---

## ROLES

Role hierarchy — assigned to activities via TASKRSRC.role_id.

| Field | Type | Description |
|-------|------|-------------|
| role_id | Integer | Unique ID |
| role_short_name | String | Role ID (code) |
| role_name | String | Role name |
| role_descr | String | Responsibilities |
| parent_role_id | Integer | FK to self — parent role |
| seq_num | Integer | Sort order |
| cost_qty_type | String | Price time units |
| def_cost_qty_link_flag | Y/N | Calculate costs from units |

---

## ROLERATE

Date-effective role price rates. Same structure as RSRCRATE but for roles.

| Field | Type | Description |
|-------|------|-------------|
| role_rate_id | Integer | Unique ID |
| role_id | Integer | FK to ROLES |
| start_date | DateTime | Effective date |
| cost_per_qty | Decimal | Standard Rate / Price per Unit 1 |
| cost_per_qty2 | Decimal | Internal Rate / Price per Unit 2 |
| cost_per_qty3 | Decimal | External Rate / Price per Unit 3 |
| cost_per_qty4 | Decimal | Price per Unit 4 |
| cost_per_qty5 | Decimal | Price per Unit 5 |
| max_qty_per_hr | Decimal | Max units per time |

---

## RSRCROLE

Assigns roles to resources (many-to-many).

| Field | Type | Description |
|-------|------|-------------|
| rsrc_role_id | Integer | Unique ID |
| rsrc_id | Integer | FK to RSRC |
| role_id | Integer | FK to ROLES |
| rsrc_name | String | Resource name (denormalized) |
| rsrc_short_name | String | Resource ID (denormalized) |
| rsrc_type | String | Resource type (denormalized) |
| role_name | String | Role name (denormalized) |
| role_short_name | String | Role ID (denormalized) |
| skill_level | String | Proficiency level |

---

## TASKRSRC

Resource assignments to activities. One row per resource-activity combination.

**Oracle-confirmed cost field names:** `target_cost`, `remain_cost`, `act_reg_cost`, `act_ot_cost`. These may differ in older exports — always check the `%F` header.

| Field | Type | Description |
|-------|------|-------------|
| taskrsrc_id | Integer | Unique assignment identifier |
| task_id | Integer | FK to TASK |
| rsrc_id | Integer | FK to RSRC |
| role_id | Integer | FK to ROLES — role for this assignment |
| proj_id | Integer | FK to PROJECT |
| acct_id | Integer | FK to ACCOUNT |
| rsrc_type | String | Resource type (denormalized) |
| rate_type | String | Rate type for cost calculation |
| cost_per_qty | Decimal | Price per unit (overrides resource default) |
| cost_per_qty_source_type | String | Rate source |
| cost_qty_link_flag | Y/N | Calculate costs from units |
| target_qty | Decimal | Budgeted/planned units |
| remain_qty | Decimal | Remaining units |
| act_reg_qty | Decimal | Actual regular units |
| act_ot_qty | Decimal | Actual overtime units |
| target_qty_per_hr | Decimal | Budgeted/planned units per time |
| remain_qty_per_hr | Decimal | Remaining units per time |
| target_cost | Decimal | Budgeted/planned cost |
| remain_cost | Decimal | Remaining cost |
| act_reg_cost | Decimal | Actual regular cost |
| act_ot_cost | Decimal | Actual overtime cost |
| act_this_per_cost | Decimal | Actual this period cost |
| act_this_per_qty | Decimal | Actual this period units |
| target_start_date | DateTime | Planned start |
| target_end_date | DateTime | Planned finish |
| act_start_date | DateTime | Actual start |
| act_end_date | DateTime | Actual finish |
| restart_date | DateTime | Remaining early start |
| reend_date | DateTime | Remaining early finish |
| rem_late_start_date | DateTime | Remaining late start |
| rem_late_end_date | DateTime | Remaining late finish |
| target_lag_drtn_hr_cnt | Decimal | Original lag |
| relag_drtn_hr_cnt | Decimal | Remaining lag |
| rollup_dates_flag | Y/N | Drive activity dates |
| ot_factor | Decimal | Overtime factor |
| curv_id | Integer | Resource curve ID |
| guid | String | Global unique ID |
| create_date | DateTime | Assignment date |
| create_user | String | Assigned by |
| skill_level | String | Proficiency level |

**Resource cost loading pattern:**
```python
task_costs = {}
for tr in tables.get('TASKRSRC', []):
    tid = tr['task_id']
    task_costs.setdefault(tid, {'budget': 0.0, 'actual': 0.0, 'remaining': 0.0})
    task_costs[tid]['budget'] += float(tr.get('target_cost', 0) or 0)
    task_costs[tid]['actual'] += float(tr.get('act_reg_cost', 0) or 0)
    task_costs[tid]['actual'] += float(tr.get('act_ot_cost', 0) or 0)
    task_costs[tid]['remaining'] += float(tr.get('remain_cost', 0) or 0)
```

---

## PCATTYPE

Project code types.

| Field | Type | Description |
|-------|------|-------------|
| proj_catg_type_id | Integer | Unique ID |
| proj_catg_type | String | Project code name |
| proj_catg_short_len | Integer | Max code length |
| seq_num | Integer | Sort order |
| super_flag | Y/N | Secure code |

---

## PCATVAL

Project code values.

| Field | Type | Description |
|-------|------|-------------|
| proj_catg_id | Integer | Unique ID |
| proj_catg_type_id | Integer | FK to PCATTYPE |
| parent_proj_catg_id | Integer | FK to self — hierarchical parent |
| proj_catg_short_name | String | Code value |
| proj_catg_name | String | Code description |
| seq_num | Integer | Sort order |

---

## PROJPCAT

Assigns project codes to projects.

| Field | Type | Description |
|-------|------|-------------|
| proj_id | Integer | FK to PROJECT |
| proj_catg_type_id | Integer | FK to PCATTYPE |
| proj_catg_id | Integer | FK to PCATVAL — assigned code value |

---

## RCATTYPE

Resource code types.

| Field | Type | Description |
|-------|------|-------------|
| rsrc_catg_type_id | Integer | Unique ID |
| rsrc_catg_type | String | Resource code name |
| rsrc_catg_short_len | Integer | Max code length |
| seq_num | Integer | Sort order |
| super_flag | Y/N | Secure code |

---

## RCATVAL

Resource code values.

| Field | Type | Description |
|-------|------|-------------|
| rsrc_catg_id | Integer | Unique ID |
| rsrc_catg_type_id | Integer | FK to RCATTYPE |
| parent_rsrc_catg_id | Integer | FK to self — hierarchical parent |
| rsrc_catg_short_name | String | Code value |
| rsrc_catg_name | String | Code description |
| seq_num | Integer | Sort order |

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

## MEMOTYPE

Notebook topic definitions.

| Field | Type | Description |
|-------|------|-------------|
| memo_type_id | Integer | Unique ID |
| memo_type | String | Notebook topic name |
| seq_num | Integer | Sort order |
| task_flag | Y/N | Available for activities |
| wbs_flag | Y/N | Available for WBS nodes |
| proj_flag | Y/N | Available for projects |
| eps_flag | Y/N | Available for EPS nodes |

---

## TASKMEMO

Activity notebook entries (rich-text notes attached to activities).

| Field | Type | Description |
|-------|------|-------------|
| memo_id | Integer | Unique ID |
| task_id | Integer | FK to TASK |
| proj_id | Integer | FK to PROJECT |
| memo_type_id | Integer | FK to MEMOTYPE |
| task_memo | String | Notebook text (may contain HTML) |

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

The `clndr_data` field uses a nested parenthetical notation. It is NOT tab-delimited.

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
    ...
  )
)
```

### Work Period Format
- Non-working day: `(0||0())`
- Standard workday: `(0||1(s|08:00|f|17:00))`
- Split workday: `(0||1(s|08:00|f|12:00)(s|13:00|f|17:00))`

### Exception Days
- Holiday: `(0||0(d|44927)())`
- Saturday makeup: `(0||0(d|44927)(0||0(s|08:00|f|17:00)()))`

---

## Date Encoding in Calendars {#date-encoding}

Calendar exception dates use a serial number: days since December 30, 1899 (Excel epoch).

```python
from datetime import datetime, timedelta
# Serial -> date
actual_date = datetime(1899, 12, 30) + timedelta(days=serial_number)
# Date -> serial
serial = (target_date - datetime(1899, 12, 30)).days
```

**Examples:** 44927 = 2023-01-01 | 45292 = 2024-01-01 | 46023 = 2026-01-01

---

## Validation Checklist {#validation-checklist}

### Structure
- First line is `ERMHDR\t<version>`
- All tables have `%T`, `%F`, at least one `%R`, and `%E`
- Field count in `%F` matches field count in every `%R`
- Tab delimiter used throughout
- Line endings are CRLF (`\r\n`)
- File encoding is Windows-1252 or UTF-8 with BOM

### Referential Integrity
- Every `proj_id` in TASK exists in PROJECT
- Every `wbs_id` in TASK exists in PROJWBS
- Every `clndr_id` in TASK and PROJECT exists in CALENDAR/CLNDR
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
- No tab characters embedded in data values
- Status codes use valid P6 enum values
