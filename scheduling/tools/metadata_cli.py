"""metadata_cli.py -- read/write the per-project metadata JSON.

Project metadata pins the context that makes duration knowledge useful.
A "5-day pour footings" insight means nothing without knowing it came
from a K-12 project in Utah Valley with structural masonry. This metadata
is captured once per project and inherited by every duration entry +
postmortem snapshot.

Storage:
    <project>/project-metadata.json    (both new + legacy layouts)

Schema (all optional; the ones the user fills in are the ones that
get persisted -- no defaults are forced):

    {
      "project_name": "Murray City Apex Center",
      "project_type": "office-tenant-improvement" | "k-12" | "lab-research" | ...,
      "delivery_method": "design-bid-build" | "design-build" | "cm-at-risk" | "cm-gc" | ...,
      "region": "Utah Valley" | "Salt Lake" | "St George" | "Boise" | ...,
      "square_footage": 50000,
      "floor_count": 2,
      "dollar_value": 18500000,
      "difficulty": "low" | "medium" | "high",
      "building_systems": ["structural-masonry", "steel-joist", "tilt-up", "wood",
                            "hybrid", "pre-engineered-metal", "concrete"],
      "notes": "any freeform clarifying detail"
    }

Subcommands:
    set    "<project>" --key value [--key value ...]   merge fields
    get    "<project>" [--field name]                  read one or all
    show   "<project>"                                 pretty-print
    init   "<project>"                                 create empty stub

Exit codes: 0 ok, 1 error.
"""

import argparse
import json
import sys
from pathlib import Path

import _layout


_KNOWN_FIELDS = [
    'project_name',
    'project_type',
    'delivery_method',
    'region',
    'square_footage',
    'floor_count',
    'dollar_value',
    'difficulty',
    'building_systems',
    'notes',
]

_INT_FIELDS = {'square_footage', 'floor_count', 'dollar_value'}
_LIST_FIELDS = {'building_systems'}


def _err(msg):
    print(f'ERROR: {msg}', file=sys.stderr)
    return 1


def _read(project, layout):
    p = _layout.metadata_path(project, layout)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


def _write(project, layout, data):
    p = _layout.metadata_path(project, layout)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                 encoding='utf-8')


def _coerce(field, value):
    if value is None or value == '':
        return None
    if field in _INT_FIELDS:
        try:
            return int(str(value).replace(',', '').replace('$', '').strip())
        except ValueError:
            return None
    if field in _LIST_FIELDS:
        if isinstance(value, list):
            return [str(v).strip() for v in value if str(v).strip()]
        return [v.strip() for v in str(value).split(',') if v.strip()]
    return str(value).strip()


# -------------------------------------------------------------------------
# Subcommands
# -------------------------------------------------------------------------

def cmd_set(args):
    project = Path(args.project).resolve()
    layout = _layout.detect_layout(project)
    data = _read(project, layout)
    # Default project_name from folder if not supplied
    data.setdefault('project_name', project.name)
    changed = []
    for field in _KNOWN_FIELDS:
        attr = field.replace('-', '_')
        val = getattr(args, attr, None)
        if val is None:
            continue
        coerced = _coerce(field, val)
        if coerced is None or coerced == '':
            if field in data:
                del data[field]
                changed.append(f'  -{field}')
        else:
            data[field] = coerced
            changed.append(f'  {field}: {coerced}')
    _write(project, layout, data)
    if changed:
        print(f'Updated {_layout.metadata_path(project, layout).name}:')
        for c in changed:
            print(c)
    else:
        print('No fields changed.')
    return 0


