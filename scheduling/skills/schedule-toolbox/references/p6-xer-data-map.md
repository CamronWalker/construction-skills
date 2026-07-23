# P6 XER Data Map — Import-Debugging Reference

A practical field-map and troubleshooting reference for the Primavera P6 **XER**
file format, oriented toward the tables Westland generates and touches and the
import failures we actually hit.

**Field maps** in Section 3 are transcribed from Oracle's *Primavera P6 EPPM XER
Import/Export Data Map Guide (Project)*, Version 23 (April 2023) — the same
source behind the per-table files in [`oracle-docs/`](oracle-docs/). Those are
**facts** (the P6 field → column-name maps). Sections 4–6 (**data types**,
**common import failures**, **validator cross-reference**) are Westland's own
analysis — the Oracle guide documents *meanings*, not *types*, and says nothing
about what crashes an import.

> This is a working reference, not a reprint. Only the ~14 Westland-touched
> tables are inline here. The complete per-table set (70+ tables) lives in
> [`oracle-docs/`](oracle-docs/); parsing mechanics live in
> [`xer-format.md`](xer-format.md); generation/modification live in
> [`xer-generation.md`](xer-generation.md) and [`xer-modify.md`](xer-modify.md).

---

## Contents

1. [What an XER is](#1-what-an-xer-is)
2. [How to read a field map](#2-how-to-read-a-field-map)
3. [Per-table field maps (Westland-touched)](#3-per-table-field-maps-westland-touched)
4. [Field data types](#4-field-data-types-westland-analysis)
5. [Common import failures](#5-common-import-failures-westland-analysis)
6. [Validator cross-reference](#6-validator-cross-reference)

---

## 1. What an XER is

An XER is P6's **plain-text, tab-delimited** interchange file — one flat file
holding every table of a project export, stacked one after another.

- **Encoding:** Windows-1252 (`cp1252`) is standard. Real-world files also turn
  up as `utf-8-sig` / `utf-8` / `latin-1`; parse with a fallback chain.
- **Line endings:** CRLF (`\r\n`).
- **Delimiter:** a single TAB (`\t`) between fields. Fields are **not** quoted;
  a literal tab or newline inside a value would corrupt the row.
- **Empty vs. null:** an empty field is just two adjacent tabs — there is no
  explicit null token.

### Line markers

Every line begins with a marker in the first column:

| Marker | Meaning |
|--------|---------|
| `ERMHDR` | **First line.** Export header — version, export date, encoding hint, currency, and the exporting user/database. Not a table. |
| `%T` | **Table.** `%T<TAB>TABLE_NAME` starts a new table block (e.g. `%T\tTASK`). |
| `%F` | **Fields.** `%F<TAB>col1<TAB>col2<TAB>…` — the column header row for the current table. Column order is defined here and every `%R` row matches it positionally. |
| `%R` | **Row.** `%R<TAB>val1<TAB>val2<TAB>…` — one data record. Values line up with the preceding `%F` by position. |
| `%E` | **End.** Last line of the file. |

A minimal shape:

```
ERMHDR	23	2026-07-23	Project	...	USD
%T	PROJECT
%F	proj_id	proj_short_name	plan_start_date	last_recalc_date	...
%R	1234	W1177	2026-07-01 08:00	2026-07-20 08:00	...
%T	PROJWBS
%F	wbs_id	proj_id	obs_id	seq_num	...	wbs_name	...
%R	5001	1234	1	100	...	Neiafu Tonga Temple Construction	...
%E
```

Tables appear in dependency order (parents before children). **P6 gives no
useful error dialog on a malformed import** — it either silently drops rows or
access-violates (see Section 5) — so structure and types must be exact before
handoff. Run `validate_xer_structure` (Section 6) as the gate.

---

## 2. How to read a field map

Each table below is the Oracle `%F` column set, one row per column:

| Field | P6 Column Name / Meaning |
|-------|--------------------------|

- **Field** = the literal token in the `%F` header (what you write in code).
- **P6 Column Name / Meaning** = the friendly label P6's UI shows for that field
  (what a scheduler recognizes).
- `(P6 Professional only)` / `(P6 EPPM only)` marks fields that only one edition
  populates — both editions tolerate the other's fields being present or empty.

The **Unique ID** of each table is its integer primary key (`proj_id`,
`wbs_id`, `task_id`, …). Fields ending `_id` that are *not* the Unique ID are
foreign keys pointing at another table's Unique ID. See Section 4 for types.

---

## 3. Per-table field maps (Westland-touched)

The tables a Westland proposal/update schedule generates or edits. Full set for
every other table: [`oracle-docs/`](oracle-docs/).

### PROJECT — Projects

The single project header row. `proj_id` is the numeric key; `proj_short_name`
is the human "Project ID" code. Its date fields are the most common
`MALFORMED_DATETIME` offenders (Section 5b).

| Field | P6 Column Name / Meaning |
|-------|--------------------------|
| acct_id | Default Cost Account |
| act_pct_link_flag | Link Percent Complete With Actual |
| act_this_per_link_flag | Link actual-to-date and actual-this-period units/costs |
| add_act_remain_flag | Add Actual To Remain |
| add_by_name | Added By |
| add_date | Date Added |
| allow_complete_flag | Can resources mark activities completed |
| allow_neg_act_flag | Allow Negative Actual Units |
| apply_actuals_date | Last Apply Actuals Date |
| base_type_id | Baseline Type |
| batch_sum_flag | Enable Summarization |
| checkout_date | Date Checked Out |
| checkout_flag | Project Check-out Status |
| checkout_user_id | Checked Out By |
| chng_eff_cmp_pct_flag | Resources Edit Percent Complete (P6 Professional only) |
| clndr_id | Default Calendar |
| control_updates_flag | Status Update Control |
| cost_qty_recalc_flag | Cost Qty Recalc Flag |
| cr_external_key | Content Repository External UUID |
| critical_drtn_hr_cnt | Critical activities have float ≤ this |
| critical_path_type | Critical Path Type |
| def_complete_pct_type | Default Percent Complete Type |
| def_cost_per_qty | Default Price / Unit |
| def_duration_type | Default Duration Type |
| def_qty_type | Default Price Time Units |
| def_rate_type | Rate Type |
| def_rollup_dates_flag | Drive Activity Dates Default |
| def_task_type | Default Activity Type |
| fcst_start_date | Project Forecast Start |
| fintmpl_id | Financial Period Calendar ID |
| fy_start_month_num | Fiscal Year Begins |
| guid | Global Unique ID |
| hist_interval | History Interval |
| hist_level | History Level |
| intg_proj_type | Integrated Project (P6 Professional only) |
| last_baseline_update_date | Last Update Date |
| last_checksum | Last Checksum |
| last_fin_dates_id | Financial Period |
| last_level_date | Last Leveled Date |
| last_recalc_date | Last Recalc Date (the **data date**) |
| last_schedule_date | Last Scheduled Date (P6 EPPM only) |
| last_tasksum_date | Last Summarized Date |
| location_id | Project Location |
| msp_managed_flag | MS Project Managed Flag (P6 Professional only) |
| name_sep_char | Code Separator |
| orig_proj_id | Original Project |
| plan_end_date | Must Finish By |
| plan_start_date | Planned Start |
| priority_num | Project Leveling Priority |
| proj_id | **Unique ID** |
| proj_short_name | Project ID (the human code, e.g. `W1177`) |
| proj_url | Project Web Site URL |
| project_flag | Project Flag |
| px_enable_publication_flag | Enable Publication |
| px_last_update_date | Last Publish-Project run (P6 Professional only) |
| px_priority | Publication Priority (P6 EPPM only) |
| rem_target_link_flag | Link Budget and At Completion |
| reset_planned_flag | Reset Original to Remaining |
| risk_level | Risk Level (P6 Professional only) |
| rsrc_multi_assign_flag | Can assign resource multiple times to activity |
| rsrc_self_add_flag | Can resources assign selves to activities |
| scd_end_date | Schedule Finish |
| source_proj_id | Source Project |
| step_complete_flag | Physical Percent Complete uses Steps Completed |
| strgy_priority_num | Strategic Priority |
| sum_assign_level | Summary Assignment Level |
| sum_base_proj_id | Project Baseline |
| sum_data_date | Summarized Data Date (P6 Professional only) |
| sum_only_flag | Contains Summarized Data Only (P6 Professional only) |
| task_code_base | Activity ID Suffix |
| task_code_prefix | Activity ID Prefix |
| task_code_prefix_flag | Activity ID based on selected activity |
| task_code_step | Activity ID Increment |
| ts_rsrc_vs_inact_actv_flag | Resource can view activities from an inactive project (P6 Professional only) |
| use_project_baseline_flag | Use Project Baseline Flag |
| wbs_max_sum_level | WBS Max Summarization Level |
| web_local_root_path | Web Site Root Directory |

### PROJWBS — WBS

The WBS tree. The **root node** (`proj_node_flag='Y'`) carries the long project
name in `wbs_name` (Section 5c). `obs_id`, `seq_num`, `est_wt`, `proj_node_flag`,
`sum_data_flag`, and `status_code` are P6-required on every node (Section 5a).

| Field | P6 Column Name / Meaning |
|-------|--------------------------|
| ann_dscnt_rate_pct | Annual Discount Rate |
| anticip_end_date | Anticipated Finish |
| anticip_start_date | Anticipated Start |
| dscnt_period_type | Discount Application Period |
| est_wt | Est Weight (P6 Professional only) |
| ev_compute_type | Earned Value Percent Complete Technique |
| ev_etc_compute_type | Earned Value Estimate-to-Complete Technique |
| ev_etc_user_value | Earned Value Performance Factor |
| ev_user_pct | Earned Value Percent Complete |
| guid | Global Unique ID |
| indep_remain_total_cost | Independent ETC Total Cost |
| indep_remain_work_qty | Independent ETC Labor Units |
| obs_id | Responsible Manager (FK → OBS) |
| orig_cost | Original Budget |
| parent_wbs_id | Parent WBS (FK → PROJWBS; empty on root) |
| phase_id | WBS Category |
| proj_id | Project (FK → PROJECT) |
| proj_node_flag | Project Node (`Y` on the root) |
| seq_num | Sort Order |
| status_code | Project Status |
| status_reviewer | User Reviewing Status |
| sum_data_flag | Contains Summary Data |
| tmpl_guid | Methodology Global Unique ID |
| wbs_id | **Unique ID** |
| wbs_name | WBS Name (root node = the long project name) |
| wbs_short_name | WBS Code |

### TASK — Activities

Activities and milestones. Durations are in **hours** (`*_hr_cnt`). Many
bit-flags / enums / quantity decimals here are P6-required on every row
(Section 5a).

| Field | P6 Column Name / Meaning |
|-------|--------------------------|
| act_end_date | Actual Finish |
| act_equip_qty | Actual Nonlabor Units |
| act_start_date | Actual Start |
| act_this_per_equip_qty | Actual This Period Nonlabor Units |
| act_this_per_work_qty | Actual This Period Labor Units |
| act_work_qty | Actual Labor Units |
| auto_compute_act_flag | Auto Compute Actuals |
| clndr_id | Calendar (FK → CALENDAR) |
| complete_pct_type | Percent Complete Type |
| create_date | Added Date |
| create_user | Added By |
| cstr_date | Primary Constraint Date |
| cstr_date2 | Secondary Constraint Date |
| cstr_type | Primary Constraint |
| cstr_type2 | Secondary Constraint |
| driving_path_flag | Longest Path |
| duration_type | Duration Type |
| early_end_date | Early Finish |
| early_start_date | Early Start |
| est_wt | Est Weight (P6 Professional only) |
| expect_end_date | Expected Finish |
| external_early_start_date | External Early Start |
| external_late_end_date | External Late Finish |
| float_path | Float Path |
| float_path_order | Float Path Order |
| free_float_hr_cnt | Free Float |
| guid | Global Unique ID |
| late_end_date | Late Finish |
| late_start_date | Late Start |
| location_id | Activity Location |
| lock_plan_flag | Lock Remaining |
| phys_complete_pct | Physical Percent Complete |
| priority_type | Activity Leveling Priority |
| proj_id | Project (FK → PROJECT) |
| reend_date | Remaining Early Finish |
| rem_late_end_date | Remaining Late Finish |
| rem_late_start_date | Remaining Late Start |
| remain_drtn_hr_cnt | Remaining Duration |
| remain_equip_qty | Remaining Nonlabor Units |
| remain_work_qty | Remaining Labor Units |
| restart_date | Remaining Early Start |
| resume_date | Resume Date |
| rev_fdbk_flag | New Feedback |
| review_end_date | Review Finish (P6 Professional only) |
| review_type | Review Status (P6 Professional only) |
| rsrc_id | Primary Resource |
| status_code | Activity Status |
| suspend_date | Suspend Date |
| target_drtn_hr_cnt | Planned/Original Duration |
| target_end_date | Planned Finish |
| target_equip_qty | Planned/Budgeted Nonlabor Units |
| target_start_date | Planned Start |
| target_work_qty | Planned/Budgeted Labor Units |
| task_code | Activity ID |
| task_id | **Unique ID** |
| task_name | Activity Name |
| task_type | Activity Type |
| tmpl_guid | Methodology Global Unique ID |
| total_float_hr_cnt | Total Float |
| update_date | Last Modified Date |
| update_user | Last Modified By |
| wbs_id | WBS (FK → PROJWBS) |

### TASKPRED — Activity Relationships

The logic network. **Direction is easy to reverse:** `task_id` is the
**successor**, `pred_task_id` is the **predecessor**.

| Field | P6 Column Name / Meaning |
|-------|--------------------------|
| comments | Comments |
| lag_hr_cnt | Lag (hours) |
| pred_proj_id | Predecessor Project (FK → PROJECT) |
| pred_task_id | Predecessor (FK → TASK) |
| pred_type | Relationship Type (`PR_FS`/`PR_SS`/`PR_FF`/`PR_SF`) |
| proj_id | Successor Project (FK → PROJECT) |
| task_id | Successor (FK → TASK) |
| task_pred_id | **Unique ID** |

### CALENDAR — Calendars

Work patterns. `clndr_data` holds the encoded workweek/exceptions string.
Table name is `CALENDAR` in modern exports (`CLNDR` in some older ones).

| Field | P6 Column Name / Meaning |
|-------|--------------------------|
| base_clndr_id | Parent Calendar (FK → CALENDAR; empty on a base calendar) |
| clndr_data | Data (encoded workweek + exceptions) |
| clndr_id | **Unique ID** |
| clndr_name | Calendar Name |
| clndr_type | Calendar Type |
| day_hr_cnt | Work Hours Per Day |
| default_flag | Default |
| last_chng_date | Date Last Changed |
| month_hr_cnt | Work Hours Per Month |
| proj_id | Project (FK → PROJECT; empty on a global calendar) |
| rsrc_private | Personal Calendar (P6 EPPM only) |
| week_hr_cnt | Work Hours Per Week |
| year_hr_cnt | Work Hours Per Year |

### ACTVTYPE — Activity Codes (code definitions)

The activity-code *types* (e.g. Westland's "Responsibility"). `proj_id` empty =
a global code type.

| Field | P6 Column Name / Meaning |
|-------|--------------------------|
| actv_code_type | Activity Code |
| actv_code_type_id | **Unique ID** |
| actv_code_type_scope | Activity Code Type Scope |
| actv_short_len | Max Code Length |
| proj_id | EPS/Project (FK → PROJECT; empty on a global type) |
| seq_num | Sort Order |
| super_flag | Secure Code |

### ACTVCODE — Activity Code Values

The individual values under a code type (e.g. the trade codes).

| Field | P6 Column Name / Meaning |
|-------|--------------------------|
| actv_code_id | **Unique ID** |
| actv_code_name | Description |
| actv_code_type_id | Activity Code (FK → ACTVTYPE) |
| color | Color (P6 EPPM only) |
| parent_actv_code_id | Parent Activity Code Value (FK → ACTVCODE) |
| seq_num | Sort Order |
| short_name | Activity Code Value |

### TASKACTV — Activity Code Assignments

Join table: which code value is assigned to which activity.

| Field | P6 Column Name / Meaning |
|-------|--------------------------|
| actv_code_id | Activity Code Value (FK → ACTVCODE) |
| actv_code_type_id | Activity Code (FK → ACTVTYPE) |
| proj_id | Project (FK → PROJECT) |
| task_id | Activity (FK → TASK) |

### OBS — Organizational Breakdown Structure

Responsible-manager tree. Every `PROJWBS.obs_id` must resolve to a row here.

| Field | P6 Column Name / Meaning |
|-------|--------------------------|
| guid | Global Unique ID |
| obs_descr | OBS Description |
| obs_id | **Unique ID** |
| obs_name | OBS Name |
| parent_obs_id | Parent OBS (FK → OBS) |
| seq_num | Sort Order |

### CURRTYPE — Currency Types

| Field | P6 Column Name / Meaning |
|-------|--------------------------|
| base_exch_rate | Exchange Rate |
| curr_id | **Unique ID** |
| curr_short_name | Currency ID |
| curr_symbol | Currency Symbol |
| curr_type | Currency Name |
| decimal_digit_cnt | Number of Digits after Decimal |
| decimal_symbol | Decimal Symbol |
| digit_group_symbol | Digit Grouping Symbol |
| group_digit_cnt | Currency Group Digit Count |
| neg_curr_fmt_type | Negative Currency Format |
| pos_curr_fmt_type | Positive Currency Format |

### FINDATES — Financial Periods

> **Note on FINTMPL.** There is **no `FINTMPL` table** in this Oracle guide.
> The financial-period *periods* live in **FINDATES**; the reference to a
> financial-period **calendar/template** is the `PROJECT.fintmpl_id` field
> ("Financial Period Calendar ID"). If you were told to look for FINTMPL, this
> is the table you actually want.

| Field | P6 Column Name / Meaning |
|-------|--------------------------|
| end_date | End Date |
| fin_dates_id | **Unique ID** |
| fin_dates_name | Period Name |
| start_date | Start Date |

### SCHEDOPTIONS — Schedule Options

The scheduling engine settings. `sched_calendar_on_relationship_lag`
(`rcal_Successor` by default) and `sched_retained_logic` (`Y`/`N`) most affect
CPM parity.

| Field | P6 Column Name / Meaning |
|-------|--------------------------|
| enable_multiple_longest_path_calc | Enable multiple longest-path calc |
| key_activity_for_multiple_longest_paths | Key activity for multiple longest paths |
| level_all_rsrc_flag | Level all resources |
| level_float_thrs_cnt | Leveling float threshold |
| level_keep_sched_date_flag | Preserve scheduled early dates |
| level_outer_assign_flag | Level outer assignments |
| level_outer_assign_priority | Outer-assignment priority |
| level_over_alloc_pct | Over-allocation % |
| level_within_float_flag | Level within float |
| LevelPriorityList | Leveling priority list |
| limit_multiple_longest_path_calc | Limit multiple longest-path calc |
| max_multiple_longest_path | Max multiple longest paths |
| proj_id | Project (FK → PROJECT) |
| sched_calendar_on_relationship_lag | Calendar for relationship lag (`rcal_Successor` default) |
| sched_float_type | Total-float computation basis |
| sched_lag_early_start_flag | Compute start-to-start lag from early start |
| sched_open_critical_flag | Treat open-ended activities as critical |
| sched_outer_depend_type | External-relationship handling |
| sched_progress_override | Progress Override (vs. Retained Logic) |
| sched_retained_logic | Retained Logic (`Y`/`N`) |
| sched_setplantoforecast | Set planned = remaining for not-started |
| sched_use_expect_end_flag | Use expected finish dates |
| sched_use_project_end_date_for_float | Float relative to project Must-Finish-By |
| schedoptions_id | **Unique ID** |
| use_total_float_multiple_longest_paths | Use total float for multiple longest paths |

### MEMOTYPE — Notebook Topics

| Field | P6 Column Name / Meaning |
|-------|--------------------------|
| eps_flag | Available for EPS |
| memo_type | Notebook Topic |
| memo_type_id | **Unique ID** |
| proj_flag | Available for Projects |
| seq_num | Sort Order |
| task_flag | Available for Activity |
| wbs_flag | Available for WBS |

### UDFTYPE — User Defined Fields

| Field | P6 Column Name / Meaning |
|-------|--------------------------|
| indicator_expression | Indicator expression |
| logical_data_type | Data Type |
| summary_indicator_expression | Summary indicator expression |
| super_flag | Secure Code |
| table_name | Table |
| udf_type_id | **Unique ID** |
| udf_type_label | Title |
| udf_type_name | User Defined Field |

---

## 4. Field data types (Westland analysis)

The Oracle guide gives **meanings, not types**. The rules below are derived
empirically from an audit of **200+ real, P6-importable Westland exports** (the
validator's calibration set is 204) and are the difference between a file P6
accepts and one it crashes on. Regenerate them any time from the corpus at
`…/OneDrive - Westland Construction/40 Cowork/training_data` (187+ `.xer`; the
donor `BTLP.xer` is under `Proposal Schedules/`).

### 4.1 Integer keys and foreign keys → INTEGER

Every **Unique ID** and every `_id` foreign key is a base-10 integer
(`^-?\d+$`), never text. Non-empty values only — optional FKs are legitimately
blank (see 4.5).

| Kind | Columns |
|------|---------|
| Primary keys (Unique ID) | `proj_id`, `wbs_id`, `task_id`, `clndr_id`, `obs_id`, `task_pred_id`, `actv_code_type_id`, `actv_code_id`, `curr_id`, `fin_dates_id`, `memo_type_id`, `udf_type_id`, `schedoptions_id`, `acct_id`, `rsrc_id` |
| Foreign keys | `parent_wbs_id`, `parent_obs_id`, `parent_actv_code_id`, `base_clndr_id`, `pred_task_id`, `pred_proj_id`, `proj_id` (on every child table), `wbs_id`/`clndr_id` (on TASK), `obs_id` (on PROJWBS), `actv_code_type_id` (on ACTVCODE/TASKACTV) |

The single most damaging violation: putting the **human project code** (e.g.
`W1177`, `HHRETAIL`) into `proj_id`. `proj_id` is the numeric key; the human
code belongs in `proj_short_name` (see 5c).

### 4.2 Datetimes → `YYYY-MM-DD HH:MM` (never a bare date)

P6 datetime columns require a **full date *and* time**, 24-hour, minute
precision: `2026-07-01 08:00`. A bare `2026-07-01` is an *unsupported datetime
format* — it crashes the import (see 5b). Use a work-shift time such as `08:00`
for planned dates and `00:00`/`08:00` consistently for the data date.

- **PROJECT datetimes:** `plan_start_date`, `plan_end_date`, `scd_end_date`,
  `last_recalc_date`, `last_schedule_date`, `fcst_start_date`,
  `last_tasksum_date`, `add_date`, `sum_refresh_date`.
- **TASK datetimes:** `act_start_date`, `act_end_date`, `target_start_date`,
  `target_end_date`, `early_start_date`, `early_end_date`, `late_start_date`,
  `late_end_date`, `restart_date`, `reend_date`, `rem_late_start_date`,
  `rem_late_end_date`, `expect_end_date`, `cstr_date`, `cstr_date2`,
  `suspend_date`, `resume_date`, `create_date`, `update_date`.

### 4.3 Durations, quantities, costs → NUMERIC (decimal), default `0`

- Durations end `_hr_cnt` and are **hours** (days × the calendar's
  `day_hr_cnt`, usually 8): `target_drtn_hr_cnt`, `remain_drtn_hr_cnt`,
  `total_float_hr_cnt`, `free_float_hr_cnt`, `lag_hr_cnt`.
- Units end `_qty`: `target_work_qty`, `act_work_qty`, `remain_work_qty`,
  `target_equip_qty`, `act_equip_qty`, `remain_equip_qty`, and the
  `act_this_per_*` pair.
- These are P6-required on TASK: emit `0` (or `0.0`), **never empty** (see 5a).

### 4.4 Bit flags → `Y` / `N`

Columns ending `_flag` (and a few like `super_flag`) are single-character
`Y`/`N`. Examples: `proj_node_flag`, `sum_data_flag`, `rev_fdbk_flag`,
`lock_plan_flag`, `auto_compute_act_flag`, `default_flag`, `driving_path_flag`.
On TASK/PROJWBS these are P6-required — emit `Y`/`N`, never empty.

### 4.5 Enumerations → prefixed tokens

| Field | Values |
|-------|--------|
| `task_type` | `TT_Task`, `TT_Mile` (start), `TT_FinMile` (finish), `TT_WBS`, `TT_LOE`, `TT_Rsrc` |
| `status_code` | `TK_NotStart`, `TK_Active`, `TK_Complete` |
| `pred_type` | `PR_FS`, `PR_SS`, `PR_FF`, `PR_SF` |
| `cstr_type` / `cstr_type2` | `CS_MSO`, `CS_MSOB`, `CS_MEO`, `CS_MEOB`, `CS_ALAP`, `CS_MANDSTART`, `CS_MANDFIN` |
| `duration_type` | `DT_FixedDrtn`, `DT_FixedDUR2`, `DT_FixedRate`, `DT_FixedQty` |
| `complete_pct_type` | `CP_Phys`, `CP_Drtn`, `CP_Units` |
| `priority_type` | `PT_Top`, `PT_High`, `PT_Normal`, `PT_Low`, `PT_Lowest` |

`priority_type` is P6-required on TASK (`PT_Normal` is the safe default).

### 4.6 Optional-empty vs. required-non-empty

A blank field is fine **only** where P6 tolerates it. Legitimately-empty
examples: `parent_wbs_id` on the root WBS, `base_clndr_id` on a base calendar,
`proj_id` on a global activity-code type, `ev_compute_type` /
`ev_etc_compute_type` on some WBS nodes. Everything in the P6-required sets
(Section 5a) must carry a value on **every** row. The tell of the generator bug
is *internal inconsistency* — some rows fill a column and siblings leave it
blank; that never happens in a genuine P6 export.

### 4.7 Field-name gotchas

- `cstr_type`/`cstr_date` are the Oracle-correct spellings (not `constr_*`).
- Calendar table is `CALENDAR` in modern exports, `CLNDR` in some older ones.
- `last_recalc_date` on PROJECT **is** the data date.
- TASKPRED direction: `task_id` = successor, `pred_task_id` = predecessor.

---

## 5. Common import failures (Westland analysis)

The three failure modes hit while generating proposal schedules, all fixed in
scheduling **10.1.1**. Each is what a colleague will actually bring you: a file
that opens fine in a text editor but detonates on import. All three surface in
P6 as the **same** opaque crash — **Event Code `AVAA0-1866-2`**, an
`EAccessViolation` ("Read of address `0x8`") raised in
`TfrmWizImport.wizImportFinish` — so the SmartPM message (below) is usually the
faster diagnostic.

### 5a. Empty P6-required NOT-NULL columns

- **Symptom:** P6 access-violates on import (`AVAA0-1866-2`). No row-level
  error; the whole import dies at finish.
- **Root cause:** a generated `TASK`/`PROJWBS` row populates only a subset of
  columns, leaving P6's NOT-NULL columns blank — bit-flags, `priority_type`,
  quantity decimals, `obs_id`, `est_wt`, `seq_num`. P6 dereferences these while
  finalizing the import and reads a null. A genuine P6 export fills them on
  every row.
- **Rule:** populate the full required set on **every** row.
  - `TASK`: `phys_complete_pct`, `rev_fdbk_flag`, `est_wt`, `lock_plan_flag`,
    `auto_compute_act_flag`, `complete_pct_type`, `task_type`, `duration_type`,
    `status_code`, `priority_type`, `act_work_qty`, `remain_work_qty`,
    `target_work_qty`, `act_equip_qty`, `remain_equip_qty`, `target_equip_qty`,
    `act_this_per_work_qty`, `act_this_per_equip_qty`.
  - `PROJWBS`: `obs_id`, `seq_num`, `est_wt`, `proj_node_flag`, `sum_data_flag`,
    `status_code`.
  - Types per Section 4: flags `Y`/`N`, quantities `0`, `priority_type`
    `PT_Normal`, `est_wt` `1`.
- **Guard:** `INCOMPLETE_TASK_ROW` / `INCOMPLETE_WBS_ROW`.

### 5b. A bare `YYYY-MM-DD` datetime (no time)

- **Symptom:** SmartPM refuses the file — *"Unknown exception parsing file
  [Unsupported datetime format: …]"*; P6 crashes with `AVAA0-1866-2`.
- **Root cause:** a datetime column (classically the data date,
  `PROJECT.last_recalc_date`) written as `2026-07-01` with no time. P6/SmartPM
  parse these columns as full datetimes and reject a date-only value.
- **Rule:** every datetime is `YYYY-MM-DD HH:MM` (Section 4.2). For the data
  date, pick a shift time (e.g. `2026-07-01 08:00`) and keep it consistent.
- **Guard:** `MALFORMED_DATETIME` (checks the PROJECT and TASK datetime fields).

### 5c. A non-numeric `proj_id`

- **Symptom:** SmartPM refuses the file — *"Unknown exception parsing file [For
  input string: …]"* (a Java `parseLong` failure); P6 crashes with
  `AVAA0-1866-2`.
- **Root cause:** the human project code (e.g. `W1177`, `HHRETAIL`) was written
  into `proj_id`, which is a numeric key. The importer's integer parse fails and
  P6 null-derefs when the key won't bind.
- **Rule — correct field mapping:**
  - `proj_id` = the numeric **Unique ID** (an integer).
  - `proj_short_name` = the human **"Project ID"** code (`W1177`).
  - the long project name = the **root `PROJWBS` node's `wbs_name`** (with
    `proj_node_flag='Y'`).
- **Guard:** `NON_NUMERIC_ID` (checks the integer key/FK columns of PROJECT,
  PROJWBS, TASK, CALENDAR, TASKPRED, OBS, SCHEDOPTIONS, ACTVTYPE, ACTVCODE,
  TASKACTV).

---

## 6. Validator cross-reference

[`lib/xer_validate.py`](../lib/xer_validate.py) enforces the Section-5 rules —
run it via the **`validate_xer_structure`** MCP tool (the file-import gate; see
[`SKILL.md`](../SKILL.md)). `import_ready` is false if any `error`-severity
issue is present. The four checks added in 10.1.1:

| Check code | Category | Severity | Guards against |
|------------|----------|----------|----------------|
| `INCOMPLETE_TASK_ROW` | Data | error | 5a — empty P6-required TASK columns |
| `INCOMPLETE_WBS_ROW` | Data | error | 5a — empty P6-required PROJWBS columns |
| `MALFORMED_DATETIME` | Data | error | 5b — bare `YYYY-MM-DD` in a datetime field |
| `NON_NUMERIC_ID` | Data | error | 5c — text in an integer key/FK |

Calibration: all four were audited against 204 real, P6-importable Westland
exports so they never false-flag a genuine file. Two deliberate design points:

- `INCOMPLETE_*` only requires a column when **some sibling row in the same
  table populates it** — i.e. it flags the *internally-inconsistent* "half-built"
  file (the generator-bug signature), not a uniformly-sparse legitimate export.
  `ev_compute_type` / `ev_etc_compute_type` are intentionally **not** required —
  91 of the 204 audited exports leave them empty on some nodes.
- `NON_NUMERIC_ID` and `MALFORMED_DATETIME` check **non-empty values only**, so
  legitimately-empty optional FKs (root `parent_wbs_id`, base `base_clndr_id`,
  global `proj_id`) pass.

These join the pre-existing file-integrity checks (`DUPLICATE_ACTIVITY_ID`,
`DANGLING_PREDECESSOR`/`SUCCESSOR`/`CALENDAR`, `CIRCULAR_LOGIC`, `SELF_LOOP`,
`INVALID_DATE`, `INVALID_RELATIONSHIP_TYPE`, `INVALID_STATUS_CODE`,
`ORPHAN_ACTIVITY`, and the duplicate/structure/status family). Always run
`validate_xer_structure` after any XER write and confirm `import_ready: true`
before handing a file to P6, SmartPM, or Procore.

---

*Field maps: Oracle, "Primavera P6 EPPM XER Import/Export Data Map Guide
(Project)," Version 23 (April 2023). Data types, failure analysis, and validator
mapping: Westland Construction.*
