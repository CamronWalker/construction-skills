---
name: schedule-best-practices
description: >
  Guide for building and maintaining construction schedules that score well on best practice metrics.
  Use this skill whenever the user asks how to improve a schedule, wants best practice guidance for
  creating or updating a P6 schedule, asks about the DCMA 14-point assessment, GAO schedule standards,
  AACE recommended practices, or wants to know how to achieve a high quality score. Also trigger when
  the user mentions "schedule quality", "schedule health", "best practices", "logic check",
  "float analysis", "constraint check", "open ends", "critical path", or asks "how do I make
  this schedule better?" Use this as a backcheck when generating or updating schedules with the
  schedule-xer-generate or schedule-xer-read-modify skills. Works with XER files or any schedule data.
---

# Construction Schedule Best Practices

This skill provides actionable guidance for building schedules that achieve high best practice scores. It covers industry standards (DCMA, GAO, AACE) and extended metrics used by schedule quality tools. Use it when creating, updating, or backchecking schedules.

## Critical: Scope Filtering

**Before computing ANY metric, filter the schedule to incomplete work only.** This is the single most important step — without it, every metric will be inflated by completed activities and their historical relationships.

The correct analysis scope:
1. **Incomplete activities** — Status is NOT `TK_Complete`. This is your denominator for activity-based metrics.
2. **Incomplete relationships** — Only relationships where BOTH the predecessor AND successor are incomplete. This is your denominator for relationship-based metrics.
3. **Exclude LOE activities** from most metrics (they derive dates from linked activities, not from their own logic).

Schedule quality tools apply this filtering automatically. If you skip it, your numbers won't match any industry tool and will be misleading — completed work inflates relationship counts, float statistics, and logic metrics because completed activities retain their original relationships even though they no longer affect the schedule.

```python
def filter_to_incomplete_scope(tasks, predecessors):
    """Filter to incomplete activities and their inter-relationships."""
    incomplete = [t for t in tasks if t.get('status_code', '') != 'TK_Complete']
    incomplete_ids = {t['task_id'] for t in incomplete}

    # Only relationships where BOTH pred and succ are incomplete
    incomplete_rels = [p for p in predecessors
                       if p.get('task_id', '') in incomplete_ids
                       and p.get('pred_task_id', '') in incomplete_ids]

    # Separate milestones from activities
    milestone_types = {'TT_Mile', 'TT_FinMile'}
    loe_types = {'TT_LOE'}
    activities = [t for t in incomplete
                  if t.get('task_type', '') not in milestone_types
                  and t.get('task_type', '') not in loe_types]
    milestones = [t for t in incomplete if t.get('task_type', '') in milestone_types]

    return incomplete, activities, milestones, incomplete_rels
```

---

## Industry Standards Overview

Three frameworks form the foundation. They overlap but serve different purposes.

**DCMA 14-Point Assessment** — The most widely used quick-assessment tool. Originally for defense, now the de facto standard across commercial construction. Each metric has a pass/fail threshold.

**GAO Schedule Assessment Guide** (GAO-16-89G) — More comprehensive. Organizes quality into four characteristics: comprehensive, well-constructed, credible, and controlled. Gold standard for public projects.

**AACE Recommended Practices** — Deep dives on specific topics: RP 29R-03 (Forensic Schedule Analysis), RP 38R-06 (Schedule Basis), RP 49R-06 (Critical Path), RP 53R-06 (Schedule Update Review).

---

## How to Achieve a High Best Practice Score

These are the highest-impact actions for scoring well. Address them in priority order when building or fixing a schedule.

### Priority 1: Complete Logic Network
Every non-milestone, non-LOE activity needs at least one predecessor AND one successor. This single factor drives multiple metrics — missing logic, high float, relationship ratio, and dangling activities all improve when the network is complete. Target: 0% missing logic.

### Priority 2: Use Finish-to-Start Relationships
FS should be ≥ 90% of all relationships. Use SS only when work genuinely overlaps. Use FF sparingly and only for real finish-to-finish dependencies. Never use SF. When in doubt, default to FS.

