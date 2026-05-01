"""show_diff.py -- pairwise diff between two XER versions of the same
project, with name-similarity heuristic + path-impact summary.

Wraps `xer_compare.compare_xer_pair` and adds:

  - Code-reassignment detection: if a task_code's duration changed
    drastically AND its task_name diverges, classify as "likely
    reassignment" rather than a duration change. The legacy diff would
    show "Submit HVAC Materials 140d -> 5d" when the activity behind
    APEX0700 actually changed entirely.
  - Path-impact: pull SC date delta + critical-path length delta from the
    paths block of each version's `schedule-activities.json` if available.
  - One-line classification of the iteration's character (write-back /
    sample-normalize / restructure / anchor-cleanup / paste-back).

Usage:
    python show_diff.py "<project>" <vA> <vB>
        # vA, vB are version numbers; resolved against Old Iterations/
        # (new layout) or directly under Proposal Schedule/ (legacy).
        # vA="current" or vB="current" reads the project root XER.
    python show_diff.py "<project>" v3 v4
    python show_diff.py "<project>" v12 current
"""

import argparse
import difflib
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

from _xer_io import parse_xer
from _cpm_loader import reference_dir
import _layout


_VERSION_RE = re.compile(r'-v(\d+)\.xer$', re.IGNORECASE)


