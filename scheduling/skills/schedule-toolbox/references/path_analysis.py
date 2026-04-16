"""
Path Analysis — SC path coverage, delay impact analysis, per-activity path insight.

Pure function library. Pass parsed XER data in, get structured results out.

Usage:
    from path_analysis import analyze_sc_path_coverage, compute_delay_impacts, render_delay_html

    coverage = analyze_sc_path_coverage(tasks, preds)
    impacts = compute_delay_impacts(tasks, preds, calendars, data_date)
    render_delay_html(impacts, tasks_by_id, 'delay_report.html')
"""

from datetime import datetime, timedelta, date
from collections import defaultdict, deque
import os
import importlib.util

# Import from same directory
_dir = os.path.dirname(os.path.abspath(__file__))

_spec = importlib.util.spec_from_file_location('calendar_engine', os.path.join(_dir, 'calendar_engine.py'))
_cal_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cal_mod)

_spec2 = importlib.util.spec_from_file_location('cpm_engine', os.path.join(_dir, 'cpm_engine.py'))
_cpm_mod = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(_cpm_mod)

build_calendar_lookup = _cal_mod.build_calendar_lookup
work_hours_between = _cal_mod.work_hours_between
schedule_forward_backward = _cpm_mod.schedule_forward_backward
_parse_date = _cpm_mod._parse_date
_format_date = _cpm_mod._format_date
_safe_float = _cpm_mod._safe_float


# ---------------------------------------------------------------------------
# SC milestone finder (same logic as cpm_engine / score_schedule)
# ---------------------------------------------------------------------------

def _find_sc_milestone(tasks):
    """Find the Substantial Completion milestone."""
    exc = {'TT_WBS', 'TT_LOE'}
    for t in tasks:
        if t.get('task_type', '') in exc:
            continue
        name = t.get('task_name', '')
        if 'Substantial Completion' in name and 'Turnover to Owner' in name:
            if t.get('status_code', '') != 'TK_Complete':
                return t
    for t in tasks:
        if t.get('task_type', '') in exc:
            continue
        if t.get('task_name', '').strip() == 'Substantial Completion':
            if t.get('task_type', '') in ('TT_FinMile', 'TT_Mile'):
                if t.get('status_code', '') != 'TK_Complete':
                    return t
    for t in tasks:
        if t.get('task_type', '') in exc:
            continue
        if t.get('task_type', '') not in ('TT_FinMile', 'TT_Mile'):
            continue
        if 'Substantial Completion' in t.get('task_name', ''):
            if t.get('status_code', '') != 'TK_Complete':
                return t
    return None


# ---------------------------------------------------------------------------
# SC Path Coverage
# ---------------------------------------------------------------------------

def _walk_predecessors(sc_task_id, preds):
    """BFS backward from SC through all predecessor chains. Returns set of connected task_ids."""
    succ_to_preds = defaultdict(set)
    for p in preds:
        succ_to_preds[p.get('task_id', '')].add(p.get('pred_task_id', ''))

    visited = set()
    queue = deque([sc_task_id])
    while queue:
        tid = queue.popleft()
        if tid in visited:
            continue
        visited.add(tid)
        for pred_id in succ_to_preds.get(tid, set()):
            if pred_id not in visited:
                queue.append(pred_id)
    return visited


def _group_by_wbs(disconnected_tasks, wbs_lookup):
    """Group disconnected tasks by WBS area."""
    groups = defaultdict(list)
    for t in disconnected_tasks:
        wbs_id = t.get('wbs_id', '')
        wbs_name = wbs_lookup.get(wbs_id, 'Unknown WBS')
        groups[wbs_name].append({
            'task_id': t.get('task_id', ''),
            'task_code': t.get('task_code', '') or t.get('task_id', ''),
            'task_name': t.get('task_name', ''),
        })
    return dict(groups)


