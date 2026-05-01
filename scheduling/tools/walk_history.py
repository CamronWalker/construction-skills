"""walk_history.py -- walk a project's full iteration chain (v1 -> current)
and print a per-iteration narrative.

Calls show_diff under the hood for each consecutive pair, prints a one-line
classification and the headline numbers, then a compact list of the top
duration changes / adds / removes.

Usage:
    python walk_history.py "<project>"
    python walk_history.py "<project>" --top 3
    python walk_history.py "<project>" --json
"""

import argparse
import json
import re
import sys
from pathlib import Path

from _xer_io import parse_xer
import _layout
import importlib.util, os
from _cpm_loader import reference_dir


_VERSION_RE = re.compile(r'-v(\d+)\.xer$', re.IGNORECASE)


def _enumerate_versions(project, layout):
    """Return ordered list of (version_int, path).

    For new layout: every -v{N}.xer in Old Iterations/, then current at root
    as the implicit latest_version+1.
    For legacy: every -v{N}.xer in Proposal Schedule/.
    """
    project = Path(project)
    found = []
    if layout == _layout.LAYOUT_NEW:
        iters = _layout.iterations_dir(project, layout)
        if iters.is_dir():
            for p in iters.glob('*.xer'):
                m = _VERSION_RE.search(p.name)
                if m:
                    found.append((int(m.group(1)), p))
        cur = _layout.find_current_xer(project, layout)
        if cur is not None:
            implicit_v = (max((v for v, _ in found), default=0)) + 1
            found.append((implicit_v, cur))
    else:
        proposal = _layout.proposal_dir(project, layout)
        for p in proposal.glob('*.xer'):
            m = _VERSION_RE.search(p.name)
            if m:
                found.append((int(m.group(1)), p))
    found.sort(key=lambda x: x[0])
    return found


