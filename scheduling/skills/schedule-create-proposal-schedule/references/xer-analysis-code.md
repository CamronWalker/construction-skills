# XER Analysis — Schedule Profile Extraction

Use `references/xer_analysis.py` to extract comparable metrics from sample XER files.

## Usage

```python
from xer_analysis import extract_schedule_profile

tables = parse_xer('sample.xer')
profile = extract_schedule_profile(tables, 'Sample Project')
```

## Profile Fields

| Field | Description |
|-------|-------------|
| `total_activities` | Non-summary, non-LOE activity count |
| `relationship_ratio` | Rels / activities |
| `rel_type_distribution` | `{FS: N, SS: N, FF: N, SF: N}` |
| `duration_min/max/median/avg_days` | Duration stats in working days |
| `wbs_tree` | Indented WBS hierarchy string |
| `wbs_depth` / `wbs_node_count` | WBS stats |
| `milestones` | `[{name, type, date}]` |
| `naming_samples` | Up to 5 activity names per WBS node |
| `calendars` | `[(name, id)]` |

## Presenting Results

For each sample schedule, present:

```
[Project Name] ([filename])
- Duration: [X] months | Activities: [N] | Ratio: [X.X]:1
- WBS ([depth] levels, [N] nodes):
  [wbs_tree]
- Durations: [min]-[max] days (avg [avg])
- Relationships: FS [X]%, SS [Y]%, FF [Z]%
- Milestones: [list]
- Calendar: [names]
- Sample Activities: [5-10 representative names]
```
