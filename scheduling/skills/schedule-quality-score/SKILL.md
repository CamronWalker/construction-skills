---
name: schedule-quality-score
description: >
  Score a Primavera P6 schedule against industry best practice metrics and output a quality report
  as a Markdown file. Use this skill whenever the user asks to "score a schedule", "grade a schedule",
  "run a quality check", "generate a schedule quality report", "best practice score", "schedule scorecard",
  or wants to evaluate how well a schedule follows CPM scheduling standards. Also trigger when the user
  uploads an XER and asks "how does this schedule look?" or "is this schedule any good?" or wants to
  compare schedule quality across projects. Works with XER files parsed by the schedule-xer-read-modify
  skill. Outputs a .md report with a letter grade, scored metrics, and key findings.
---

# Schedule Quality Score

This skill computes a best practice score for a Primavera P6 schedule and generates a Markdown quality report. The scoring system evaluates schedule quality metrics across relationship health, float analysis, logic completeness, and constraint usage. The algorithm is calibrated against SmartPM grades across 9 real construction schedules.

## How the Scoring Works

**Base score: 100 points.** Points are deducted for each scored metric that falls outside acceptable thresholds. The remaining score maps to a letter grade using the standard academic scale. Informational metrics are reported but don't affect the score.

### Grade Scale

| Grade | Score Range | Color |
|-------|------------|-------|
| A+    | 97 – 100   | Green |
| A     | 93 – 96    | Green |
| A-    | 90 – 92    | Green |
| B+    | 87 – 89    | Yellow-Green |
| B     | 83 – 86    | Yellow |
| B-    | 80 – 82    | Yellow |
| C+    | 77 – 79    | Orange |
| C     | 73 – 76    | Orange |
| C-    | 70 – 72    | Red-Orange |
| D+    | 67 – 69    | Red |
| D     | 65 – 66    | Red |
| D-    | Below 65   | Red |

---

## Scope Filtering (Critical First Step)

Before computing ANY metric, apply two-stage scope filtering:

### Stage 1: Exclude completed tasks and non-schedulable types
- Remove tasks with `status_code == 'TK_Complete'`
- Remove WBS/LOE tasks (`TT_WBS`, `TT_LOE`)
- Keep all incomplete activities and milestones

### Stage 2: Substantial Completion scenario filtering
Walk backward from the Substantial Completion milestone through the predecessor chain to identify the "in-scope" tasks. Only tasks that are predecessors (direct or transitive) of the SC milestone are scored. This matches SmartPM's scenario-based filtering and prevents post-SC activities from inflating missing logic, constraint counts, etc.

**SC milestone priority search:**
1. Name contains both "Substantial Completion" and "Turnover to Owner"
2. Exact name "Substantial Completion" that is a milestone type
3. Any milestone containing "Substantial Completion"

**If no SC milestone is found, use the full incomplete scope (Stage 1 only).**

After SC filtering, rebuild the relationship set to only include relationships between in-scope tasks. Report both total schedule size and filtered scope.

---

## Scored Metrics (These Affect the Grade)

Each metric below can deduct points from the 100-point base. Maximum possible deductions are shown for each metric.

### 1. Relationship Type Distribution (max -8 pts total)

Evaluate FS, SS, FF, SF percentages from in-scope relationships.

| Metric | Passing | Deduction |
|--------|---------|-----------|
| **FS %** | ≥ 90% | -1 pt if 80-90%, -2 pts if < 80% |
| **SS %** | ≤ 5% | -1 pt if 5-10%, -2 pts if > 10% |
| **FF %** | ≤ 5% | -1 pt if 5-10%, -2 pts if > 10% |
| **SF %** | < 1% | -2 pts if ≥ 1% of relationships |

### 2. Average Activity Total Float (max -2 pts)

Mean total float in working days across in-scope activities (not milestones). Scored bidirectionally.

| Range | Deduction |
|-------|-----------|
| < 10 days | -2 pts (schedule too tight or behind) |
| 10 – 15 days | -1 pt (schedule slightly tight) |
| 15 – 44 days | 0 (healthy) |
| > 44 days | -2 pts (logic network too loose) |

Compute: `sum(total_float_hr_cnt for each activity) / count / 8`

**Negative Float Detection:** If average float is negative (< 0), the schedule is in recovery mode. This triggers special handling for Critical Path % and Relationship Ratio (see those sections).

### 3. Critical Path % (max -2.5 pts)

Percentage of incomplete in-scope tasks with total float within ±8 hours of zero.

| Range | Deduction |
|-------|-----------|
| 10% – 20% | 0 (healthy) |
| 5% – 10% or 20% – 25% | -1.5 pts |
| < 5% or > 25% | -2.5 pts |