def analyze_sc_path_coverage(tasks, preds, wbs_rows=None):
    """
    Identify which activities trace to Substantial Completion and which don't.

    Args:
        tasks: List of task dicts from parsed XER
        preds: List of relationship dicts from parsed XER
        wbs_rows: Optional list of WBS row dicts for grouping

    Returns:
        {
            'sc_task_id': str or None,
            'sc_task_name': str or None,
            'sc_task_code': str or None,
            'connected_count': int,
            'connected_ids': set,
            'disconnected_count': int,
            'disconnected_tasks': [{task_id, task_code, task_name, wbs_name}, ...],
            'disconnected_by_wbs': {wbs_name: [{task_id, task_code, task_name}, ...]},
            'coverage_pct': float,
            'total_incomplete': int,
            'recommendations': [str, ...],
        }
    """
    exc_types = {'TT_WBS', 'TT_LOE'}
    incomplete = [t for t in tasks
                  if t.get('status_code', '') != 'TK_Complete'
                  and t.get('task_type', '') not in exc_types]

    sc_task = _find_sc_milestone(tasks)
    if not sc_task:
        return {
            'sc_task_id': None, 'sc_task_name': None, 'sc_task_code': None,
            'connected_count': 0, 'connected_ids': set(),
            'disconnected_count': len(incomplete),
            'disconnected_tasks': [],
            'disconnected_by_wbs': {},
            'coverage_pct': 0.0,
            'total_incomplete': len(incomplete),
            'recommendations': ['No Substantial Completion milestone found. Add one and connect all work paths to it.'],
        }

    sc_id = sc_task.get('task_id', '')
    connected_ids = _walk_predecessors(sc_id, preds)

    # Build WBS lookup
    wbs_lookup = {}
    if wbs_rows:
        for w in wbs_rows:
            wbs_lookup[w.get('wbs_id', '')] = w.get('wbs_name', '')

    inc_ids = {t.get('task_id', '') for t in incomplete}
    connected = inc_ids & connected_ids
    disconnected_tasks = [t for t in incomplete if t.get('task_id', '') not in connected_ids]

    disconnected_by_wbs = _group_by_wbs(disconnected_tasks, wbs_lookup)

    coverage_pct = round(len(connected) / max(len(inc_ids), 1) * 100, 1)

    # Generate recommendations
    recommendations = []
    for wbs_name, tasks_in_wbs in sorted(disconnected_by_wbs.items(),
                                          key=lambda x: -len(x[1])):
        count = len(tasks_in_wbs)
        codes = ', '.join(t['task_code'] for t in tasks_in_wbs[:5])
        if count > 5:
            codes += f' (and {count - 5} more)'
        recommendations.append(
            f"Add successor path to SC for {count} activities in {wbs_name}: {codes}"
        )

    disconnected_list = []
    for t in disconnected_tasks:
        wbs_id = t.get('wbs_id', '')
        disconnected_list.append({
            'task_id': t.get('task_id', ''),
            'task_code': t.get('task_code', '') or t.get('task_id', ''),
            'task_name': t.get('task_name', ''),
            'wbs_name': wbs_lookup.get(wbs_id, ''),
        })

    return {
        'sc_task_id': sc_id,
        'sc_task_name': sc_task.get('task_name', ''),
        'sc_task_code': sc_task.get('task_code', ''),
        'connected_count': len(connected),
        'connected_ids': connected,
        'disconnected_count': len(disconnected_tasks),
        'disconnected_tasks': disconnected_list,
        'disconnected_by_wbs': disconnected_by_wbs,
        'coverage_pct': coverage_pct,
        'total_incomplete': len(inc_ids),
        'recommendations': recommendations,
    }


# ---------------------------------------------------------------------------
# Driving Path Tracer
# ---------------------------------------------------------------------------

def trace_driving_path(task_id, tasks_by_id, succ_map, preds, sc_task_id=None):
    """
    From a task, follow the driving (least-float) successor chain to SC or project end.

    Returns ordered list of task_ids on the driving path (including start task).
    """
    path = [task_id]
    current = task_id
    visited = {task_id}
    target = sc_task_id

    # Build succ lookup from preds
    succ_lookup = defaultdict(list)
    for p in preds:
        pred_id = p.get('pred_task_id', '')
        succ_id = p.get('task_id', '')
        succ_lookup[pred_id].append((succ_id, p))

    while True:
        successors = succ_lookup.get(current, [])
        if not successors:
            break

        # If we've reached SC, stop
        if current == target:
            break

        # Pick the driving successor (least total float)
        best_succ = None
        best_float = float('inf')
        for succ_id, rel in successors:
            if succ_id in visited:
                continue
            succ_task = tasks_by_id.get(succ_id)
            if not succ_task:
                continue
            tf = _safe_float(succ_task.get('total_float_hr_cnt',
                              succ_task.get('_tf', 999)))
            if tf < best_float:
                best_float = tf
                best_succ = succ_id

        if best_succ is None:
            break

        visited.add(best_succ)
        path.append(best_succ)
        current = best_succ

    return path