### Priority 3: Zero Negative Lag
Replace every negative lag (lead) with a proper SS or FF relationship and positive lag. Even one negative lag is a deduction.

### Priority 4: Avoid Hard Constraints
Use soft constraints (SNET, FNET) instead of hard constraints (Must Start On, Must Finish On). Attach constraints to milestones, not work activities. Target: ≤ 2% hard-constrained activities.

### Priority 5: Healthy Critical Path (5–25%)
If CP% is too low, add logic to connect floating activities to the network. If too high, check for constraint chains or over-compressed logic. A well-linked schedule naturally falls in the 5–25% range.

### Priority 6: Control Float
High float (>44 days) means missing logic ties. Average float >44 days suggests the network is too loose. Fix by linking isolated activities back into the main logic chain.

### Priority 7: Break Down Long Activities
Activities over 44 working days should be decomposed by area, phase, or trade. Target: ≤ 2% of activities exceeding the threshold.

### Priority 8: Minimize Positive Lag
Replace lags >5 days with explicit activities (e.g., replace a 14-day cure lag with a "Concrete Cure" activity). Target: ≤ 5% of relationships with positive lag.

### Priority 9: Relationship Density ≥ 1.5:1
If the ratio of relationships to activities is below 1.5, the logic is too sparse. Most activities should have 2+ ties. Healthy range: 1.5–2.5:1.

---

## The DCMA 14-Point Assessment

### 1. Missing Logic (Incomplete Logic)
**Metric:** % of incomplete activities with missing predecessors or successors
**Threshold:** ≤ 5%
**Scope:** Incomplete non-milestone, non-LOE activities; incomplete-scope relationships only

Count activities with no predecessor (open start) or no successor (open finish). Project start/finish milestones and LOE activities are excluded.

### 2. Leads (Negative Lag)
**Metric:** Count of relationships with negative lag
**Threshold:** 0
**Scope:** Incomplete-scope relationships only

Negative lag means work starts before its driver finishes — replace with proper SS/FF relationships.

### 3. Lags (Positive Lag)
**Metric:** % of relationships with positive lag
**Threshold:** ≤ 5%
**Scope:** Incomplete-scope relationships only

Lag hides duration. Replace with explicit activities where possible.

### 4. Relationship Types
**Metric:** % of relationships that are NOT Finish-to-Start
**Threshold:** ≤ 10%
**Scope:** Incomplete-scope relationships only

FS should be the dominant type. Check `pred_type` for `FS`/`PR_FS`.

### 5. Hard Constraints
**Metric:** Count/% of activities with hard constraints
**Threshold:** ≤ 5%

**P6 constraint field names:** The XER uses `cstr_type` (not `constraint_type`). Actual P6 codes:

Hard constraints (override the network — lock a date regardless of logic) — check BOTH `cstr_type` and `cstr_type2`:
- `CS_MSO` — Mandatory Start On
- `CS_MFO` — Mandatory Finish On
- `CS_MEO` — Mandatory End On
- `CS_MANDSTART` — Mandatory Start
- `CS_MANDEND` — Mandatory End
- `CS_MANDFIN` — Mandatory Finish

Soft constraints (set boundaries but allow logic to push dates):
- `CS_ALAP` — As Late As Possible
- `CS_SNET` — Start No Earlier Than (most common soft)
- `CS_SNLT` — Start No Later Than
- `CS_FNET` — Finish No Earlier Than
- `CS_FNLT` — Finish No Later Than
- `CS_MSOA` — Start On or After (equivalent to SNET)
- `CS_MSOB` — Start On or Before (equivalent to SNLT)
- `CS_MEOA` — Finish On or After (equivalent to FNET)
- `CS_MEOB` — Finish On or Before (equivalent to FNLT)

Default (no constraint): `CS_ASAP` or empty

Track hard and soft separately. Both should be reported, but only hard constraints are DCMA failures.

### 6. High Float
**Metric:** % of incomplete activities with total float > 44 working days (352 hours at 8hr/day)
**Threshold:** ≤ 5%
**Scope:** Incomplete activities only

High float usually means missing logic — the activity isn't properly constrained by the network.

