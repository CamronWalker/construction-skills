"""show_paths.py -- compact read of critical / driving / near-critical /
parallel-branch paths for a proposal-schedule project.

Reads `schedule-activities.json` only -- no CPM run, no XER parse. Just
formats the existing `paths` block for token-efficient agent context.

Usage:
    python show_paths.py "<project-folder>"
"""

import argparse
import json
import sys
from pathlib import Path


# Truncate driving-path chain dumps to this many activities (driving paths
# can run 50+ items; agents only need the head/tail to orient).
_DRIVING_HEAD = 6


def _activities_path(project):
    proposal_dir = project / 'Proposal Schedule'
    if not proposal_dir.is_dir():
        proposal_dir = project
    p = proposal_dir / 'schedule-activities.json'
    if not p.exists() and (project / 'schedule-activities.json').exists():
        p = project / 'schedule-activities.json'
    return p


def _fmt_task(t):
    return (
        f"  {t.get('id',''):10s}  "
        f"{(t.get('name','') or '')[:42]:42s}  "
        f"{t.get('early_start','')} -> {t.get('early_end','')}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project', help='Path to the proposal-schedule project folder')
    args = ap.parse_args()

    project = Path(args.project)
    activities_path = _activities_path(project)
    if not activities_path.exists():
        print(f'ERROR: schedule-activities.json not found under {project}', file=sys.stderr)
        return 1

    doc = json.loads(activities_path.read_text(encoding='utf-8'))
    proj = doc.get('project', {})
    paths = doc.get('paths', {})

    name = proj.get('name', '') or project.name
    dd = (proj.get('data_date', '') or '')[:10]
    sc_date = (proj.get('sc_milestone_date', '') or '')[:10]
    sc_code = proj.get('sc_milestone_code', '')
    sc_name = proj.get('sc_milestone_name', '')

    print(f'{name} (data date {dd}, SC {sc_date} {sc_code} {sc_name})')

    cp = paths.get('critical_path', []) or []
    print()
    print(f'CRITICAL PATH ({len(cp)} activities, 0d float)')
    for t in cp:
        print(_fmt_task(t))

    for dp in paths.get('driving_paths', []) or []:
        chain = dp.get('chain', []) or []
        print()
        print(f"DRIVING PATH -> {dp.get('to','')} "
              f"({dp.get('end_task_code','')} {dp.get('end_task_name','')[:50]}, "
              f"{len(chain)} activities)")
        head = chain[:_DRIVING_HEAD]
        tail_count = max(0, len(chain) - _DRIVING_HEAD)
        for t in head:
            print(_fmt_task(t))
        if tail_count:
            print(f"  ... {tail_count} more activities; tail:")
            for t in chain[-2:]:
                print(_fmt_task(t))

    near = paths.get('near_critical', []) or []
    if near:
        print()
        print(f'NEAR-CRITICAL CHAINS ({len(near)})')
        for i, c in enumerate(near, 1):
            label = chr(64 + i) if i <= 26 else str(i)
            print(f"  Chain {label}: {c.get('length',0)} activities, min float {c.get('float_days',0)}d")

    par = paths.get('parallel_branches', []) or []
    if par:
        print()
        print(f'PARALLEL BRANCHES ({len(par)})')

        def _node_id(node):
            if isinstance(node, dict):
                return node.get('id') or node.get('task_code') or node.get('task_id', '?')
            return str(node or '?')

        for b in par[:6]:
            div = _node_id(b.get('diverge_at', ''))
            con = _node_id(b.get('converge_at', ''))
            mfd = b.get('min_float_days', '')
            branch_count = len(b.get('branches', []) or [])
            print(f"  {div} -> {con}  ({branch_count} branches, min float {mfd}d)")
        if len(par) > 6:
            print(f"  ... {len(par) - 6} more")

    return 0


if __name__ == '__main__':
    sys.exit(main())