# ---------------------------------------------------------------------------
# Delay Impact Analysis
# ---------------------------------------------------------------------------

def _auto_detect_impacts(tasks):
    """Find impact/delayed activities automatically."""
    impacts = []
    for t in tasks:
        if t.get('task_type', '') in ('TT_WBS', 'TT_LOE'):
            continue
        if t.get('status_code', '') == 'TK_Complete':
            continue
        name = t.get('task_name', '')
        # Tasks with "IMPACT" in name (Westland convention)
        if 'IMPACT' in name.upper():
            impacts.append(t)
    return impacts


def _calendar_days_between(d1, d2):
    """Calendar day difference (not work days)."""
    if d1 is None or d2 is None:
        return 0
    if isinstance(d1, str):
        d1 = _parse_date(d1)
    if isinstance(d2, str):
        d2 = _parse_date(d2)
    if d1 is None or d2 is None:
        return 0
    return (d2.date() - d1.date()).days if hasattr(d1, 'date') else (d2 - d1).days


def compute_delay_impacts(tasks, preds, calendars, data_date, impact_activities=None):
    """
    Float Path Delay Analysis — compute how delayed activities push SC.

    Args:
        tasks: List of task dicts from parsed XER
        preds: List of relationship dicts
        calendars: List of calendar dicts
        data_date: Data date string or datetime
        impact_activities: Optional list of task_ids to analyze.
                          If None, auto-detects IMPACT tasks.

    Returns:
        {
            'sc_task_id': str,
            'sc_task_name': str,
            'sc_task_code': str,
            'baseline_sc_date': str,
            'data_date': str,
            'impacts': [{
                'task_id', 'task_code', 'task_name',
                'data_date',
                'previous_sc_date', 'revised_sc_date',
                'variance_cal_days',
                'driving_path': [task_ids],
                'is_critical': bool,
                'total_float_days': float,
            }]
        }
    """
    # Run CPM
    results, meta = schedule_forward_backward(tasks, preds, calendars, data_date)
    tasks_by_id = {t.get('task_id', ''): t for t in results}

    sc_id = meta.get('sc_milestone_id')
    sc_date = meta.get('sc_milestone_date', '')

    # Build succ map for path tracing
    succ_map = defaultdict(list)
    for p in preds:
        succ_map[p.get('pred_task_id', '')].append((p.get('task_id', ''), p))

    # Determine which activities to analyze
    if impact_activities:
        impact_tasks = [tasks_by_id[tid] for tid in impact_activities if tid in tasks_by_id]
    else:
        impact_tasks = _auto_detect_impacts(results)

    impacts = []
    for t in impact_tasks:
        tid = t.get('task_id', '')
        tf_hrs = _safe_float(t.get('total_float_hr_cnt', 0))

        # Trace driving path to SC
        path = trace_driving_path(tid, tasks_by_id, succ_map, preds, sc_id)

        # The variance: this activity's impact on SC
        # Using total float as a proxy — negative float = pushing SC
        variance_days = _calendar_days_between(
            t.get('early_start_date', ''),
            t.get('late_start_date', '')
        ) if t.get('early_start_date') and t.get('late_start_date') else 0

        impacts.append({
            'task_id': tid,
            'task_code': t.get('task_code', '') or tid,
            'task_name': t.get('task_name', ''),
            'data_date': str(data_date)[:10] if data_date else '',
            'previous_sc_date': '',  # Requires baseline comparison
            'revised_sc_date': sc_date[:10] if sc_date else '',
            'variance_cal_days': round(tf_hrs / 8, 1) * -1 if tf_hrs < 0 else 0,
            'driving_path': path,
            'driving_path_names': [
                f"{tasks_by_id.get(pid, {}).get('task_code', pid)}: "
                f"{tasks_by_id.get(pid, {}).get('task_name', '')}"
                for pid in path
            ],
            'is_critical': tf_hrs <= 0,
            'total_float_days': round(tf_hrs / 8, 1),
        })

    return {
        'sc_task_id': sc_id,
        'sc_task_name': meta.get('sc_milestone_name', ''),
        'sc_task_code': meta.get('sc_milestone_code', ''),
        'baseline_sc_date': sc_date,
        'data_date': _format_date(data_date) if isinstance(data_date, datetime) else str(data_date),
        'impacts': impacts,
    }


