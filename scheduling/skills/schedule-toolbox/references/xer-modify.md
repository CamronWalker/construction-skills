# XER Write-Back Pattern

==============================================================================
NEVER OVERWRITE THE ORIGINAL XER FILE. WRITE TO A NEW OUTPUT PATH ONLY.
CONFIRM OUTPUT PATH WITH USER BEFORE WRITING.
==============================================================================

## Why Table-Tracking Matters

Never slice lines by range — XER tables are sequential and slicing crosses table boundaries, corrupting other tables. Track `current_table` as you iterate.

## Write-Back Pattern

```python
def write_updated_xer(original_path, output_path, updated_tasks):
    """Write recalculated or modified task data back into a new XER file."""
    updated = {t['task_id']: t for t in updated_tasks}
    lines = open(original_path, 'rb').read().decode('cp1252').split('\r\n')
    current_table = None; fields = []; out_lines = []

    for line in lines:
        if line.startswith('%T'):
            current_table = line.split('\t')[1].strip() if '\t' in line else None
            out_lines.append(line)
        elif line.startswith('%F'):
            fields = [f.strip() for f in line.split('\t')[1:]]
            out_lines.append(line)
        elif line.startswith('%R') and current_table == 'TASK':
            vals = line.split('\t')[1:]
            row = dict(zip(fields, vals))
            if row.get('task_id', '') in updated:
                u = updated[row['task_id']]
                for f in ['early_start_date', 'early_end_date', 'late_start_date',
                           'late_end_date', 'total_float_hr_cnt', 'free_float_hr_cnt']:
                    if f in row and f in u:
                        row[f] = u[f]
                vals = [row.get(f, '') for f in fields]
            out_lines.append('%R\t' + '\t'.join(vals))
        else:
            out_lines.append(line)

    open(output_path, 'wb').write('\r\n'.join(out_lines).encode('cp1252'))
```

## Date Fields

Format: `YYYY-MM-DD HH:MM`. Start times typically `08:00`, finish times `17:00` (or `16:00` per calendar).

## Common Modifications

- **Rename:** Update `task_name` in TASK rows
- **Adjust duration:** Update `target_drtn_hr_cnt` and `remain_drtn_hr_cnt` (hours = days × 8)
- **Add relationship:** Insert new TASKPRED row with all required fields
- **Remove activity:** Filter TASK + TASKPRED + TASKRSRC rows simultaneously
