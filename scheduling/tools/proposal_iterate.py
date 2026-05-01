"""proposal_iterate.py -- single entry point for the proposal-schedule
iteration loop. Collapses the paste-back -> what-if -> anchor-check ->
write cycle into one CLI so the agent never reads cpm_engine.py, the full
activities JSON, or the raw XER.

Usage (typical agent flow):

    # 1. Camron pastes the Copy-for-Claude payload from the Gantt HTML.
    python proposal_iterate.py "<project>" --paste paste.json

    # 2. If the script reports anchor slips, the agent forms an absorption
    # plan with Camron, saves it to absorption.json, then re-runs:
    python proposal_iterate.py "<project>" --paste paste.json --apply absorption.json

Exit codes:
    0  -- changes applied, new -v{N+1}.xer + JSON + HTML written
    1  -- error (missing files, unparseable JSON, etc.)
    2  -- anchor slips reported; nothing written; agent + scheduler must
          form an absorption plan and re-run with --apply
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from _xer_io import parse_xer, find_latest_xer, next_xer_path, write_xer_with_updates
from _cpm_loader import load_cpm, plugin_root


def _err(msg, code=1):
    print(f'ERROR: {msg}', file=sys.stderr)
    return code


def _load_paste(path, label):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f'{label} file not found: {p}')
    return json.loads(p.read_text(encoding='utf-8'))


def _collect_duration_changes(payload):
    """Return {match_key: new_days} where match_key is task_id or task_code.

    The paste-back uses `id` for XER task_id; some agents may emit
    `task_code` instead. We keep both lookups.
    """
    out_by_id = {}
    out_by_code = {}
    for a in (payload or {}).get('activities', []) or []:
        dc = a.get('duration_change')
        if not dc:
            continue
        new_days = dc.get('to_days')
        if new_days is None:
            continue
        try:
            new_days = float(new_days)
        except (TypeError, ValueError):
            continue
        tid = a.get('id') or a.get('task_id')
        code = a.get('task_code')
        if tid:
            out_by_id[str(tid)] = new_days
        if code:
            out_by_code[str(code)] = new_days
    return out_by_id, out_by_code


def _apply_duration_changes(tasks, by_id, by_code):
    """Mutate task rows in-place. Returns count of tasks changed."""
    changed = 0
    for t in tasks:
        tid = t.get('task_id', '')
        code = t.get('task_code', '')
        new_days = by_id.get(tid)
        if new_days is None and code:
            new_days = by_code.get(code)
        if new_days is None:
            continue
        new_hr = int(round(float(new_days) * 8))
        t['target_drtn_hr_cnt'] = str(new_hr)
        # Proposal schedules: every task is TK_NotStart so remaining == target.
        # If a task is in-progress somehow, leave remain alone.
        if t.get('status_code', 'TK_NotStart') == 'TK_NotStart':
            t['remain_drtn_hr_cnt'] = str(new_hr)
        changed += 1
    return changed


def _pick_data_date(args, paste, project_rows):
    if args.data_date:
        return f'{args.data_date} 08:00'
    if paste and paste.get('data_date'):
        s = paste['data_date']
        if len(s) == 10:
            return f'{s} 08:00'
        return s
    if project_rows:
        d = project_rows[0].get('last_recalc_date') or project_rows[0].get('data_date', '')
        if d:
            return d
    return datetime.now().strftime('%Y-%m-%d 08:00')


def _slip_summary(slips, results, preds, cpm):
    """≤30-line stdout for the slips-reported case."""
    print(f'ANCHOR SLIPS: {len(slips)} -- nothing written.')
    for s in slips:
        sd = s['slip_days']
        sign = '+' if sd > 0 else ''
        print(f"  {s['task_code']:10s}  {s['kind_label']:25s}  "
              f"anchor {s['anchor_date']} -> computed {s['computed_date']}  "
              f"({sign}{sd}d)")

    # For each slip, top-5 cut candidates from the suggester.
    for s in slips:
        if s['slip_days'] <= 0:
            continue  # only show absorption for late slips
        cands = cpm.suggest_anchor_absorption(results, preds, s, max_suggestions=5)
        print(f"\n  Top cut candidates for {s['task_code']} (need {s['slip_days']}d):")
        if not cands:
            print('    (no critical-path tasks with cut leverage; logic change required)')
            continue
        for c in cands:
            print(f"    {c['task_code']:10s}  "
                  f"{(c['task_name'] or '')[:30]:30s}  "
                  f"dur {c['current_duration_days']:>5}d  "
                  f"TF {c['total_float_days']:>4}d  "
                  f"max cut {c['suggested_max_cut_days']}d")
    print('\nForm an absorption plan with the scheduler, save it as '
          'absorption.json, re-run with --apply.')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--project', required=True,
                    help='Path to the proposal-schedule project folder')
    ap.add_argument('--paste', required=True,
                    help='Path to the Copy-for-Claude paste-back JSON')
    ap.add_argument('--apply', default=None,
                    help='Path to absorption.json (additional duration cuts)')
    ap.add_argument('--data-date', default=None,
                    help='YYYY-MM-DD override for the CPM data date')
    ap.add_argument('--dry-run', action='store_true',
                    help='Run everything but write no files')
    ap.add_argument('--verbose', action='store_true',
                    help='Write debug detail to <project>/Proposal Schedule/.iterate-debug.log')
    args = ap.parse_args()

    project = Path(args.project)
    if not project.is_dir():
        return _err(f'not a directory: {project}')

    proposal_dir = project / 'Proposal Schedule'
    if not proposal_dir.is_dir():
        return _err(f'expected "{proposal_dir}" under project folder')

    try:
        paste = _load_paste(args.paste, 'paste')
        apply_payload = _load_paste(args.apply, 'apply') if args.apply else None
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return _err(str(e))

    latest = find_latest_xer(project)
    if not latest:
        return _err(f'no -v{{N}}.xer found in {proposal_dir}')
    xer_path, version = latest
    new_xer_path = next_xer_path(xer_path, version)

    anchors_path = proposal_dir / 'proposal-anchors.json'
    if not anchors_path.exists():
        return _err(f'{anchors_path.name} not found. '
                    'Run anchors_from_constraints.py to bootstrap.')
    anchors_doc = json.loads(anchors_path.read_text(encoding='utf-8'))
    anchors = anchors_doc.get('anchors', [])

    tables, table_fields, original_text = parse_xer(xer_path)
    tasks = tables.get('TASK', [])
    preds = tables.get('TASKPRED', [])
    calendars = tables.get('CALENDAR', tables.get('CLNDR', []))
    project_rows = tables.get('PROJECT', [])
    schedoptions = tables.get('SCHEDOPTIONS', [])
    wbs_rows = tables.get('PROJWBS', [])

    project_name = (
        (paste or {}).get('project')
        or anchors_doc.get('project_name')
        or (project_rows[0].get('proj_short_name', '') if project_rows else '')
        or project.name
    )

    # Collect duration changes from both paste and apply payloads
    paste_by_id, paste_by_code = _collect_duration_changes(paste)
    if apply_payload:
        apply_by_id, apply_by_code = _collect_duration_changes(apply_payload)
        # apply_* override paste_* on conflict (later instructions win)
        paste_by_id.update(apply_by_id)
        paste_by_code.update(apply_by_code)

    # Apply to in-memory task rows
    n_changed = _apply_duration_changes(tasks, paste_by_id, paste_by_code)

    data_date = _pick_data_date(args, paste, project_rows)

    cpm = load_cpm()
    results, metadata = cpm.schedule_forward_backward(
        tasks, preds, calendars, data_date, schedoptions, project_rows)

    slips = cpm.check_anchor_dates(results, anchors)
    # Distinguish "drifted but earlier" (negative slip = no problem) from
    # "drifted late" (positive slip = anchor pushed). Only late slips block.
    late_slips = [s for s in slips if s['slip_days'] > 0]

    if late_slips:
        _slip_summary(late_slips, results, preds, cpm)
        if args.verbose:
            log = proposal_dir / '.iterate-debug.log'
            log.write_text(json.dumps({'slips': slips, 'metadata': metadata},
                                       indent=2), encoding='utf-8')
        return 2

    # No late slips -- write the new XER + JSON + HTML.
    if args.dry_run:
        print('[dry-run] would write:')
        print(f'  XER:    {new_xer_path.name}')
        print(f'  JSON:   schedule-activities.json')
        print(f'  HTML:   schedule-review.html')
        print(f'  paste:  iterations/paste-{version + 1}.json')
        print(f'duration changes applied: {n_changed}')
        return 0

    # Build TASK row updates: duration changes + CPM-computed dates + float
    task_updates = {}
    for t in results:
        tid = t.get('task_id', '')
        if not tid:
            continue
        upd = {}
        for f in ('early_start_date', 'early_end_date', 'late_start_date',
                  'late_end_date', 'total_float_hr_cnt', 'free_float_hr_cnt',
                  'driving_path_flag'):
            if f in t:
                upd[f] = str(t[f])
        # Duration fields if changed
        if tid in paste_by_id or t.get('task_code', '') in paste_by_code:
            upd['target_drtn_hr_cnt'] = str(t.get('target_drtn_hr_cnt', ''))
            if 'remain_drtn_hr_cnt' in t:
                upd['remain_drtn_hr_cnt'] = str(t.get('remain_drtn_hr_cnt', ''))
        if upd:
            task_updates[tid] = upd

    write_xer_with_updates(
        original_text, table_fields,
        {'TASK': ('task_id', task_updates)},
        new_xer_path,
    )

    activities_json_path = proposal_dir / 'schedule-activities.json'
    activities_data = cpm.build_activities_json(
        results, metadata, preds,
        project_name=project_name,
        data_date=data_date,
        wbs_rows=wbs_rows,
        default_view=(paste or {}).get('default_view'),
    )
    activities_json_path.write_text(
        json.dumps(activities_data, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    # Render HTML via build_gantt_html.py (ASCII-only printout from this script)
    html_path = proposal_dir / 'schedule-review.html'
    builder = plugin_root() / 'tools' / 'build_gantt_html.py'
    proc = subprocess.run(
        ['python', str(builder), str(activities_json_path),
         '-o', str(html_path), '--project', project_name],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        if args.verbose:
            (proposal_dir / '.iterate-debug.log').write_text(
                proc.stdout + '\n---STDERR---\n' + proc.stderr,
                encoding='utf-8',
            )
        return _err(f'build_gantt_html.py failed: {proc.stderr.strip()[:200]}')

    # Archive the paste-back so the postmortem can reconstruct iteration history
    iter_dir = proposal_dir / 'iterations'
    iter_dir.mkdir(exist_ok=True)
    archive_path = iter_dir / f'paste-{version + 1}.json'
    shutil.copyfile(args.paste, archive_path)

    sc_date = (metadata.get('sc_milestone_date', '') or '')[:10]
    print(f'Wrote XER:   {new_xer_path.name}')
    print(f'Wrote JSON:  schedule-activities.json')
    print(f'Wrote HTML:  schedule-review.html')
    print(f'SC date:     {sc_date}')
    print(f'Anchor check passed ({len(anchors)} anchors, {n_changed} duration changes applied)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