# ---------------------------------------------------------------------------
# Per-Activity Path Insight
# ---------------------------------------------------------------------------

def analyze_activity_paths(tasks, preds, calendars, data_date):
    """
    For every activity, compute driving path to SC and path metrics.

    Returns:
        {
            'sc_task_id': str,
            'sc_task_name': str,
            'sc_date': str,
            'activities': [{
                'task_id', 'task_code', 'task_name',
                'total_float_days': float,
                'free_float_days': float,
                'is_critical': bool,
                'connected_to_sc': bool,
                'driving_path': [task_ids],
                'path_length': int,
            }],
            'critical_count': int,
            'near_critical_count': int,
        }
    """
    results, meta = schedule_forward_backward(tasks, preds, calendars, data_date)
    tasks_by_id = {t.get('task_id', ''): t for t in results}

    sc_id = meta.get('sc_milestone_id')
    connected_ids = _walk_predecessors(sc_id, preds) if sc_id else set()

    succ_map = defaultdict(list)
    for p in preds:
        succ_map[p.get('pred_task_id', '')].append((p.get('task_id', ''), p))

    skip_types = {'TT_WBS', 'TT_LOE'}
    activities = []
    critical_count = 0
    near_critical_count = 0

    for t in results:
        if t.get('task_type', '') in skip_types:
            continue
        if t.get('status_code', '') == 'TK_Complete':
            continue
        if not t.get('early_start_date'):
            continue

        tid = t.get('task_id', '')
        tf_hrs = _safe_float(t.get('total_float_hr_cnt', 0))
        ff_hrs = _safe_float(t.get('free_float_hr_cnt', 0))
        tf_days = round(tf_hrs / 8, 1)

        is_crit = tf_hrs <= 0
        if is_crit:
            critical_count += 1
        elif tf_hrs <= 80:
            near_critical_count += 1

        path = trace_driving_path(tid, tasks_by_id, succ_map, preds, sc_id)

        activities.append({
            'task_id': tid,
            'task_code': t.get('task_code', '') or tid,
            'task_name': t.get('task_name', ''),
            'total_float_days': tf_days,
            'free_float_days': round(ff_hrs / 8, 1),
            'is_critical': is_crit,
            'connected_to_sc': tid in connected_ids,
            'driving_path': path,
            'path_length': len(path),
        })

    # Sort by total float (critical first)
    activities.sort(key=lambda a: a['total_float_days'])

    return {
        'sc_task_id': sc_id,
        'sc_task_name': meta.get('sc_milestone_name', ''),
        'sc_date': meta.get('sc_milestone_date', ''),
        'activities': activities,
        'critical_count': critical_count,
        'near_critical_count': near_critical_count,
        'total_activities': len(activities),
    }


# ---------------------------------------------------------------------------
# HTML Reports
# ---------------------------------------------------------------------------

