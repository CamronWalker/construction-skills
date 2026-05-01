"""show_anchors.py -- compact read of anchor status for a proposal-schedule
project. Reads `proposal-anchors.json` + the latest `schedule-activities.json`
and prints one line per anchor with anchor / computed / drift.

No CPM run. No XER parse. Just JSON-to-stdout for token-efficient agent
context.

Usage:
    python show_anchors.py "<project-folder>"
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from _cpm_loader import load_cpm


def _resolve_paths(project):
    import _layout
    anchors = _layout.anchors_path(project)
    activities = _layout.activities_json_path(project)
    if not activities.exists() and (project / 'schedule-activities.json').exists():
        activities = project / 'schedule-activities.json'
    return (anchors, activities)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project', help='Path to the proposal-schedule project folder')
    args = ap.parse_args()

    project = Path(args.project)
    anchors_path, activities_path = _resolve_paths(project)

    if not anchors_path.exists():
        print(f'ERROR: {anchors_path.name} not found', file=sys.stderr)
        print('Run anchors_from_constraints.py first to bootstrap.', file=sys.stderr)
        return 1
    if not activities_path.exists():
        print(f'ERROR: {activities_path.name} not found', file=sys.stderr)
        print('Run proposal_iterate.py to generate it from the latest XER.', file=sys.stderr)
        return 1

    anchors_doc = json.loads(anchors_path.read_text(encoding='utf-8'))
    anchors = anchors_doc.get('anchors', [])
    activities = json.loads(activities_path.read_text(encoding='utf-8'))

    project_name = anchors_doc.get('project_name', '') or activities.get('project', {}).get('name', '')

    # Shape activity rows so check_anchor_dates can read them. The CPM helper
    # wants task_code + early_start_date / early_end_date fields.
    results = []
    for a in activities.get('activities', []):
        if a.get('is_summary') or a.get('kind') == 'wbs':
            continue
        results.append({
            'task_code': a.get('task_code') or a.get('id', ''),
            'task_name': a.get('name', ''),
            'task_id': a.get('task_id', ''),
            'early_start_date': a.get('early_start') or a.get('start') or '',
            'early_end_date': a.get('early_end') or a.get('end') or '',
        })

    cpm = load_cpm()
    slips = cpm.check_anchor_dates(results, anchors)
    slips_by_code = {s['task_code']: s for s in slips}

    print(f'{project_name} anchors ({anchors_path.name})')
    for a in anchors:
        code = a.get('task_code', '')
        label = a.get('kind_label', '') or a.get('task_name', '')[:30]
        kind = a.get('anchor_kind', 'finish')
        anchor_date = a.get('anchor_date', '')

        # Find activity row for the computed date
        row = next((r for r in results if r['task_code'] == code), None)
        if row is None:
            computed = '(not in activities JSON)'
            drift = '?'
        else:
            field = 'early_start_date' if kind == 'start' else 'early_end_date'
            computed = (row.get(field, '') or '')[:10] or '(not scheduled)'
            slip = slips_by_code.get(code)
            if slip is None:
                drift = 'OK'
            else:
                d = slip['slip_days']
                if d > 0:
                    drift = f'+{d}d (late)'
                else:
                    drift = f'{d}d (early)'

        print(f"  {label[:30]:30s}  {code:10s}  anchor {anchor_date} / "
              f"computed {computed:10s}  {drift}")

    if any(s['slip_days'] > 0 for s in slips):
        return 2  # at least one anchor slipping past tolerance
    return 0


if __name__ == '__main__':
    sys.exit(main())