**SKIP this metric entirely if the schedule has negative average float.**

### 4. High Float Activities (max -2.5 pts)

Activities with total float > 44 working days (352 hours). Penalize when more than 40% of the schedule is high-float.

| Passing | Deduction |
|---------|-----------|
| ≤ 40% | -2.5 pts if > 40% |

Denominator: total incomplete in-scope (activities + milestones).

### 5. Missing Logic (max -10 pts, proportional)

Non-milestone activities missing a predecessor OR a successor. **Critical: check against ALL relationships in the full schedule** (not just in-scope relationships). This prevents scope-boundary artifacts where activities lose their external relationships after SC filtering.

**Scoring: proportional, 1 point per 1% of missing logic, capped at 10. Only deduct if ML ≥ 3%.** Small amounts of missing logic (< 3%) are common at scope boundaries and do not warrant deduction.

| ML % | Deduction |
|------|-----------|
| < 3% | 0 (warning only) |
| 3-10% | 1 pt per 1% (e.g., 3% → -3 pts) |
| > 10% | Capped at -10 pts |

Denominator: total incomplete in-scope (activities + milestones), NOT just activities.

### 6. Total Relationship Ratio (max -5 pts)

Total in-scope relationships ÷ total incomplete in-scope tasks.

| Passing | Deduction |
|---------|-----------|
| ≥ 1.5 | 0 |
| 1.25 – 1.5 | -2.5 pts |
| < 1.25 | -5 pts |

**SKIP this metric entirely if the schedule has negative average float.**

### 7. Constraints (max -20 pts, proportional)

Count activities with date constraints. **Score ALL constraint types combined (hard + soft), EXCEPT CS_ALAP.** SmartPM scores constraints this way — the SC scope filtering already reduces the count to a reasonable level.

**Scoring: proportional, 1 point per 1% of constrained tasks, capped at 20.** Only deduct if the percentage exceeds 1%.

| Constraint % | Deduction |
|-------------|-----------|
| ≤ 1% | 0 |
| 1% – 20% | 1 pt per 1% |
| > 20% | Capped at -20 pts |

**Why CS_ALAP is excluded:** As Late As Possible is a scheduling directive, not a date constraint. It doesn't lock an activity to a specific date. SmartPM does not count ALAP as a constraint.

---

## Informational Metrics (Reported, Not Scored)

These metrics provide valuable context but don't affect the letter grade. Report them in a separate section of the output.

### Network Analysis
- **Convergence Bottlenecks** — Activities with ≥ 5 predecessors (count and %)
- **Divergence Bottlenecks** — Activities with ≥ 5 successors (count and %)
- **Duplicate Relationships** — Activity pairs connected by more than one relationship
- **Dangling Activities** — Missing a FS/SS predecessor AND/OR FS/FF successor
- **Low Float Activities** — Total float between 0 and 10 working days (0–80 hrs)
- **Negative Float Activities** — Total float < 0 (count and %)
- **Hard Constraints** — Count of truly mandatory constraints (CS_MSO, CS_MFO, CS_MEO, CS_MANDSTART, CS_MANDEND, CS_MANDFIN) — reported separately from scored combined count
- **Soft Constraints** — Count of directional constraints (CS_SNET, CS_SNLT, CS_FNET, CS_FNLT, CS_MSOA, CS_MSOB, CS_MEOA, CS_MEOB)
- **ALAP Constraints** — Count of CS_ALAP (not scored, but reported)
- **One Day Activities** — Duration = 8 hours exactly (count and %)
- **High Duration Activities** — Duration > 44 working days (count and %)
- **Positive Lag** — Relationships with positive lag (count and %)
- **Negative Lag** — Relationships with negative lag (count and %)

### Status Quality (require data date)
- **Out of Sequence** — Successor started/completed before predecessor finished
- **Activities Riding Data Date** — Early start = data date but not started
- **Started with 0%** — Status = Active but physical % = 0
- **Future Actual Dates** — Actual start/finish after data date
- **Missing Actual Finish** — 100% complete but no actual finish date recorded
- **Unstatused Activities** — Early dates before data date, not started
- **Remaining Duration Discrepancy** — Remaining duration doesn't match % complete

---

## Implementation

The complete scoring and report generation code is in `references/score_schedule.py`. Read that file and use it directly — do NOT rewrite the scoring logic.

The script provides two main functions:
- `compute_quality_score(tasks, preds, data_date)` → returns `(score, grade, scored, info, deductions, scope_info)`
- `generate_quality_report(project_name, data_date, score, grade, scored, info, deductions, scope)` → returns Markdown string