_WESTLAND_CSS = """
body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }
.header { background: #1a3a4a; color: white; padding: 24px 32px; }
.header h1 { margin: 0 0 8px 0; font-size: 22px; font-weight: 600; }
.header .tracking { color: #8cc; font-size: 14px; margin-top: 4px; }
.header .meta { color: #acd; font-size: 13px; margin-top: 2px; }
.container { background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.section { padding: 20px 32px; }
.section h2 { color: #1a3a4a; font-size: 18px; margin: 0 0 16px 0; border-bottom: 2px solid #1a3a4a; padding-bottom: 8px; }
.big-number { font-size: 48px; font-weight: 700; text-align: center; padding: 20px; }
.big-number.good { color: #27ae60; }
.big-number.warn { color: #e67e22; }
.big-number.bad { color: #c0392b; }
.big-number .label { font-size: 14px; color: #666; font-weight: 400; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { background: #2c3e50; color: white; padding: 8px 10px; text-align: left; }
td { padding: 6px 10px; border-bottom: 1px solid #eee; }
tr:hover { background: #f0f7ff; }
.neg { color: #c0392b; font-weight: 600; }
.pos { color: #27ae60; font-weight: 600; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: 600; }
.tag-crit { background: #c0392b; color: white; }
.tag-warn { background: #e67e22; color: white; }
.tag-ok { background: #27ae60; color: white; }
.tag-disc { background: #95a5a6; color: white; }
details { margin: 4px 0; }
summary { cursor: pointer; color: #2980b9; font-size: 12px; }
.path-list { font-size: 12px; color: #555; padding: 4px 0 4px 16px; }
.summary-grid { display: flex; gap: 24px; padding: 16px 32px; background: white; border-bottom: 1px solid #ddd; flex-wrap: wrap; }
.stat-box { text-align: center; padding: 12px 24px; }
.stat-box .num { font-size: 28px; font-weight: 700; }
.stat-box .label { font-size: 12px; color: #666; text-transform: uppercase; }
"""


def render_coverage_html(coverage_data, output_path):
    """Write SC path coverage HTML report."""
    cd = coverage_data
    pct = cd.get('coverage_pct', 0)

    if pct >= 90:
        pct_class = 'good'
    elif pct >= 70:
        pct_class = 'warn'
    else:
        pct_class = 'bad'

    if cd.get('sc_task_name'):
        tracking = f"Tracking to: {cd['sc_task_name']} [{cd.get('sc_task_code', '')}]"
    else:
        tracking = "No SC milestone found"

    # Disconnected tasks table
    rows = []
    for t in cd.get('disconnected_tasks', []):
        rows.append(f"<tr><td>{t['task_code']}</td><td>{t['task_name']}</td><td>{t.get('wbs_name','')}</td></tr>")

    # Recommendations
    recs = ''.join(f"<li>{r}</li>" for r in cd.get('recommendations', []))

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>SC Path Coverage Report</title>
<style>{_WESTLAND_CSS}</style></head><body>
<div class="container">
<div class="header">
  <h1>SC Path Coverage Analysis</h1>
  <div class="tracking">{tracking}</div>
  <div class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
</div>
<div class="summary-grid">
  <div class="stat-box"><div class="num {pct_class}">{pct}%</div><div class="label">SC Coverage</div></div>
  <div class="stat-box"><div class="num">{cd.get('connected_count',0)}</div><div class="label">Connected</div></div>
  <div class="stat-box"><div class="num" style="color:#c0392b">{cd.get('disconnected_count',0)}</div><div class="label">Disconnected</div></div>
  <div class="stat-box"><div class="num">{cd.get('total_incomplete',0)}</div><div class="label">Total Incomplete</div></div>
</div>
{'<div class="section"><h2>Recommendations</h2><ul>' + recs + '</ul></div>' if recs else ''}
<div class="section">
<h2>Disconnected Activities ({cd.get('disconnected_count',0)})</h2>
<table><thead><tr><th>Activity ID</th><th>Name</th><th>WBS Area</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</div>
</div></body></html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return output_path