### 7. Negative Float
**Metric:** Count of activities with negative total float
**Threshold:** 0

Negative float means the schedule can't make its required date with current logic and durations.

### 8. High Duration
**Metric:** % of incomplete non-milestone activities with duration > 44 working days
**Threshold:** ≤ 5%
**Scope:** Incomplete non-milestone activities (exclude milestones from count AND denominator)

### 9–14. (Remaining DCMA Metrics)
See `references/dcma-14-point-detail.md` for detailed coverage of Invalid Dates (#9), Resources (#10), Missed Tasks (#11), Critical Path Test (#12), CPLI (#13), and BEI (#14).

---

## Extended Metrics (Beyond DCMA)

These metrics go beyond the DCMA 14-point to cover network analysis, status quality, and update integrity. They are tracked by schedule quality tools and should be included in any thorough schedule quality report.

### Network Analysis

**Critical Path %**
Percentage of incomplete activities on the critical path (total float = 0). A healthy range is 5-15%. Too low suggests inadequate detail; too high suggests the schedule is over-compressed or over-constrained.

**Low Float Activities**
Incomplete activities with total float between 0 and 10 working days (0-80 hours). High percentages indicate schedule inflexibility — corrections become difficult and critical delays more likely.

**Average Activity Total Float**
Mean total float across incomplete activities, expressed in working days. Provides a single indicator of overall schedule flexibility.

**Relationship Density Ratio**
Total incomplete-scope relationships ÷ total incomplete activities. A healthy range is 1.5 to 2.5. Below 1.5 suggests the logic network is too sparse (many activities have only one tie). Above 3.0 may indicate over-linking.

**Convergence Bottlenecks**
Activities with 5 or more predecessors. A convergence bottleneck creates a critical convergence point — if any of those predecessors slip, this activity is delayed. High counts increase risk.

**Divergence Bottlenecks**
Activities with 5 or more successors. A divergence bottleneck means one activity's delay ripples out to many downstream activities. Both bottleneck types should be reviewed for logic appropriateness.

**Duplicate Relationships**
Pairs of activities connected by more than one relationship (e.g., both a FS and an SS between the same two activities). Duplicates create unpredictable scheduling behavior and should be resolved to a single, correct relationship.

**Dangling Activities**
Activities that are unbounded — missing a FS/SS predecessor AND/OR a FS/FF successor. More specific than DCMA's "missing logic" because it considers relationship types. An activity with only an FF predecessor has no start driver and is effectively dangling.

### Status Quality

**Out of Sequence**
Activities that have started or completed before their predecessors were ready (based on the logic network). Indicates either erroneous logic or acceleration efforts. Either way, the schedule should be corrected to match reality.

**Started with 0%**
Activities marked as started (status = `TK_Active`) but with 0% physical complete. May indicate the activity was started to release a successor's start-to-start tie rather than because actual work began. Each should be verified.

**Future Actual Dates**
Actual start or finish dates that fall after the data date. These are approximations rather than recorded facts, which undermines the reliability of progress data.

**Backdated Activities**
Activities with actual dates updated to reflect progress from a period before the current data date. May indicate late reporting or retroactive schedule manipulation.

**Activities Riding Data Date**
Incomplete activities whose early start equals the data date but have not actually started. These activities can start based on their logic but haven't — potentially indicating missing or erroneous logic, or work that was expected to start but hasn't.

**Unstatused Activities**
Incomplete activities where the early start/finish is before the data date but no actual start has been recorded. The activity should have started per the schedule but shows no progress.

**Missing Actual Finish Date**
Activities marked 100% complete but without an actual finish date recorded. Indicates poor update practices.

**Decreased Percent Complete**
Activities where percent complete has gone down compared to the previous update. Unusual and potentially indicates data entry errors or scope changes. *Requires comparison to a previous update.*

**Changed Actual Dates**
Activities where previously recorded actual start or finish dates were modified. Can cause erroneous historical critical path analysis. *Requires comparison to a previous update.*

### Duration Analysis

**One Day Activities**
Activities with a duration of exactly one working day. Too many suggests over-detailing or activities that should be milestones. Review for validity.

**Remaining Duration Discrepancy**
Activities where the remaining duration conflicts with the percent complete and original duration. For example, an activity at 50% complete with 80% of its duration remaining — the numbers don't add up.

**Negative Native Float**
Activities with negative total float, specifically in incomplete work (excluding completed activities that may retain stale float values from pre-completion calculations).

---

## Automated Schedule Quality Metrics

When analyzing a schedule programmatically, use this comprehensive function. It covers both DCMA 14-point metrics and extended best practice metrics.

```python
def safe_float(val, default=0):
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default

def compute_schedule_metrics(tasks, predecessors, data_date=None):
    """Compute schedule quality metrics from parsed XER data.

    IMPORTANT: Pass ALL tasks and ALL predecessors. This function
    handles scope filtering internally.
    """
    metrics = {}

    # --- SCOPE FILTERING (critical for accurate results) ---
    milestone_types = {'TT_Mile', 'TT_FinMile'}
    loe_types = {'TT_LOE'}
    completed_ids = {t['task_id'] for t in tasks if t.get('status_code') == 'TK_Complete'}
    incomplete = [t for t in tasks if t.get('status_code') != 'TK_Complete']
    incomplete_ids = {t['task_id'] for t in incomplete}

    # Activities = incomplete, non-milestone, non-LOE
    inc_activities = [t for t in incomplete
                      if t.get('task_type', '') not in milestone_types
                      and t.get('task_type', '') not in loe_types]
    inc_milestones = [t for t in incomplete if t.get('task_type', '') in milestone_types]

    # Relationships between incomplete tasks only
    inc_rels = [p for p in predecessors
                if p.get('task_id', '') in incomplete_ids
                and p.get('pred_task_id', '') in incomplete_ids]

    n_inc = len(incomplete)
    n_act = len(inc_activities)
    n_rels = len(inc_rels)

    metrics['total_tasks'] = len(tasks)
    metrics['incomplete_activities'] = n_act
    metrics['incomplete_milestones'] = len(inc_milestones)
    metrics['incomplete_total'] = n_inc
    metrics['total_relationships'] = n_rels

    # --- DCMA 1: Missing Logic ---
    has_pred = {p.get('task_id', '') for p in inc_rels}
    has_succ = {p.get('pred_task_id', '') for p in inc_rels}
    # Exclude milestones and LOE from missing logic check
    checkable = [t for t in incomplete
                 if t.get('task_type', '') not in milestone_types
                 and t.get('task_type', '') not in loe_types]
    open_start = [t for t in checkable if t['task_id'] not in has_pred]
    open_finish = [t for t in checkable if t['task_id'] not in has_succ]
    missing_ids = set(t['task_id'] for t in open_start) | set(t['task_id'] for t in open_finish)
    metrics['missing_logic'] = len(missing_ids)
    metrics['missing_logic_pct'] = round(len(missing_ids) / max(n_inc, 1) * 100, 1)

    # --- DCMA 2: Negative Lag ---
    neg_lags = [p for p in inc_rels if safe_float(p.get('lag_hr_cnt', 0)) < 0]
    metrics['negative_lag'] = len(neg_lags)
    metrics['negative_lag_pct'] = round(len(neg_lags) / max(n_rels, 1) * 100, 1)

    # --- DCMA 3: Positive Lag ---
    pos_lags = [p for p in inc_rels if safe_float(p.get('lag_hr_cnt', 0)) > 0]
    metrics['positive_lag'] = len(pos_lags)
    metrics['positive_lag_pct'] = round(len(pos_lags) / max(n_rels, 1) * 100, 1)

    # --- DCMA 4: Relationship Types ---
    fs_types = {'FS', 'PR_FS'}
    fs_count = sum(1 for p in inc_rels if p.get('pred_type', '') in fs_types)
    ss_count = sum(1 for p in inc_rels if p.get('pred_type', '') in ('SS', 'PR_SS'))
    ff_count = sum(1 for p in inc_rels if p.get('pred_type', '') in ('FF', 'PR_FF'))
    sf_count = sum(1 for p in inc_rels if p.get('pred_type', '') in ('SF', 'PR_SF'))
    non_fs_pct = round((n_rels - fs_count) / max(n_rels, 1) * 100, 1)
    metrics['rel_FS'] = fs_count
    metrics['rel_SS'] = ss_count
    metrics['rel_FF'] = ff_count
    metrics['rel_SF'] = sf_count
    metrics['non_fs_pct'] = non_fs_pct

    # --- DCMA 5: Constraints ---
    # P6 uses cstr_type (not constraint_type)
    hard_codes = {'CS_MSO', 'CS_MFO', 'CS_MEO', 'CS_MANDSTART', 'CS_MANDEND', 'CS_MANDFIN'}
    soft_codes = {'CS_SNET', 'CS_SNLT', 'CS_FNET', 'CS_FNLT', 'CS_ALAP',
                  'CS_MSOA', 'CS_MSOB', 'CS_MEOA', 'CS_MEOB'}
    hard = []
    soft = []
    for t in incomplete:
        c1 = t.get('cstr_type', t.get('constraint_type', ''))
        c2 = t.get('cstr_type2', t.get('constraint_type2', ''))
        if c1 in hard_codes or c2 in hard_codes:
            hard.append(t)
        if c1 in soft_codes or c2 in soft_codes:
            soft.append(t)
    metrics['hard_constraints'] = len(hard)
    metrics['hard_constraints_pct'] = round(len(hard) / max(n_inc, 1) * 100, 1)
    metrics['soft_constraints'] = len(soft)
    metrics['soft_constraints_pct'] = round(len(soft) / max(n_inc, 1) * 100, 1)

    # --- DCMA 6: High Float ---
    high_float_hrs = 352  # 44 days × 8 hrs
    high_float = [t for t in inc_activities if safe_float(t.get('total_float_hr_cnt', 0)) > high_float_hrs]
    metrics['high_float'] = len(high_float)
    metrics['high_float_pct'] = round(len(high_float) / max(n_act, 1) * 100, 1)

    # --- DCMA 7: Negative Float ---
    neg_float = [t for t in incomplete if safe_float(t.get('total_float_hr_cnt', 0)) < 0]
    metrics['negative_float'] = len(neg_float)

    # --- DCMA 8: High Duration ---
    high_dur = [t for t in inc_activities if safe_float(t.get('target_drtn_hr_cnt', 0)) > high_float_hrs]
    metrics['high_duration'] = len(high_dur)
    metrics['high_duration_pct'] = round(len(high_dur) / max(n_act, 1) * 100, 1)

    # --- EXTENDED: Critical Path % ---
    critical = [t for t in incomplete if safe_float(t.get('total_float_hr_cnt', 0)) == 0]
    metrics['critical_path_count'] = len(critical)
    metrics['critical_path_pct'] = round(len(critical) / max(n_inc, 1) * 100, 1)

    # --- EXTENDED: Low Float ---
    low_float = [t for t in inc_activities
                 if 0 < safe_float(t.get('total_float_hr_cnt', 0)) <= 80]
    metrics['low_float'] = len(low_float)
    metrics['low_float_pct'] = round(len(low_float) / max(n_act, 1) * 100, 1)

    # --- EXTENDED: Average Float ---
    float_vals = [safe_float(t.get('total_float_hr_cnt', 0)) for t in inc_activities]
    metrics['avg_float_days'] = round(sum(float_vals) / max(len(float_vals), 1) / 8, 1)

    # --- EXTENDED: Relationship Density ---
    metrics['relationship_ratio'] = round(n_rels / max(n_inc, 1), 1)

    # --- EXTENDED: Convergence/Divergence Bottlenecks ---
    from collections import defaultdict
    pred_count = defaultdict(int)
    succ_count = defaultdict(int)
    for p in inc_rels:
        succ_id = p.get('task_id', '')
        pred_id = p.get('pred_task_id', '')
        if succ_id:
            pred_count[succ_id] += 1
        if pred_id:
            succ_count[pred_id] += 1
    metrics['convergence_bottlenecks'] = sum(1 for v in pred_count.values() if v >= 5)
    metrics['divergence_bottlenecks'] = sum(1 for v in succ_count.values() if v >= 5)

    # --- EXTENDED: Duplicate Relationships ---
    from collections import Counter
    rel_pairs = Counter()
    for p in inc_rels:
        pair = (p.get('pred_task_id', ''), p.get('task_id', ''))
        rel_pairs[pair] += 1
    metrics['duplicate_relationships'] = sum(1 for v in rel_pairs.values() if v > 1)

    # --- EXTENDED: Dangling Activities ---
    fs_ss_pred = set()
    fs_ff_succ = set()
    for p in inc_rels:
        ptype = p.get('pred_type', '')
        succ_id = p.get('task_id', '')
        pred_id = p.get('pred_task_id', '')
        if ptype in ('FS', 'PR_FS', 'SS', 'PR_SS'):
            fs_ss_pred.add(succ_id)
        if ptype in ('FS', 'PR_FS', 'FF', 'PR_FF'):
            fs_ff_succ.add(pred_id)
    dangling = [t for t in inc_activities
                if t['task_id'] not in fs_ss_pred or t['task_id'] not in fs_ff_succ]
    metrics['dangling_activities'] = len(dangling)

    # --- EXTENDED: One Day Activities ---
    one_day = [t for t in inc_activities if safe_float(t.get('target_drtn_hr_cnt', 0)) == 8]
    metrics['one_day_activities'] = len(one_day)
    metrics['one_day_pct'] = round(len(one_day) / max(n_act, 1) * 100, 1)

    # --- EXTENDED: Out of Sequence ---
    oos = 0
    active_or_complete = {t['task_id'] for t in tasks
                          if t.get('status_code') in ('TK_Active', 'TK_Complete')}
    for p in predecessors:
        succ_id = p.get('task_id', '')
        pred_id = p.get('pred_task_id', '')
        # Successor is active/complete but predecessor hasn't started
        if succ_id in active_or_complete and pred_id not in active_or_complete:
            if pred_id in incomplete_ids:
                oos += 1
    metrics['out_of_sequence'] = oos

    # --- EXTENDED: Started with 0% ---
    started_zero = [t for t in incomplete
                    if t.get('status_code') == 'TK_Active'
                    and safe_float(t.get('phys_complete_pct', 0)) == 0]
    metrics['started_with_zero_pct'] = len(started_zero)

    # --- EXTENDED: Negative Native Float ---
    metrics['negative_native_float'] = len([t for t in incomplete
                                             if safe_float(t.get('total_float_hr_cnt', 0)) < 0])

    # --- EXTENDED: Future Actual Dates ---
    if data_date:
        from datetime import datetime
        def parse_dt(v):
            if not v: return None
            for fmt in ['%Y-%m-%d %H:%M', '%Y-%m-%d']:
                try: return datetime.strptime(v.strip(), fmt)
                except: pass
            return None

        future_actual = 0
        for t in tasks:
            as_dt = parse_dt(t.get('act_start_date', ''))
            ae_dt = parse_dt(t.get('act_end_date', ''))
            if (as_dt and as_dt > data_date) or (ae_dt and ae_dt > data_date):
                future_actual += 1
        metrics['future_actual_dates'] = future_actual

    # --- EXTENDED: Remaining Duration Discrepancy ---
    rem_disc = 0
    for t in inc_activities:
        pct = safe_float(t.get('phys_complete_pct', 0))
        target = safe_float(t.get('target_drtn_hr_cnt', 0))
        remain = safe_float(t.get('remain_drtn_hr_cnt', 0))
        if target > 0 and pct > 0:
            expected = target * (1 - pct / 100)
            if remain > 0 and abs(remain - expected) / target > 0.15:
                rem_disc += 1
    metrics['remaining_duration_discrepancy'] = rem_disc

    # --- SUMMARY ---
    dcma_checks = {
        'logic': metrics['missing_logic_pct'] <= 5.0,
        'leads': metrics['negative_lag'] == 0,
        'lags': metrics['positive_lag_pct'] <= 5.0,
        'rel_types': non_fs_pct <= 10.0,
        'constraints': metrics['hard_constraints_pct'] <= 5.0,
        'high_float': metrics['high_float_pct'] <= 5.0,
        'neg_float': metrics['negative_float'] == 0,
        'high_duration': metrics['high_duration_pct'] <= 5.0,
    }
    metrics['dcma_passed'] = sum(dcma_checks.values())
    metrics['dcma_total'] = len(dcma_checks)
    metrics['dcma_details'] = dcma_checks

    return metrics
```

---

## Reporting Template

When presenting schedule quality findings, use this structure:

```
## Schedule Quality Assessment — [Project Name]

**Date:** [Assessment date]
**Data Date:** [Schedule data date]
**Incomplete Activities:** [count] | **Incomplete Milestones:** [count]
**Incomplete Relationships:** [count] | **Relationship Ratio:** [X.X:1]

### DCMA 14-Point Summary

| # | Metric | Value | Threshold | Status |
|---|--------|-------|-----------|--------|
| 1 | Missing Logic | X/Y (Z%) | ≤ 5% | PASS/FAIL |
| 2 | Leads (Negative Lag) | X | 0 | PASS/FAIL |
| 3 | Positive Lag | X/Y (Z%) | ≤ 5% | PASS/FAIL |
| 4 | Relationship Types | Z% non-FS | ≤ 10% | PASS/FAIL |
| 5 | Hard Constraints | X (Z%) | ≤ 5% | PASS/FAIL |
| 6 | High Float | X/Y (Z%) | ≤ 5% | PASS/FAIL |
| 7 | Negative Float | X | 0 | PASS/FAIL |
| 8 | High Duration | X/Y (Z%) | ≤ 5% | PASS/FAIL |

### Extended Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| Critical Path % | X/Y (Z%) | Healthy: 5-15% |
| Low Float Activities | X (Z%) | — |
| Avg Float (days) | X | — |
| Convergence Bottlenecks | X | Activities with 5+ predecessors |
| Divergence Bottlenecks | X | Activities with 5+ successors |
| Duplicate Relationships | X | — |
| Dangling Activities | X | Unbounded FS/SS + FS/FF |
| Out of Sequence | X | — |
| One Day Activities | X (Z%) | — |
| Started with 0% | X | — |
| Soft Constraints | X | — |
| Future Actual Dates | X | — |
| Neg Native Float | X | — |

### Findings & Recommendations

[For each issue, describe the specific activities flagged and recommend corrective actions]
```

---

## GAO Schedule Assessment — The Four Characteristics

### 1. Comprehensive
The schedule should capture all required work: procurement, submittals, permits, inspections, owner decisions, commissioning, punchlist, and weather/seasonal considerations.

### 2. Well-Constructed
Sound scheduling practices: complete logic, appropriate relationship types, minimal constraints, no negative lag, reasonable durations, consistent calendars, proper activity types, and a WBS that supports reporting.

### 3. Credible
Realistic, defensible dates: rational critical path, reasonable float values, durations aligned with historical data, and risk acknowledged.

### 4. Controlled
Consistent maintenance: regular updates, current data date, actual dates recorded, baseline maintained, changes documented, BEI and CPLI tracked.

---

## Organizational Standards Layer

The industry standards above form the foundation. Organizations layer on additional requirements.

### Common Additions
- **WBS Standards** — Required levels, naming conventions, mandatory nodes
- **Activity Standards** — ID format, naming conventions, duration ranges, required codes
- **Logic Standards** — Density ratio (1.5-2.5), maximum chain length, milestone gates
- **Calendar Standards** — Standard definitions, holidays, seasonal adjustments
- **Update Standards** — Frequency, required fields, baseline rules, narrative requirements

To customize, create `references/org-standards.md` in this skill's directory.

---

## Reference Files

- `references/dcma-14-point-detail.md` — Deep dive on each DCMA metric with edge cases and remediation
- `references/org-standards.md` — Organization-specific standards (create to customize)
- For XER table schemas and parsing details, see the **schedule-xer-read-modify** skill

All dates in XER files use `YYYY-MM-DD HH:MM` format.
