"""score_with_sidecar.py -- score an XER's quality (DCMA / Westland rubric)
and write a small JSON sidecar to Old Iterations/scores/ so the diff and
walk CLIs can show score deltas across iterations.

Wraps the score_schedule helper from schedule-toolbox/references/. Sidecar
is intentionally small -- top-level letter grade + numeric score + per-check
booleans -- so the JSON is cheap to read repeatedly during a walk.

Usage:
    python score_with_sidecar.py "<project>" [--version current]
    python score_with_sidecar.py "<project>" --version 11
    python score_with_sidecar.py "<project>" --no-sidecar     # just print, no write
"""

import argparse
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


def _load_score():
    spec = importlib.util.spec_from_file_location(
        'score_schedule', os.path.join(reference_dir(), 'score_schedule.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _resolve_version(project, layout, label):
    project = Path(project)
    if isinstance(label, str) and label.lower() == 'current':
        cur = _layout.find_current_xer(project, layout)
        if cur is None:
            raise FileNotFoundError(f'no current XER at {project}')
        return cur, _layout.latest_archived_version(project, layout) + 1
    m = re.match(r'^v?(\d+)$', str(label).strip(), re.IGNORECASE)
    if not m:
        raise ValueError(f'unrecognized version label: {label!r}')
    n = int(m.group(1))
    if layout == _layout.LAYOUT_NEW:
        iters = _layout.iterations_dir(project, layout)
        for p in iters.glob('*.xer'):
            mm = _VERSION_RE.search(p.name)
            if mm and int(mm.group(1)) == n:
                return p, n
        archived = _layout.latest_archived_version(project, layout)
        if n == archived + 1:
            cur = _layout.find_current_xer(project, layout)
            if cur is not None:
                return cur, n
        raise FileNotFoundError(f'v{n}.xer not found in {iters}')
    proposal = _layout.proposal_dir(project, layout)
    for p in proposal.glob('*.xer'):
        mm = _VERSION_RE.search(p.name)
        if mm and int(mm.group(1)) == n:
            return p, n
    raise FileNotFoundError(f'v{n}.xer not found in {proposal}')


def _data_date_from_tables(tables):
    proj = tables.get('PROJECT', [])
    if not proj:
        return None
    return proj[0].get('last_recalc_date') or proj[0].get('data_date') or None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project', help='Path to the project folder')
    ap.add_argument('--version', default='current',
                    help='Version to score (current, v3, 3, ...)')
    ap.add_argument('--no-sidecar', action='store_true',
                    help='Print result, do not write JSON sidecar')
    ap.add_argument('--json', action='store_true',
                    help='Emit machine-readable JSON to stdout')
    args = ap.parse_args()

    project = Path(args.project)
    if not project.is_dir():
        print(f'ERROR: not a directory: {project}', file=sys.stderr)
        return 1
    layout = _layout.detect_layout(project)

    try:
        xer_path, version = _resolve_version(project, layout, args.version)
    except (FileNotFoundError, ValueError) as e:
        print(f'ERROR: {e}', file=sys.stderr)
        return 1

    tables, _, _ = parse_xer(xer_path)
    tasks = tables.get('TASK', [])
    preds = tables.get('TASKPRED', [])
    data_date = _data_date_from_tables(tables)

    sc = _load_score()
    score, grade, scored, info, deductions, scope, details = sc.compute_quality_score(
        tasks, preds, data_date)

    sidecar = {
        'version': version,
        'xer': xer_path.name,
        'data_date': data_date,
        'score': round(score, 1),
        'grade': grade,
        'sc_milestone_date': info.get('sc_date', '') if isinstance(info, dict) else '',
        'task_count_in_scope': info.get('scope_task_count', 0) if isinstance(info, dict) else 0,
    }

    if not args.no_sidecar:
        out_dir = _layout.scores_dir(project, layout)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f'v{version}.json'
        out_path.write_text(json.dumps(sidecar, indent=2, default=str), encoding='utf-8')

    if args.json:
        print(json.dumps(sidecar, indent=2, default=str))
        return 0

    print(f'Scored: {xer_path.name}')
    print(f'  v{version}  grade {grade}  score {sidecar["score"]}')
    if not args.no_sidecar:
        print(f'  sidecar: {_layout.scores_dir(project, layout) / f"v{version}.json"}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