def cmd_get(args):
    project = Path(args.project).resolve()
    layout = _layout.detect_layout(project)
    data = _read(project, layout)
    if args.field:
        if args.field in data:
            v = data[args.field]
            if isinstance(v, list):
                print(','.join(v))
            else:
                print(v)
            return 0
        return _err(f'field not set: {args.field}')
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def cmd_show(args):
    project = Path(args.project).resolve()
    layout = _layout.detect_layout(project)
    data = _read(project, layout)
    p = _layout.metadata_path(project, layout)
    if not data:
        print(f'(no metadata at {p.relative_to(project) if p.is_relative_to(project) else p})')
        print()
        print('Use:  propsched metadata set "<project>" --project-type k-12 '
              '--region "Utah Valley" --square-footage 50000 ...')
        return 0
    print(f'Project metadata ({p.name}):')
    width = max((len(k) for k in data), default=0)
    for k in _KNOWN_FIELDS:
        if k in data:
            v = data[k]
            if isinstance(v, list):
                v = ', '.join(v) if v else '(empty)'
            print(f'  {k:<{width}} : {v}')
    # Show extras at the end
    for k in data:
        if k not in _KNOWN_FIELDS:
            print(f'  {k:<{width}} : {data[k]}')
    return 0


def cmd_init(args):
    project = Path(args.project).resolve()
    layout = _layout.detect_layout(project)
    p = _layout.metadata_path(project, layout)
    if p.exists() and not args.force:
        return _err(f'already exists: {p.name} (use --force to overwrite)')
    stub = {
        'project_name': project.name,
        'project_type': '',
        'delivery_method': '',
        'region': '',
        'square_footage': None,
        'floor_count': None,
        'dollar_value': None,
        'difficulty': '',
        'building_systems': [],
        'notes': '',
    }
    _write(project, layout, stub)
    print(f'Created {p.name} with empty fields.')
    print('Fill in via:  propsched metadata set "<project>" --project-type k-12 ...')
    return 0


# -------------------------------------------------------------------------
# Main
# -------------------------------------------------------------------------

def _add_set_args(p):
    p.add_argument('project', help='Path to the project folder')
    p.add_argument('--project-name', dest='project_name', default=None)
    p.add_argument('--project-type', dest='project_type', default=None,
                   help='K-12, office-tenant-improvement, lab-research, ...')
    p.add_argument('--delivery-method', dest='delivery_method', default=None,
                   help='design-bid-build, design-build, cm-at-risk, cm-gc, ...')
    p.add_argument('--region', dest='region', default=None,
                   help='Utah Valley, Salt Lake, St George, Boise, ...')
    p.add_argument('--square-footage', dest='square_footage', default=None,
                   help='Building gross sf (commas/$ accepted)')
    p.add_argument('--floor-count', dest='floor_count', default=None)
    p.add_argument('--dollar-value', dest='dollar_value', default=None,
                   help='Project dollar value (commas/$ accepted)')
    p.add_argument('--difficulty', dest='difficulty', default=None,
                   help='low | medium | high')
    p.add_argument('--building-systems', dest='building_systems', default=None,
                   help='Comma-separated list (structural-masonry, steel-joist, '
                        'tilt-up, wood, hybrid, ...)')
    p.add_argument('--notes', dest='notes', default=None)


def main():
    ap = argparse.ArgumentParser(description='Project metadata CLI.')
    sub = ap.add_subparsers(dest='subcommand', required=True)

    p_set = sub.add_parser('set', help='Set/update metadata fields')
    _add_set_args(p_set)

    p_get = sub.add_parser('get', help='Read metadata (one field or all as JSON)')
    p_get.add_argument('project', help='Path to the project folder')
    p_get.add_argument('--field', default=None, help='Single field to read')

    p_show = sub.add_parser('show', help='Pretty-print metadata')
    p_show.add_argument('project', help='Path to the project folder')

    p_init = sub.add_parser('init', help='Create an empty metadata stub')
    p_init.add_argument('project', help='Path to the project folder')
    p_init.add_argument('--force', action='store_true',
                        help='Overwrite if it already exists')

    args = ap.parse_args()
    if args.subcommand == 'set':
        return cmd_set(args)
    if args.subcommand == 'get':
        return cmd_get(args)
    if args.subcommand == 'show':
        return cmd_show(args)
    if args.subcommand == 'init':
        return cmd_init(args)
    ap.error(f'unknown subcommand: {args.subcommand}')


if __name__ == '__main__':
    sys.exit(main())
