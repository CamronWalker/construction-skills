# WBS Patterns for Proposal Schedules

The Westland standard WBS (from `westland-procedures-summary.md`) is the starting tree:

```
PROJECT
  SUMMARY & MILESTONES
  PRE-CONSTRUCTION
  PROCUREMENT
  CONSTRUCTION
  COMMISSIONING & CLOSE-OUT
```

Where **DEMOLITION** and **post-demo sitework** attach depends on the project's phasing. Pick the pattern from the decision table at the bottom, confirm with the user in Phase 3 before generating activities, then apply.

## Skeleton and the WBS ID baseline

`create_xer_from_template("westland-skeleton-v1", ...)` writes the standard base tree shown above, plus the mid-level standard sub-nodes under each top-level band (DESIGN under PRE-CONSTRUCTION; SITEWORK/STRUCTURE/ENCLOSURE/INTERIOR under CONSTRUCTION; etc.) and two milestones (MILESTONE-NTP, MILESTONE-SC). The skeleton's PROJECT root node has `wbs_id="1"`. The skeleton assigns sequential `wbs_id` values starting at 1; the highest `wbs_id` in the v1 skeleton is **21**. Every `add_wbs` in the first `apply_xer_changes` call therefore receives ids starting at 22.

**Recommended approach — dry-run capture:** Rather than hardcoding predicted ids (which break if the skeleton changes), make a first call with `dry_run=True` and `strict=False`. Each change record in the response includes a `result` block with `new_wbs_id`. Collect those ids, then build the real `add_wbs` list using the captured values as `parent_wbs_id` for child nodes. This is more verbose but is immune to skeleton version changes.

The hardcoded-id examples below are illustrative. In production, use the dry-run-capture approach.

## Pattern A — Greenfield / Full Teardown First

DEMOLITION sits between PROCUREMENT and CONSTRUCTION. Post-demo sitework is normal new-school sitework under CONSTRUCTION/SITEWORK.

```
PROJECT
  SUMMARY & MILESTONES
  PRE-CONSTRUCTION
  PROCUREMENT
  DEMOLITION                         <- top-level, before CONSTRUCTION
    HAZMAT ABATEMENT
    UTILITY DISCONNECT
    BUILDING DEMO
    GRUB
  CONSTRUCTION
    SITEWORK                         <- normal sitework path
      INITIAL SITEWORK
      BALANCE OF SITEWORK
    STRUCTURE & SUBROUGH
    BUILDING ENCLOSURE
    INTERIOR ROUGH-IN & FINISHES
  COMMISSIONING & CLOSE-OUT
```

**Triggers:**
- Site has structures that come down fully before construction starts
- No occupancy during build
- Post-demo footprint becomes the new-school footprint

### MCP change records for Pattern A

The skeleton already has CONSTRUCTION/SITEWORK and its children. Pattern A only adds the DEMOLITION top-level branch and its four children. No FINAL SITEWORK is needed — post-demo sitework goes under the standard CONSTRUCTION/SITEWORK.

Using the dry-run-capture approach: run one `apply_xer_changes` with `dry_run=True` to capture `new_wbs_id` for DEMOLITION (call it `$DEMO_ID`), then run the real call. For illustration, assuming DEMOLITION receives id 22:

```json
[
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO",
      "wbs_name":      "DEMOLITION",
      "parent_wbs_id": "1",
      "wbs_short_name": "DEMO"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.HAZ",
      "wbs_name":      "HAZMAT ABATEMENT",
      "parent_wbs_id": "22",
      "wbs_short_name": "HAZMAT"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.UTIL",
      "wbs_name":      "UTILITY DISCONNECT",
      "parent_wbs_id": "22",
      "wbs_short_name": "UTIL DISC"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.BLDG",
      "wbs_name":      "BUILDING DEMO",
      "parent_wbs_id": "22",
      "wbs_short_name": "BLDG DEMO"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.GRUB",
      "wbs_name":      "GRUB",
      "parent_wbs_id": "22",
      "wbs_short_name": "GRUB"
    }
  }
]
```

