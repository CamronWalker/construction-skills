# Analysis Tools Reference

All tools are pure-function libraries. Parse XER first, pass data in, get results out. Do NOT rewrite.

## SC Path Coverage

Requires: `calendar_engine.py` + `cpm_engine.py` + `path_analysis.py` (load in that order)

```python
result = pa_mod.analyze_sc_path_coverage(tasks, preds, wbs_rows)
pa_mod.render_coverage_html(result, 'coverage.html')
```

Returns: connected/disconnected activity counts by WBS, coverage %, recommendations.

## Delay Impact / TIA

```python
result = pa_mod.compute_delay_impacts(tasks, preds, calendars, data_date)
pa_mod.render_delay_html(result, 'delay.html')
```

Auto-detects IMPACT activities, traces driving paths to SC, computes variance.

## Per-Activity Path Insight

```python
result = pa_mod.analyze_activity_paths(tasks, preds, calendars, data_date)
pa_mod.render_paths_html(result, 'paths.html')
```

For every activity: driving path to SC, float, critical status, path length.

## Schedule Comparison (vs baseline or previous update)

Load `xer_compare.py`:

```python
result = xc_mod.compare_schedules(current_tables, baseline_tables=None, previous_tables=None)
xc_mod.render_comparison_html(result, 'comparison.html')
```

Flexible: current vs baseline, current vs previous update, or all three. Reports missed starts/finishes, SC tracking across all provided schedules.

## Baseline Note

BASELN and BASLNTYPE are not in standard P6 project XER exports (only in full DB backup XERs). For baseline comparison in practice, use two separate XER files (current export + baseline export) with `compare_schedules()`.
