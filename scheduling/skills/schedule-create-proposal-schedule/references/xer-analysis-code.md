# XER Analysis Code for Proposal Schedule Planning

Use these functions to extract schedule profiles from sample XER files during the proposal schedule planning process.

```python
def extract_schedule_profile(tables, file_name):
    """Extract a schedule profile from parsed XER tables for comparison."""
    tasks = tables.get('TASK', [])
    wbs = tables.get('PROJWBS', [])
    preds = tables.get('TASKPRED', [])
    project = tables.get('PROJECT', [{}])[0]
    calendars = tables.get('CALENDAR', tables.get('CLNDR', []))

    # Filter to non-summary, non-LOE activities
    real_tasks = [t for t in tasks if t.get('task_type', '') not in ('TT_WBS', 'TT_LOE')]

    # Duration stats — XER stores hours internally, convert to days (/ 8) for display
    durations_hrs = [float(t.get('target_drtn_hr_cnt', 0)) for t in real_tasks
                     if t.get('task_type', '') not in ('TT_Mile', 'TT_FinMile')]
    durations = [d / 8 for d in durations_hrs]  # Convert to working days

    # Relationship type distribution
    rel_types = {}
    for p in preds:
        rt = p.get('pred_type', 'PR_FS').replace('PR_', '')
        rel_types[rt] = rel_types.get(rt, 0) + 1

    # Milestone list
    milestones = [
        {'name': t.get('task_name', ''), 'type': t.get('task_type', ''),
         'date': t.get('cstr_date', t.get('early_end_date', ''))}
        for t in tasks if t.get('task_type', '') in ('TT_Mile', 'TT_FinMile')
    ]

    # Activity naming patterns — sample first 15 activity names per WBS node
    naming_samples = {}
    for t in real_tasks[:50]:
        wbs_id = t.get('wbs_id', 'unknown')
        if wbs_id not in naming_samples:
            naming_samples[wbs_id] = []
        if len(naming_samples[wbs_id]) < 5:
            naming_samples[wbs_id].append(t.get('task_name', ''))

    profile = {
        'file_name': file_name,
        'project_name': project.get('project_name', 'Unknown'),
        'start_date': project.get('start_date', ''),
        'end_date': project.get('end_date', ''),

        # WBS structure
        'wbs_tree': build_wbs_tree(wbs),
        'wbs_depth': max_wbs_depth(wbs),
        'wbs_node_count': len(wbs),

        # Activity patterns
        'total_activities': len(real_tasks),
        'activity_types': count_by_field(real_tasks, 'task_type'),
        'naming_samples': naming_samples,

        # Duration statistics (working days)
        'duration_min_days': min(durations) if durations else 0,
        'duration_max_days': max(durations) if durations else 0,
        'duration_median_days': sorted(durations)[len(durations)//2] if durations else 0,
        'duration_avg_days': sum(durations) / len(durations) if durations else 0,

        # Logic network
        'relationship_count': len(preds),
        'relationship_ratio': round(len(preds) / max(len(real_tasks), 1), 2),
        'rel_type_distribution': rel_types,

        # Milestones
        'milestones': milestones,

        # Calendars
        'calendars': [(c.get('clndr_name', ''), c.get('clndr_id', ''))
                      for c in calendars],
    }
    return profile


def build_wbs_tree(wbs_records):
    """Reconstruct WBS hierarchy as an indented list."""
    nodes = {w.get('wbs_id'): w for w in wbs_records}
    children = {}
    root = None
    for w in wbs_records:
        parent = w.get('parent_wbs_id', '')
        if parent and parent in nodes:
            children.setdefault(parent, []).append(w.get('wbs_id'))
        elif not parent:
            root = w.get('wbs_id')

    def render(node_id, depth=0):
        node = nodes.get(node_id, {})
        lines = ['  ' * depth + node.get('wbs_name', node_id)]
        for child_id in children.get(node_id, []):
            lines.extend(render(child_id, depth + 1))
        return lines

    if root:
        return '\n'.join(render(root))
    return '\n'.join(w.get('wbs_name', '') for w in wbs_records)


def max_wbs_depth(wbs_records):
    """Calculate maximum depth of WBS hierarchy."""
    nodes = {w.get('wbs_id'): w for w in wbs_records}
    def depth(node_id, d=0):
        node = nodes.get(node_id, {})
        parent = node.get('parent_wbs_id', '')
        if parent and parent in nodes:
            return depth(parent, d + 1)
        return d
    return max((depth(w.get('wbs_id')) for w in wbs_records), default=0)


def count_by_field(records, field):
    """Count records by a field value."""
    counts = {}
    for r in records:
        val = r.get(field, 'unknown')
        counts[val] = counts.get(val, 0) + 1
    return counts
```

## Presenting Analysis Results

After extracting profiles, present a summary for each sample schedule:

```
**Schedule: [Project Name] ([file_name])**
- Duration: [X] months | Activities: [N] | Relationship Ratio: [X.X]:1
- WBS Structure ([depth] levels, [node_count] nodes):
  [indented WBS tree]
- Milestones: [list]
- Duration Range: [min]-[max] days (median [med], avg [avg])
- Relationship Types: FS [X]%, SS [Y]%, FF [Z]%
- Calendar: [calendar names]
- Sample Activities: [5-10 representative names by WBS area]
```

Also extract from bid documents:
- Project name, location, type
- Contract duration / substantial completion date
- Required milestones and interim deadlines
- Phasing requirements
- Liquidated damages amounts and triggers
- Schedule specification requirements
- Scope summary by major division or area
- Special conditions (occupied building, phased turnover, seasonal restrictions)
