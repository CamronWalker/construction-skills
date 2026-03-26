# DCMA 14-Point Assessment — Detailed Reference

This file provides deeper detail on each DCMA metric, including calculation methods, edge cases, and remediation strategies. Load this reference when performing a thorough schedule assessment.

## Table of Contents
1. [Metric Calculation Details](#calculations)
2. [Edge Cases & Exceptions](#edge-cases)
3. [Remediation Playbook](#remediation)
4. [Interpreting Results in Context](#context)

---

## Critical: Scope Filtering

All DCMA metrics should be computed against **incomplete activities only** (status != `TK_Complete`). Completed activities are historical data and don't affect the forward schedule. Both DCMA reviewers and tools like SmartPM/Acumen scope to incomplete work. Also exclude LOE (`TT_LOE`) and WBS summary (`TT_WBS`) activity types from most metrics. Relationships should be filtered to only those between incomplete activities.

See the main `schedule-best-practices/SKILL.md` for the `filter_to_incomplete_scope()` function.

---

## Metric Calculation Details {#calculations}

### 1. Incomplete Logic

**Formula:**
```
incomplete_pct = (activities_with_open_starts + activities_with_open_finishes - duplicates) / total_non_milestone_activities × 100
```

**What counts as "open":**
- Open start: no predecessor relationship of any type (FS, SS, FF, SF)
- Open finish: no successor relationship of any type

**Exclusions (don't count these as violations):**
- Project start milestone (expected to have no predecessor)
- Project finish milestone (expected to have no successor)
- LOE activities that are linked to start/finish of other activities
- Summary-level activities (TT_WBS type) — these inherit dates from children

**Edge case — cross-project links:** If the XER contains multiple projects, relationships that cross project boundaries should still count. An activity with a predecessor in a different project is NOT open.

### 2. Leads (Negative Lag)

**Formula:**
```
leads_count = count of relationships where lag_hr_cnt < 0
leads_pct = leads_count / total_relationships × 100
```

**Why zero tolerance:** Even a single negative lag can distort the critical path. The scheduler calculates the successor's start as predecessor_finish + lag. If lag is -8 hours (one day), the successor starts before the predecessor finishes. This creates a logical impossibility that the scheduler resolves mathematically but that doesn't reflect reality.

**Common offenders:**
- "Start framing 2 days before drywall delivery" — replace with SS relationship from "Order Drywall" to "Start Framing"
- "Begin exterior paint 1 week before interior is complete" — replace with SS from Interior to Exterior with appropriate positive lag

### 3. Positive Lag

**Formula:**
```
lag_pct = count of relationships where lag_hr_cnt > 0 / total_relationships × 100
```

**Acceptable lag uses (judgment calls):**
- Concrete cure time (3-7 days) — borderline. Best practice says make it an activity, but a 3-day cure lag on a FS relationship is widely accepted.
- Submittal review cycles — better as an activity chain (Submit → Review → Approve), but a lag on a FS from "Submit" to "Fabricate" is common in practice.

**Unacceptable lag uses:**
- Lag to represent procurement lead time (should be procurement activities)
- Lag to pad the schedule (add duration to actual activities instead)
- Lag on SS or FF relationships that makes the logic unclear

### 4. Relationship Types

**Formula:**
```
non_fs_pct = (SS_count + FF_count + SF_count) / total_relationships × 100
```

**When non-FS is appropriate:**
- SS: Overlapping work where the successor can start after the predecessor starts (e.g., framing can start on one floor while still framing another)
- FF: When two activities must finish together (e.g., "Install Equipment" FF → "Connect Utilities" — utilities connection must finish when or after equipment install finishes)
- SF: Almost never. This means "predecessor must start before successor can finish." Real-world SF situations are extremely rare. If you see SF relationships, question them.

### 5. Hard Constraints

**Hard vs. soft:**
- Hard: Must Start On / Must Finish On — override the network logic
- Soft: CS_SNET, CS_FNET, CS_SNLT, CS_FNLT — work with the network
- Default: CS_ASAP — no constraint

**P6 hard constraint codes vary between versions — check ALL of these:**
```python
hard_codes = {
    'CS_MSO', 'CS_MFO', 'CS_MEO',  # Short forms
    'CS_MSOA', 'CS_MSOB',           # Must Start On variants
    'CS_MEOA', 'CS_MEOB',           # Must End/Finish On variants
    'CS_MANDSTART', 'CS_MANDEND'    # Full-name variants
}
```

**Also check `cstr_type2`:** P6 supports dual constraints. An activity might have a soft primary constraint (SNET) and a hard secondary constraint (Must Finish On). Always check both `cstr_type` and `cstr_type2`:
```python
cstr1 = task.get('cstr_type', task.get('constraint_type', ''))
cstr2 = task.get('cstr_type2', task.get('constraint_type2', ''))
has_hard = cstr1 in hard_codes or cstr2 in hard_codes
```

**When hard constraints are acceptable:**
- Contractual milestone dates that are truly immovable
- Regulatory deadlines (permit expiration, seasonal restrictions with fixed dates)
- Even in these cases, prefer attaching the constraint to a milestone activity rather than a work activity

### 6. High Float

**Calculation:**
```
# Convert float threshold to hours based on calendar
# Standard: 44 working days × 8 hrs/day = 352 hours
high_float_tasks = [t for t in tasks if total_float_hrs > threshold_hrs]
high_float_pct = len(high_float_tasks) / total_tasks × 100
```

**What high float really means:**
- > 44 days: The activity can slip over 2 months without affecting the project finish
- This is often a symptom, not a problem itself. The root cause is usually missing logic.
- Some activities genuinely have high float (e.g., landscaping that can happen anytime in the last 3 months). But if 20% of your activities have high float, the schedule has logic gaps.

### 7. Negative Float

**Root causes of negative float:**
- A hard constraint (MSO/MFO) that conflicts with the logic network
- The schedule was updated with delays but the finish date wasn't extended
- An out-of-sequence update (activity started before its predecessor finished)
- The schedule genuinely can't make the deadline with current logic and durations

**How to address:**
1. First, determine if it's a data issue (bad constraint, wrong actual date) or a real schedule problem
2. If real, identify the activities driving the negative float (usually on or near the critical path)
3. Options: crash durations, fast-track by changing logic, negotiate the deadline, or increase resources

### 8. High Duration

**Threshold logic:**
- 44 working days ≈ 2 calendar months
- Activities longer than this are too coarse for effective management
- Exception: procurement/fabrication activities where the contractor has no daily control (e.g., "Fabricate Steel" at 60 days is acceptable if it's a vendor-controlled duration)

**Decomposition guidance:**
- Break by physical area: "Install HVAC" → "Install HVAC - Floor 1", "Install HVAC - Floor 2"
- Break by phase: "Install Roofing" → "Install Roof Insulation", "Install Roof Membrane", "Install Flashings"
- Break by trade sequence: "MEP Rough-in" → "Plumbing Rough-in", "Electrical Rough-in", "HVAC Rough-in"

---

## Edge Cases & Exceptions {#edge-cases}

### Level of Effort (LOE) Activities
LOE activities derive their dates from linked activities, not from their own logic. This creates special handling:
- Don't count LOE activities in the logic completeness check (they have links, not predecessors/successors)
- Don't count LOE durations in the high duration check (their duration is calculated, not planned)
- Do verify that every LOE has proper start and finish links

### External Constraints vs. Hard Constraints
A milestone with CS_SNET (Start No Earlier Than) that represents a permit date is fundamentally different from a work activity with a Must Start On constraint (CS_MSOA / CS_MANDSTART). The first is good practice — the constraint represents a real-world dependency. The second is schedule manipulation.

When counting constraints, distinguish between:
- Milestone constraints (usually acceptable)
- Work activity constraints (usually problematic)
- Constraint type (hard vs. soft)

### Multi-Calendar Schedules
When a schedule uses multiple calendars (5-day for office work, 6-day for site work, 7-day for concrete), float calculations become complex. An activity with 40 hours of float on a 5-day calendar has 5 days of float. The same 40 hours on an 8-day, 10-hour calendar has 4 days.

Always convert float to working days using the activity's assigned calendar when comparing against thresholds.

---

## Remediation Playbook {#remediation}

Priority order for fixing schedule issues (address these in order):

1. **Negative float** — This is urgent. The schedule says the project can't make its deadline.
2. **Incomplete logic** — This undermines everything else. Dates for unlinked activities are meaningless.
3. **Leads (negative lags)** — These create false logic and distort the critical path.
4. **Hard constraints** — Remove or soften constraints that override the network.
5. **Critical path test** — Verify the critical path tells a coherent story.
6. **High float** — Add missing logic to pull high-float activities into the network.
7. **High duration** — Decompose long activities for better tracking.
8. **Lags** — Replace significant lags with explicit activities.
9. **Relationship types** — Review non-FS relationships for appropriateness.

### When to Accept Threshold Violations
Not every violation needs to be fixed. Context matters:

- **Proposal schedule:** More latitude. The schedule is a planning tool, not a control baseline. 5-10% logic gaps may be acceptable if the overall approach is sound.
- **Baseline schedule:** Strict. This is the control document. Aim for zero or near-zero violations on all metrics.
- **Update schedule:** Moderate. Some violations may result from real-world conditions (out-of-sequence starts, owner-caused delays). Document them but don't necessarily "fix" them by falsifying the data.

---

## Interpreting Results in Context {#context}

### What a "Good" Score Looks Like

A well-built CPM schedule typically scores:
- Logic: < 2% incomplete
- Leads: 0
- Lags: < 3%
- Relationship types: < 8% non-FS
- Constraints: < 2% hard constraints
- High float: < 3%
- Negative float: 0
- High duration: < 3%
- CPLI: 1.0 - 1.1
- BEI: 0.95 - 1.05

### Red Flags That Go Beyond the Numbers
Even if the metrics look good, watch for:
- **Logic density too low:** If there are 500 activities and 400 relationships, the ratio is 0.8 — many activities probably have only one predecessor. Healthy schedules typically have 1.5-2.5 relationships per activity.
- **All activities on the critical path:** If 80% of activities have zero float, something is wrong — probably a constraint chain or a single logic path with no parallel work.
- **Uniform durations:** If every activity is exactly 5 or 10 days, the scheduler probably didn't estimate individual activities — they used default durations.
- **No milestones:** A schedule without milestones has no checkpoints for management reporting.
- **No procurement activities:** Long-lead items not in the schedule will cause surprises.