In the real (non-dry-run) call, replace `"22"` with the `new_wbs_id` captured from the dry run for the DEMOLITION record. Then append all `add_activity` and `add_logic` records for the full project and make one bulk call.

## Pattern B — Occupied-Building Rebuild

DEMOLITION is a top-level branch **after** CONSTRUCTION, before COMMISSIONING & CLOSE-OUT. A **FINAL SITEWORK** sub-branch nests under DEMOLITION to hold the post-demo work on the old footprint.

```
PROJECT
  SUMMARY & MILESTONES
  PRE-CONSTRUCTION
  PROCUREMENT
  CONSTRUCTION                       <- new building on undeveloped portion of site
    SITEWORK                         <- new-school-adjacent sitework only
      INITIAL SITEWORK
      BALANCE OF SITEWORK
    STRUCTURE & SUBROUGH
    BUILDING ENCLOSURE
    INTERIOR ROUGH-IN & FINISHES
  DEMOLITION                         <- top-level, AFTER CONSTRUCTION
    HAZMAT ABATEMENT
    UTILITY DISCONNECT
    BUILDING DEMO
    GRUB
    FINAL SITEWORK                   <- post-demo site buildout
      INITIAL SITEWORK
      BALANCE OF SITEWORK
      SITEWORK COMPLETION
  COMMISSIONING & CLOSE-OUT
```

**Triggers:**
- Occupants stay in the existing structure through new-construction Substantial Completion
- Demo begins at or after SC (students move in, old school empties)
- Old footprint becomes fields, courts, paving, parking, or other non-building use

**Why the structure matters:** A reviewer needs to see "what happens during construction" and "what happens after demo" as two separate branches. The post-demo activities (paving, striping, mow strips, topsoil, irrigation, playground, bollards, hardscape, site lighting) physically cannot start until demo is done. Putting them under new-school SITEWORK implies they run alongside new-school construction, which is false and misreads in any SmartPM or P6 review.

This was the SFJHS case. The skill originally missed it because the "add DEMOLITION above CONSTRUCTION" one-liner covered only Pattern A.

### MCP change records for Pattern B

Pattern B adds DEMOLITION as a top-level branch (after CONSTRUCTION in display order, controlled by activity sequence rather than WBS order in P6) and nests FINAL SITEWORK under DEMOLITION with three children. The skeleton has no DEMOLITION branch, so all eight records below are new.

Full `add_wbs` list (run with `dry_run=True` first to capture ids; the sequence below illustrates the id progression assuming skeleton max wbs_id = 21):

```json
[
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO",
      "wbs_name":      "DEMOLITION",
      "parent_wbs_id": "1",
      "wbs_short_name": "DEMO"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.HAZ",
      "wbs_name":      "HAZMAT ABATEMENT",
      "parent_wbs_id": "22",
      "wbs_short_name": "HAZMAT"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.UTIL",
      "wbs_name":      "UTILITY DISCONNECT",
      "parent_wbs_id": "22",
      "wbs_short_name": "UTIL DISC"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.BLDG",
      "wbs_name":      "BUILDING DEMO",
      "parent_wbs_id": "22",
      "wbs_short_name": "BLDG DEMO"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.GRUB",
      "wbs_name":      "GRUB",
      "parent_wbs_id": "22",
      "wbs_short_name": "GRUB"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.FSITE",
      "wbs_name":      "FINAL SITEWORK",
      "parent_wbs_id": "22",
      "wbs_short_name": "FINAL SITE"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.FSITE.INIT",
      "wbs_name":      "INITIAL SITEWORK",
      "parent_wbs_id": "27",
      "wbs_short_name": "INIT SITE"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.FSITE.BAL",
      "wbs_name":      "BALANCE OF SITEWORK",
      "parent_wbs_id": "27",
      "wbs_short_name": "BAL SITE"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.FSITE.COMP",
      "wbs_name":      "SITEWORK COMPLETION",
      "parent_wbs_id": "27",
      "wbs_short_name": "SITE COMP"
    }
  }
]
```

