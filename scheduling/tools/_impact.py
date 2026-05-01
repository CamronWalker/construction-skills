"""_impact.py -- compute what an iteration's CPM run actually changed
relative to the prior version. Drives the "Impact" block in
proposal_iterate.py output.

We diff the parsed-XER task state (which carries the prior CPM's stamped
early_*/late_*/total_float fields) against the post-CPM `results` list.
Both sides are in memory after `proposal_iterate.py` parses the current
XER and runs schedule_forward_backward, so this module is pure compute --
no extra I/O, no second CPM pass.

The impact dict's shape is stable so renderers can pick out only the
sections that have meaningful changes (the "don't print unchanged" rule
in `_render_impact`).
"""

from datetime import datetime


def _parse(s):
    if not s:
        return None
    s = (s or '').strip()
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _date_only(s):
    return (s or '').strip()[:10]


def snapshot_old(tasks):
    """Capture the pre-CPM state so we can diff after CPM runs.

    Must be called BEFORE _apply_duration_changes or schedule_forward_backward
    mutates the task dicts in place. Returns a small dict keyed by task_id
    with the fields we need for the impact summary.
    """
    snap = {}
    for t in tasks:
        tid = t.get('task_id', '')
        if not tid:
            continue
        snap[tid] = {
            'task_code': t.get('task_code', ''),
            'task_name': t.get('task_name', ''),
            'task_type': t.get('task_type', ''),
            'early_start_date': t.get('early_start_date', ''),
            'early_end_date': t.get('early_end_date', ''),
            'total_float_hr_cnt': t.get('total_float_hr_cnt', ''),
            'target_drtn_hr_cnt': t.get('target_drtn_hr_cnt', ''),
        }
    return snap


def _anchor_drift_days(task_ef_or_es, anchor_date):
    a = _parse(anchor_date)
    c = _parse(task_ef_or_es)
    if not a or not c:
        return None
    return (c.replace(hour=0, minute=0, second=0, microsecond=0)
            - a.replace(hour=0, minute=0, second=0, microsecond=0)).days


def anchor_drift_table(tasks_or_snap_by_code, anchors):
    """For each anchor, return drift in days (computed_date - anchor_date).

    `tasks_or_snap_by_code` is a dict keyed by task_code with at minimum
    `early_start_date` and `early_end_date` fields.
    """
    out = {}
    for a in anchors:
        code = a.get('task_code', '')
        if not code or code not in tasks_or_snap_by_code:
            continue
        rec = tasks_or_snap_by_code[code]
        kind = (a.get('anchor_kind') or 'finish').lower()
        date_field = 'early_start_date' if kind == 'start' else 'early_end_date'
        drift = _anchor_drift_days(rec.get(date_field, ''), a.get('anchor_date', ''))
        if drift is None:
            continue
        out[code] = {
            'kind_label': a.get('kind_label', ''),
            'task_code': code,
            'anchor_date': a.get('anchor_date', ''),
            'computed_date': _date_only(rec.get(date_field, '')),
            'drift_days': drift,
        }
    return out


def _by_code(records_or_results):
    return {r.get('task_code', ''): r for r in records_or_results
            if r.get('task_code')}


def task_shifts(old_snap, results, top_n=5):
    """Return tasks whose early_end_date moved most, sorted by |delta| desc.

    Filters out:
      - tasks with no prior date (first-iteration case)
      - tasks with zero shift (the "don't print unchanged" rule)
      - WBS / LOE rows
    """
    shifts = []
    for r in results:
        tid = r.get('task_id', '')
        if r.get('task_type', '') in ('TT_WBS', 'TT_LOE'):
            continue
        if tid not in old_snap:
            continue
        old = old_snap[tid]
        old_ef = _parse(old.get('early_end_date', ''))
        new_ef = _parse(r.get('early_end_date', ''))
        if not old_ef or not new_ef:
            continue
        delta = (new_ef - old_ef).days
        if delta == 0:
            continue
        shifts.append({
            'task_id': tid,
            'task_code': r.get('task_code', '') or old.get('task_code', ''),
            'task_name': r.get('task_name', '') or old.get('task_name', ''),
            'old_ef': _date_only(old.get('early_end_date', '')),
            'new_ef': _date_only(r.get('early_end_date', '')),
            'delta_days': delta,
        })
    shifts.sort(key=lambda s: -abs(s['delta_days']))
    return shifts[:top_n]


