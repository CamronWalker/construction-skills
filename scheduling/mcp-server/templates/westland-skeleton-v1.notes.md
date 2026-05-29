# westland-skeleton-v1.xer — Curation Notes

## PENDING MANUAL VALIDATION

This skeleton passed round-trip byte-identity and `xer_validate` (import_ready=True,
zero errors) but has **NOT yet been import-tested in Primavera P6 or Procore**.
That gate is required before scheduling 9.0.0 is distributed. Until then, treat
the skeleton as a validated artifact pending final acceptance, not a production-ready
template.

Manual validation steps remaining:
1. Import `westland-skeleton-v1.xer` into a Primavera P6 test environment and confirm
   the project appears with the correct WBS tree, two milestones, and the NTP->SC FS edge.
2. Confirm the calendar "Standard" (clndr_id 18261) loads correctly with its work-week
   definition intact.
3. Import the same file into Procore (Schedule module) and confirm the project can be
   created and activities are visible.
4. Only after both imports succeed: remove this section and distribute 9.0.0.

---

## Donor File

- **Path:** `C:\Users\camron\OneDrive - Westland Construction\40 Cowork\training_data\Proposal Schedules\BTLP.xer`
- **Name:** Bountiful Temple Landscape Water Conserve Project (BTLP)
- **Encoding:** cp1252 (standard P6 Windows export)
- **Validated in:** Primavera P6 (real project, exported 2026-03-16)
- **Table inventory:** CURRTYPE(18), FINTMPL(1), MEMOTYPE(1), OBS(1), UDFTYPE(1),
  PROJECT(1), CALENDAR(364), SCHEDOPTIONS(1), PROJWBS(9), ACTVTYPE(7), TASK(43),
  WBSMEMO(1), ACTVCODE(60), TASKPRED(46), TASKACTV(301), UDFVALUE(41)

BTLP is used as the donor because it is a recent, P6-validated Westland proposal schedule
with a clean structure, a self-contained Standard calendar, and the full set of Westland
global lookup tables (CURRTYPE, ACTVTYPE, ACTVCODE).

---

## Build Process

The skeleton is produced by `build_skeleton.py` in the repo root (not committed; used only
during E2). It calls `xer_io.parse_for_writing` on the donor, surgically replaces or
rebuilds each table per the recipe below, then writes via `xer_io.write`. The Write tool
is never used on `.xer` paths — the PreToolUse hook blocks it.

---

## Per-Table Decisions

### Tables Kept Verbatim

These sections are preserved as-is from the donor, including their original raw_lines for
byte-identical round-trip:

| Table | Rows | Rationale |
|-------|------|-----------|
| CURRTYPE | 18 | P6 currency/unit global lookup — reusable across projects |
| FINTMPL | 1 | Financial template reference — Westland standard |
| MEMOTYPE | 1 | Memo type lookup — Westland standard |
| OBS | 1 | Organizational Breakdown Structure node — Westland obs_id 540 |
| UDFTYPE | 1 | User-defined field type definition — Westland standard |
| ACTVTYPE | 7 | Activity type lookup — Westland standard 7 types |
| ACTVCODE | 60 | Activity code values — Westland standard 60 codes |

### CALENDAR — Filtered to One Row

The donor contained 364 calendars (global + resource + project calendars from the full P6
database). Only **clndr_id 18261 ("Standard")** is retained.

Rationale:
- PROJECT.clndr_id = 18261; all tasks reference it.
- clndr_id 18261 has `base_clndr_id = ''` (self-contained, no parent calendar dependency).
- day_hr_cnt=8, week_hr_cnt=40: standard M-F 8-hour workday.
- Dropping the other 363 calendars eliminates irrelevant resource/global calendars that
  would confuse import and bloat the template.

The calendar row's `proj_id` is updated to 'TEMPLATE' for consistency with all other
TEMPLATE-stamped proj_id fields.

### PROJECT — Placeholder Substitution

Start from BTLP's 71-field PROJECT row. Project-specific fields are cleared or replaced
with template placeholders. The 57 constant fields (scheduling options, default types,
EV settings, etc.) are kept verbatim from BTLP — they represent Westland's standard
project configuration.

Fields replaced:

| Field | Template value | Reason |
|-------|----------------|--------|
| proj_id | "TEMPLATE" | Referential anchor; all tables use this |
| proj_short_name | "TEMPLATE" | Project-specific |
| task_code_prefix | "" | Set per-project at creation |
| plan_start_date | "" | Set by create_xer_from_template |
| scd_end_date | "" | Set by create_xer_from_template |
| last_recalc_date | "" | No CPM run on template |
| last_schedule_date | "" | No CPM run on template |
| fcst_start_date | "" | Set by create_xer_from_template |
| plan_end_date | "" | Set by create_xer_from_template |
| guid | "" | P6 generates on import; empty is cleaner for a template |
| add_date | "" | Cosmetic; removed for clean template |
| add_by_name | "" | Cosmetic; removed for clean template |

`clndr_id` is kept as "18261" (matches the retained calendar).

### SCHEDOPTIONS — proj_id Fixed

Single row kept verbatim except `proj_id` updated to 'TEMPLATE'. All scheduling option
values (retained logic, float type, outer dependency type, etc.) are kept from BTLP as
Westland's standard scheduling configuration.

### PROJWBS — Canonical Westland Tree (Rebuilt)