def _load_xer_compare():
    spec = importlib.util.spec_from_file_location(
        'xer_compare', os.path.join(reference_dir(), 'xer_compare.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# Same heuristic as show_diff (kept duplicated to avoid coupling)
def _classify(cmp_result, name_lookup, reassignment_count, cstr_delta=0):
    added = len(cmp_result.get('added_tasks', []))
    removed = len(cmp_result.get('removed_tasks', []))
    durs = cmp_result.get('changed_durations', []) or []
    rels = cmp_result.get('changed_relationships', {}) or {}
    rels_count = (rels.get('added_count', 0) + rels.get('removed_count', 0)
                  + rels.get('changed_count', 0))
    n_durs = len(durs)
    no_content_change = (added == 0 and removed == 0 and n_durs == 0 and rels_count == 0)
    if no_content_change:
        # Constraint clearing alone = anchor-cleanup; everything else = write-back
        if cstr_delta <= -3:
            return 'anchor-cleanup'
        return 'write-back'
    if added == 0 and removed == 0 and rels_count == 0 and n_durs <= 5:
        return 'paste-back'
    if reassignment_count >= 5:
        return 'restructure'
    if n_durs >= 50 and added <= 3 and removed <= 3:
        negs = sum(1 for d in durs if d.get('delta_days', 0) < 0)
        poss = sum(1 for d in durs if d.get('delta_days', 0) > 0)
        if negs >= poss * 3 and negs >= 30:
            return 'sample-normalize'
    if added + removed >= 3 or rels_count >= 5:
        return 'restructure'
    return 'mixed'


def _build_name_lookup(old_tables, new_tables):
    lookup = {}
    for t in old_tables.get('TASK', []):
        c = t.get('task_code', '')
        if c:
            lookup[('old', c)] = t.get('task_name', '')
    for t in new_tables.get('TASK', []):
        c = t.get('task_code', '')
        if c:
            lookup[('new', c)] = t.get('task_name', '')
    return lookup


def _name_similarity(a, b):
    import difflib
    return difflib.SequenceMatcher(None, (a or '').lower(),
                                    (b or '').lower()).ratio()


def _count_reassignments(durs, name_lookup):
    n = 0
    for d in durs:
        c = d.get('task_code', '')
        on = name_lookup.get(('old', c), '')
        nn = name_lookup.get(('new', c), '')
        if on and nn and _name_similarity(on, nn) < 0.5 and abs(d.get('delta_days', 0)) >= 5:
            n += 1
    return n


def _shape(tables):
    tasks = [t for t in tables.get('TASK', [])
             if t.get('task_type') not in ('TT_WBS', 'TT_LOE')]
    n = len(tasks)
    total_dur_d = sum(float(t.get('target_drtn_hr_cnt') or 0) for t in tasks) / 8
    cstr = sum(1 for t in tables.get('TASK', []) if (t.get('cstr_type') or '').strip())
    return n, round(total_dur_d), cstr


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project', help='Path to the project folder')
    ap.add_argument('--top', type=int, default=3,
                    help='Top N entries per category')
    ap.add_argument('--json', action='store_true',
                    help='Emit machine-readable JSON')
    args = ap.parse_args()

    project = Path(args.project)
    if not project.is_dir():
        print(f'ERROR: not a directory: {project}', file=sys.stderr)
        return 1
    layout = _layout.detect_layout(project)
    versions = _enumerate_versions(project, layout)
    if len(versions) < 2:
        print(f'Only {len(versions)} version(s) found; need at least 2 for a walk.')
        return 0

    xc = _load_xer_compare()
    transitions = []
    prev_v, prev_path = versions[0]
    prev_tables, _, _ = parse_xer(prev_path)
    prev_n, prev_dur, prev_cstr = _shape(prev_tables)

    for v, p in versions[1:]:
        tables, _, _ = parse_xer(p)
        cmp_r = xc.compare_xer_pair(prev_tables, tables, match_by='task_code')
        names = _build_name_lookup(prev_tables, tables)
        durs = cmp_r.get('changed_durations', [])
        reassign_n = _count_reassignments(durs, names)
        n, dur, cstr = _shape(tables)
        cls = _classify(cmp_r, names, reassign_n, cstr_delta=cstr - prev_cstr)
        transitions.append({
            'from_version': prev_v,
            'to_version': v,
            'from_xer': prev_path.name,
            'to_xer': p.name,
            'classification': cls,
            'sc_old': cmp_r.get('sc_date_old', ''),
            'sc_new': cmp_r.get('sc_date_new', ''),
            'sc_slip_days': cmp_r.get('sc_slip_days', 0),
            'tasks_old': prev_n, 'tasks_new': n,
            'total_dur_old': prev_dur, 'total_dur_new': dur,
            'constraints_old': prev_cstr, 'constraints_new': cstr,
            'added_count': len(cmp_r.get('added_tasks', [])),
            'removed_count': len(cmp_r.get('removed_tasks', [])),
            'duration_change_count': len(durs),
            'reassignment_count': reassign_n,
            'top_duration_changes': sorted(
                durs, key=lambda d: -abs(d.get('delta_days', 0))
            )[:args.top],
        })
        prev_v, prev_path, prev_tables = v, p, tables
        prev_n, prev_dur, prev_cstr = n, dur, cstr

    if args.json:
        print(json.dumps({'project': str(project), 'transitions': transitions},
                         indent=2, default=str))
        return 0

    # Markdown narrative
    print(f'Walk: {project.name}')
    base_v, base_path = versions[0]
    base_n, base_dur, base_cstr = _shape(parse_xer(base_path)[0])
    print(f'Baseline v{base_v} ({base_path.name}): '
          f'{base_n} tasks, total {base_dur}d, {base_cstr} constraints')
    print()
    for t in transitions:
        cls_tag = f'[{t["classification"]}]'
        print(f'v{t["from_version"]} -> v{t["to_version"]}  {cls_tag}')
        print(f'  tasks {t["tasks_old"]}->{t["tasks_new"]} ({t["tasks_new"]-t["tasks_old"]:+d})  '
              f'total_dur {t["total_dur_old"]}->{t["total_dur_new"]}d '
              f'({t["total_dur_new"]-t["total_dur_old"]:+d})  '
              f'constraints {t["constraints_old"]}->{t["constraints_new"]} '
              f'({t["constraints_new"]-t["constraints_old"]:+d})')
        print(f'  SC {t["sc_old"]} -> {t["sc_new"]} ({t["sc_slip_days"]:+d}d)  '
              f'+{t["added_count"]} -{t["removed_count"]}  durs:{t["duration_change_count"]}'
              + (f'  reassigns:{t["reassignment_count"]}' if t['reassignment_count'] else ''))
        for d in t['top_duration_changes']:
            print(f'    {d["task_code"]:10s}  '
                  f'{(d.get("task_name") or "")[:36]:36s}  '
                  f'{d.get("old_duration_days",0):>5}d -> {d.get("new_duration_days",0):>5}d  '
                  f'({d.get("delta_days",0):+.1f}d)')
        print()
    return 0


if __name__ == '__main__':
    sys.exit(main())
