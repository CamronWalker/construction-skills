---
name: schedule-standards
description: >
  Westland Construction scheduling standards, best practices, and quality scoring for P6 schedules.
  Use this skill whenever the user asks about schedule quality, best practices, Westland standards,
  WBS structure, DCMA 14-point, schedule health, scoring a schedule, grading a schedule, generating
  a quality report, or asks "how do I make this schedule better?" Also use as a backcheck when
  generating or modifying schedules with the schedule-xer skill. Trigger on: "schedule quality",
  "score a schedule", "grade a schedule", "quality check", "quality report", "DCMA", "best practices",
  "Westland standards", "schedule scorecard", "schedule health", "is this schedule any good?"
---

# Westland Scheduling Standards & Quality Scoring

This skill provides Westland-specific scheduling standards and industry best practices, plus the ability to score a schedule against those standards and generate a quality report.

## Westland Standard WBS Structure

All Westland schedules follow this WBS unless the project scope requires adaptation:

```
PROJECT
  SUMMARY & MILESTONES
    CONTRACT MILESTONES & SUMMARY BARS
    KEY PERFORMANCE MILESTONES
  PRE-CONSTRUCTION
    DESIGN
    ESTIMATES - CONSTRUCTABILITY REPORTS - SCHEDULE UPDATES
    BIM MODELING
    TRADE PRE-QUALIFICATION
    BUY OUT - PROPOSAL & AWARD
    OWNER PERMIT / CONSENT PROCESS
  PROCUREMENT
    SUBMITTALS - APPROVALS - FABRICATION - DELIVERY
  CONSTRUCTION
    SITEWORK
      INITIAL SITEWORK (CLEAR & GRUB - CUT & FILL - ROUGH GRADE - UTILITIES)
      BALANCE OF SITEWORK (HARDSCAPE - LANDSCAPE - EQUIPMENT ENCLOSURES)
    STRUCTURE & SUBROUGH [by AREA - LEVEL]
    BUILDING ENCLOSURE - WINDOWS - ENTRIES - FINISH SYSTEMS [by ELEVATION - AREA - LEVEL]
    INTERIOR ROUGH-IN & FINISHES [by AREA - LEVEL]
  COMMISSIONING & CLOSE-OUT [by Building, Area, or Floor]
```

**Flexibility:** Adapt as needed — Demo phase above Construction, multiple buildings, phased turnover, etc. The structure is a starting point, not a straitjacket.

## Westland Schedule Requirements

- **Milestones:** One every 30 days (Critical Path or Significant Event) + all contract-required milestones
- **Responsibility Codes:** Every task assigned a responsible party using Westland standard codes
- **Update Cadence:** Weekly during construction (bi-monthly minimum). Preconstruction updates at each design milestone.
- **Deliverables:** Updated Baseline, Critical Path, Longest Path, 4-Week Rolling Schedule, applicable filters
- **SmartPM:** Quality Checker run before baselining. Analytics uploaded with each update.
- **Activity Naming:** Verb + Noun. Allowed acronyms: HVAC, MEP, CMU, GC, SWPPP, OAC, RFI, IFC, TAB. Use & not "and". Spell out: Notice to Proceed, Substantial Completion, Final Completion.

---

## Priority Actions for Schedule Quality

| Priority | Action | Target |
|----------|--------|--------|
| 1 | Complete logic network — every activity needs predecessor + successor | 0% missing logic |
| 2 | Use Finish-to-Start relationships | FS >= 90% |
| 3 | Zero negative lag (leads) | 0 leads |
| 4 | Avoid hard constraints — use soft (SNET, FNET) on milestones only | <= 2% hard |
| 5 | Healthy critical path | 10-20% of activities |
| 6 | Control float — high float means missing logic | <= 40% with float > 44 days |
| 7 | Break down long activities by area/phase/trade | <= 5% over 44 working days |
| 8 | Minimize positive lag — replace with explicit activities | <= 5% of relationships |
| 9 | Relationship density | >= 1.5:1 ratio |

---

## DCMA 14-Point Quick Reference

| # | Metric | Threshold | Scope |
|---|--------|-----------|-------|
| 1 | Missing Logic | <= 5% | Incomplete non-milestone, non-LOE |
| 2 | Leads (Negative Lag) | 0 | Incomplete relationships |
| 3 | Positive Lag | <= 5% | Incomplete relationships |
| 4 | Relationship Types (non-FS) | <= 10% | Incomplete relationships |
| 5 | Hard Constraints | <= 5% | Incomplete activities |
| 6 | High Float (> 44 days) | <= 5% | Incomplete activities |
| 7 | Negative Float | 0 | All incomplete |
| 8 | High Duration (> 44 days) | <= 5% | Incomplete non-milestone |