def render_delay_html(impact_data, output_path):
    """Write delay impact HTML report matching the screenshot format."""
    d = impact_data

    if d.get('sc_task_name'):
        tracking = f"Tracking to: {d['sc_task_name']} [{d.get('sc_task_code', '')}]"
    else:
        tracking = "No SC milestone found"

    rows = []
    for imp in d.get('impacts', []):
        variance = imp.get('variance_cal_days', 0)
        if variance < 0:
            var_class = 'neg'
        elif variance > 0:
            var_class = 'pos'
        else:
            var_class = ''

        crit_tag = '<span class="tag tag-crit">CRITICAL</span>' if imp.get('is_critical') else ''

        # Expandable driving path
        path_items = ''.join(f"<div>→ {name}</div>" for name in imp.get('driving_path_names', []))
        path_detail = f'<details><summary>View driving path ({len(imp.get("driving_path",[]))} activities)</summary><div class="path-list">{path_items}</div></details>' if path_items else ''

        rows.append(
            f"<tr>"
            f"<td><strong>{imp['task_code']}</strong></td>"
            f"<td>{imp['task_name']}</td>"
            f"<td>{imp.get('data_date','')}</td>"
            f"<td>{imp.get('previous_sc_date','—')}</td>"
            f"<td>{imp.get('revised_sc_date','')}</td>"
            f"<td class='{var_class}'>{variance}</td>"
            f"<td>{imp.get('total_float_days', '')}</td>"
            f"<td>{crit_tag}</td>"
            f"</tr>"
            f"<tr><td colspan='8' style='padding:0 10px'>{path_detail}</td></tr>"
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Delay Impact Analysis</title>
<style>{_WESTLAND_CSS}</style></head><body>
<div class="container">
<div class="header">
  <h1>Float Path Delay Analysis</h1>
  <div class="tracking">{tracking}</div>
  <div class="meta">Data Date: {d.get('data_date','')} | Projected SC: {d.get('baseline_sc_date','')} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
</div>
<div class="section">
<table>
<thead><tr>
  <th>Activity ID</th><th>Delayed Schedule Activity</th><th>Data Date</th>
  <th>Previous SC</th><th>Revised SC</th><th>Variance (CD)</th>
  <th>Float (days)</th><th>Status</th>
</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</div>
</div></body></html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return output_path


def render_paths_html(path_data, output_path):
    """Write per-activity path analysis HTML report."""
    pd = path_data

    if pd.get('sc_task_name'):
        tracking = f"Tracking to: {pd['sc_task_name']} — {pd.get('sc_date', '')}"
    else:
        tracking = "No SC milestone found"

    rows = []
    for a in pd.get('activities', []):
        tf = a.get('total_float_days', 0)
        if a.get('is_critical'):
            row_class = 'style="background:#fde8e8"'
            float_class = 'neg'
        elif tf <= 10:
            row_class = 'style="background:#fef3e2"'
            float_class = 'neg'
        else:
            row_class = ''
            float_class = 'pos' if tf > 20 else ''

        sc_tag = '<span class="tag tag-ok">Yes</span>' if a.get('connected_to_sc') else '<span class="tag tag-disc">No</span>'
        crit_tag = '<span class="tag tag-crit">CRITICAL</span>' if a.get('is_critical') else ''

        rows.append(
            f"<tr {row_class}>"
            f"<td>{a['task_code']}</td>"
            f"<td>{a['task_name']}</td>"
            f"<td class='{float_class}'>{tf}</td>"
            f"<td>{a.get('free_float_days', 0)}</td>"
            f"<td>{sc_tag}</td>"
            f"<td>{a.get('path_length', 0)}</td>"
            f"<td>{crit_tag}</td>"
            f"</tr>"
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Activity Path Analysis</title>
<style>{_WESTLAND_CSS}</style></head><body>
<div class="container">
<div class="header">
  <h1>Activity Path Analysis</h1>
  <div class="tracking">{tracking}</div>
  <div class="meta">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
</div>
<div class="summary-grid">
  <div class="stat-box"><div class="num">{pd.get('total_activities',0)}</div><div class="label">Activities</div></div>
  <div class="stat-box" style="color:#c0392b"><div class="num">{pd.get('critical_count',0)}</div><div class="label">Critical</div></div>
  <div class="stat-box" style="color:#e67e22"><div class="num">{pd.get('near_critical_count',0)}</div><div class="label">Near-Critical</div></div>
</div>
<div class="section">
<table>
<thead><tr>
  <th>Activity ID</th><th>Name</th><th>TF (days)</th><th>FF (days)</th>
  <th>SC Connected</th><th>Path Length</th><th>Status</th>
</tr></thead>
<tbody>{''.join(rows)}</tbody>
</table>
</div>
</div></body></html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return output_path
