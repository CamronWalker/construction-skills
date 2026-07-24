"""proposal_iterate.py -- single entry point for the proposal-schedule
iteration loop. Collapses the paste-back -> what-if -> anchor-check ->
write cycle into one CLI so the agent never reads cpm_engine.py, the full
activities JSON, or the raw XER.

Usage (typical agent flow):

    # 1. Camron pastes the Copy-for-Claude payload from the Gantt HTML.
    python proposal_iterate.py --project "<project>" --paste paste.json

    # 2. If the script reports anchor slips, the agent forms an absorption
    # plan with Camron, saves it to absorption.json, then re-runs:
    python proposal_iterate.py --project "<project>" --paste paste.json --apply absorption.json

Folder layout (v4.0.0+, "new" layout):
    <project>/
        <Project Name>.xer                <- current XER (no -vN suffix)
        schedule-activities.json
        proposal-anchors.json
        Old Iterations/
            <Project Name> -v1.xer ... -v{N-1}.xer
            paste-*.json
            scores/v{N}.json
            .cpm-cache/

Legacy layout (Proposal Schedule/) is auto-detected and continues to work
with the original write-back semantics (-v{N+1}.xer in place).

Exit codes:
    0  -- changes applied, new XER + JSON written
    1  -- error
    2  -- anchor slips reported; nothing written
"""

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from _xer_io import parse_xer, next_xer_path, write_xer_with_updates
from _cpm_loader import load_cpm, reference_dir
import _cpm_cache
import _layout
import _impact
import importlib.util


def _err(msg, code=1):
    print(f'ERROR: {msg}', file=sys.stderr)
    return code


_score_module = None


def _load_score_module():
    """Lazy-load score_schedule from schedule-toolbox/lib/."""
    global _score_module
    if _score_module is not None:
        return _score_module
    import os
    spec = importlib.util.spec_from_file_location(
        'score_schedule', os.path.join(reference_dir(), 'score_schedule.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    _score_module = mod
    return mod


def _score_results(results, preds, data_date):
    """Run compute_quality_score on the post-CPM state. Returns a small
    sidecar-shaped dict, or None on failure.

    `data_date` from proposal_iterate is a string ('YYYY-MM-DD HH:MM'); the
    scorer's internal comparisons require a datetime, so parse it here.
    """
    try:
        sc = _load_score_module()
        dd = data_date
        if isinstance(dd, str):
            for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d'):
                try:
                    dd = datetime.strptime(dd.strip(), fmt)
                    break
                except (ValueError, AttributeError):
                    continue
        score, grade, scored, info, deductions, scope, details = sc.compute_quality_score(
            results, preds, dd)
    except Exception as e:
        print(f'WARN: scoring skipped ({e})', file=sys.stderr)
        return None
    return {
        'score': round(score, 1),
        'grade': grade,
        'deductions': dict(deductions or {}),
        'data_date': data_date,
    }


def _read_score_sidecar(project, version, layout):
    if version is None:
        return None
    p = _layout.scores_dir(project, layout) / f'v{version}.json'
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return None


def _write_score_sidecar(project, version, score_data, layout, xer_name=''):
    out_dir = _layout.scores_dir(project, layout)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        'version': version,
        'xer': xer_name,
        'score': score_data['score'],
        'grade': score_data['grade'],
        'deductions': score_data.get('deductions', {}),
        'data_date': score_data.get('data_date'),
    }
    (out_dir / f'v{version}.json').write_text(
        json.dumps(payload, indent=2, default=str), encoding='utf-8')


def _load_paste(path, label):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f'{label} file not found: {p}')
    return json.loads(p.read_text(encoding='utf-8'))


