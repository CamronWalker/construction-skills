"""anchors_from_constraints.py -- one-shot bootstrap.

Reads the latest -v{N}.xer in a proposal-schedule project folder, finds tasks
with anchor-class hard constraints (CS_MSO, CS_FNLT, CS_MANDSTART,
CS_MANDFIN, CS_MEOB, CS_MFO), writes them into
`<project>/Proposal Schedule/proposal-anchors.json`, and emits a sibling
-v{N+1}.xer with those constraint fields cleared.

Westland's anchor-via-logic rule: anchor dates stay pinned by logic and
durations, not constraints. This script lifts an existing constraint-heavy
schedule into the new convention in one shot.

Usage:
    python anchors_from_constraints.py "<project-folder>"
    python anchors_from_constraints.py "<project-folder>" --dry-run
    python anchors_from_constraints.py "<project-folder>" --include-types CS_MSO,CS_FNLT
"""

import argparse
import json
import sys
from pathlib import Path

from _xer_io import parse_xer, find_latest_xer, next_xer_path, write_xer_with_updates


# Constraint types we lift into anchors. Seasonal / weather constraints
# (CS_MSOA = Must Start On or After) stay in the XER -- they're not anchors,
# they're real construction logic.
DEFAULT_ANCHOR_CONSTRAINTS = {
    'CS_MSO',        # Must Start On
    'CS_MANDSTART',  # Mandatory Start
    'CS_FNLT',       # Finish No Later Than
    'CS_MANDFIN',    # Mandatory Finish
    'CS_MEOB',       # Must End On or Before
    'CS_MFO',        # Must Finish On
}

START_KINDS = {'CS_MSO', 'CS_MANDSTART'}
FINISH_KINDS = {'CS_FNLT', 'CS_MANDFIN', 'CS_MEOB', 'CS_MFO'}

KIND_LABELS = {
    'NTP': ['NTP', 'Notice to Proceed', 'Construction Award'],
    'Award': ['Project Award', 'Construction Award'],
    '100% CDs Issued': ['100% CDs', '100% CD'],
    'Substantial Completion': ['Substantial Completion'],
    'Procurement Recommendations': ['Procurement Recommendations'],
    'Warranty End': ['Warranty End'],
}


def _guess_kind_label(task_name):
    """Best-effort human label for a task that's about to become an anchor."""
    n = (task_name or '').strip()
    for label, needles in KIND_LABELS.items():
        for needle in needles:
            if needle.lower() in n.lower():
                return label
    return n[:60]


def _date_only(s):
    """'2026-09-01 08:00' -> '2026-09-01'."""
    return (s or '').strip()[:10]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project', help='Path to the proposal-schedule project folder')
    ap.add_argument('--dry-run', action='store_true',
                    help='Print the anchors that would be lifted, write nothing')
    ap.add_argument('--include-types', default='',
                    help='Comma-separated constraint types to lift '
                         '(default: ' + ','.join(sorted(DEFAULT_ANCHOR_CONSTRAINTS)) + ')')
    args = ap.parse_args()

    project = Path(args.project)
    if not project.is_dir():
        print(f'ERROR: not a directory: {project}', file=sys.stderr)
        return 1

    anchor_types = (
        {t.strip().upper() for t in args.include_types.split(',') if t.strip()}
        if args.include_types
        else DEFAULT_ANCHOR_CONSTRAINTS
    )

    latest = find_latest_xer(project)
    if not latest:
        print(f'ERROR: no -v{{N}}.xer found under {project}', file=sys.stderr)
        return 1
    xer_path, version = latest

    anchors_path = (project / 'Proposal Schedule' / 'proposal-anchors.json'
                    if (project / 'Proposal Schedule').is_dir()
                    else project / 'proposal-anchors.json')

    tables, table_fields, original_text = parse_xer(xer_path)
    tasks = tables.get('TASK', [])
    project_rows = tables.get('PROJECT', [])
    project_name = ''
    if project_rows:
        project_name = (project_rows[0].get('proj_short_name', '')
                        or project_rows[0].get('proj_id', ''))
    if not project_name:
        project_name = project.name

    anchors = []
    task_updates = {}
    for t in tasks:
        cstr = (t.get('cstr_type') or '').strip()
        cstr_date = (t.get('cstr_date') or '').strip()
        if cstr not in anchor_types or not cstr_date:
            continue
        anchor_kind = 'start' if cstr in START_KINDS else 'finish'
        anchors.append({
            'kind_label': _guess_kind_label(t.get('task_name', '')),
            'task_code': t.get('task_code', ''),
            'task_name': t.get('task_name', ''),
            'anchor_kind': anchor_kind,
            'anchor_date': _date_only(cstr_date),
            'source': f'Lifted from XER constraint {cstr} on {xer_path.name}',
        })
        task_updates[t.get('task_id', '')] = {
            'cstr_type': '',
            'cstr_date': '',
        }

    if not anchors:
        print(f'No anchor-class constraints found in {xer_path.name}.')
        print(f'Looked for: {", ".join(sorted(anchor_types))}')
        return 0

    print(f'Project: {project_name}')
    print(f'Source XER: {xer_path.name}')
    print(f'Lifting {len(anchors)} anchor(s):')
    for a in anchors:
        print(f"  {a['task_code']:8s}  {a['kind_label']:30s}  "
              f"{a['anchor_kind']:6s}  {a['anchor_date']}")

    if args.dry_run:
        print('\n[dry-run] would write:', anchors_path)
        new_xer = next_xer_path(xer_path, version)
        print(f'[dry-run] would write: {new_xer.name} (constraints cleared)')
        return 0

    anchors_path.write_text(
        json.dumps({'project_name': project_name, 'anchors': anchors},
                   ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
    new_xer = next_xer_path(xer_path, version)
    write_xer_with_updates(
        original_text, table_fields,
        {'TASK': ('task_id', task_updates)},
        new_xer,
    )

    print()
    print(f'Wrote anchors: {anchors_path}')
    print(f'Wrote XER:     {new_xer.name}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