def _load(name):
    spec = importlib.util.spec_from_file_location(
        name, os.path.join(reference_dir(), f'{name}.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _resolve_version(project, layout, label):
    """Resolve 'v3' / '3' / 'current' to a Path object pointing at the XER."""
    project = Path(project)
    if isinstance(label, str) and label.lower() == 'current':
        cur = _layout.find_current_xer(project, layout)
        if cur is None:
            raise FileNotFoundError(f'no current XER at {project}')
        return cur
    # Accept 'v3', 'V3', '3'
    m = re.match(r'^v?(\d+)$', str(label).strip(), re.IGNORECASE)
    if not m:
        raise ValueError(f'unrecognized version label: {label!r}')
    n = int(m.group(1))
    if layout == _layout.LAYOUT_NEW:
        # Look in Old Iterations/ for -v{n}.xer
        iters = _layout.iterations_dir(project, layout)
        candidates = [p for p in iters.glob('*.xer') if _VERSION_RE.search(p.name)
                      and int(_VERSION_RE.search(p.name).group(1)) == n]
        if candidates:
            return candidates[0]
        # If asking for the newest version, treat as current
        archived = _layout.latest_archived_version(project, layout)
        if n == archived + 1:
            cur = _layout.find_current_xer(project, layout)
            if cur is not None:
                return cur
        raise FileNotFoundError(f'v{n}.xer not found in {iters}')
    # Legacy: look in Proposal Schedule/
    proposal = _layout.proposal_dir(project, layout)
    candidates = [p for p in proposal.glob('*.xer') if _VERSION_RE.search(p.name)
                  and int(_VERSION_RE.search(p.name).group(1)) == n]
    if not candidates:
        raise FileNotFoundError(f'v{n}.xer not found in {proposal}')
    return candidates[0]


def _name_similarity(a, b):
    """Ratio of similarity between two task names (0.0..1.0)."""
    return difflib.SequenceMatcher(None, (a or '').lower(),
                                    (b or '').lower()).ratio()


def _classify_iteration(cmp_result, name_lookup, cstr_delta=0):
    """Single-word classification of the diff's character.

    Returns one of: write-back, anchor-cleanup, sample-normalize,
    restructure, paste-back, mixed.
    """
    added = len(cmp_result.get('added_tasks', []))
    removed = len(cmp_result.get('removed_tasks', []))
    durs = cmp_result.get('changed_durations', []) or []
    rels = cmp_result.get('changed_relationships', {}) or {}
    rels_count = (rels.get('added_count', 0) + rels.get('removed_count', 0)
                  + rels.get('changed_count', 0))
    n_durs = len(durs)
    no_content_change = (added == 0 and removed == 0 and n_durs == 0 and rels_count == 0)

    if no_content_change:
        if cstr_delta <= -3:
            return 'anchor-cleanup'
        return 'write-back'

    if added == 0 and removed == 0 and rels_count == 0 and n_durs <= 5:
        return 'paste-back'

    reassignments = 0
    for d in durs:
        code = d.get('task_code', '')
        old_name = name_lookup.get(('old', code), '')
        new_name = name_lookup.get(('new', code), '')
        if old_name and new_name and _name_similarity(old_name, new_name) < 0.5:
            reassignments += 1
    if reassignments >= 5:
        return 'restructure'

    if n_durs >= 50 and added <= 3 and removed <= 3:
        negatives = sum(1 for d in durs if d.get('delta_days', 0) < 0)
        positives = sum(1 for d in durs if d.get('delta_days', 0) > 0)
        if negatives >= positives * 3 and negatives >= 30:
            return 'sample-normalize'

    if added + removed >= 3 or rels_count >= 5:
        return 'restructure'

    return 'mixed'


def _build_name_lookup(old_tables, new_tables):
    """For each task_code in either side, record old/new task_name."""
    lookup = {}
    for t in old_tables.get('TASK', []):
        code = t.get('task_code', '')
        if code:
            lookup[('old', code)] = t.get('task_name', '')
    for t in new_tables.get('TASK', []):
        code = t.get('task_code', '')
        if code:
            lookup[('new', code)] = t.get('task_name', '')
    return lookup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project', help='Path to the project folder')
    ap.add_argument('vA', help='Older version (v3, 3, or "current")')
    ap.add_argument('vB', help='Newer version (v4, 4, or "current")')
    ap.add_argument('--top', type=int, default=5,
                    help='Top N entries per category to show')
    ap.add_argument('--json', action='store_true',
                    help='Emit machine-readable JSON instead of markdown')
    args = ap.parse_args()

    project = Path(args.project)
    if not project.is_dir():
        print(f'ERROR: not a directory: {project}', file=sys.stderr)
        return 1
    layout = _layout.detect_layout(project)

    try:
        path_a = _resolve_version(project, layout, args.vA)
        path_b = _resolve_version(project, layout, args.vB)
    except (FileNotFoundError, ValueError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1

    old_tables, _, _ = parse_xer(path_a)
    new_tables, _, _ = parse_xer(path_b)

    xc = _load('xer_compare')
    cmp_result = xc.compare_xer_pair(old_tables, new_tables, match_by='task_code')
    name_lookup = _build_name_lookup(old_tables, new_tables)

    # Constraint counts (compare_xer_pair doesn't surface; do it ourselves
    # before classification so anchor-cleanup can fire on it)
    old_cstr = sum(1 for t in old_tables.get('TASK', []) if (t.get('cstr_type') or '').strip())
    new_cstr = sum(1 for t in new_tables.get('TASK', []) if (t.get('cstr_type') or '').strip())
    classification = _classify_iteration(cmp_result, name_lookup, cstr_delta=new_cstr - old_cstr)

    # Recompute the top duration changes with reassignment flagging
    durs = list(cmp_result.get('changed_durations', []))
    durs.sort(key=lambda d: -abs(d.get('delta_days', 0)))
    enriched_durs = []
    for d in durs[:args.top]:
        code = d['task_code']
        old_name = name_lookup.get(('old', code), '')
        new_name = name_lookup.get(('new', code), '')
        sim = _name_similarity(old_name, new_name)
        d2 = dict(d)
        d2['old_name'] = old_name
        d2['new_name'] = new_name
        d2['name_similarity'] = round(sim, 2)
        d2['flag'] = 'likely-reassignment' if sim < 0.5 and abs(d.get('delta_days', 0)) >= 5 else ''
        enriched_durs.append(d2)

    if args.json:
        print(json.dumps({
            'classification': classification,
            'old_xer': str(path_a.name),
            'new_xer': str(path_b.name),
            'sc_old': cmp_result.get('sc_date_old', ''),
            'sc_new': cmp_result.get('sc_date_new', ''),
            'sc_slip_days': cmp_result.get('sc_slip_days', 0),
            'added_count': len(cmp_result.get('added_tasks', [])),
            'removed_count': len(cmp_result.get('removed_tasks', [])),
            'duration_change_count': len(cmp_result.get('changed_durations', [])),
            'rel_change_count': sum([
                cmp_result.get('changed_relationships', {}).get(k, 0)
                for k in ('added_count', 'removed_count', 'changed_count')
            ]),
            'old_constraint_count': old_cstr,
            'new_constraint_count': new_cstr,
            'top_duration_changes': enriched_durs,
        }, indent=2, default=str))
        return 0

    # Markdown / human-readable output
    print(f'Diff: {path_a.name} -> {path_b.name}')
    print(f'Classification: {classification}')
    print(f'  SC: {cmp_result.get("sc_date_old","")} -> {cmp_result.get("sc_date_new","")} '
          f'({cmp_result.get("sc_slip_days",0):+d}d)')
    print(f'  added: {len(cmp_result.get("added_tasks",[]))}  '
          f'removed: {len(cmp_result.get("removed_tasks",[]))}  '
          f'duration_changes: {len(cmp_result.get("changed_durations",[]))}  '
          f'rel_changes: '
          f'{sum([cmp_result.get("changed_relationships",{}).get(k,0) for k in ("added_count","removed_count","changed_count")])}')
    print(f'  constraints: {old_cstr} -> {new_cstr} ({new_cstr-old_cstr:+d})')

    added = cmp_result.get('added_tasks', [])
    removed = cmp_result.get('removed_tasks', [])
    if added:
        print(f'\nAdded ({len(added)}, top {min(args.top,len(added))}):')
        for a in added[:args.top]:
            print(f'  + {a["task_code"]:10s}  {(a["task_name"] or "")[:50]:50s}  {a["duration_days"]}d')
    if removed:
        print(f'\nRemoved ({len(removed)}, top {min(args.top,len(removed))}):')
        for r in removed[:args.top]:
            print(f'  - {r["task_code"]:10s}  {(r["task_name"] or "")[:50]:50s}  {r["duration_days"]}d')
    if enriched_durs:
        print(f'\nTop duration changes (top {len(enriched_durs)} by |delta|):')
        for d in enriched_durs:
            flag = f'  [{d["flag"]}]' if d['flag'] else ''
            print(f'  {d["task_code"]:10s}  '
                  f'{(d["new_name"] or d["old_name"] or "")[:36]:36s}  '
                  f'{d["old_duration_days"]:>5}d -> {d["new_duration_days"]:>5}d  '
                  f'({d["delta_days"]:+.1f}d){flag}')
            if d['flag']:
                print(f'             old name: {d["old_name"][:60]}')
                print(f'             new name: {d["new_name"][:60]}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