**Id progression in the example above** (skeleton max = 21):

| Record | wbs_name | Receives id |
|--------|----------|-------------|
| 1 | DEMOLITION | 22 |
| 2 | HAZMAT ABATEMENT | 23 |
| 3 | UTILITY DISCONNECT | 24 |
| 4 | BUILDING DEMO | 25 |
| 5 | GRUB | 26 |
| 6 | FINAL SITEWORK | 27 |
| 7 | INITIAL SITEWORK (under FINAL SITEWORK) | 28 |
| 8 | BALANCE OF SITEWORK (under FINAL SITEWORK) | 29 |
| 9 | SITEWORK COMPLETION (under FINAL SITEWORK) | 30 |

In production, replace all parent_wbs_id references with values captured from the dry-run pass — do not assume the skeleton's max wbs_id stays at 21 across skeleton versions.

After the `add_wbs` records, append the full `add_activity` and `add_logic` records for every activity and relationship in the project, then make one bulk call.

## Pattern C — Phased Turnover / Partial Occupancy

Two viable shapes depending on how the phasing breaks out. Either interleave DEMOLITION with construction phases, or keep DEMOLITION as one top-level branch with timing driven by the phasing plan.

**Shape C1 — interleaved phases:**

```
PROJECT
  SUMMARY & MILESTONES
  PRE-CONSTRUCTION
  PROCUREMENT
  PHASE 1 CONSTRUCTION
  PHASE 1 TURNOVER
  DEMOLITION (partial)               <- only what Phase 2 needs cleared
  PHASE 2 CONSTRUCTION
  PHASE 2 TURNOVER
  ...
  COMMISSIONING & CLOSE-OUT
```

**Shape C2 — single DEMOLITION branch, phased internally:**

```
PROJECT
  SUMMARY & MILESTONES
  PRE-CONSTRUCTION
  PROCUREMENT
  CONSTRUCTION (phased internally by wing/building/area)
  DEMOLITION
    PHASE 1 DEMO
    PHASE 2 DEMO
    FINAL SITEWORK (if applicable)
  COMMISSIONING & CLOSE-OUT
```

**Triggers:**
- Owner occupies parts of the site in stages
- Demo interleaves with construction phases (e.g., wing-by-wing hospital renovation, school addition with partial teardown of an existing wing)

Shape C1 reads more clearly when turnover milestones are contractual. Shape C2 reads more clearly when the phases are internal logistics and the owner only cares about the final turnover. Pick based on how the contract structures turnover.

### MCP change records for Pattern C

Pattern C structures vary more than A or B. The records below are representative examples for each shape, not exhaustive. Tailor the phase names, count, and nesting to the contract's actual phasing structure.

**Shape C1 — interleaved phases (representative two-phase example):**

The skeleton has no PHASE branches. Add them as top-level nodes under the PROJECT root, interspersed with a DEMOLITION node. Display order in P6 follows the activity sequence, not WBS order, so ensure milestones and logic drive the right reading.

```json
[
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "PH1",
      "wbs_name":      "PHASE 1 CONSTRUCTION",
      "parent_wbs_id": "1",
      "wbs_short_name": "PH1 CONSTR"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "PH1TO",
      "wbs_name":      "PHASE 1 TURNOVER",
      "parent_wbs_id": "1",
      "wbs_short_name": "PH1 TO"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO",
      "wbs_name":      "DEMOLITION",
      "parent_wbs_id": "1",
      "wbs_short_name": "DEMO"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "PH2",
      "wbs_name":      "PHASE 2 CONSTRUCTION",
      "parent_wbs_id": "1",
      "wbs_short_name": "PH2 CONSTR"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "PH2TO",
      "wbs_name":      "PHASE 2 TURNOVER",
      "parent_wbs_id": "1",
      "wbs_short_name": "PH2 TO"
    }
  }
]
```

