# Schedule Quality Report Template

Use this template when presenting schedule quality findings. The `generate_quality_report()` function in `score_schedule.py` generates this format automatically, but this template is provided for manual report creation or customization.

```markdown
## Schedule Quality Assessment — [Project Name]

**Date:** [Assessment date]
**Data Date:** [Schedule data date]
**Incomplete Activities:** [count] | **Incomplete Milestones:** [count]
**Incomplete Relationships:** [count] | **Relationship Ratio:** [X.X:1]

### Overall Grade: [Letter Grade] ([Score]/100)

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

### Scored Metrics Detail

| Metric | Value | Deduction | Notes |
|--------|-------|-----------|-------|
| Relationship Types | FS X%, SS Y%, FF Z%, SF W% | -X pts | [detail] |
| Avg Activity Float | X days | -X pts | [detail] |
| Critical Path % | X% | -X pts | [detail] |
| High Float Activities | X (Y%) | -X pts | [detail] |
| Missing Logic | X (Y%) | -X pts | [detail] |
| Relationship Ratio | X.X:1 | -X pts | [detail] |
| Constraints | X (Y%) | -X pts | [detail] |

### Recommended Improvements

[Ordered by score impact — up to 20 example activities per category with task_code identifiers]

### Extended Metrics

| Metric | Value | Notes |
|--------|-------|-------|
| Critical Path % | X/Y (Z%) | Healthy: 10-20% |
| Low Float Activities | X (Z%) | Float 0-10 days |
| Avg Float (days) | X | Healthy: 15-44 days |
| Convergence Bottlenecks | X | Activities with 5+ predecessors |
| Divergence Bottlenecks | X | Activities with 5+ successors |
| Duplicate Relationships | X | — |
| Dangling Activities | X | Missing FS/SS pred or FS/FF succ |
| Out of Sequence | X | — |
| One Day Activities | X (Z%) | — |
| Started with 0% | X | — |
| Hard Constraints | X | Mandatory date locks |
| Soft Constraints | X | Directional constraints |
| ALAP Constraints | X | Not scored |
| High Duration | X (Z%) | > 44 working days |
| Positive Lag | X (Z%) | — |
| Negative Lag | X | — |

### Findings & Recommendations

[For each issue, describe the specific activities flagged and recommend corrective actions]

### Westland Standards Compliance

- [ ] Milestones every 30 days
- [ ] Responsibility codes assigned to all tasks
- [ ] WBS follows Westland standard structure
- [ ] SmartPM Quality Checker run
```
