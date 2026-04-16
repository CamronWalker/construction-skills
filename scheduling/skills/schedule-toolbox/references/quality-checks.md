# Quality Checks Reference

CLI: `python references/quality_checks.py <check_name> <xer_path>`

Run all: `python references/quality_checks.py all <xer_path>`

Full report + HTML: `python references/score_schedule.py <xer_path> [--html output.html]`

Every result returns: `{check, label, scored, deduction_pts, count, total, pct, threshold, status, tasks[{task_id, task_code, task_name, ...}]}`

`status` values: `PASS` / `FAIL` / `WARN` / `INFO`

## Scored Checks (affect grade)

| Check Name | Threshold | Key Extra Fields |
|------------|-----------|-----------------|
| `finish_to_start` | >= 90% | `tasks` = non-FS rels |
| `start_to_start` | <= 5% | `tasks` = SS rel pairs |
| `finish_to_finish` | <= 5% | `tasks` = FF rel pairs |
| `start_to_finish` | 0% | `tasks` = SF rel pairs |
| `avg_total_float` | 15-44 days | `avg_days` |
| `critical_path_pct` | 10-20% | `tasks` = critical activities |
| `missing_logic` | < 3% | `no_pred_tasks[]`, `no_succ_tasks[]` |
| `total_relationships` | >= 1.5:1 | `ratio`, `rel_count`, `task_count` |
| `constraints` | <= 1% hard | `tasks` with `cstr_type` |

**Constraint rule:** Only `CS_MSO` and `CS_MFO` (mandatory) are scored. Soft constraints (`CS_SNET`, `CS_SNLT`, `CS_FNET`, `CS_FNLT`, `CS_MSOA`, `CS_MSOB`, `CS_MEOA`, `CS_MEOB`) are informational. `CS_ALAP` excluded.

## Informational Checks

| Check Name | Key Extra Fields |
|------------|-----------------|
| `high_float` | `tasks` with `float_days` |
| `low_float` | `tasks` with `float_days` |
| `negative_float` | `tasks` with `float_days` |
| `high_duration` | `tasks` with `duration_days` |
| `one_day` | `tasks` |
| `positive_lag` | rel pairs with `lag_days` |
| `negative_lag` | rel pairs with `lag_days` |
| `convergence` | `tasks` with `pred_count` (>= 5) |
| `divergence` | `tasks` with `succ_count` (>= 5) |
| `dangling` | `tasks` (open start or finish) |
| `duplicate_rels` | duplicate rel pairs |
| `future_actual` | `tasks` with future actual dates |
| `missing_actual_finish` | complete tasks with no actual finish |
| `hard_constraints` | `tasks` with `cstr_type` |
| `soft_constraints` | `tasks` with `cstr_type` |
| `unstatused` | should-have-started tasks |
| `out_of_sequence` | OOS activities |
| `started_with_zero` | active at 0% |
| `remaining_dur_discrepancy` | `original_days`, `remaining_days` |
| `riding_data_date` | preds complete, held by data date |
| `later_than_sc` | `tasks` finishing after SC |
| `sc_coverage` | `sc_milestone{}`, `off_path_tasks[]`, pct on SC path |

## End-of-Project Mode

When < ~50 incomplete activities remain, thresholds loosen automatically:
- FS target: >= 80%, SS/FF limit: <= 15%, CP%: 5-60%, ratio: >= 1.25:1

`_meta.end_of_project: true` in `all` output indicates active mode.

## Grade Scale

A+ (97+), A (93+), A- (90+), B+ (87+), B (83+), B- (80+), C+ (77+), C (73+), C- (70+), D+ (67+), D (65+), D- (below)

Calibrated against 10 Westland XER+SmartPM report pairs. All A/A- range schedules score correctly.
