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