The BTLP-specific WBS tree (9 nodes) is replaced with the 21-node canonical Westland
proposal schedule WBS structure. Nodes are assigned sequential integer IDs 1–21;
seq_num is in steps of 100 within each parent's children.

The root node (wbs_id=1, proj_node_flag='Y') has `parent_wbs_id = ""` (empty string).
**Convention:** P6 import places the project under the importer-selected EPS node;
an empty parent_wbs_id on the proj_node_flag=Y root is the standard template convention.
The importer will attach the root to whatever EPS node they select during import.

Canonical tree:

```
1   PROJECT (root)
├── 2   SUMMARY & MILESTONES
│   ├── 3   CONTRACT MILESTONES & SUMMARY BARS
│   └── 4   KEY PERFORMANCE MILESTONES          ← milestones live here
├── 5   PRE-CONSTRUCTION
│   └── 6   DESIGN
│       ├── 7   ESTIMATES - CONSTRUCTABILITY REPORTS - SCHEDULE UPDATES
│       ├── 8   BIM MODELING
│       ├── 9   TRADE PRE-QUALIFICATION
│       ├── 10  BUY OUT - PROPOSAL & AWARD
│       └── 11  OWNER PERMIT / CONSENT PROCESS
├── 12  PROCUREMENT
│   └── 13  SUBMITTALS - APPROVALS - FABRICATION - DELIVERY
├── 14  CONSTRUCTION
│   ├── 15  SITEWORK
│   │   ├── 16  INITIAL SITEWORK
│   │   └── 17  BALANCE OF SITEWORK
│   ├── 18  STRUCTURE & SUBROUGH
│   ├── 19  BUILDING ENCLOSURE - WINDOWS - ENTRIES - FINISH SYSTEMS
│   └── 20  INTERIOR ROUGH-IN & FINISHES
└── 21  COMMISSIONING & CLOSE-OUT
```

Constant fields inherited from BTLP root row: est_wt='1', sum_data_flag='N',
status_code='WS_Open', ev_compute_type='EC_Cmp_pct', ev_etc_compute_type='EE_PF_cpi',
obs_id='540'. GUID and tmpl_guid cleared to '' on all nodes.

### TASK — Two Milestones (Rebuilt)

BTLP's 43 tasks are replaced with 2 template milestones, both placed under
wbs_id=4 (KEY PERFORMANCE MILESTONES). Template is BTLP4 ("Anticipated Notice To Proceed",
TT_FinMile), which carries all the correct constant field defaults.

| task_id | task_code | task_name | task_type |
|---------|-----------|-----------|-----------|
| 1 | MILESTONE-NTP | Notice to Proceed | TT_Mile (start milestone) |
| 2 | MILESTONE-SC | Substantial Completion | TT_FinMile (finish milestone) |

All date fields, cstr_type/cstr_type2, guid, tmpl_guid, create_date, update_date,
create_user, update_user cleared to ''. Both tasks reference clndr_id='18261'.

### TASKPRED — One FS Edge (Rebuilt)

Single row: task_id=1 (NTP) -> task_id=2 (SC), pred_type='PR_FS', lag_hr_cnt='0'.
Both milestones are connected, so the `ORPHAN_ACTIVITY` check does not fire.

### WBSMEMO — Dropped

BTLP's WBSMEMO row references wbs_id=222954, which no longer exists in the canonical
tree. Including it would produce a dangling reference. The table is dropped entirely from
the output. An empty WBSMEMO section would trigger an import quirk on some P6 versions;
dropping is cleaner.

### TASKACTV — Dropped

301 rows of activity-code assignments for BTLP's 43 tasks. All tasks were replaced;
all assignments are invalid. Dropped entirely.

### UDFVALUE — Dropped

41 rows of user-defined field values for BTLP's tasks. All tasks were replaced;
all values are invalid. Dropped entirely.

---

## Output Section Order

```
CURRTYPE, FINTMPL, MEMOTYPE, OBS, UDFTYPE, PROJECT, CALENDAR, SCHEDOPTIONS,
PROJWBS, ACTVTYPE, TASK, ACTVCODE, TASKPRED
```

13 sections total (16 donor sections minus WBSMEMO, TASKACTV, UDFVALUE).
The last section (TASKPRED) carries `e_line='%E'`; all others have `e_line=None`,
matching the P6 XER convention.

---

## Validation Results

```
round-trip: OK (byte-identical after parse -> write cycle)
import_ready: True
errors: 0
warnings: 13 (all ORPHANED_WBS_BRANCH)
info: 0
```

The 13 warnings are leaf WBS nodes with no tasks assigned — expected for a 2-milestone
skeleton. These nodes will receive tasks when `create_xer_from_template` generates a
project-specific schedule. The warnings do not affect P6 import ability.

No `ORPHAN_ACTIVITY` warnings: both milestones are connected by the NTP->SC edge.

---

## Usage

This skeleton is the donor for `create_xer_from_template` (Phase F). The tool:
1. Calls `xer_io.parse_for_writing` on this file.
2. Stamps PROJECT with the provided project metadata (proj_id, proj_short_name,
   plan_start_date, etc.).
3. Updates PROJWBS.wbs_id references and TASK/TASKPRED proj_id fields to the new proj_id.
4. Adds project-specific activities under the appropriate WBS nodes.
5. Writes the result via `xer_io.write`.

The skeleton itself is never modified after this commit.