Add DEMOLITION children (HAZMAT, UTILITY DISCONNECT, BUILDING DEMO, GRUB) using the id captured from the DEMOLITION node's dry-run pass, same as in Pattern A.

**Shape C2 — single DEMOLITION branch, phased internally:**

The skeleton's CONSTRUCTION node already exists. Add phase children under CONSTRUCTION, then add a top-level DEMOLITION with internal phase nodes:

```json
[
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO",
      "wbs_name":      "DEMOLITION",
      "parent_wbs_id": "1",
      "wbs_short_name": "DEMO"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.PH1",
      "wbs_name":      "PHASE 1 DEMO",
      "parent_wbs_id": "22",
      "wbs_short_name": "PH1 DEMO"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.PH2",
      "wbs_name":      "PHASE 2 DEMO",
      "parent_wbs_id": "22",
      "wbs_short_name": "PH2 DEMO"
    }
  },
  {
    "type": "add_wbs",
    "spec": {
      "wbs_code":      "DEMO.FSITE",
      "wbs_name":      "FINAL SITEWORK",
      "parent_wbs_id": "22",
      "wbs_short_name": "FINAL SITE"
    }
  }
]
```

Replace `"22"` with the DEMOLITION id captured from the dry-run pass. Add FINAL SITEWORK children (INITIAL SITEWORK, BALANCE OF SITEWORK, SITEWORK COMPLETION) if the contract has post-demo site buildout, using the same approach as Pattern B.

## Standard Westland WBS (no DEMOLITION)

When there is no demolition in scope — new construction on a clear site, or an interior fit-out — the skeleton's base tree is the complete WBS structure. No `add_wbs` records are needed for the WBS itself.

### MCP change records for the Standard baseline

Skip the `add_wbs` records entirely. The `apply_xer_changes` call for a standard project contains only `add_activity` and `add_logic` records:

```json
[
  {
    "type": "add_activity",
    "spec": {
      "code":          "A1010",
      "name":          "Mobilization",
      "duration_days": 5,
      "calendar_id":   "CAL-5DAY",
      "wbs_id":        "<skeleton wbs_id for CONSTRUCTION or appropriate node>",
      "activity_type": "TT_Task"
    }
  },
  {
    "type": "add_logic",
    "predecessor_id": "MILESTONE-NTP",
    "successor_id":   "A1010",
    "relationship":   "FS",
    "lag_days":       0
  }
]
```

Reference `create_xer_from_template`'s returned `ntp_milestone` and `sc_milestone` task_ids when writing logic records to and from the skeleton milestones. The skeleton's WBS node ids for the standard bands are stable within a skeleton version — run a single dry-run call with no changes (empty `changes=[]`) to inspect the current id map if needed.

## Decision Table

| Occupancy during construction | Demo timing relative to SC | Pattern |
|---|---|---|
| Site empty / full teardown before new work | Before construction starts | **A** |
| Full occupancy of the existing structure | At or after Substantial Completion | **B** |
| Partial / rolling occupancy with phased turnover | Interleaved with construction phases | **C** |
| No demolition in scope | — | Standard Westland WBS (no DEMOLITION branch) |

## How to use in Phase 3

When the Phasing & Occupancy Profile (Phase 2) is clear, present the pattern choice to the user **before** generating activities:

> "Based on the phasing profile (full occupancy through SC, demo after SC, old footprint becomes fields), I'm using **Pattern B**: DEMOLITION top-level after CONSTRUCTION, with FINAL SITEWORK nested under DEMOLITION for the old-footprint work. Confirm before I lay out activities?"

If the profile is ambiguous (e.g., phasing language in the RFP is unclear), surface it as a Phase 4 question rather than guessing. The WBS pattern is too structural to quietly assume.