def _collect_duration_changes(payload):
    """Return ({task_id: new_days}, {task_code: new_days})."""
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

    for s in slips:
        if s['slip_days'] <= 0:
            continue
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
                    help='Write debug detail to .iterate-debug.log')
    ap.add_argument('--no-cache', action='store_true',
                    help='Skip the CPM result cache; always re-run forward/backward')
    args = ap.parse_args()

    project = Path(args.project)
    if not project.is_dir():
        return _err(f'not a directory: {project}')

    layout = _layout.detect_layout(project)
    proposal_dir = _layout.proposal_dir(project, layout)
    iter_dir = _layout.iterations_dir(project, layout)
    if layout == _layout.LAYOUT_LEGACY and not proposal_dir.is_dir():
        return _err(f'legacy layout detected but {proposal_dir} not found')

    try:
        paste = _load_paste(args.paste, 'paste')
        apply_payload = _load_paste(args.apply, 'apply') if args.apply else None
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return _err(str(e))

    current_xer = _layout.find_current_xer(project, layout)
    if not current_xer:
        return _err(f'no current XER found in {proposal_dir}')

    anchors_path = _layout.anchors_path(project, layout)
    if not anchors_path.exists():
        return _err(f'{anchors_path.name} not found at {anchors_path.parent}. '
                    'Run propsched bootstrap-anchors to create it.')
    anchors_doc = json.loads(anchors_path.read_text(encoding='utf-8'))
    anchors = anchors_doc.get('anchors', [])

    tables, table_fields, original_text = parse_xer(current_xer)
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

    # Snapshot the pre-CPM task state for the impact diff. Must happen BEFORE
    # _apply_duration_changes or schedule_forward_backward mutates task dicts.
    old_snap = _impact.snapshot_old(tasks)

    paste_by_id, paste_by_code = _collect_duration_changes(paste)
    if apply_payload:
        apply_by_id, apply_by_code = _collect_duration_changes(apply_payload)
        paste_by_id.update(apply_by_id)
        paste_by_code.update(apply_by_code)

    n_changed = _apply_duration_changes(tasks, paste_by_id, paste_by_code)

    data_date = _pick_data_date(args, paste, project_rows)

    cpm = load_cpm()
    cache_key = _cpm_cache.hash_inputs(tasks, preds, data_date)
    # _cpm_cache builds `<dir>/.cpm-cache/<key>.json`; the layout helper's
    # cache_dir() returns `.../Old Iterations/.cpm-cache`, so we hand
    # _cpm_cache its parent (the iterations folder) to keep both modules
    # consistent.
    cache_root = _layout.iterations_dir(project, layout)
    cache_hit = False
    if not args.no_cache:
        cached = _cpm_cache.load(cache_root, cache_key)
        if cached is not None:
            results, metadata = cached
            cache_hit = True
    if not cache_hit:
        results, metadata = cpm.schedule_forward_backward(
            tasks, preds, calendars, data_date, schedoptions, project_rows)
        if not args.no_cache:
            _cpm_cache.store(cache_root, cache_key, results, metadata)

    slips = cpm.check_anchor_dates(results, anchors)
    late_slips = [s for s in slips if s['slip_days'] > 0]

    if late_slips:
        _slip_summary(late_slips, results, preds, cpm)
        if args.verbose:
            log = _layout.debug_log_path(project, layout)
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(json.dumps({'slips': slips, 'metadata': metadata},
                                       indent=2, default=str), encoding='utf-8')
        return 2

    # Compute target paths
    current_version = None  # legacy path sets this; new layout doesn't need it
    if layout == _layout.LAYOUT_NEW:
        # Archive the current root XER, then write new content to root
        archive_version = _layout.latest_archived_version(project, layout) + 1
        archived_path = _layout.archived_xer_path(
            project, archive_version, layout=layout)
        new_root_path = current_xer  # stays at root
        new_version = archive_version + 1
        paste_archive = iter_dir / f'paste-{new_version}.json'
        next_label = f'v{new_version} (current at root)'
    else:
        # Legacy: write -v{N+1}.xer in place
        archived_path = None
        # Derive next from filename
        from _xer_io import find_latest_xer
        latest = find_latest_xer(project)
        _, current_version = latest
        new_root_path = next_xer_path(current_xer, current_version)
        new_version = current_version + 1
        paste_archive = iter_dir / f'paste-{new_version}.json'
        next_label = new_root_path.name
        iter_dir.mkdir(parents=True, exist_ok=True)

    if args.dry_run:
        print('[dry-run] would write:')
        print(f'  XER:    {next_label}')
        print(f'  JSON:   {_layout.activities_json_path(project, layout).name}')
        print(f'  paste:  {paste_archive.relative_to(project)}')
        if layout == _layout.LAYOUT_NEW and archived_path:
            print(f'  archive: {archived_path.name}')
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
        if tid in paste_by_id or t.get('task_code', '') in paste_by_code:
            upd['target_drtn_hr_cnt'] = str(t.get('target_drtn_hr_cnt', ''))
            if 'remain_drtn_hr_cnt' in t:
                upd['remain_drtn_hr_cnt'] = str(t.get('remain_drtn_hr_cnt', ''))
        if upd:
            task_updates[tid] = upd

    if layout == _layout.LAYOUT_NEW:
        # Archive: copy current root XER to Old Iterations/<name> -v{N}.xer
        # (Westland immutability: we never mutate the existing XER bytes; the
        # archive is the original file as-is.)
        iter_dir.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(current_xer, archived_path)
        # Now write new content back to the root path (overwriting the
        # already-archived original).
        write_xer_with_updates(
            original_text, table_fields,
            {'TASK': ('task_id', task_updates)},
            new_root_path,
        )
    else:
        # Legacy: preserve original at -v{N}.xer, write updated -v{N+1}.xer
        write_xer_with_updates(
            original_text, table_fields,
            {'TASK': ('task_id', task_updates)},
            new_root_path,
        )

    activities_json = _layout.activities_json_path(project, layout)
    activities_data = cpm.build_activities_json(
        results, metadata, preds,
        project_name=project_name,
        data_date=data_date,
        wbs_rows=wbs_rows,
        default_view=(paste or {}).get('default_view'),
        version=new_version,
    )
    activities_json.write_text(
        json.dumps(activities_data, ensure_ascii=False, indent=2),
        encoding='utf-8',
    )

    # Compute impact + score the new state. (HTML rendering retired — the
    # review surface is now the online link; publish via generate_proposal_review_link.)
    impact = _impact.compute_impact(old_snap, results, anchors)
    score_data = _score_results(results, preds, data_date)

    # ===== Score sidecar handoff =====
    # new_version is computed above (new layout: archive_version + 1; legacy:
    # current_version + 1) so it can also flow into the activities JSON.
    prior_version = (new_version - 1) if new_version else None
    prior_score_data = _read_score_sidecar(project, prior_version, layout) if prior_version else None
    if score_data and new_version:
        _write_score_sidecar(project, new_version, score_data, layout, xer_name=new_root_path.name)

    # Archive paste-back
    iter_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.paste, paste_archive)

    # ===== Print summary =====
    print(f'Wrote XER:   {new_root_path.name}')
    if layout == _layout.LAYOUT_NEW and archived_path:
        print(f'Archived:    Old Iterations/{archived_path.name}')
    print(f'Wrote JSON.')
    print(f'Anchors check passed ({len(anchors)} anchors, {n_changed} duration changes applied).')
    print('')
    for line in _impact.render_impact(impact, prior_score_data, score_data):
        print(line)
    return 0


if __name__ == '__main__':
    sys.exit(main())
