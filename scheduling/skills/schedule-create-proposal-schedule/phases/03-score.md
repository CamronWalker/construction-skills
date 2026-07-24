# Phase 7: Score & Iterate

Load this file when scoring schedule quality (DCMA / Westland rubric)
and fixing failing checks. This is a separate iteration loop from the
paste-back loop in `phases/02-iterate.md`: scoring fixes are about
schedule *quality* (logic, float, dangling), not about Camron's content
edits.

For paste-back iteration, see `phases/02-iterate.md`.

---

**Letter grade targets are ranges, not floors.** If the user asks for "at least an A", treat the lower bound of that letter (A- = 90) as the stopping point. Confirm at that threshold and only push higher if the user explicitly accepts the trade-off:

> *"I can get you to 93 but only by adding 100+ soft constraints; the A- at 90.5 is cleaner. Which do you want?"*

A 90.5 (A-) with honest logic beats a 95.0 (A) propped up by bulk soft constraints. The Westland procedures doc is explicit: "teams must resist the temptation to then assume the schedule is accurate. It may be a great outline, but without real input from trade partners, suppliers, design teams, owners, etc. the schedule will not be a true reflection of how the work will progress." A reviewer who opens a proposal with 140 CS_FNLT constraints reads it as dishonest -- which is how Westland loses a job, not wins one.

### How to iterate -- targeted, not full-rescore

**Run the full score ONCE** (`score_schedule.py <xer>`) to identify which metrics are failing. After that, query individual checks via the toolbox's `quality_checks.py <check_name> <xer>` CLI to get the specific failing activities as JSON -- no rescoring the whole schedule per fix. Each check returns `task_code`, `task_name`, and `issues[]` for every offender. Examples:

```
python quality_checks.py dangling <xer>
python quality_checks.py missing_logic <xer>
python quality_checks.py high_float <xer>
python quality_checks.py soft_constraints <xer>
python quality_checks.py out_of_sequence <xer>
```

Fix what that check surfaces, then query the next failing check. Rescore with `score_schedule.py` at most once per major iteration to confirm progress -- not after every edit.

### The two buckets -- never mix in one iteration

Classify each failing metric into ONE bucket and fix each in a separate iteration:

**Bucket 1 -- Real-logic fixes (always allowed)**
- Add genuinely missing logic ties (from `missing_logic` and `dangling` check results)
- Tighten FS->SS/FF where parallel work is real and documented in the sample
- Remove redundant ties (`duplicate_rels` check)
- Fix wrong predecessors (`out_of_sequence`)
- Correct calendar assignments

**Bucket 2 -- Rubric-adjusting moves (STOP and ask before applying)**
- Bulk CS_FNLT / CS_FNET to pin late dates against the float deduction
- Bulk CS_MEOA / CS_MEOB on milestones with no contract or physical basis
- Adding milestones solely to shorten the longest path
- Closing open-ends with nonsense terminal ties

Hard cap: no more than 5 soft constraints added in a single iteration without user consent. Any bulk pass must be a separate, user-approved iteration, not mixed in with real-logic fixes.

### Before closing dangling activities -- classify first

Dangling activities are not all the same bug, and the wrong close is worse than leaving it open. Build the classification from `quality_checks.py dangling <xer>` and choose the close per-category:

- **Procurement chain (fabricate -> deliver)** -> tie the delivery activity to its **installation activity** (the trade activity that consumes the material). Procurement should not dangle, but it also should not be artificially tied to Construction Clean or any unrelated milestone. The correct successor is whichever activity physically uses the material.

  **Guard rail:** before accepting a procurement -> installation tie as final, check whether that procurement chain is the sole driver of the first phase of the schedule. A 12-month lead time must not be the first 12 months of an 18-month project -- that would mean no parallel work is happening during procurement, which is never true. If procurement is solo-driving: look for the parallel work that should be running alongside (preconstruction activities, early trade prequal, site prep, design milestones for CM/GC, mobilization, early-release site packages) and wire those in. Procurement is one stream of many, not the spine.

  In the sample schedule, long-leads may intentionally dangle to save modeling time for a proposal package; do not copy that pattern into the output without giving each procurement chain its real installation successor.

- **Intermediate activity missing a successor** -> real logic bug. Close with the correct downstream activity (not a sweeping FS+0 to a terminal milestone).
- **Terminal-looking activity** (final inspections, survey, closeout) -> confirm it genuinely ends the project before tying to a milestone.

Ask for user confirmation on the classification table before mass-closing.

### Stopping rule

After TWO iterations of real-logic fixes, if still below the lower-bound target:
1. Stop iterating.
2. Produce a narrative note documenting remaining deductions as structural to the schedule approach (e.g., *"SS% is 19% because this is a compressed fast-track; defensible in narrative"*).
3. Deliver the current schedule + the note for the proposal package.

Letter grade is a floor, not a target to maximize. Present the final quality report, the narrative note (if any), and XER file location when complete. Then run the final XER-validation gate (see `02-iterate.md`) -- import-readiness is a hard gate on the deliverable.
