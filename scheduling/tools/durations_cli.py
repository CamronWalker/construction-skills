"""durations_cli.py -- per-activity duration knowledge keyed by project
context.

Context-free durations don't mean anything. "Pour footings -- 5d" is
useless without knowing it came from a K-12 in Utah Valley with
structural masonry. This DB binds every duration entry to the project
metadata snapshot at the moment it was recorded, so future drafts can
query "what have we seen for pour-footings on K-12 jobs in this region?"
and get an honest answer.

Storage:
    <project>/Old Iterations/durations.json

Schema:

    {
      "schema": "westland-durations",
      "schema_version": 1,
      "entries": [
        {
          "task_code": "APEX0040",
          "task_name": "Pour Footings",
          "final_duration_days": 5,
          "source": "reviewer:Steve Westover" | "super:Mike" | "self" | "estimator:Camron",
          "rationale": "Soil conditions in Utah Valley typically drive 5-7d for this size pour",
          "version": 7,
          "date": "2026-04-30",
          "project_metadata": {
              "project_name": "...",
              "project_type": "k-12",
              "region": "Utah Valley",
              "square_footage": 50000,
              "building_systems": ["structural-masonry"],
              ...
          }
        }
      ]
    }

Subcommands:
    add      "<project>" --task-code X --duration N --source ... --rationale ...
    extract  "<project>"   pull duration_change items from parked reviewer feedback into durations.json
    query    [--project <p>] [--task-code X] [--type t] [--region r] ...
                            search the local project's durations.json AND, with
                            --root <dir>, every project under <root> for
                            cross-project knowledge
    list     "<project>"   enumerate entries in this project's durations.json

Exit codes: 0 ok, 1 error.
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import _layout


SCHEMA = 'westland-durations'
SCHEMA_VERSION = 1


def _err(msg):
    print(f'ERROR: {msg}', file=sys.stderr)
    return 1


def _read_db(project, layout):
    p = _layout.durations_path(project, layout)
    if not p.exists():
        return {'schema': SCHEMA, 'schema_version': SCHEMA_VERSION, 'entries': []}
    try:
        data = json.loads(p.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {'schema': SCHEMA, 'schema_version': SCHEMA_VERSION, 'entries': []}
    data.setdefault('schema', SCHEMA)
    data.setdefault('schema_version', SCHEMA_VERSION)
    data.setdefault('entries', [])
    return data


def _write_db(project, layout, data):
    p = _layout.durations_path(project, layout)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def _read_metadata_snapshot(project, layout):
    """Read project-metadata.json so we can stamp it onto every entry."""
    p = _layout.metadata_path(project, layout)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


def _activities_index(project, layout):
    aj = _layout.activities_json_path(project, layout)
    if not aj.exists():
        return None, {}, {}
    try:
        data = json.loads(aj.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None, {}, {}
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


def _today():
    return datetime.now().strftime('%Y-%m-%d')


# -------------------------------------------------------------------------
# Subcommands
# -------------------------------------------------------------------------

def cmd_add(args):
    project = Path(args.project).resolve()
    layout = _layout.detect_layout(project)
    if not args.task_code and not args.task_name:
        return _err('--task-code or --task-name is required')
    if args.duration is None:
        return _err('--duration is required (days)')

    metadata = _read_metadata_snapshot(project, layout)
    cur_version, _, by_code = _activities_index(project, layout)
    task_name = args.task_name
    if not task_name and args.task_code and args.task_code in by_code:
        task_name = by_code[args.task_code].get('name', '')

    entry = {
        'task_code': args.task_code or None,
        'task_name': task_name or '',
        'final_duration_days': float(args.duration) if '.' in str(args.duration)
                                else int(args.duration),
        'source': args.source or 'self',
        'rationale': args.rationale or '',
        'version': args.version if args.version is not None else cur_version,
        'date': args.date or _today(),
        'project_metadata': metadata,
    }
    db = _read_db(project, layout)
    db['entries'].append(entry)
    _write_db(project, layout, db)
    print(f'Added duration entry: '
          f'[{entry["task_code"] or "?"}] {entry["task_name"]} = '
          f'{entry["final_duration_days"]}d  '
          f'(source: {entry["source"]}, project: {metadata.get("project_name", project.name)})')
    return 0


def cmd_extract(args):
    """Pull duration_change items out of parked reviewer feedback into durations.json.

    For each parked reviewer JSON: every activity that has a
    duration_change becomes a candidate entry. We take the *suggested*
    duration (to_days) as the final, since we are only ingesting feedback
    that the scheduler is acting on. Source is "reviewer:{name}".
    """
    project = Path(args.project).resolve()
    layout = _layout.detect_layout(project)
    rf_dir = _layout.reviewer_feedback_dir(project, layout)
    if not rf_dir.is_dir():
        print('(no reviewer-feedback/ directory; nothing to extract)')
        return 0
    metadata = _read_metadata_snapshot(project, layout)
    cur_version, _, by_code = _activities_index(project, layout)

    db = _read_db(project, layout)
    existing_keys = set()
    for e in db['entries']:
        existing_keys.add((
            e.get('task_code'),
            e.get('source'),
            e.get('date'),
            e.get('final_duration_days'),
        ))

    added = 0
    skipped = 0
    for f in sorted(rf_dir.glob('*.json')):
        try:
            payload = json.loads(f.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            continue
        rev = (payload.get('reviewer') or {}).get('name', 'unknown')
        rd = payload.get('review_date') or _today()
        rv = payload.get('version_reviewed')
        for item in payload.get('activities') or []:
            dc = item.get('duration_change')
            if not dc:
                continue
            to_d = dc.get('to_days')
            if to_d is None:
                continue
            tc = item.get('task_code')
            tn = (item.get('task_snapshot') or {}).get('name') or item.get('name', '')
            entry = {
                'task_code': tc,
                'task_name': tn,
                'final_duration_days': to_d,
                'source': f'reviewer:{rev}',
                'rationale': item.get('comment') or '',
                'version': rv,
                'date': rd,
                'project_metadata': metadata,
            }
            key = (entry['task_code'], entry['source'], entry['date'],
                   entry['final_duration_days'])
            if key in existing_keys:
                skipped += 1
                continue
            db['entries'].append(entry)
            existing_keys.add(key)
            added += 1
    if added:
        _write_db(project, layout, db)
    print(f'Extracted {added} duration entr{"y" if added == 1 else "ies"} '
          f'from reviewer feedback'
          + (f' (skipped {skipped} duplicates)' if skipped else '')
          + '.')
    return 0


def _scan_dbs(roots):
    """Yield (project_path, durations_data) tuples for every project under roots."""
    for root in roots:
        root = Path(root)
        if not root.is_dir():
            continue
        # Find any durations.json under root (depth-3 max: root/<project>/Old Iterations/durations.json)
        for p in root.rglob('durations.json'):
            try:
                data = json.loads(p.read_text(encoding='utf-8'))
            except (OSError, json.JSONDecodeError):
                continue
            if data.get('schema') != SCHEMA:
                continue
            # Project folder is two parents up (Old Iterations/durations.json)
            project = p.parent.parent
            yield project, data


def _matches_filter(entry, task_code=None, task_substr=None,
                    project_type=None, region=None, system=None):
    if task_code and entry.get('task_code') != task_code:
        return False
    if task_substr:
        name = (entry.get('task_name') or '').lower()
        if task_substr.lower() not in name:
            return False
    pm = entry.get('project_metadata') or {}
    if project_type and project_type.lower() not in (pm.get('project_type') or '').lower():
        return False
    if region and region.lower() not in (pm.get('region') or '').lower():
        return False
    if system:
        systems = [s.lower() for s in (pm.get('building_systems') or [])]
        if system.lower() not in systems:
            return False
    return True


def cmd_query(args):
    if args.project:
        project = Path(args.project).resolve()
        layout = _layout.detect_layout(project)
        sources = [(project, _read_db(project, layout))]
    elif args.root:
        sources = list(_scan_dbs([args.root]))
    else:
        return _err('must pass either --project or --root')

    matches = []
    for proj, db in sources:
        for e in db.get('entries') or []:
            if _matches_filter(e,
                               task_code=args.task_code,
                               task_substr=args.task,
                               project_type=args.type,
                               region=args.region,
                               system=args.system):
                matches.append((proj, e))

    if args.json:
        out = []
        for proj, e in matches:
            d = dict(e)
            d['_source_project'] = str(proj)
            out.append(d)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if not matches:
        print('No matching duration entries.')
        return 0

    # Group by task name
    by_task = {}
    for proj, e in matches:
        key = (e.get('task_code') or '?', e.get('task_name') or '?')
        by_task.setdefault(key, []).append((proj, e))

    print(f'{len(matches)} duration entr{"y" if len(matches) == 1 else "ies"} '
          f'matched.')
    print()
    for (code, name), entries in sorted(by_task.items()):
        ds = [e['final_duration_days'] for _, e in entries
              if e.get('final_duration_days') is not None]
        if ds:
            ds_sorted = sorted(ds)
            mn, mx = ds_sorted[0], ds_sorted[-1]
            avg = sum(ds) / len(ds)
            range_str = f'{mn}d' if mn == mx else f'{mn}-{mx}d (avg {avg:.1f})'
        else:
            range_str = '?'
        print(f'[{code}] {name}  --  {len(entries)} obs, {range_str}')
        for proj, e in entries:
            pm = e.get('project_metadata') or {}
            ctx = []
            if pm.get('project_type'):
                ctx.append(pm['project_type'])
            if pm.get('region'):
                ctx.append(pm['region'])
            if pm.get('building_systems'):
                ctx.append('+'.join(pm['building_systems']))
            ctx_str = ', '.join(ctx) if ctx else '(no metadata)'
            rationale = e.get('rationale') or ''
            if len(rationale) > 80:
                rationale = rationale[:77] + '...'
            print(f'    {e.get("final_duration_days")}d  '
                  f'[{e.get("source")}]  {ctx_str}'
                  + (f'  -- {rationale}' if rationale else ''))
    return 0


def cmd_list(args):
    project = Path(args.project).resolve()
    layout = _layout.detect_layout(project)
    db = _read_db(project, layout)
    entries = db.get('entries') or []
    if not entries:
        print(f'(no duration entries for {project.name})')
        return 0
    print(f'{len(entries)} duration entr{"y" if len(entries) == 1 else "ies"} '
          f'in {project.name}:')
    for e in entries:
        print(f'  {e.get("date")}  [{e.get("task_code") or "?"}] '
              f'{e.get("task_name", "")}  {e.get("final_duration_days")}d  '
              f'(v{e.get("version")}, source: {e.get("source")})')
    return 0


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(
        description='Duration knowledge DB (per-activity, project-context-bound).')
    sub = ap.add_subparsers(dest='subcommand', required=True)

    p_add = sub.add_parser('add', help='Add a duration entry')
    p_add.add_argument('project', help='Path to the project folder')
    p_add.add_argument('--task-code', dest='task_code', default=None)
    p_add.add_argument('--task-name', dest='task_name', default=None,
                       help='Override task name (otherwise pulled from activities JSON)')
    p_add.add_argument('--duration', required=True,
                       help='Final duration in days')
    p_add.add_argument('--source', default='self',
                       help='reviewer:Name | super:Name | self | estimator:Name')
    p_add.add_argument('--rationale', default='',
                       help='Why this duration; supers/reviewers context')
    p_add.add_argument('--version', type=int, default=None,
                       help='XER version this entry is tied to (default: current)')
    p_add.add_argument('--date', default=None,
                       help='Date of the entry (default: today)')

    p_ext = sub.add_parser('extract',
                           help='Pull duration_change items from parked reviewer feedback')
    p_ext.add_argument('project', help='Path to the project folder')

    p_q = sub.add_parser('query',
                         help='Search durations by task / project context')
    p_q.add_argument('--project', default=None,
                     help='Search within a single project')
    p_q.add_argument('--root', default=None,
                     help='Search across every project under this root')
    p_q.add_argument('--task-code', dest='task_code', default=None)
    p_q.add_argument('--task', dest='task', default=None,
                     help='Substring match on task_name')
    p_q.add_argument('--type', default=None,
                     help='Filter by project_type substring')
    p_q.add_argument('--region', default=None,
                     help='Filter by region substring')
    p_q.add_argument('--system', default=None,
                     help='Filter by building_systems entry')
    p_q.add_argument('--json', action='store_true',
                     help='Emit machine-readable JSON')

    p_list = sub.add_parser('list', help='Enumerate entries in this project')
    p_list.add_argument('project', help='Path to the project folder')

    args = ap.parse_args()
    if args.subcommand == 'add':
        return cmd_add(args)
    if args.subcommand == 'extract':
        return cmd_extract(args)
    if args.subcommand == 'query':
        return cmd_query(args)
    if args.subcommand == 'list':
        return cmd_list(args)
    ap.error(f'unknown subcommand: {args.subcommand}')


if __name__ == '__main__':
    sys.exit(main())
