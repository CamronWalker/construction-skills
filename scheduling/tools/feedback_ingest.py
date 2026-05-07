"""feedback_ingest.py -- park a reviewer-feedback JSON and report drift
against the current XER.

The HTML schedule-review download exports a JSON like:

    {
      "schema": "westland-reviewer-feedback",
      "schema_version": 1,
      "reviewer": {"name": "Steve Westover", "email": "..."},
      "review_date": "2026-05-01",
      "project": "Murray City Apex Center",
      "version_reviewed": 5,
      "activities": [
        {
          "id": "12345",
          "task_code": "APEX0040",
          "name": "...",
          "duration_change": {"from_days": 5, "to_days": 7},
          "comment": "...",
          "task_snapshot": {
            "name": "...",
            "duration_days": 5,
            "early_start": "2026-05-12",
            "early_end": "2026-05-19",
            "total_float_days": 4
          }
        }
      ],
      ...
    }

A reviewer can take days or weeks to respond. By the time their JSON
lands, the schedule may have advanced several versions -- task codes
may have been renamed, durations may have changed, tasks may have been
dropped entirely. This verb does NOT auto-apply changes. It parks the
JSON for the scheduler and reports drift so the scheduler can decide
what to keep.

Subcommands:
    ingest "<project>" --file feedback.json     park JSON + report drift
    list   "<project>"                          enumerate parked JSONs
    show   "<project>" <filename>               re-print drift for one file

Storage:
    new layout:    <project>/Old Iterations/reviewer-feedback/
                       {reviewer-slug}-{review-date}-v{N}.json
    legacy layout: same folder under Proposal Schedule/iterations/

Exit codes:
    0  ingested cleanly (current version, no drift)
    1  error
    2  ingested with drift warnings (older version, missing tasks, etc.)
"""

import argparse
import json
import re
import sys
from pathlib import Path

import _layout


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def _slugify(s):
    s = re.sub(r'[^a-zA-Z0-9]+', '-', str(s or '')).strip('-').lower()
    return s[:40] or 'reviewer'


def _read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def _err(msg):
    print(f'ERROR: {msg}', file=sys.stderr)
    return 1


def _activities_index(project, layout):
    """Return (current_version, by_id, by_code) from schedule-activities.json."""
    aj = _layout.activities_json_path(project, layout)
    if not aj.exists():
        return None, {}, {}
    data = json.loads(aj.read_text(encoding='utf-8'))
    proj = data.get('project') or {}
    cur_version = proj.get('version')
    by_id, by_code = {}, {}
    for a in data.get('activities', []):
        aid = a.get('id')
        code = a.get('task_code')
        if aid is not None:
            by_id[str(aid)] = a
        if code:
            by_code[code] = a
    return cur_version, by_id, by_code


def _detect_drift(payload, current_version, by_id, by_code):
    """Return a list of (severity, message) tuples summarizing drift."""
    drift = []
    rv = payload.get('version_reviewed')
    if rv is not None and current_version is not None:
        try:
            rv_i = int(rv)
            cv_i = int(current_version)
        except (TypeError, ValueError):
            rv_i = cv_i = None
        if rv_i is not None and cv_i is not None:
            if rv_i < cv_i:
                drift.append(('warn',
                    f'feedback is for v{rv_i}; current is v{cv_i} '
                    f'(reviewer is {cv_i - rv_i} version(s) behind)'))
            elif rv_i > cv_i:
                drift.append(('error',
                    f'feedback claims v{rv_i} but current is v{cv_i} '
                    f'(file may be from a different project or copy)'))
    elif rv is None:
        drift.append(('info',
            'feedback JSON has no version_reviewed; cannot check version drift'))

    # Per-activity comparison vs current schedule
    for item in payload.get('activities', []) or []:
        aid = item.get('id')
        code = item.get('task_code')
        snap = item.get('task_snapshot') or {}
        cur = None
        if aid is not None and str(aid) in by_id:
            cur = by_id[str(aid)]
        elif code and code in by_code:
            cur = by_code[code]
        label = code or aid or '(unknown)'
        if cur is None:
            drift.append(('warn',
                f'task {label} no longer in current schedule '
                f'(may have been removed or recoded)'))
            continue
        # Name drift
        snap_name = (snap.get('name') or '').strip()
        cur_name = (cur.get('name') or '').strip()
        if snap_name and cur_name and snap_name != cur_name:
            drift.append(('info',
                f'task {label} renamed: "{snap_name}" -> "{cur_name}"'))
        # Duration drift (only meaningful if reviewer logged a duration_change)
        snap_dur = snap.get('duration_days')
        cur_dur = cur.get('duration_days')
        if (snap_dur is not None and cur_dur is not None
                and snap_dur != cur_dur):
            edit = item.get('duration_change') or {}
            edit_str = ''
            if edit:
                edit_str = (f' (reviewer suggested {edit.get("from_days")} '
                            f'-> {edit.get("to_days")})')
            drift.append(('warn',
                f'task {label} duration changed since review: '
                f'{snap_dur}d -> {cur_dur}d{edit_str}'))
    return drift


