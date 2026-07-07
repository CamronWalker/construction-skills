---
name: schedule-assign-responsibility
description: >
  Assign or review Westland "Responsibility - Global" (trade) activity codes on a P6/XER
  schedule so every activity carries a responsible party. Use when a schedule has blank or
  unassigned responsibility, when responsibility was bulk-set roughly and needs cleanup, or
  before a baseline / quality pass that expects trades. Trigger on: "assign responsibility",
  "responsibility codes", "responsibility - global", "responsible party", "trade codes",
  "who does this activity", "first pass responsibility", "unassigned responsibility", "code
  the schedule by trade", "fill in responsible parties".
---

# Assign Responsibility (Trade) Codes

## Overview

Westland tags every real activity with a **Responsibility - Global** activity code (the trade). Keyword matching alone tops out ~85% and misfires in predictable ways — masonry coded as structural steel, roof drains as roofing, an A/E submittal review coded as the trade instead of the architect — because historical labels disagree across jobs. The right code is chosen by **reasoning per activity** from its name, its WBS trade context, and who actually self-performs or supplies the work. The MCP is an accelerator; judgment is the decider; the human is asked only on genuine ambiguity.

## Tools & inputs

- `suggest_responsibility(xer_path, only_unassigned=True)` — fast keyword draft: `assigned` (confident), `unsure` (each with `candidates`), and `all_codes` (the canonical list). Treat it as a draft, not truth.
- `list_activities` / `get_activity` — the roster with each activity's WBS path + existing code, and one activity's neighbors, for context.
- `apply_xer_changes` with `set_responsibility` records — writes the code.
- The canonical code list ships in `schedule-toolbox/references/responsibility-codes.json` (also returned as `all_codes`). Edit that JSON to add a trade or tune keywords.
- `TT_WBS` summary rows and `TT_LOE` level-of-effort bars are **not** coded — skip them.

## Method

1. **Accelerate.** Call `suggest_responsibility(only_unassigned=True)` for the draft. `only_unassigned=True` is the normal fill-the-blanks pass; use `False` to re-suggest across everything (needed when cleaning up rough bulk codes).
2. **Reason per activity — do not rubber-stamp the keyword draft.** Pull the roster (`list_activities`), split it into batches of ~50, and dispatch **one subagent per batch** (the Agent/Task tool, or a `Workflow` for deterministic fan-out) to assign each activity a code **plus a one-line rationale**, reasoning from: (a) the activity scope, (b) its `wbs_path` — system / area / phase usually names the trade, (c) who self-performs or supplies it, (d) the existing code — correct rough priors, don't inherit them. Give each subagent its batch rows + `all_codes`; have it write its picks to a file and return them. For a small schedule, adjudicate inline instead of fanning out.
3. **Validate.** Every activity covered exactly once; every code ∈ `all_codes`; re-classify anything a batch dropped. Escalate only genuinely ambiguous cases to the human (a bare "Rough-In" that could be MECH/HVAC/PLUM/ELEC) — don't guess.
4. **Write once.** A single `apply_xer_changes` call carrying all `set_responsibility` records:
   ```json
   { "type": "set_responsibility", "activity_id": "A1050", "code": "ELEC", "name": "Electrical" }
   ```
   It writes the `ACTVTYPE → ACTVCODE → TASKACTV` chain, prefers the global code (never a project-scoped duplicate), replaces any existing code on the activity, and creates the code value if missing. Emits a new `-modified.xer`; never overwrites the source.
5. **Verify.** `list_activities(trade_filter=...)` or re-run `suggest_responsibility(only_unassigned=True)` — confirm the blanks are filled.

## Trade heuristics (where keyword matching misfires)

| Activity | Code | Not |
|---|---|---|
| Masonry / CMU / veneer / "paint & seal block" | MASON (PAINT for the seal coat) | STR-STEEL |
| Structural steel, joists, deck, embeds, anchor bolts | STR-STEEL | ROOF ("joists & deck (low roof)") |
| Bundled "MEP" (in-wall / branch / above-ceiling / rough / finish) | MEP | a single trade |
| Dedicated lighting, panels, transformer, deep-trench electrical | ELEC | MEP |
| Dedicated plumbing / fixtures; RTU / AHU / ductwork / set mech units | PLUM / HVAC | MEP |
| Under-slab vapor barrier, fire-riser slab, geofoam pour, housekeeping pad | CONC-STRU | WB / FIRE / HVAC |
| Snow-melt (hydronic tubing) | MECH | HVAC |
| "A/E Review" / "PE Review" submittal | ARCH | the trade |
| Procurement "Prepare Submittal" / "Procure" / "Fabricate" | trade by procurement WBS (e.g. DHDW for door frames & slabs) | WEST |
| NTP, Construction Start/Duration, Substantial/Final Completion, Turnover, Punchlist, Final Inspections, mobilization, temp protection | WEST | a trade |
| Owner move-in / occupancy | OWNER | WEST |
| IMPACT / delay activities | IMPACTS | — |

Full step detail and code-list notes: `references/responsibility-assignment.md`.

## Common mistakes

- **Rubber-stamping the keyword draft.** It's ~85%; the misfires above are systematic. Reason, don't accept.
- **Inheriting bad existing codes.** Rough bulk priors are common (e.g. everything structural tagged STR-STEEL, masonry included) — re-suggest with `only_unassigned=False` and correct them.
- **Coding LOE/WBS/milestone rows as trades.** Skip `TT_WBS` and `TT_LOE`; milestones are WEST/OWNER, not a trade.
- **Codes not in `all_codes`.** Only use codes from the list; add a real missing trade to `responsibility-codes.json`.
- **Dropping activities in the fan-out.** Validate one-code-per-activity coverage before writing.
- **Multiple write calls.** One `apply_xer_changes` with all records = one CPM run.