---

## Workflow

1. **Parse the XER** using the `schedule-xer-read-modify` skill's parser
2. **Extract data date** from the PROJECT table (`last_recalc_date` or `data_date`)
3. **Read `references/score_schedule.py`** from this skill's directory
4. **Write a runner script** that:
   - Imports the parsed XER data (tasks and predecessors)
   - Calls `compute_quality_score()` with all tasks and all predecessors
   - Calls `generate_quality_report()` to produce the Markdown output
   - Saves the .md report
5. **Execute the runner script** and save the .md file to the project folder
6. **Present findings** to the user with a brief summary

When scoring multiple schedules for comparison, output a summary table showing all projects, their grades, and key deductions side by side.

---

## Calibration Notes

This scoring algorithm was calibrated against 9 real construction schedules with SmartPM ground truth grades. Key calibration findings:

**Calibration results (9 schedules):**
- 5/9 exact grade matches
- 9/9 within ±1 grade level
- Average score difference: 1.2 points

**Calibration data:**

| Project | Our Grade | Our Score | SmartPM Grade | SmartPM Score | Diff |
|---------|-----------|-----------|---------------|---------------|------|
| Nauvoo VC | D+ | 69.5 | D+ | 69.3 | +0.2 |
| Pago Pago | B | 84.0 | B+ | 87.5 | -3.5 |
| Anchorage | A- | 91.8 | A- | 91.9 | -0.1 |
| Provo Rock Canyon | A- | 90.8 | B+ | 88.0 | +2.8 |
| Wellington | B+ | 88.0 | A- | 90.0 | -2.0 |
| Neiafu | A | 93.2 | A | 95.0 | -1.8 |
| Provo Airport | B | 86.1 | B | 86.3 | -0.2 |
| SGRWRF Lab | A- | 90.0 | B+ | 89.5 | +0.5 |
| Pacific Horizon CU | A | 95.0 | A | 95.0 | +0.0 |

**Key discoveries during calibration:**

1. **SC scope filtering is essential.** SmartPM filters scope to the Substantial Completion scenario. Without this, post-SC activities inflate missing logic, constraint counts, and other metrics.

2. **Missing Logic must be checked against ALL relationships** in the full schedule, not just in-scope relationships. Checking only in-scope rels causes scope-boundary artifacts where activities lose their external predecessors/successors, inflating ML from ~3% to 40-50% in small scopes.

3. **Missing Logic ≥ 3% threshold.** Small amounts of ML (< 3%) are common at scope boundaries and SmartPM does not penalize them. Only deduct when ML ≥ 3%.

4. **CS_ALAP is not a constraint.** ALAP is a scheduling directive, not a date lock. SmartPM does not count it. One schedule (PHCU) had 17 ALAP constraints that were incorrectly penalized before this was discovered.

5. **Constraint threshold is 1%, not 0.5%.** Projects with ≤ 1% constrained tasks receive no deduction. This was validated across all 9 projects.

6. **Negative-float schedules need exemptions.** When average float is deeply negative (schedule is behind), CP% and Relationship Ratio metrics become meaningless. All tasks have negative float, so either 0% or 100% appear "critical" depending on threshold.

7. **Average float is bidirectional.** Both too-low (< 10 days = tight/behind) and too-high (> 44 days = loose logic) deserve deductions. The healthy range is 15–44 days.

8. **CP% healthy range is 10–20%**, narrower than the original 5–25%. SmartPM expects a tighter critical path band.

9. **High Float threshold is 40%**, not 50%. SmartPM penalizes when more than 40% of activities have float > 44 days.

10. **Relationship Ratio is steeper with max -5.** SmartPM penalizes sparse logic networks more aggressively: < 1.25 ratio → -5 pts, 1.25-1.5 → -2.5 pts.

11. **SmartPM does not deduct for High Duration, Positive Lag, or Negative Lag.** These remain informational only.

12. **The standard academic grade scale matches SmartPM exactly.** All 9 SmartPM scores map correctly to their grades using 97/93/90/87/83/80/77/73/70/67/65 thresholds.

13. **Proportional scoring for ML and Constraints** (1 pt per 1%) produces much better calibration than threshold-based scoring. Capped at 10 for ML and 20 for Constraints.

**Known limitations:**
- SmartPM uses named scenarios (e.g., "Interior Float") that may differ from our SC-based scope. This can cause scope count differences in some projects.
- SmartPM may calculate float values differently for deeply negative-float schedules, leading to divergent avg float and CP% values.
- Remaining grade mismatches (4/9) are primarily driven by these scope/float calculation differences, not threshold differences.