def _safe_float(v, d=0.0):
    try:
        return float(v) if v else d
    except (TypeError, ValueError):
        return d


def critical_path_summary(tasks_or_results):
    """Return (length, end_task_code, end_task_name) of the critical-path
    chain (TF<=0 tasks). Best-effort when some dates are missing.
    """
    crit = []
    for t in tasks_or_results:
        if t.get('task_type', '') in ('TT_WBS', 'TT_LOE'):
            continue
        tf_hr = _safe_float(t.get('total_float_hr_cnt', 999), 999)
        if tf_hr <= 0.5:
            ef = _parse(t.get('early_end_date', ''))
            if ef:
                crit.append((ef, t))
    if not crit:
        return (0, '', '')
    crit.sort(key=lambda x: x[0])
    end = crit[-1][1]
    return (
        len(crit),
        end.get('task_code', '') or '',
        end.get('task_name', '') or '',
    )


def near_critical_count(tasks_or_results):
    """Tasks with 0 < TF < 5d (40 work-hours)."""
    n = 0
    for t in tasks_or_results:
        if t.get('task_type', '') in ('TT_WBS', 'TT_LOE'):
            continue
        tf_hr = _safe_float(t.get('total_float_hr_cnt', 0))
        if 0 < tf_hr < 40:
            n += 1
    return n


def compute_impact(old_snap, results, anchors):
    """Top-level helper called by proposal_iterate after CPM finishes.

    Returns a dict with the data the renderer needs. Old-state fields are
    None when the prior XER had no CPM dates baked in (first iteration).
    """
    old_by_code = {v.get('task_code', ''): v for v in old_snap.values()
                   if v.get('task_code')}
    new_by_code = _by_code(results)

    has_old_dates = any(v.get('early_end_date') for v in old_snap.values())

    old_drift = anchor_drift_table(old_by_code, anchors) if has_old_dates else {}
    new_drift = anchor_drift_table(new_by_code, anchors)
    anchor_changes = []
    for code, new_d in new_drift.items():
        old_d = old_drift.get(code)
        if old_d and old_d['drift_days'] == new_d['drift_days']:
            continue  # unchanged -- omit
        anchor_changes.append({
            **new_d,
            'old_drift_days': old_d['drift_days'] if old_d else None,
        })

    sc_old = sc_new = ''
    sc_delta = None
    for a in anchors:
        if (a.get('kind_label') or '').lower().startswith('substantial'):
            code = a.get('task_code', '')
            if code in new_by_code:
                sc_new = _date_only(new_by_code[code].get('early_end_date', ''))
            if code in old_by_code and has_old_dates:
                sc_old = _date_only(old_by_code[code].get('early_end_date', ''))
            break
    if sc_old and sc_new:
        d_old = _parse(sc_old)
        d_new = _parse(sc_new)
        if d_old and d_new:
            sc_delta = (d_new - d_old).days

    shifts = task_shifts(old_snap, results, top_n=5) if has_old_dates else []

    new_cp_len, new_cp_end_code, new_cp_end_name = critical_path_summary(results)
    if has_old_dates:
        old_cp_len, old_cp_end_code, _ = critical_path_summary(list(old_snap.values()))
    else:
        old_cp_len, old_cp_end_code = None, None

    return {
        'has_old_dates': has_old_dates,
        'sc_old': sc_old,
        'sc_new': sc_new,
        'sc_delta_days': sc_delta,
        'anchor_changes': anchor_changes,
        'task_shifts': shifts,
        'critical_path': {
            'length': new_cp_len,
            'end_code': new_cp_end_code,
            'end_name': new_cp_end_name,
            'length_old': old_cp_len,
            'end_code_old': old_cp_end_code,
            'changed': old_cp_end_code is not None and old_cp_end_code != new_cp_end_code,
        },
        'near_critical': {
            'count_new': near_critical_count(results),
            'count_old': near_critical_count(list(old_snap.values())) if has_old_dates else None,
        },
    }


