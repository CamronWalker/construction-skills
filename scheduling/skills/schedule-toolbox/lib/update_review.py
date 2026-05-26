"""
update_review.py -- Schedule Update Review Tools

Answers the question: "What do I need to collect from the field by <date>?"
Also supports resource-filtered queries: "What is the electrician doing this month?"

==============================================================================
!!!!!!!!!!!!!!!!!!  CRITICAL RULE -- NEVER WRITE XER FILES  !!!!!!!!!!!!!!!!!!
THIS MODULE IS READ-ONLY. IT ANALYZES PARSED XER DATA IN MEMORY ONLY.
NEVER WRITE, MODIFY, OR OVERWRITE ANY XER FILE UNDER ANY CIRCUMSTANCES.
HISTORICAL SCHEDULE RECORDS MUST NEVER BE ALTERED BY ANALYSIS TOOLS.
==============================================================================

CLI Usage:
  python update_review.py expected_updates <xer_path> <future_date>
  python update_review.py expected_updates <xer_path> <future_date> --resource ELEC
  python update_review.py riding_data_date <xer_path>
  python update_review.py trade_activities <xer_path> <future_date> <resource_code>

Dates: YYYY-MM-DD format.

Output: JSON to stdout.
  expected_updates returns:
    {
      data_date, future_date, resource_filter,
      to_start:    [{task_id, task_code, task_name, early_start, resource}],
      to_finish:   [{task_id, task_code, task_name, early_finish, resource}],
      in_progress: [{task_id, task_code, task_name, pct_complete, resource}],
      summary: {to_start_count, to_finish_count, in_progress_count}
    }
"""

from collections import defaultdict
from datetime import datetime


# ==============================================================================
# HELPERS
# ==============================================================================

def _safe_float(val, default=0.0):
    try:
        return float(val) if val not in (None, '') else default
    except (ValueError, TypeError):
        return default


def _parse_dt(v):
    if not v or not str(v).strip():
        return None
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(str(v).strip(), fmt)
        except ValueError:
            continue
    return None


def _task_rec(t, extra=None):
    r = {
        'task_id': t.get('task_id', ''),
        'task_code': t.get('task_code', ''),
        'task_name': t.get('task_name', ''),
    }
    if extra:
        r.update(extra)
    return r


def _parse_xer(file_path):
    """Parse XER file to tables dict. READ ONLY -- never writes back."""
    for enc in ('cp1252', 'utf-8-sig', 'utf-8', 'latin-1'):
        try:
            with open(file_path, 'rb') as f:
                raw = f.read()
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    tables = {}
    current_table = None
    fields = []
    for line in text.split('\r\n'):
        if line.startswith('%T'):
            current_table = line.split('\t')[1].strip()
            tables[current_table] = []
        elif line.startswith('%F'):
            fields = [f.strip() for f in line.split('\t')[1:]]
        elif line.startswith('%R') and current_table:
            vals = line.split('\t')[1:]
            tables[current_table].append(dict(zip(fields, vals)))
    return tables


def _build_resource_map(tables):
    """Build task_id -> list of resource short names from RSRC + TASKRSRC."""
    rsrc_lookup = {r['rsrc_id']: r.get('rsrc_short_name', r.get('rsrc_name', ''))
                   for r in tables.get('RSRC', [])}
    task_resources = defaultdict(list)
    for tr in tables.get('TASKRSRC', []):
        tid = tr.get('task_id', '')
        rsrc_id = tr.get('rsrc_id', '')
        rsrc_name = rsrc_lookup.get(rsrc_id, rsrc_id)
        if rsrc_name:
            task_resources[tid].append(rsrc_name)
    return dict(task_resources)


def _activity_filter(tasks):
    """Incomplete non-WBS/LOE activities only."""
    exc = {'TT_WBS', 'TT_LOE'}
    return [t for t in tasks
            if t.get('status_code', '') != 'TK_Complete'
            and t.get('task_type', '') not in exc]


# ==============================================================================
# EXPECTED UPDATES
# ==============================================================================

def expected_updates(tables, future_date, resource_filter=None):
    """
    Return activities that need field updates between now and future_date.

    to_start:    Not-started activities scheduled to start before future_date.
    to_finish:   In-progress activities scheduled to finish before future_date.
    in_progress: Currently active activities (regardless of scheduled finish).

    resource_filter: resource short_name substring match (case-insensitive), e.g. 'ELEC'.
    """
    tasks = tables.get('TASK', [])
    proj = tables.get('PROJECT', [{}])
    data_date_str = proj[0].get('last_recalc_date') or proj[0].get('data_date', '')
    dd = _parse_dt(data_date_str)
    fd = _parse_dt(future_date) if isinstance(future_date, str) else future_date
    resource_map = _build_resource_map(tables)

    acts = _activity_filter(tasks)
    if resource_filter:
        rf = resource_filter.upper()
        acts = [t for t in acts
                if any(rf in r.upper() for r in resource_map.get(t['task_id'], []))]

    to_start = []
    to_finish = []
    in_progress = []

    for t in acts:
        tid = t['task_id']
        status = t.get('status_code', '')
        resources = resource_map.get(tid, [])
        base = _task_rec(t, {'resources': resources})

        if status == 'TK_NotStart':
            es = _parse_dt(t.get('early_start_date', ''))
            if es and es <= fd:
                to_start.append({**base,
                                 'early_start': t.get('early_start_date', ''),
                                 'early_finish': t.get('early_end_date', ''),
                                 'duration_days': round(_safe_float(t.get('target_drtn_hr_cnt', 0)) / 8, 1)})

        elif status == 'TK_Active':
            ef = _parse_dt(t.get('early_end_date', ''))
            in_progress.append({**base,
                                 'pct_complete': _safe_float(t.get('phys_complete_pct', 0)),
                                 'early_finish': t.get('early_end_date', ''),
                                 'remaining_days': round(_safe_float(t.get('remain_drtn_hr_cnt', 0)) / 8, 1)})
            if ef and ef <= fd:
                to_finish.append({**base,
                                  'pct_complete': _safe_float(t.get('phys_complete_pct', 0)),
                                  'early_finish': t.get('early_end_date', ''),
                                  'remaining_days': round(_safe_float(t.get('remain_drtn_hr_cnt', 0)) / 8, 1)})

    # Sort by date
    to_start.sort(key=lambda x: x.get('early_start', ''))
    to_finish.sort(key=lambda x: x.get('early_finish', ''))
    in_progress.sort(key=lambda x: x.get('early_finish', ''))

    return {
        'data_date': data_date_str,
        'future_date': str(future_date),
        'resource_filter': resource_filter,
        'to_start': to_start,
        'to_finish': to_finish,
        'in_progress': in_progress,
        'summary': {
            'to_start_count': len(to_start),
            'to_finish_count': len(to_finish),
            'in_progress_count': len(in_progress),
            'total_needing_update': len(to_start) + len(in_progress),
        },
    }


