"""postmortem_finalize.py -- assemble the post-approval postmortem folder.

Tier 7+: a postmortem is no longer a single .md file. It is a
self-contained folder copyable to a master library:

    Old Iterations/postmortems/{YYYY-MM-DD}-{project-slug}/
        postmortem.md
        project-metadata.json     <- snapshot at completion
        durations-captured.json   <- duration entries added this cycle (if any)
        reviewer-feedback/
            *.json                <- copies of every parked reviewer JSON

The agent writes postmortem.md (the human-readable narrative). This
script does the boring assembly: creates the folder, snapshots metadata,
copies reviewer-feedback/, and (optionally) extracts durations from this
cycle's reviewer feedback.

Usage:

    python postmortem_finalize.py "<project>" --slug murray-apex-center
    python postmortem_finalize.py "<project>" --slug murray-apex --date 2026-04-30
    python postmortem_finalize.py "<project>" --slug ... --skip-durations
    python postmortem_finalize.py "<project>" --slug ... --print-stub > postmortem.md

Exit codes: 0 ok, 1 error.
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

import _layout


def _err(msg):
    print(f'ERROR: {msg}', file=sys.stderr)
    return 1


def _read_metadata(project, layout):
    p = _layout.metadata_path(project, layout)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


def _read_durations(project, layout):
    p = _layout.durations_path(project, layout)
    if not p.exists():
        return {'entries': []}
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {'entries': []}


def _activities_summary(project, layout):
    aj = _layout.activities_json_path(project, layout)
    if not aj.exists():
        return {}
    try:
        data = json.loads(aj.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}
    proj = data.get('project') or {}
    acts = data.get('activities') or []
    return {
        'name': proj.get('name'),
        'version': proj.get('version'),
        'data_date': proj.get('data_date'),
        'sc_milestone_date': proj.get('sc_milestone_date'),
        'project_end_date': proj.get('project_end_date'),
        'activity_count': len(acts),
    }


def _filter_durations_for_cycle(durations, cycle_start_date):
    """Return durations entries dated on/after cycle_start_date (string YYYY-MM-DD)."""
    if not cycle_start_date:
        return list(durations.get('entries') or [])
    out = []
    for e in durations.get('entries') or []:
        d = e.get('date') or ''
        if d >= cycle_start_date:
            out.append(e)
    return out


def _stub_postmortem(metadata, summary, slug, date_str):
    proj_name = metadata.get('project_name') or summary.get('name') or slug
    proj_type = metadata.get('project_type') or 'unknown'
    final_v = summary.get('version') or '?'
    data_date = metadata.get('proposal_data_date') or summary.get('data_date') or ''
    return f'''---
project: "{proj_name}"
project_type: "{proj_type}"
proposal_data_date: "{data_date}"
draft_version: 1
final_version: {final_v}
iteration_count: ?
scheduler: "camron"
postmortem_date: "{date_str}"
---

## What I drafted (v1)
<!-- High-level summary of v1: activity count, total duration, anchor dates,
top-level WBS structure. -->

## What shipped (v{final_v})
<!-- Deltas vs v1: total duration change, anchor movements, new/removed activities,
structural shifts. -->

## What I missed
<!-- Per substantive correction:
  - **Change** -- what the scheduler edited (concrete: from X to Y)
  - **Signal I should have caught** -- bid doc, similar XER, Westland convention
  - **Hypothesis I am extracting** -- first-person, scoped, NOT a rule
-->

## Reviewer feedback received
<!-- Summarize external reviewer JSONs ingested this cycle. Cite reviewer
+ date for each material insight kept. -->

## Themes within this project
<!-- Patterns recurring across multiple corrections in this single cycle. -->

## Hypotheses for next time
<!-- Numbered, first-person, scoped to project type. NOT rules. -->
'''


def main():
    ap = argparse.ArgumentParser(
        description='Assemble a self-contained postmortem folder at final approval.')
    ap.add_argument('project', help='Path to the project folder')
    ap.add_argument('--slug', required=True,
                    help='Project slug for the folder name (e.g. murray-apex-center)')
    ap.add_argument('--date', default=None,
                    help='Postmortem date (default: today YYYY-MM-DD)')
    ap.add_argument('--cycle-start', default=None,
                    help='Earliest date to consider when extracting durations '
                         '(default: include all)')
    ap.add_argument('--skip-durations', action='store_true',
                    help='Do not snapshot durations.json into the folder')
    ap.add_argument('--skip-reviewer-feedback', action='store_true',
                    help='Do not copy reviewer-feedback/ into the folder')
    ap.add_argument('--force', action='store_true',
                    help='Overwrite existing folder if present')
    ap.add_argument('--print-stub', action='store_true',
                    help='Print a postmortem.md skeleton to stdout (do not create folder)')
    args = ap.parse_args()

    project = Path(args.project).resolve()
    if not project.is_dir():
        return _err(f'project folder not found: {project}')
    layout = _layout.detect_layout(project)
    date_str = args.date or datetime.now().strftime('%Y-%m-%d')
    metadata = _read_metadata(project, layout)
    summary = _activities_summary(project, layout)

    if args.print_stub:
        print(_stub_postmortem(metadata, summary, args.slug, date_str))
        return 0

    pm_root = _layout.postmortems_dir(project, layout)
    pm_dir = pm_root / f'{date_str}-{args.slug}'
    if pm_dir.exists():
        if not args.force:
            return _err(f'postmortem folder already exists: '
                        f'{pm_dir.relative_to(project)} (use --force to overwrite)')
        shutil.rmtree(pm_dir)
    pm_dir.mkdir(parents=True, exist_ok=True)

    # 1. project-metadata.json snapshot
    if metadata:
        (pm_dir / 'project-metadata.json').write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')

    # 2. durations-captured.json (this cycle only)
    if not args.skip_durations:
        durations = _read_durations(project, layout)
        cycle_entries = _filter_durations_for_cycle(durations, args.cycle_start)
        if cycle_entries:
            (pm_dir / 'durations-captured.json').write_text(
                json.dumps({'entries': cycle_entries}, ensure_ascii=False, indent=2),
                encoding='utf-8')

    # 3. reviewer-feedback/ copies
    rf_count = 0
    if not args.skip_reviewer_feedback:
        rf_src = _layout.reviewer_feedback_dir(project, layout)
        if rf_src.is_dir():
            rf_dst = pm_dir / 'reviewer-feedback'
            rf_dst.mkdir(exist_ok=True)
            for f in rf_src.glob('*.json'):
                shutil.copy2(f, rf_dst / f.name)
                rf_count += 1

    # 4. postmortem.md stub if not already supplied
    pm_md = pm_dir / 'postmortem.md'
    if not pm_md.exists():
        pm_md.write_text(_stub_postmortem(metadata, summary, args.slug, date_str),
                         encoding='utf-8')

    rel = pm_dir.relative_to(project)
    print(f'Postmortem folder ready: {rel}')
    print(f'  postmortem.md            (stub written; agent should fill in)')
    if metadata:
        print(f'  project-metadata.json    snapshot of {len(metadata)} field(s)')
    if not args.skip_durations:
        n = len(_filter_durations_for_cycle(_read_durations(project, layout),
                                            args.cycle_start))
        if n:
            print(f'  durations-captured.json  {n} entr{"y" if n == 1 else "ies"} from this cycle')
    if not args.skip_reviewer_feedback:
        if rf_count:
            print(f'  reviewer-feedback/       {rf_count} file(s) copied')
    return 0


if __name__ == '__main__':
    sys.exit(main())