def _format_drift(drift):
    if not drift:
        return '  (none)'
    lines = []
    for sev, msg in drift:
        prefix = {'error': '  [error]', 'warn': '  [warn] ', 'info': '  [info] '}.get(sev, '  ')
        lines.append(f'{prefix} {msg}')
    return '\n'.join(lines)


# -------------------------------------------------------------------------
# Subcommands
# -------------------------------------------------------------------------

def cmd_ingest(args):
    project = Path(args.project).resolve()
    layout = _layout.detect_layout(project)
    src = Path(args.file)
    if not src.exists():
        return _err(f'feedback file not found: {src}')
    try:
        payload = _read_json(src)
    except (OSError, json.JSONDecodeError) as e:
        return _err(f'unreadable JSON: {e}')

    schema = payload.get('schema')
    if schema != 'westland-reviewer-feedback':
        print(f'WARNING: unexpected schema "{schema}"; continuing anyway',
              file=sys.stderr)

    reviewer = (payload.get('reviewer') or {}).get('name', '').strip()
    if not reviewer:
        return _err('feedback JSON is missing reviewer.name')
    review_date = payload.get('review_date') or 'unknown-date'
    rv = payload.get('version_reviewed')
    rv_str = f'v{rv}' if rv is not None else 'unknown'

    rf_dir = _layout.reviewer_feedback_dir(project, layout)
    rf_dir.mkdir(parents=True, exist_ok=True)
    fname = f'{_slugify(reviewer)}-{review_date}-{rv_str}.json'
    dest = rf_dir / fname

    if dest.exists() and not args.force:
        return _err(f'destination already exists: {dest.relative_to(project)} '
                    f'(use --force to overwrite)')
    dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                    encoding='utf-8')

    # Detect drift vs current activities JSON
    cur_version, by_id, by_code = _activities_index(project, layout)
    drift = _detect_drift(payload, cur_version, by_id, by_code)

    n_acts = len(payload.get('activities') or [])
    print(f'Ingested: {dest.relative_to(project)}')
    print(f'  Reviewer:        {reviewer}')
    print(f'  Review date:     {review_date}')
    print(f'  Version reviewed:{rv_str}'
          + (f'   Current: v{cur_version}' if cur_version is not None else ''))
    print(f'  Comments + edits: {n_acts}')
    print()
    print('Drift report:')
    print(_format_drift(drift))

    has_error = any(s == 'error' for s, _ in drift)
    has_warn = any(s == 'warn' for s, _ in drift)
    if has_error:
        return 1
    if has_warn:
        return 2
    return 0