def _grade_delta_label(prior_score, new_score):
    if prior_score is None:
        return ''
    delta = new_score - prior_score
    sign = '+' if delta >= 0 else ''
    return f'({sign}{delta:.1f})'


def render_impact(impact, prior_score_data, new_score_data):
    """Render the Impact + Score blocks. Skips sections with no signal.

    Returns a list of strings (one per stdout line) for the caller to
    print after the file-write summary.
    """
    lines = []
    lines.append('Impact:')

    if impact.get('sc_delta_days') is not None and impact['sc_delta_days'] != 0:
        sign = '+' if impact['sc_delta_days'] > 0 else ''
        lines.append(f'  SC: {impact["sc_old"]} -> {impact["sc_new"]} '
                     f'({sign}{impact["sc_delta_days"]}d)')
    elif impact.get('sc_new'):
        lines.append(f'  SC: {impact["sc_new"]} (unchanged)')

    cp = impact.get('critical_path', {})
    if cp.get('changed'):
        lines.append(f'  Critical path: {cp["length"]} activities, ends '
                     f'{cp["end_code"]} {cp["end_name"][:40]} '
                     f'(was {cp["end_code_old"]})')
    elif cp.get('end_code'):
        delta_marker = ''
        if cp.get('length_old') is not None and cp['length'] != cp['length_old']:
            d = cp['length'] - cp['length_old']
            sign = '+' if d > 0 else ''
            delta_marker = f' ({sign}{d})'
        lines.append(f'  Critical path: {cp["length"]} activities{delta_marker}, '
                     f'ends {cp["end_code"]} {cp["end_name"][:40]} (unchanged end)')

    if impact.get('anchor_changes'):
        lines.append('  Anchor drift (changed only):')
        for ch in impact['anchor_changes']:
            label = ch.get('kind_label', '') or ch['task_code']
            new_d = ch['drift_days']
            old_d = ch.get('old_drift_days')
            new_label = f'{new_d:+d}d'
            if old_d is None:
                drift_str = f'(new) {new_label}'
            else:
                drift_str = f'{old_d:+d}d -> {new_label}'
            move = ''
            if old_d is not None and old_d != new_d:
                move_d = new_d - old_d
                move = f'  (pulled in {-move_d}d)' if move_d < 0 else f'  (pushed out {move_d}d)'
            lines.append(f'    {label[:25]:25s}  {ch["task_code"]:10s}  {drift_str}{move}')

    if impact.get('task_shifts'):
        lines.append(f'  Tasks shifted (top {len(impact["task_shifts"])} by |EF delta|):')
        for s in impact['task_shifts']:
            sign = '+' if s['delta_days'] > 0 else ''
            lines.append(f'    {s["task_code"]:10s}  '
                         f'{(s["task_name"] or "")[:36]:36s}  '
                         f'EF {sign}{s["delta_days"]}d')

    nc = impact.get('near_critical', {})
    if nc.get('count_new') is not None and nc.get('count_old') is not None:
        if nc['count_new'] != nc['count_old']:
            d = nc['count_new'] - nc['count_old']
            sign = '+' if d > 0 else ''
            lines.append(f'  Near-critical chains: {nc["count_new"]} ({sign}{d})')

    # Score block
    if new_score_data:
        prior_score = (prior_score_data or {}).get('score') if prior_score_data else None
        prior_grade = (prior_score_data or {}).get('grade') if prior_score_data else None
        delta_label = _grade_delta_label(prior_score, new_score_data['score'])
        if prior_score is not None:
            lines.append('')
            lines.append(f'Score: {prior_grade} {prior_score} -> '
                         f'{new_score_data["grade"]} {new_score_data["score"]} {delta_label}')
        else:
            lines.append('')
            lines.append(f'Score: {new_score_data["grade"]} {new_score_data["score"]} '
                         f'(no prior sidecar to compare)')
        deductions = new_score_data.get('deductions') or {}
        if deductions:
            ranked = sorted(deductions.items(), key=lambda kv: -kv[1])[:3]
            if ranked:
                lines.append('  Top deductions:')
                for k, v in ranked:
                    lines.append(f'    {k:18s}  -{v:.1f}')
                lines.append('  Run `propsched score "<project>"` for full breakdown + activity lists.')

    return lines