For detailed metric calculations, edge cases, and remediation strategies, read `references/dcma-14-point-detail.md`.

---

## Scope Filtering (Critical First Step)

Before computing ANY metric, filter to incomplete work only:
1. Exclude `TK_Complete` tasks and `TT_WBS`/`TT_LOE` types
2. Apply Substantial Completion scenario filtering — walk backward from SC milestone through predecessor chain
3. Rebuild relationship set to only include relationships between in-scope tasks

```python
incomplete = [t for t in tasks if t.get('status_code') != 'TK_Complete'
              and t.get('task_type', '') not in ('TT_WBS', 'TT_LOE')]
incomplete_ids = {t['task_id'] for t in incomplete}
inc_rels = [p for p in preds
            if p['task_id'] in incomplete_ids and p['pred_task_id'] in incomplete_ids]
```

---

## Scoring Algorithm

**Base score: 100 points.** Points deducted for each metric outside acceptable thresholds.

### Grade Scale

| Grade | Range | | Grade | Range |
|-------|-------|-|-------|-------|
| A+ | 97-100 | | C+ | 77-79 |
| A | 93-96 | | C | 73-76 |
| A- | 90-92 | | C- | 70-72 |
| B+ | 87-89 | | D+ | 67-69 |
| B | 83-86 | | D | 65-66 |
| B- | 80-82 | | D- | < 65 |

### Scored Metrics (7 metrics, affect grade)

| Metric | Max Deduction | Key Thresholds |
|--------|--------------|----------------|
| Relationship Type Distribution | -8 pts | FS<80% -2, SS/FF>10% -2 each, SF>=1% -2 |
| Average Activity Float | -2 pts | <10 days -2, 10-15 -1, 15-44 pass, >44 -2 |
| Critical Path % | -2.5 pts | 10-20% pass, outside -1.5 to -2.5. SKIP if avg float negative. |
| High Float Activities | -2.5 pts | >40% of activities with float >44 days |
| Missing Logic | -10 pts | Proportional: 1pt per 1% over 3%, capped at 10. Check ALL relationships. |
| Relationship Ratio | -5 pts | >=1.5 pass, 1.25-1.5 -2.5, <1.25 -5. SKIP if avg float negative. |
| Constraints | -20 pts | Proportional: 1pt per 1% over 1%, capped at 20. Exclude CS_ALAP. |

### Informational Metrics (reported, not scored)
Convergence/Divergence Bottlenecks, Duplicate Relationships, Dangling Activities, Low/Negative Float, Out of Sequence, Started with 0%, Future Actual Dates, One Day Activities, High Duration, Positive/Negative Lag, Hard/Soft/ALAP Constraints.

---

## Scoring Workflow

1. Parse the XER using the `schedule-xer` skill
2. Extract data date from PROJECT table (`last_recalc_date` or `data_date`)
3. Read `references/score_schedule.py` from this skill's directory
4. Write a runner script that calls `compute_quality_score(tasks, preds, data_date)` then `render_quality_html(...)` to produce an HTML report (or `generate_quality_report(...)` for Markdown)
5. Save the report to the project folder
6. Present findings with grade, key deductions, and recommended fixes

When used as a backcheck during schedule generation, use the `details` dict from `compute_quality_score()` directly — it contains every flagged activity with `task_code` for targeted fixes.

---

## Calibration

Calibrated against 9 real construction schedules vs SmartPM grades:
- 5/9 exact grade matches, 9/9 within +/-1 grade level
- Average score difference: 1.2 points

---

## Reference Files

| File | When to Load |
|------|-------------|
| `references/westland-standards.md` | Full Westland SOP — development lifecycle, deliverables, impact docs, formatting, SmartPM integration |
| `references/dcma-14-point-detail.md` | Detailed DCMA metrics with edge cases, constraint codes, and remediation playbook |
| `references/gao-aace-reference.md` | GAO four characteristics and AACE recommended practices — load when public project or spec requires |
| `references/score_schedule.py` | Python scoring implementation — load to run quality score. Functions: `compute_quality_score()`, `generate_quality_report()`, `render_quality_html()`. Use `render_quality_html()` for user-facing HTML reports. |
| `references/reporting-template.md` | Quality report markdown template — load when generating report manually |