def cmd_list(args):
    project = Path(args.project).resolve()
    layout = _layout.detect_layout(project)
    rf_dir = _layout.reviewer_feedback_dir(project, layout)
    if not rf_dir.is_dir():
        print(f'(no reviewer feedback for {project.name})')
        return 0
    cur_version, _, _ = _activities_index(project, layout)
    files = sorted(rf_dir.glob('*.json'))
    if not files:
        print(f'(reviewer-feedback/ exists but is empty)')
        return 0
    print(f'Reviewer feedback for {project.name} '
          f'(current: v{cur_version if cur_version is not None else "?"})')
    print()
    for f in files:
        try:
            data = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            print(f'  [unreadable] {f.name}')
            continue
        rev = (data.get('reviewer') or {}).get('name', '?')
        rd = data.get('review_date', '?')
        rv = data.get('version_reviewed')
        rv_str = f'v{rv}' if rv is not None else '?'
        n = len(data.get('activities') or [])
        stale = ''
        if (cur_version is not None and rv is not None
                and isinstance(rv, int) and rv < int(cur_version)):
            stale = f'  [stale: {int(cur_version) - rv} version(s) behind]'
        print(f'  {f.name}')
        print(f'    {rev} -- {rd} -- {rv_str} -- {n} item(s){stale}')
    return 0


def cmd_show(args):
    project = Path(args.project).resolve()
    layout = _layout.detect_layout(project)
    rf_dir = _layout.reviewer_feedback_dir(project, layout)
    target = rf_dir / args.filename
    if not target.exists():
        # Allow bare reviewer slug -> latest match
        matches = sorted(rf_dir.glob(f'{args.filename}*.json'))
        if not matches:
            return _err(f'no feedback file matches: {args.filename}')
        target = matches[-1]
    try:
        payload = _read_json(target)
    except (OSError, json.JSONDecodeError) as e:
        return _err(f'unreadable JSON: {e}')

    cur_version, by_id, by_code = _activities_index(project, layout)
    drift = _detect_drift(payload, cur_version, by_id, by_code)

    rev = (payload.get('reviewer') or {}).get('name', '?')
    rd = payload.get('review_date', '?')
    rv = payload.get('version_reviewed')
    print(f'File:            {target.relative_to(project)}')
    print(f'Reviewer:        {rev}')
    print(f'Review date:     {rd}')
    print(f'Version reviewed: v{rv}' if rv is not None else
          'Version reviewed: unknown')
    if cur_version is not None:
        print(f'Current version:  v{cur_version}')
    print()
    print('Comments + edits:')
    for item in payload.get('activities') or []:
        code = item.get('task_code') or item.get('id') or '?'
        name = (item.get('task_snapshot') or {}).get('name') or item.get('name') or ''
        dc = item.get('duration_change')
        c = item.get('comment')
        line = f'  [{code}] {name}'
        if dc:
            line += f'  duration: {dc.get("from_days")} -> {dc.get("to_days")}'
        print(line)
        if c:
            for cl in c.splitlines():
                print(f'        {cl}')
    print()
    print('Drift report:')
    print(_format_drift(drift))
    return 0


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description='Park a reviewer-feedback JSON; report drift vs current XER.')
    sub = ap.add_subparsers(dest='subcommand', required=True)

    p_ing = sub.add_parser('ingest', help='Park a feedback JSON and report drift')
    p_ing.add_argument('project', help='Path to the project folder')
    p_ing.add_argument('--file', required=True,
                       help='Path to the reviewer-feedback JSON')
    p_ing.add_argument('--force', action='store_true',
                       help='Overwrite an existing parked file with the same name')

    p_list = sub.add_parser('list', help='List parked reviewer-feedback files')
    p_list.add_argument('project', help='Path to the project folder')

    p_show = sub.add_parser('show', help='Re-print drift for one parked file')
    p_show.add_argument('project', help='Path to the project folder')
    p_show.add_argument('filename',
                        help='Filename inside reviewer-feedback/ (or a prefix)')

    args = ap.parse_args()
    if args.subcommand == 'ingest':
        return cmd_ingest(args)
    if args.subcommand == 'list':
        return cmd_list(args)
    if args.subcommand == 'show':
        return cmd_show(args)
    ap.error(f'unknown subcommand: {args.subcommand}')


if __name__ == '__main__':
    sys.exit(main())