# ==============================================================================
# RIDING DATA DATE (standalone -- mirrors quality_checks version)
# ==============================================================================

def riding_data_date(tables):
    """Not-started activities whose logic is complete but held by data date."""
    tasks = tables.get('TASK', [])
    preds = tables.get('TASKPRED', [])
    proj = tables.get('PROJECT', [{}])
    data_date_str = proj[0].get('last_recalc_date') or proj[0].get('data_date', '')
    dd = _parse_dt(data_date_str)

    exc = {'TT_WBS', 'TT_LOE'}
    acts = [t for t in tasks if t.get('status_code') != 'TK_Complete'
            and t.get('task_type', '') not in exc]
    n = len(acts)

    complete_ids = {t['task_id'] for t in tasks if t.get('status_code') == 'TK_Complete'}
    pred_map = defaultdict(set)
    for p in preds:
        pred_map[p.get('task_id', '')].add(p.get('pred_task_id', ''))

    riding = []
    for t in acts:
        if t.get('status_code', '') != 'TK_NotStart':
            continue
        tid = t['task_id']
        task_preds = pred_map.get(tid, set())
        if not task_preds:
            continue
        if all(pid in complete_ids for pid in task_preds):
            es = _parse_dt(t.get('early_start_date', ''))
            if dd and es and abs((es - dd).total_seconds()) < 86400:
                riding.append(_task_rec(t, {'early_start': t.get('early_start_date', '')}))

    return {
        'data_date': data_date_str,
        'count': len(riding),
        'total_incomplete': n,
        'pct': round(len(riding) / max(n, 1) * 100, 1),
        'tasks': riding,
        'note': 'All predecessors complete. Only the data date is holding these back.',
    }


# ==============================================================================
# TRADE ACTIVITIES (resource-filtered activity list for a date window)
# ==============================================================================

def trade_activities(tables, future_date, resource_code):
    """
    Return all activities assigned to a resource/trade between data_date and future_date.
    resource_code: substring match against rsrc_short_name (e.g. 'ELEC', 'MECH', 'GC').
    """
    result = expected_updates(tables, future_date, resource_filter=resource_code)
    all_active = result['in_progress'] + result['to_start']
    all_active.sort(key=lambda x: x.get('early_start', x.get('early_finish', '')))
    return {
        'resource_filter': resource_code,
        'data_date': result['data_date'],
        'future_date': result['future_date'],
        'activities': all_active,
        'count': len(all_active),
        'in_progress': len(result['in_progress']),
        'starting_soon': len(result['to_start']),
    }


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

if __name__ == '__main__':
    import sys
    import json

    COMMANDS = ('expected_updates', 'riding_data_date', 'trade_activities')

    if len(sys.argv) < 3:
        print(json.dumps({
            'error': 'Usage: python update_review.py <command> <xer_path> [future_date] [--resource CODE]',
            'commands': list(COMMANDS),
        }))
        sys.exit(1)

    cmd = sys.argv[1].lower()
    xer_path = sys.argv[2]

    # Parse optional args
    future_date_arg = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith('--') else None
    resource_arg = None
    for i, arg in enumerate(sys.argv):
        if arg == '--resource' and i + 1 < len(sys.argv):
            resource_arg = sys.argv[i + 1]
    # trade_activities positional resource
    if cmd == 'trade_activities' and len(sys.argv) > 4 and resource_arg is None:
        resource_arg = sys.argv[4]

    # PARSE -- READ ONLY, NEVER WRITES
    tables = _parse_xer(xer_path)

    if cmd == 'riding_data_date':
        out = riding_data_date(tables)

    elif cmd == 'expected_updates':
        if not future_date_arg:
            print(json.dumps({'error': 'expected_updates requires <future_date> (YYYY-MM-DD)'}))
            sys.exit(1)
        out = expected_updates(tables, future_date_arg, resource_filter=resource_arg)

    elif cmd == 'trade_activities':
        if not future_date_arg or not resource_arg:
            print(json.dumps({'error': 'trade_activities requires <future_date> <resource_code>'}))
            sys.exit(1)
        out = trade_activities(tables, future_date_arg, resource_arg)

    else:
        out = {'error': f'Unknown command: {cmd}', 'available': list(COMMANDS)}

    print(json.dumps(out, indent=2, default=str))
