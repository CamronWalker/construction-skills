# Update Review Reference

CLI: `python references/update_review.py <command> <xer_path> [args]`

## Expected Updates

"What do I need to collect from the field by date X?"

```
python references/update_review.py expected_updates <xer_path> <YYYY-MM-DD>
python references/update_review.py expected_updates <xer_path> <YYYY-MM-DD> --resource ELEC
```

Returns:
- `to_start[]` — not-started with `early_start <= future_date`: `{task_id, task_code, task_name, resources[], early_start, early_finish, duration_days}`
- `to_finish[]` — in-progress with `early_finish <= future_date`: `{..., pct_complete, early_finish, remaining_days}`
- `in_progress[]` — all active tasks regardless of finish: same fields as to_finish
- `summary` — `{to_start_count, to_finish_count, in_progress_count, total_needing_update}`

## Trade Activities

"What is the electrician doing this month?"

```
python references/update_review.py trade_activities <xer_path> <YYYY-MM-DD> <RESOURCE_CODE>
```

`RESOURCE_CODE` = substring match on `rsrc_short_name` (e.g. `ELEC`, `MECH`, `GC`, `PLMB`)

Returns: `{resource_filter, data_date, future_date, activities[], count, in_progress, starting_soon}`

## Riding Data Date

"Which activities are ready to go but held back only by the data date?"

```
python references/update_review.py riding_data_date <xer_path>
```

Returns: `{data_date, count, total_incomplete, pct, tasks[{task_id, task_code, task_name, early_start}]}`
