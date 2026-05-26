"""
CPM Engine — Forward/backward pass, float calculation for P6 XER schedules.

Pure function library. Pass parsed XER data in, get calculated schedule out.

Usage:
    from calendar_engine import build_calendar_lookup
    from cpm_engine import schedule_forward_backward, render_schedule_html

    cal_lookup = build_calendar_lookup(calendars)
    results, metadata = schedule_forward_backward(tasks, preds, calendars, data_date)
    render_schedule_html(results, 'Project Name', data_date, metadata, 'schedule.html')
"""

from datetime import datetime, timedelta
from collections import defaultdict, deque
import json
import os

# Import calendar_engine from same directory
import importlib.util
_dir = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location('calendar_engine', os.path.join(_dir, 'calendar_engine.py'))
_cal_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_cal_mod)

build_calendar_lookup = _cal_mod.build_calendar_lookup
add_work_hours = _cal_mod.add_work_hours
subtract_work_hours = _cal_mod.subtract_work_hours
work_hours_between = _cal_mod.work_hours_between
next_work_start = _cal_mod.next_work_start
snap_to_work_time = _cal_mod.snap_to_work_time
_default_calendar = _cal_mod._default_calendar

# Milestone resolver — try regular import first (when lib/ is on sys.path
# this matches the class identity path_analysis / score_schedule see, so
# `except MilestoneAmbiguousError` keeps catching across modules), with a
# spec_from_file_location fallback for the case where a tool loaded
# cpm_engine without adjusting sys.path. In the fallback we register the
# module under 'milestones' so any later `from milestones import ...` in
# the same process resolves to the same module object.
import sys as _sys  # local alias to avoid shadowing existing `sys` usage
try:
    if _dir not in _sys.path:
        _sys.path.insert(0, _dir)
    from milestones import MilestoneAmbiguousError, resolve_default_milestone  # noqa: E402
except ImportError:
    _ms_spec = importlib.util.spec_from_file_location(
        'milestones', os.path.join(_dir, 'milestones.py'))
    _ms_mod = importlib.util.module_from_spec(_ms_spec)
    _sys.modules['milestones'] = _ms_mod
    _ms_spec.loader.exec_module(_ms_mod)
    MilestoneAmbiguousError = _ms_mod.MilestoneAmbiguousError
    resolve_default_milestone = _ms_mod.resolve_default_milestone


# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------

def _parse_date(date_str):
    """Parse 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD' to datetime, None if empty."""
    if not date_str or not date_str.strip():
        return None
    s = date_str.strip()
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _format_date(dt):
    """Format datetime to 'YYYY-MM-DD HH:MM' string."""
    if dt is None:
        return ''
    return dt.strftime('%Y-%m-%d %H:%M')


def _safe_float(val, default=0.0):
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


# ---------------------------------------------------------------------------
# SC milestone resolution
#
# D4 removed the name-matching `_find_sc_milestone` heuristic that lived here
# (and in score_schedule.py / path_analysis.py / xer_compare.py). The
# `schedule_forward_backward` function now resolves the terminal milestone
# structurally via `milestones.resolve_default_milestone` -- the same helper
# that score_schedule and path_analysis use after D2/D3. Callers that need
# to override the auto-resolution (e.g. multi-terminal-milestone schedules)
# pass `milestone_id` explicitly; see the function docstring below.
# ---------------------------------------------------------------------------


def check_anchor_dates(results, anchors, tolerance_days=0):
    """Compare CPM results against project anchor dates and report any slips.

    Anchors are the bid-given milestones (NTP, drawings issued, SC, final
    GMP, etc.) captured as project metadata -- NOT as XER constraints.
    Westland best practice is to keep these dates pinned via *logic and
    durations*, not hard constraints, so the schedule remains honest about
    what's actually driving each date.

    During the proposal-schedule iteration loop, Claude calls this after
    a what-if CPM but BEFORE writing the next -v{N+1}.xer. Any non-zero
    slip means the proposed change would push an anchor; Claude must
    formulate an absorption plan and confirm with the scheduler before
    regenerating the file.

    Args:
        results: list of task dicts after schedule_forward_backward (each
            has early_start_date / early_end_date populated)
        anchors: list of anchor dicts from the project's anchors metadata
            (typically `<project>/proposal-anchors.json`). Each entry:
                - task_code (str): matches results[*].task_code
                - anchor_date (str: YYYY-MM-DD)
                - anchor_kind (str): "start" or "finish" -- which side of
                    the task the date applies to (default "finish")
                - kind_label (str, optional): human label like "NTP" / "SC"
        tolerance_days (int): allowed slip without reporting (default 0)

    Returns: list of slip dicts, one per anchor that drifted past tolerance:
        {task_code, task_name, kind_label, anchor_date, computed_date,
         anchor_kind, slip_days}.
        Empty list = all anchors hold.
    """
    by_code = {t.get('task_code', ''): t for t in results}
    slips = []
    for a in anchors:
        code = a.get('task_code', '')
        t = by_code.get(code)
        if not t:
            continue
        anchor_kind = (a.get('anchor_kind') or 'finish').lower()
        anchor_d = _parse_date(a.get('anchor_date', ''))
        if not anchor_d:
            continue
        if anchor_kind == 'start':
            computed = _parse_date(t.get('early_start_date', ''))
        else:
            computed = _parse_date(t.get('early_end_date', ''))
        if not computed:
            continue
        # Compare date-only — anchor_date is YYYY-MM-DD, but early_*_date
        # carries a time-of-day (08:00 / 17:00) that would otherwise show
        # an on-time task as a fractional-day slip.
        computed_d = computed.replace(hour=0, minute=0, second=0, microsecond=0)
        anchor_d_norm = anchor_d.replace(hour=0, minute=0, second=0, microsecond=0)
        slip = (computed_d - anchor_d_norm).days
        if abs(slip) <= tolerance_days:
            continue
        slips.append({
            'task_id': t.get('task_id', ''),
            'task_code': code,
            'task_name': t.get('task_name', ''),
            'kind_label': a.get('kind_label', ''),
            'anchor_date': a.get('anchor_date', ''),
            'computed_date': computed_d.strftime('%Y-%m-%d'),
            'anchor_kind': anchor_kind,
            'slip_days': int(slip),
        })
    return slips


def suggest_anchor_absorption(results, preds, slip, max_suggestions=8):
    """For a single anchor slip, return candidate edits that would pull
    the anchor task back to its target date.

    Walks predecessors of the slipped task and ranks the chain by duration
    (longest tasks first -- highest leverage per cut). Returns concrete
    suggestions Claude can surface to the scheduler for confirmation;
    Claude is expected to present these as options, not auto-apply.

    Args:
        results: task list after schedule_forward_backward
        preds: TASKPRED rows
        slip: one entry from check_anchor_dates() return value (must
            include task_id and slip_days)
        max_suggestions: cap on the number of candidate tasks listed

    Returns: list of suggestion dicts:
        {task_id, task_code, task_name, current_duration_days,
         suggested_max_cut_days, total_float_days, kind, rationale}
        Sum of `suggested_max_cut_days` across the list is at least the
        slip; Claude picks a subset that adds up to the slip and presents
        the absorption plan to the scheduler.
    """
    target_id = slip.get('task_id', '')
    slip_days = abs(int(slip.get('slip_days', 0)))
    if not target_id or slip_days == 0:
        return []

    # Build predecessor map from preds rows
    pred_map = defaultdict(list)
    for r in preds:
        succ_id = r.get('task_id', '')
        pred_id = r.get('pred_task_id', '')
        if succ_id and pred_id:
            pred_map[succ_id].append(pred_id)
    tasks_by_id = {t.get('task_id', ''): t for t in results}

    # Walk back from the target task collecting all upstream tasks
    upstream = set()
    queue = [target_id]
    seen = set()
    while queue:
        tid = queue.pop()
        if tid in seen:
            continue
        seen.add(tid)
        if tid != target_id:
            upstream.add(tid)
        for p in pred_map.get(tid, []):
            if p not in seen:
                queue.append(p)
        # Cap traversal so a large schedule doesn't fan out infinitely
        if len(seen) > 1000:
            break

    # Rank candidates by current duration (largest first), excluding
    # milestones (zero-duration). Tasks with high total_float can be
    # cut without affecting the anchor — so prefer tasks WITHOUT float
    # (= on the driving path to the anchor).
    cands = []
    for tid in upstream:
        t = tasks_by_id.get(tid)
        if not t:
            continue
        ttype = t.get('task_type', '')
        if ttype in ('TT_Mile', 'TT_FinMile', 'TT_WBS', 'TT_LOE'):
            continue
        dur_hr = _safe_float(t.get('target_drtn_hr_cnt', 0))
        dur_days = dur_hr / 8
        if dur_days < 1:
            continue
        tf_hr = _safe_float(t.get('total_float_hr_cnt', 0))
        tf_days = tf_hr / 8
        # Only critical-path tasks (TF <= 1d) actually pull the anchor in.
        # Tasks with float are on parallel branches — cutting them just
        # gives those branches more slack and doesn't move the anchor.
        # Once Camron has allocated cuts on the critical path and the
        # near-critical path becomes the new bottleneck, run the function
        # again on the new what-if results.
        if tf_days > 1:
            continue
        # Suggest a cut up to ~half the duration (still leaves a sane
        # estimate). Claude can adjust on a per-task basis.
        max_cut = max(1, int(dur_days * 0.5))
        cands.append({
            'task_id': tid,
            'task_code': t.get('task_code', ''),
            'task_name': t.get('task_name', ''),
            'current_duration_days': round(dur_days, 1),
            'suggested_max_cut_days': max_cut,
            'total_float_days': round(tf_days, 1),
            'kind': 'duration_cut',
            'rationale': f'On the driving path to the anchor (TF {round(tf_days,1)}d). Cutting up to {max_cut}d preserves a realistic estimate.',
        })

    # Largest-leverage tasks first so Claude considers them first
    cands.sort(key=lambda c: -c['current_duration_days'])
    return cands[:max_suggestions]


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------

def _build_graph(tasks, preds):
    """
    Build network graph from task and relationship lists.

    Returns:
        tasks_by_id: {task_id: task_dict}
        succ_map: {pred_task_id: [(succ_task_id, rel_dict), ...]}
        pred_map: {task_id: [(pred_task_id, rel_dict), ...]}
        cpm_tasks: list of task_ids to schedule (excludes WBS, LOE)
    """
    skip_types = {'TT_WBS', 'TT_LOE'}
    tasks_by_id = {}
    cpm_task_ids = set()

    for t in tasks:
        tid = t.get('task_id', '')
        tasks_by_id[tid] = t
        if t.get('task_type', '') not in skip_types:
            cpm_task_ids.add(tid)

    succ_map = defaultdict(list)  # pred -> [(succ, rel)]
    pred_map = defaultdict(list)  # succ -> [(pred, rel)]

    for r in preds:
        succ_id = r.get('task_id', '')       # task_id = SUCCESSOR
        pred_id = r.get('pred_task_id', '')   # pred_task_id = PREDECESSOR
        if succ_id in cpm_task_ids and pred_id in cpm_task_ids:
            succ_map[pred_id].append((succ_id, r))
            pred_map[succ_id].append((pred_id, r))

    return tasks_by_id, succ_map, pred_map, cpm_task_ids


def _find_cycles(remaining_ids, adj):
    """
    Find all cycles in a directed graph using DFS.
    Returns list of cycles, each cycle is a list of task_ids.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in remaining_ids}
    path = []
    cycles = []

    def dfs(node):
        color[node] = GRAY
        path.append(node)
        for succ in adj.get(node, []):
            if succ not in remaining_ids:
                continue
            if color[succ] == GRAY:
                # Found cycle — extract from where succ appears in path
                idx = path.index(succ)
                cycles.append(list(path[idx:]))
            elif color[succ] == WHITE:
                dfs(succ)
        path.pop()
        color[node] = BLACK

    for tid in remaining_ids:
        if color[tid] == WHITE:
            dfs(tid)

    return cycles


def _topological_sort(task_ids, pred_map, tasks_by_id=None):
    """
    Kahn's algorithm for topological ordering.
    Returns list of task_ids in forward-pass order.

    If circular dependencies exist, breaks the cycles by removing
    back-edges and returns the order with cycles broken. Stores
    cycle info in tasks_by_id['_circular_deps'] if provided.
    """
    # Count incoming edges (within our CPM scope).
    # Sort task_ids for deterministic ordering — Python set iteration
    # is non-deterministic, and different topological orderings can
    # produce different CPM results when ties exist.
    sorted_ids = sorted(task_ids)
    in_degree = {tid: 0 for tid in sorted_ids}
    adj = defaultdict(list)

    for succ_id in sorted_ids:
        for pred_id, _ in pred_map.get(succ_id, []):
            if pred_id in in_degree:
                in_degree[succ_id] += 1
                adj[pred_id].append(succ_id)

    # Sort initial queue and maintain sorted insertion for determinism
    queue = deque(sorted(tid for tid, deg in in_degree.items() if deg == 0))
    order = []

    while queue:
        tid = queue.popleft()
        order.append(tid)
        new_ready = []
        for succ_id in adj[tid]:
            in_degree[succ_id] -= 1
            if in_degree[succ_id] == 0:
                new_ready.append(succ_id)
        # Sort newly ready tasks for determinism
        for s in sorted(new_ready):
            queue.append(s)

    if len(order) == len(task_ids):
        return order, []  # No cycles

    # --- Circular dependencies detected ---
    scheduled = set(order)
    remaining = {tid for tid in task_ids if tid not in scheduled}

    # Find the actual cycles for reporting
    cycles = _find_cycles(remaining, adj)

    # Build human-readable cycle info
    cycle_details = []
    for cycle in cycles:
        chain = []
        for tid in cycle:
            if tasks_by_id and tid in tasks_by_id:
                t = tasks_by_id[tid]
                code = t.get('task_code', tid)
                name = t.get('task_name', '')
                chain.append(f"{code} ({name})")
            else:
                chain.append(tid)
        # Show the loop: A -> B -> C -> A
        chain.append(chain[0])
        cycle_details.append(' → '.join(chain))

    # Break cycles: for each remaining task, remove one back-edge
    # by artificially setting in_degree to 0 for the task with
    # the fewest remaining predecessors
    while remaining:
        # Pick the task with lowest in_degree among remaining
        best = min(remaining, key=lambda t: in_degree[t])
        in_degree[best] = 0
        queue = deque([best])
        while queue:
            tid = queue.popleft()
            if tid in scheduled:
                continue
            scheduled.add(tid)
            order.append(tid)
            remaining.discard(tid)
            for succ_id in adj[tid]:
                if succ_id in remaining:
                    in_degree[succ_id] -= 1
                    if in_degree[succ_id] <= 0:
                        queue.append(succ_id)

    return order, cycle_details


# ---------------------------------------------------------------------------
# Duration helpers
# ---------------------------------------------------------------------------

def _get_duration_hours(task):
    """Get effective duration in hours for CPM calculation."""
    task_type = task.get('task_type', '')
    status = task.get('status_code', '')

    # Milestones have zero duration
    if task_type in ('TT_Mile', 'TT_FinMile'):
        return 0.0

    # Complete tasks — use actual dates, no duration calculation needed
    if status == 'TK_Complete':
        return 0.0

    # Active tasks — use remaining duration
    if status == 'TK_Active':
        return _safe_float(task.get('remain_drtn_hr_cnt', 0))

    # Not started — use target duration
    return _safe_float(task.get('target_drtn_hr_cnt',
                        task.get('remain_drtn_hr_cnt', 0)))


def _get_calendar(task, cal_lookup):
    """Get the parsed calendar for a task."""
    cid = task.get('clndr_id', '')
    if cid in cal_lookup:
        return cal_lookup[cid]
    # Try first calendar in lookup as fallback
    for k, v in cal_lookup.items():
        if k:
            return v
    return _default_calendar()


def _get_lag_calendar(pred_task, succ_task, cal_lookup, lag_cal_option, default_cal_id):
    """
    Get the calendar to use for relationship lag computation.
    Based on P6's sched_calendar_on_relationship_lag option.
    """
    opt = (lag_cal_option or '').lower()
    if 'predecessor' in opt:
        return _get_calendar(pred_task, cal_lookup)
    elif '24' in opt:
        # 24-hour calendar: all days working, all hours working
        return {
            'work_week': {i: [(0, 1440)] for i in range(7)},
            'exceptions': {},
            'hours_per_day': 24.0,
        }
    elif 'default' in opt:
        if default_cal_id and default_cal_id in cal_lookup:
            return cal_lookup[default_cal_id]
        return _get_calendar(succ_task, cal_lookup)
    else:
        # Default: successor calendar (rcal_Successor)
        return _get_calendar(succ_task, cal_lookup)


# ---------------------------------------------------------------------------
# Relationship math
# ---------------------------------------------------------------------------

def _is_fs(pred_type):
    return pred_type in ('FS', 'PR_FS')

def _is_ss(pred_type):
    return pred_type in ('SS', 'PR_SS')

def _is_ff(pred_type):
    return pred_type in ('FF', 'PR_FF')

def _is_sf(pred_type):
    return pred_type in ('SF', 'PR_SF')


def _relationship_contribution_forward(pred_task, rel, succ_cal, lag_cal=None):
    """
    Compute what a predecessor relationship pushes on the successor.

    Args:
        pred_task: predecessor task dict (with _es, _ef set)
        rel: relationship dict
        succ_cal: successor's parsed calendar
        lag_cal: calendar to use for lag computation (from scheduling option).
                 If None, uses succ_cal.

    Returns: (target, dt) where target is 'es' or 'ef'
    """
    pred_type = rel.get('pred_type', 'PR_FS')
    lag_hours = _safe_float(rel.get('lag_hr_cnt', 0))
    cal = lag_cal or succ_cal

    pred_es = pred_task.get('_es')
    pred_ef = pred_task.get('_ef')

    if pred_es is None or pred_ef is None:
        return None

    # For SS/SF: P6's reference point depends on lag:
    # - Zero lag: use computed early start (_es) — "start at same time"
    #   means when the predecessor's remaining work is scheduled.
    # - Nonzero lag: use actual start (_act_start) — lag is measured from
    #   when work actually began, partially consumed by actual progress.
    # For FS/FF from completed predecessors: lag is consumed — use _ef
    # directly, no lag applied.
    if lag_hours:
        pred_start = pred_task.get('_act_start', pred_es)
    else:
        pred_start = pred_es  # Zero lag: use computed ES
    is_completed = pred_task.get('status_code', '') == 'TK_Complete'

    if _is_fs(pred_type):
        # Succ ES >= Pred EF + lag
        # For completed preds with zero lag: contribution = pred_ef (lag consumed).
        # For completed preds with positive lag: P6 applies lag from act_end_date
        # (the lag represents a waiting period after actual completion, e.g. curing).
        # For completed preds with negative lag (lead): P6 applies lead from
        # the stored EF (not act_end, which would be in the distant past).
        if is_completed:
            if lag_hours and lag_hours > 0:
                # Positive lag (waiting period after completion, e.g. curing):
                # apply from act_end_date
                act_end = _parse_date(pred_task.get('act_end_date', ''))
                base = act_end or pred_ef
                return ('es', add_work_hours(base, lag_hours, cal))
            # Zero lag or negative lag (lead): consumed for completed preds.
            # Lead is moot since predecessor already finished.
            return ('es', pred_ef)
        if lag_hours:
            if lag_hours > 0:
                dt = add_work_hours(pred_ef, lag_hours, cal)
            else:
                dt = subtract_work_hours(pred_ef, abs(lag_hours), cal)
        else:
            dt = pred_ef
        return ('es', dt)
    elif _is_ss(pred_type):
        # Succ ES >= Pred start + lag.
        # Positive lag: consumed by progress — contribution = max(result, pred_es).
        # Negative lag (lead): successor can start BEFORE predecessor — no floor.
        if lag_hours:
            if lag_hours > 0:
                dt = add_work_hours(pred_start, lag_hours, cal)
                # Positive lag can't pull earlier than predecessor's position
                if dt < pred_es:
                    dt = pred_es
            else:
                dt = subtract_work_hours(pred_start, abs(lag_hours), cal)
        else:
            dt = pred_start
        return ('es', dt)
    elif _is_ff(pred_type):
        # Succ EF >= Pred EF + lag
        if is_completed:
            if lag_hours and lag_hours > 0:
                act_end = _parse_date(pred_task.get('act_end_date', ''))
                base = act_end or pred_ef
                return ('ef', add_work_hours(base, lag_hours, cal))
            return ('ef', pred_ef)
        if lag_hours:
            dt = add_work_hours(pred_ef, lag_hours, cal) if lag_hours > 0 else subtract_work_hours(pred_ef, abs(lag_hours), cal)
        else:
            dt = pred_ef
        return ('ef', dt)
    elif _is_sf(pred_type):
        # Succ EF >= Pred start + lag.
        # Same consumed-lag logic as SS.
        if lag_hours:
            if lag_hours > 0:
                dt = add_work_hours(pred_start, lag_hours, cal)
                if dt < pred_es:
                    dt = pred_es
            else:
                dt = subtract_work_hours(pred_start, abs(lag_hours), cal)
        else:
            dt = pred_start
        return ('ef', dt)
    return None


def _relationship_constraint_backward(succ_task, rel, succ_cal, lag_cal=None):
    """
    Compute what a successor relationship constrains on the predecessor.

    Returns: (target, dt) where target is 'ls' or 'lf'
    """
    pred_type = rel.get('pred_type', 'PR_FS')
    lag_hours = _safe_float(rel.get('lag_hr_cnt', 0))
    cal = lag_cal or succ_cal

    succ_ls = succ_task.get('_ls')
    succ_lf = succ_task.get('_lf')

    if succ_ls is None or succ_lf is None:
        return None

    if _is_fs(pred_type):
        # Pred LF <= Succ LS - lag
        dt = subtract_work_hours(succ_ls, lag_hours, cal) if lag_hours else succ_ls
        return ('lf', dt)
    elif _is_ss(pred_type):
        # Pred LS <= Succ LS - lag
        dt = subtract_work_hours(succ_ls, lag_hours, cal) if lag_hours else succ_ls
        return ('ls', dt)
    elif _is_ff(pred_type):
        # Pred LF <= Succ LF - lag
        dt = subtract_work_hours(succ_lf, lag_hours, cal) if lag_hours else succ_lf
        return ('lf', dt)
    elif _is_sf(pred_type):
        # Pred LS <= Succ LF - lag
        dt = subtract_work_hours(succ_lf, lag_hours, cal) if lag_hours else succ_lf
        return ('ls', dt)
    return None


# ---------------------------------------------------------------------------
# Constraint handling
# ---------------------------------------------------------------------------

_HARD_START = {'CS_MSO', 'CS_MANDSTART'}
_HARD_FINISH = {'CS_MFO', 'CS_MEO', 'CS_MANDEND', 'CS_MANDFIN'}
_FWD_START = {'CS_SNET', 'CS_MSOA'}   # Start No Earlier Than
_FWD_FINISH = {'CS_FNET', 'CS_MEOA'}  # Finish No Earlier Than
_BWD_START = {'CS_SNLT', 'CS_MSOB'}   # Start No Later Than
_BWD_FINISH = {'CS_FNLT', 'CS_MEOB'}  # Finish No Later Than


def _apply_constraint_forward(task, es, ef, cal):
    """Apply constraints during forward pass. Returns (es, ef)."""
    duration = _get_duration_hours(task)

    for cstr_field, date_field in [('cstr_type', 'cstr_date'),
                                    ('cstr_type2', 'cstr_date2'),
                                    ('constraint_type', 'constraint_date')]:
        ctype = task.get(cstr_field, '')
        cdate = _parse_date(task.get(date_field, ''))
        if not ctype or not cdate:
            continue

        if ctype in _HARD_START:
            es = cdate
            ef = add_work_hours(es, duration, cal) if duration else es
        elif ctype in _HARD_FINISH:
            ef = cdate
            es = subtract_work_hours(ef, duration, cal) if duration else ef
        elif ctype in _FWD_START:
            if cdate > es:
                es = cdate
                ef = add_work_hours(es, duration, cal) if duration else es
        elif ctype in _FWD_FINISH:
            if cdate > ef:
                ef = cdate
                es = subtract_work_hours(ef, duration, cal) if duration else ef

    return es, ef


def _apply_constraint_backward(task, ls, lf, cal):
    """Apply constraints during backward pass. Returns (ls, lf)."""
    duration = _get_duration_hours(task)

    for cstr_field, date_field in [('cstr_type', 'cstr_date'),
                                    ('cstr_type2', 'cstr_date2'),
                                    ('constraint_type', 'constraint_date')]:
        ctype = task.get(cstr_field, '')
        cdate = _parse_date(task.get(date_field, ''))
        if not ctype or not cdate:
            continue

        if ctype in _HARD_START:
            ls = cdate
            lf = add_work_hours(ls, duration, cal) if duration else ls
        elif ctype in _HARD_FINISH:
            lf = cdate
            ls = subtract_work_hours(lf, duration, cal) if duration else lf
        elif ctype in _BWD_START:
            if cdate < ls:
                ls = cdate
                lf = add_work_hours(ls, duration, cal) if duration else ls
        elif ctype in _BWD_FINISH:
            if cdate < lf:
                lf = cdate
                ls = subtract_work_hours(lf, duration, cal) if duration else lf

    return ls, lf


# ---------------------------------------------------------------------------
# Forward pass
# ---------------------------------------------------------------------------

def _forward_pass(tasks_by_id, topo_order, pred_map, succ_map, cal_lookup, data_date,
                   lag_cal_option='', default_cal_id='', use_expect_end=False):
    """
    Forward pass: compute Early Start (ES) and Early Finish (EF) for all tasks.
    Results stored as _es and _ef on each task dict.
    """
    for tid in topo_order:
        task = tasks_by_id[tid]
        cal = _get_calendar(task, cal_lookup)
        status = task.get('status_code', '')
        task_type = task.get('task_type', '')
        duration = _get_duration_hours(task)

        # Completed tasks: use P6's stored early dates directly from the XER.
        # P6 already computed these correctly during its schedule run —
        # they account for predecessor pushes, retained logic, etc.
        # We trust them as-is rather than recomputing (which loses the
        # completed-chain cascade that P6 handles internally).
        if status == 'TK_Complete':
            stored_es = _parse_date(task.get('early_start_date', ''))
            stored_ef = _parse_date(task.get('early_end_date', ''))
            # Use P6's stored dates but never go before data_date.
            # Stored dates after data_date reflect P6's completed-chain
            # cascade (predecessor pushes). Dates before data_date are
            # stale from the original schedule and should floor to data_date.
            es = max(stored_es, data_date) if stored_es else data_date
            ef = max(stored_ef, data_date) if stored_ef else es
            act_start = _parse_date(task.get('act_start_date', ''))
            task['_act_start'] = act_start or data_date
            task['_es'] = es
            task['_ef'] = ef
            continue

        # Active tasks: trust P6's stored early dates as the baseline, then
        # check if incomplete predecessors push later (retained logic).
        # P6's stored dates reflect internal scheduling factors that are
        # impractical to replicate exactly (resource leveling, etc.)
        if status == 'TK_Active':
            stored_es = _parse_date(task.get('early_start_date', ''))
            stored_ef = _parse_date(task.get('early_end_date', ''))
            act_start = _parse_date(task.get('act_start_date', ''))
            # When sched_use_expect_end_flag=Y and expect_end_date is set,
            # P6 uses it as the expected finish instead of computed EF.
            expect_end = _parse_date(task.get('expect_end_date', '')) if use_expect_end else None
            base_es = stored_es or data_date
            base_ef = expect_end or stored_ef or add_work_hours(data_date, duration, cal)

            # Store actual dates for contribution to successors.
            # P6 uses actual start for SS/SF lag, computed EF for FS/FF.
            task['_act_start'] = act_start or base_es
            # Active tasks don't have act_end — use computed EF
            # (no _act_end set, so contribution function uses _ef)

            # Ensure not before data_date
            if base_es < data_date:
                base_es = data_date
            if base_ef < data_date:
                base_ef = add_work_hours(data_date, duration, cal)

            # Retained logic: incomplete predecessors can push ES/EF later
            for pred_id, rel in pred_map.get(tid, []):
                pred_task = tasks_by_id.get(pred_id)
                if not pred_task or pred_task.get('_es') is None:
                    continue
                if pred_task.get('status_code', '') == 'TK_Complete':
                    continue
                lag_c = _get_lag_calendar(pred_task, task, cal_lookup, lag_cal_option, default_cal_id)
                contrib = _relationship_contribution_forward(pred_task, rel, cal, lag_c)
                if contrib and contrib[0] == 'es' and contrib[1] > base_es:
                    base_es = contrib[1]
                    base_ef = add_work_hours(base_es, duration, cal)
                elif contrib and contrib[0] == 'ef' and contrib[1] > base_ef:
                    base_ef = contrib[1]
                    if duration:
                        new_es = subtract_work_hours(base_ef, duration, cal)
                        if new_es > base_es:
                            base_es = new_es
                    else:
                        base_es = base_ef

            task['_es'] = base_es
            task['_ef'] = base_ef
            continue

        # Not-started tasks: compute from predecessor relationships
        es_candidates = []
        ef_candidates = []

        for pred_id, rel in pred_map.get(tid, []):
            pred_task = tasks_by_id.get(pred_id)
            if not pred_task or pred_task.get('_es') is None:
                continue
            lag_c = _get_lag_calendar(pred_task, task, cal_lookup, lag_cal_option, default_cal_id)
            contrib = _relationship_contribution_forward(pred_task, rel, cal, lag_c)
            if contrib is None:
                continue
            if contrib[0] == 'es':
                es_candidates.append(contrib[1])
            elif contrib[0] == 'ef':
                ef_candidates.append(contrib[1])

        # --- Compute ES from FS/SS relationships ---
        if es_candidates:
            es = max(es_candidates)
        else:
            es = data_date  # No FS/SS predecessors — start at data date

        # Not-started tasks cannot start before data_date
        if es < data_date:
            es = data_date

        # Snap ES to valid work time — but NOT for finish milestones,
        # which in P6 align to the predecessor's end-of-day time.
        # Use snap_to_work_time (not next_work_start) to preserve
        # mid-period times like 15:00 within 13:00-17:00.
        is_finish_mile = task_type == 'TT_FinMile'
        if not is_finish_mile:
            es = snap_to_work_time(es, cal)

        # Compute EF from ES + duration
        ef = add_work_hours(es, duration, cal) if duration else es

        # --- Check EF-driving relationships (FF, SF) ---
        if ef_candidates:
            ef_from_rels = max(ef_candidates)
            if ef_from_rels > ef:
                # FF/SF relationship pushes EF later
                ef = ef_from_rels
                # Derive ES from this later EF (don't snap — EF-derived ES
                # can land at end-of-day, which is valid for milestones and
                # FF-driven tasks in P6)
                if duration:
                    es_from_ef = subtract_work_hours(ef, duration, cal)
                    if es_from_ef > es:
                        es = es_from_ef
                        # Recompute EF to be consistent
                        ef = add_work_hours(es, duration, cal)
                else:
                    # Zero-duration milestone: ES = EF
                    es = ef

        # Apply forward constraints
        es, ef = _apply_constraint_forward(task, es, ef, cal)

        # Re-snap ES after constraints — constraints can set ES to non-work
        # times (e.g., CS_MSOA with midnight date). Snap ensures work time.
        # For finish milestones with hard-finish constraints (CS_MEO/MFO),
        # P6 also snaps to next work start.
        if not is_finish_mile:
            es_snapped = snap_to_work_time(es, cal)
            if es_snapped != es:
                es = es_snapped
                ef = add_work_hours(es, duration, cal) if duration else es
        elif is_finish_mile and duration == 0:
            # FinMile: check if constraint pushed ES to end-of-day
            cstr = task.get('cstr_type', '')
            if cstr in _HARD_FINISH:
                es_snapped = next_work_start(es, cal)
                if es_snapped != es:
                    es = es_snapped
                    ef = es

        task['_es'] = es
        task['_ef'] = ef


# ---------------------------------------------------------------------------
# Backward pass
# ---------------------------------------------------------------------------

def _backward_pass(tasks_by_id, reverse_topo, succ_map, pred_map, cal_lookup, project_end,
                    lag_cal_option='', default_cal_id=''):
    """
    Backward pass: compute Late Start (LS) and Late Finish (LF) for all tasks.
    Results stored as _ls and _lf on each task dict.
    """
    for tid in reverse_topo:
        task = tasks_by_id[tid]
        cal = _get_calendar(task, cal_lookup)
        status = task.get('status_code', '')
        duration = _get_duration_hours(task)

        # Completed tasks: late = early
        if status == 'TK_Complete':
            task['_ls'] = task['_es']
            task['_lf'] = task['_ef']
            continue

        # Compute from successor relationships
        ls_candidates = []
        lf_candidates = []

        for succ_id, rel in succ_map.get(tid, []):
            succ_task = tasks_by_id.get(succ_id)
            if not succ_task or succ_task.get('_ls') is None:
                continue
            lag_c = _get_lag_calendar(task, succ_task, cal_lookup, lag_cal_option, default_cal_id)
            constraint = _relationship_constraint_backward(succ_task, rel, cal, lag_c)
            if constraint is None:
                continue
            if constraint[0] == 'lf':
                lf_candidates.append(constraint[1])
            elif constraint[0] == 'ls':
                ls_candidates.append(constraint[1])

        # Determine LF
        if lf_candidates:
            lf = min(lf_candidates)
        else:
            lf = project_end  # No successors — use project end

        # Determine LS from LF
        lf_derived_ls = subtract_work_hours(lf, duration, cal) if duration else lf

        # Check LS-driving relationships (SS, SF backward)
        if ls_candidates:
            ls_from_rels = min(ls_candidates)
            if ls_from_rels < lf_derived_ls:
                ls = ls_from_rels
                # Check if LS + duration < LF — if so, LF stays
                ls_derived_lf = add_work_hours(ls, duration, cal) if duration else ls
                if ls_derived_lf < lf:
                    lf = lf  # Keep the more constraining LF
            else:
                ls = lf_derived_ls
        else:
            ls = lf_derived_ls

        # Apply backward constraints
        ls, lf = _apply_constraint_backward(task, ls, lf, cal)

        task['_ls'] = ls
        task['_lf'] = lf


# ---------------------------------------------------------------------------
# Float calculation
# ---------------------------------------------------------------------------

def _compute_float(tasks_by_id, succ_map, cal_lookup):
    """Compute total float and free float for all tasks."""
    for tid, task in tasks_by_id.items():
        if '_es' not in task or '_ls' not in task:
            continue
        if task.get('_es') is None or task.get('_ls') is None:
            continue

        cal = _get_calendar(task, cal_lookup)

        # Total Float = LS - ES in work hours
        tf = work_hours_between(task['_es'], task['_ls'], cal)
        task['_tf'] = tf

        # Free Float: min slack across all successor relationships
        ff = float('inf')
        has_succ = False

        for succ_id, rel in succ_map.get(tid, []):
            succ_task = tasks_by_id.get(succ_id)
            if not succ_task or succ_task.get('_es') is None:
                continue
            has_succ = True

            pred_type = rel.get('pred_type', 'PR_FS')
            lag_hours = _safe_float(rel.get('lag_hr_cnt', 0))

            # Free float depends on relationship type
            if _is_fs(pred_type):
                # FF = Succ.ES - Pred.EF - lag (in work hours)
                gap = work_hours_between(task['_ef'], succ_task['_es'], cal) - lag_hours
            elif _is_ss(pred_type):
                gap = work_hours_between(task['_es'], succ_task['_es'], cal) - lag_hours
            elif _is_ff(pred_type):
                gap = work_hours_between(task['_ef'], succ_task['_ef'], cal) - lag_hours
            elif _is_sf(pred_type):
                gap = work_hours_between(task['_es'], succ_task['_ef'], cal) - lag_hours
            else:
                continue

            ff = min(ff, gap)

        if not has_succ:
            ff = tf  # Tasks with no successors: free float = total float

        task['_ff'] = max(0, ff) if ff != float('inf') else max(0, tf)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def schedule_forward_backward(tasks, preds, calendars, data_date,
                               schedoptions=None, project=None,
                               milestone_id=None):
    """
    Run CPM forward and backward passes on parsed XER data.

    Args:
        tasks: List of task dicts from parsed XER TASK table
        preds: List of relationship dicts from parsed XER TASKPRED table
        calendars: List of calendar dicts from parsed XER CALENDAR/CLNDR table
        data_date: "YYYY-MM-DD HH:MM" string or datetime
        schedoptions: Optional list of SCHEDOPTIONS row dicts (for lag calendar option)
        project: Optional list of PROJECT row dicts (for default calendar ID)
        milestone_id: Optional task_id of the project's terminal milestone (e.g.
            the Substantial Completion finish marker). Used only to populate the
            ``sc_milestone_*`` fields in the returned metadata -- CPM
            correctness does not depend on it (project_end is computed from the
            latest EF across all tasks). When omitted, the function calls
            :func:`milestones.resolve_default_milestone` to pick the unique
            terminal non-WBS / non-LOE / non-complete milestone. If the
            schedule has more than one terminal milestone the metadata fields
            quietly fall through to ``None`` rather than raising -- CPM is a
            foundational utility and many transitive callers don't care about
            SC. Pass ``milestone_id`` explicitly when you do.

    Returns:
        (results, metadata) where:
        - results: list of task dicts with updated fields:
            early_start_date, early_end_date, late_start_date, late_end_date,
            total_float_hr_cnt, free_float_hr_cnt, driving_path_flag
        - metadata: dict with:
            sc_milestone_id, sc_milestone_name, sc_milestone_code,
            sc_milestone_date, project_end_source
    """
    # Parse data date
    if isinstance(data_date, str):
        dd = _parse_date(data_date)
    else:
        dd = data_date
    if dd is None:
        dd = datetime.now()

    # Read scheduling options
    sched_opts = (schedoptions or [{}])[0] if schedoptions else {}
    lag_cal_option = sched_opts.get('sched_calendar_on_relationship_lag', '')
    use_expect_end = sched_opts.get('sched_use_expect_end_flag', 'N') == 'Y'
    proj_row = (project or [{}])[0] if project else {}
    default_cal_id = proj_row.get('default_clndr_id', '') or proj_row.get('clndr_id', '')

    # Build calendar lookup
    cal_lookup = build_calendar_lookup(calendars)

    # Build graph
    tasks_by_id, succ_map, pred_map, cpm_task_ids = _build_graph(tasks, preds)

    # Topological sort (with cycle detection)
    topo_order, cycle_details = _topological_sort(cpm_task_ids, pred_map, tasks_by_id)

    # Forward pass
    _forward_pass(tasks_by_id, topo_order, pred_map, succ_map, cal_lookup, dd,
                  lag_cal_option, default_cal_id, use_expect_end)

    # Determine project end for backward pass.
    # P6 uses the latest EF across all tasks (= scd_end_date in PROJECT),
    # NOT the SC milestone EF. This matters when there are activities after
    # SC (e.g., Final Completion, close-out, punch lists).
    # Resolve the terminal milestone for the metadata (informational only --
    # CPM correctness doesn't depend on it). If the caller passed
    # milestone_id, use it directly; otherwise auto-resolve via
    # resolve_default_milestone. Swallow MilestoneAmbiguousError -- a
    # multi-terminal schedule shouldn't break CPM for callers that don't
    # care about SC; consumers that need disambiguation pass milestone_id.
    sc_task = None
    if milestone_id is not None:
        for t in tasks:
            if t.get('task_id', '') == milestone_id:
                if t.get('status_code', '') != 'TK_Complete':
                    sc_task = t
                break
    else:
        try:
            resolved = resolve_default_milestone(tasks, preds)
        except MilestoneAmbiguousError:
            resolved = None
        if resolved is not None:
            for t in tasks:
                if t.get('task_id', '') == resolved:
                    sc_task = t
                    break

    # Project end = max EF across all computed tasks
    max_ef = dd
    for tid in cpm_task_ids:
        t = tasks_by_id[tid]
        if t.get('_ef') and t['_ef'] > max_ef:
            max_ef = t['_ef']
    project_end = max_ef

    # Build metadata (SC milestone info for reports, separate from backward pass endpoint)
    if sc_task and sc_task.get('task_id') in tasks_by_id:
        sc_tid = sc_task['task_id']
        sc_in_graph = tasks_by_id[sc_tid]
        metadata = {
            'sc_milestone_id': sc_tid,
            'sc_milestone_name': sc_task.get('task_name', ''),
            'sc_milestone_code': sc_task.get('task_code', ''),
            'sc_milestone_date': _format_date(sc_in_graph.get('_ef', dd)),
            'project_end_date': _format_date(project_end),
            'project_end_source': 'latest activity finish',
        }
    else:
        metadata = {
            'sc_milestone_id': None,
            'sc_milestone_name': None,
            'sc_milestone_code': None,
            'sc_milestone_date': _format_date(project_end),
            'project_end_date': _format_date(project_end),
            'project_end_source': 'latest activity finish',
        }

    # Report circular dependencies if found
    if cycle_details:
        metadata['circular_dependencies'] = cycle_details
        metadata['circular_dependency_count'] = len(cycle_details)

    # Backward pass
    reverse_topo = list(reversed(topo_order))
    _backward_pass(tasks_by_id, reverse_topo, succ_map, pred_map, cal_lookup, project_end,
                    lag_cal_option, default_cal_id)

    # ALAP: "As Late As Possible" — shifts early dates right to consume
    # free float, butting the activity against its earliest successor.
    # Process in reverse topological order so ALAP chains cascade correctly
    # (furthest-downstream ALAP shifts first, then upstream ALAP uses
    # the shifted successor dates).
    for tid in reversed(topo_order):
        t = tasks_by_id[tid]
        if t.get('status_code', '') in ('TK_Complete', 'TK_Active'):
            continue
        cstr1 = t.get('cstr_type', '')
        cstr2 = t.get('cstr_type2', '')
        if cstr1 != 'CS_ALAP' and cstr2 != 'CS_ALAP':
            continue

        cal = _get_calendar(t, cal_lookup)
        duration = _get_duration_hours(t)
        fwd_es = t.get('_es')
        if fwd_es is None:
            continue

        # For each successor relationship, compute the latest this task
        # can start without delaying that successor.
        max_es_candidates = []
        for succ_id, rel in succ_map.get(tid, []):
            succ = tasks_by_id.get(succ_id)
            if not succ or succ.get('_es') is None:
                continue
            pred_type = rel.get('pred_type', 'PR_FS')
            lag_hours = _safe_float(rel.get('lag_hr_cnt', 0))
            lag_c = _get_lag_calendar(t, succ, cal_lookup, lag_cal_option, default_cal_id)

            succ_es = succ['_es']
            succ_ef = succ['_ef']

            if _is_fs(pred_type):
                # pred EF + lag <= succ ES
                max_ef = subtract_work_hours(succ_es, lag_hours, lag_c) if lag_hours else succ_es
                max_es = subtract_work_hours(max_ef, duration, cal) if duration else max_ef
                max_es_candidates.append(max_es)
            elif _is_ss(pred_type):
                # pred ES + lag <= succ ES
                max_es = subtract_work_hours(succ_es, lag_hours, lag_c) if lag_hours else succ_es
                max_es_candidates.append(max_es)
            elif _is_ff(pred_type):
                # pred EF + lag <= succ EF
                max_ef = subtract_work_hours(succ_ef, lag_hours, lag_c) if lag_hours else succ_ef
                max_es = subtract_work_hours(max_ef, duration, cal) if duration else max_ef
                max_es_candidates.append(max_es)
            elif _is_sf(pred_type):
                # pred ES + lag <= succ EF
                max_es = subtract_work_hours(succ_ef, lag_hours, lag_c) if lag_hours else succ_ef
                max_es_candidates.append(max_es)

        if not max_es_candidates:
            continue  # No successors — ALAP has no effect

        alap_es = min(max_es_candidates)

        # ALAP can only shift later, never earlier than forward pass
        if alap_es <= fwd_es:
            continue

        t['_es'] = alap_es
        t['_ef'] = add_work_hours(alap_es, duration, cal) if duration else alap_es

    # Float calculation
    _compute_float(tasks_by_id, succ_map, cal_lookup)

    # Write results back to task dicts
    results = []
    for t in tasks:
        tid = t.get('task_id', '')
        if tid in tasks_by_id and '_es' in tasks_by_id[tid]:
            src = tasks_by_id[tid]
            t['early_start_date'] = _format_date(src.get('_es'))
            t['early_end_date'] = _format_date(src.get('_ef'))
            t['late_start_date'] = _format_date(src.get('_ls'))
            t['late_end_date'] = _format_date(src.get('_lf'))
            t['total_float_hr_cnt'] = str(round(src.get('_tf', 0), 2))
            t['free_float_hr_cnt'] = str(round(src.get('_ff', 0), 2))
            t['driving_path_flag'] = 'Y' if src.get('_tf', 999) <= 0 else 'N'
        results.append(t)

    return results, metadata


# ---------------------------------------------------------------------------
# Path extraction (post-processing on schedule_forward_backward results)
# ---------------------------------------------------------------------------

# Constraints that pin a task to a finish-by date — treat as key end-states
_PATH_END_CONSTRAINTS = {'CS_FNLT', 'CS_MEOB', 'CS_MFO', 'CS_MEO',
                          'CS_MANDFIN', 'CS_MANDEND'}

# Near-critical threshold in working hours (5 working days at 8 hrs/day)
_NEAR_CRITICAL_HR = 40


def _path_task_summary(t, task_id):
    """Compact dict for a task in a path chain."""
    tf_hr = _safe_float(t.get('total_float_hr_cnt', 0))
    return {
        'id': t.get('task_code', '') or task_id,
        'task_id': task_id,
        'name': t.get('task_name', ''),
        'early_start': (t.get('early_start_date', '') or '')[:10],
        'early_end': (t.get('early_end_date', '') or '')[:10],
        'total_float_days': round(tf_hr / 8, 1),
    }


def _build_path_maps(results, preds):
    """Build pred/succ adjacency maps scoped to schedulable tasks."""
    skip_types = {'TT_WBS', 'TT_LOE'}
    tasks_by_id = {t.get('task_id', ''): t for t in results}
    cpm_ids = {tid for tid, t in tasks_by_id.items()
               if t.get('task_type', '') not in skip_types and tid}

    pred_map = defaultdict(list)
    succ_map = defaultdict(list)
    for r in preds:
        succ_id = r.get('task_id', '')
        pred_id = r.get('pred_task_id', '')
        if succ_id in cpm_ids and pred_id in cpm_ids:
            pred_map[succ_id].append(pred_id)
            succ_map[pred_id].append(succ_id)
    return tasks_by_id, cpm_ids, pred_map, succ_map


def _trace_back(end_id, tasks_by_id, pred_map):
    """Walk backwards picking least-float predecessor. Returns earliest-to-end order."""
    chain = []
    current = end_id
    visited = set()
    while current and current not in visited:
        chain.append(current)
        visited.add(current)
        best_pred, best_float = None, float('inf')
        for pred_id in pred_map.get(current, []):
            if pred_id in visited:
                continue
            tf = _safe_float(tasks_by_id.get(pred_id, {}).get('total_float_hr_cnt', 999))
            if tf < best_float:
                best_float = tf
                best_pred = pred_id
        current = best_pred
    return list(reversed(chain))


def _trace_forward(start_id, tasks_by_id, succ_map, max_steps=50):
    """Walk forward picking least-float successor. Returns start-to-furthest order."""
    chain = [start_id]
    visited = {start_id}
    current = start_id
    while len(chain) < max_steps:
        best_succ, best_float = None, float('inf')
        for s in succ_map.get(current, []):
            if s in visited:
                continue
            tf = _safe_float(tasks_by_id.get(s, {}).get('total_float_hr_cnt', 999))
            if tf < best_float:
                best_float = tf
                best_succ = s
        if best_succ is None:
            break
        chain.append(best_succ)
        visited.add(best_succ)
        current = best_succ
    return chain


def _find_parallel_branches(tasks_by_id, succ_map, cpm_ids, limit=10):
    """Find diverge-then-converge subgraphs ranked by criticality."""
    branches = []
    seen_pairs = set()

    for tid in cpm_ids:
        succs = [s for s in succ_map.get(tid, []) if s in cpm_ids]
        if len(succs) < 2:
            continue
        for i in range(len(succs)):
            for j in range(i + 1, len(succs)):
                s1, s2 = succs[i], succs[j]
                key = (tid,) + tuple(sorted([s1, s2]))
                if key in seen_pairs:
                    continue
                seen_pairs.add(key)

                chain1 = _trace_forward(s1, tasks_by_id, succ_map)
                chain2 = _trace_forward(s2, tasks_by_id, succ_map)
                set1 = set(chain1)
                converge = next((t for t in chain2 if t in set1), None)
                if not converge or converge in (s1, s2):
                    continue

                idx1 = chain1.index(converge)
                idx2 = chain2.index(converge)
                b1 = chain1[:idx1 + 1]
                b2 = chain2[:idx2 + 1]
                # Need both branches to be more than just the convergence node
                if len(b1) < 2 or len(b2) < 2:
                    continue

                all_ids = b1 + b2
                min_float_hr = min(
                    _safe_float(tasks_by_id.get(c, {}).get('total_float_hr_cnt', 999))
                    for c in all_ids
                )
                branches.append({
                    'diverge_at': _path_task_summary(tasks_by_id.get(tid, {}), tid),
                    'converge_at': _path_task_summary(tasks_by_id.get(converge, {}), converge),
                    'min_float_days': round(min_float_hr / 8, 1),
                    'branches': [
                        [_path_task_summary(tasks_by_id.get(c, {}), c) for c in b1],
                        [_path_task_summary(tasks_by_id.get(c, {}), c) for c in b2],
                    ],
                })

    branches.sort(key=lambda b: b['min_float_days'])
    return branches[:limit]


def extract_paths(results, metadata, preds):
    """
    Post-processing on schedule_forward_backward() output. Walks driving-path
    flags backwards from key end-states (SC milestone, project_end, FNLT-
    constrained tasks) to produce ordered chains. Identifies critical and
    near-critical sequences and parallel branches.

    Args:
        results: list of task dicts from schedule_forward_backward
        metadata: metadata dict from schedule_forward_backward
        preds: list of relationship dicts (TASKPRED rows) — same input that
               was passed to schedule_forward_backward

    Returns:
        {
            'critical_path': [task_summary, ...],
            'near_critical': [{float_days, length, chain}, ...],
            'driving_paths': [{to, end_task_id, end_task_code, chain}, ...],
            'parallel_branches': [{diverge_at, converge_at, min_float_days, branches}, ...],
        }
    """
    tasks_by_id, cpm_ids, pred_map, succ_map = _build_path_maps(results, preds)

    # ------------------------------------------------------------------
    # Identify key end-states
    # ------------------------------------------------------------------
    end_states = []  # list of (label, task_id)
    seen_ends = set()

    sc_id = metadata.get('sc_milestone_id') if metadata else None
    if sc_id and sc_id in tasks_by_id:
        end_states.append(('SC milestone', sc_id))
        seen_ends.add(sc_id)

    # Project end = task with the latest early finish
    proj_end_id, proj_end_dt = None, None
    for tid in cpm_ids:
        ef = _parse_date(tasks_by_id[tid].get('early_end_date', ''))
        if ef and (proj_end_dt is None or ef > proj_end_dt):
            proj_end_dt, proj_end_id = ef, tid
    if proj_end_id and proj_end_id not in seen_ends:
        end_states.append(('project_end', proj_end_id))
        seen_ends.add(proj_end_id)

    # FNLT-constrained tasks
    for tid in cpm_ids:
        t = tasks_by_id[tid]
        cstr = t.get('cstr_type', '') or t.get('constraint_type', '')
        cstr2 = t.get('cstr_type2', '')
        if cstr in _PATH_END_CONSTRAINTS or cstr2 in _PATH_END_CONSTRAINTS:
            if tid not in seen_ends:
                label = f"FNLT: {t.get('task_code', '') or tid}"
                end_states.append((label, tid))
                seen_ends.add(tid)

    # ------------------------------------------------------------------
    # Driving paths: full trace_back from each end-state.
    # The critical path is whichever driving path yields the longest run
    # of TF<=0 tasks (project_end may be a punch-list / warranty tail that
    # isn't the canonical critical chain — SC milestone is more reliable).
    # ------------------------------------------------------------------
    driving_paths = []
    best_crit_chain = []  # longest TF<=0 sequence across all driving paths
    for label, end_id in end_states:
        chain_ids = _trace_back(end_id, tasks_by_id, pred_map)
        if not chain_ids:
            continue
        end_task = tasks_by_id.get(end_id, {})
        driving_paths.append({
            'to': label,
            'end_task_id': end_id,
            'end_task_code': end_task.get('task_code', '') or end_id,
            'end_task_name': end_task.get('task_name', ''),
            'chain': [_path_task_summary(tasks_by_id[tid], tid) for tid in chain_ids],
        })

        # Collect contiguous TF<=0 segment for critical-path candidate
        crit_segment = [
            tid for tid in chain_ids
            if _safe_float(tasks_by_id[tid].get('total_float_hr_cnt', 999)) <= 0.01
        ]
        if len(crit_segment) > len(best_crit_chain):
            best_crit_chain = crit_segment

    critical_path = [_path_task_summary(tasks_by_id[tid], tid) for tid in best_crit_chain]

    # ------------------------------------------------------------------
    # Near-critical chains: 0 < TF < 40 hr (5 working days), grouped
    # ------------------------------------------------------------------
    near_set = set()
    for tid in cpm_ids:
        tf = _safe_float(tasks_by_id[tid].get('total_float_hr_cnt', 999))
        if 0 < tf < _NEAR_CRITICAL_HR:
            near_set.add(tid)

    near_chains = []
    used = set()
    # Order tails by latest EF first so longer downstream chains anchor first
    def _ef_key(tid):
        dt = _parse_date(tasks_by_id[tid].get('early_end_date', ''))
        return dt.timestamp() if dt else 0

    for tid in sorted(near_set, key=_ef_key, reverse=True):
        if tid in used:
            continue
        # Only seed from a "tail" — task whose successors are not near-critical
        if any(s in near_set for s in succ_map.get(tid, [])):
            continue
        chain = []
        current = tid
        while current and current in near_set and current not in used:
            chain.append(current)
            used.add(current)
            best_pred, best_float = None, float('inf')
            for pred_id in pred_map.get(current, []):
                if pred_id in near_set and pred_id not in used:
                    tf = _safe_float(tasks_by_id[pred_id].get('total_float_hr_cnt', 999))
                    if tf < best_float:
                        best_float = tf
                        best_pred = pred_id
            current = best_pred
        if not chain:
            continue
        chain.reverse()
        chain_min_hr = min(
            _safe_float(tasks_by_id[c].get('total_float_hr_cnt', 999))
            for c in chain
        )
        near_chains.append({
            'float_days': round(chain_min_hr / 8, 1),
            'length': len(chain),
            'chain': [_path_task_summary(tasks_by_id[c], c) for c in chain],
        })
    near_chains.sort(key=lambda c: (c['float_days'], -c['length']))

    # ------------------------------------------------------------------
    # Parallel branches: diverge-then-converge subgraphs
    # ------------------------------------------------------------------
    parallel_branches = _find_parallel_branches(tasks_by_id, succ_map, cpm_ids)

    return {
        'critical_path': critical_path,
        'near_critical': near_chains,
        'driving_paths': driving_paths,
        'parallel_branches': parallel_branches,
    }


# ---------------------------------------------------------------------------
# Activities JSON export (consumed by build_gantt_html.py)
# ---------------------------------------------------------------------------

def _wbs_lookup(wbs_rows):
    """{wbs_id: {wbs_name, parent_wbs_id, level}} from XER PROJWBS rows."""
    by_id = {}
    if not wbs_rows:
        return by_id
    for w in wbs_rows:
        wid = w.get('wbs_id', '')
        if not wid:
            continue
        by_id[wid] = {
            'wbs_id': wid,
            'wbs_name': w.get('wbs_name', '') or w.get('wbs_short_name', ''),
            'parent_wbs_id': w.get('parent_wbs_id', '') or '',
            'seq_num': w.get('seq_num', '') or '',
        }
    # Compute depth via parent chain
    def depth(wid, seen=None):
        seen = seen or set()
        if wid in seen or wid not in by_id:
            return 0
        seen.add(wid)
        parent = by_id[wid].get('parent_wbs_id', '')
        if not parent or parent not in by_id:
            return 1
        return 1 + depth(parent, seen)
    for wid, info in by_id.items():
        info['level'] = depth(wid)
    return by_id


def build_activities_json(results, metadata, preds, project_name=None,
                           data_date=None, wbs_rows=None, default_view=None,
                           version=None):
    """
    Build the schedule-activities.json structure consumed by build_gantt_html.py.

    Includes the activity list with WBS hierarchy + the `paths` analytics
    section (critical, near-critical, driving paths, parallel branches).

    Args:
        results: task list after schedule_forward_backward
        metadata: metadata from schedule_forward_backward
        preds: TASKPRED rows
        project_name: optional project display name
        data_date: optional data date string
        wbs_rows: optional PROJWBS rows for hierarchy
        default_view: optional dict with px_per_day / display_unit /
            scroll_left / scroll_top / expanded_ids / table_width_px.
            When the user clicks "Copy for Claude" with the Default-view
            checkbox on, the pasted payload includes a `default_view`
            block; pass it through here so the next HTML render restores
            the same zoom, units, scroll, expand state, and splitter width.

    Returns: dict ready to serialize as JSON
    """
    skip_types = {'TT_LOE'}  # WBS rows are emitted as summary nodes, but actual
                              # XER WBS task-rows (TT_WBS) are excluded since
                              # PROJWBS provides the hierarchy
    wbs_by_id = _wbs_lookup(wbs_rows)

    activities = []
    pred_lookup = defaultdict(list)
    for r in preds:
        succ_id = r.get('task_id', '')
        pred_id = r.get('pred_task_id', '')
        ptype = r.get('pred_type', 'PR_FS')
        lag = _safe_float(r.get('lag_hr_cnt', 0))
        pred_lookup[succ_id].append({
            'pred_task_id': pred_id,
            'type': ptype,
            'lag_hr': lag,
        })

    # Emit WBS summary rows first
    for wid, info in wbs_by_id.items():
        activities.append({
            'id': wid,
            'task_id': wid,
            'name': info['wbs_name'],
            'parent': info.get('parent_wbs_id') or None,
            'wbs_level': info.get('level', 1),
            'is_summary': True,
            'kind': 'wbs',
        })

    # Emit task rows
    for t in results:
        ttype = t.get('task_type', '')
        if ttype in skip_types:
            continue
        if ttype == 'TT_WBS':
            continue  # PROJWBS provides hierarchy; these dummy rows are skipped
        tid = t.get('task_id', '')
        if not tid:
            continue
        es = _parse_date(t.get('early_start_date', ''))
        ef = _parse_date(t.get('early_end_date', ''))
        ls = _parse_date(t.get('late_start_date', ''))
        lf = _parse_date(t.get('late_end_date', ''))
        tf_hr = _safe_float(t.get('total_float_hr_cnt', 0))
        ff_hr = _safe_float(t.get('free_float_hr_cnt', 0))
        wbs_id = t.get('wbs_id', '') or None
        wbs_level = wbs_by_id.get(wbs_id, {}).get('level', 0) + 1 if wbs_id else 1

        is_milestone = ttype in ('TT_Mile', 'TT_FinMile')
        progress = 100 if t.get('status_code', '') == 'TK_Complete' else (
            50 if t.get('status_code', '') == 'TK_Active' else 0
        )

        activities.append({
            'id': t.get('task_code', '') or tid,
            'task_id': tid,
            'task_code': t.get('task_code', ''),
            'name': t.get('task_name', ''),
            'parent': wbs_id,
            'wbs_id': wbs_id,
            'wbs_level': wbs_level,
            'is_summary': False,
            'is_milestone': is_milestone,
            'kind': 'milestone' if is_milestone else 'task',
            'task_type': ttype,
            'status': t.get('status_code', ''),
            'progress': progress,
            'start': _format_date(es) if es else '',
            'end': _format_date(ef) if ef else '',
            'early_start': _format_date(es) if es else '',
            'early_end': _format_date(ef) if ef else '',
            'late_start': _format_date(ls) if ls else '',
            'late_end': _format_date(lf) if lf else '',
            'total_float_days': round(tf_hr / 8, 1),
            'free_float_days': round(ff_hr / 8, 1),
            'driving_path': t.get('driving_path_flag', '') == 'Y',
            'dependencies': pred_lookup.get(tid, []),
        })

    paths = extract_paths(results, metadata or {}, preds)

    sc_md = metadata or {}
    out = {
        'project': {
            'name': project_name or '',
            'version': version,
            'data_date': (data_date if isinstance(data_date, str) else _format_date(data_date)) if data_date else '',
            'sc_milestone_name': sc_md.get('sc_milestone_name', ''),
            'sc_milestone_code': sc_md.get('sc_milestone_code', ''),
            'sc_milestone_date': sc_md.get('sc_milestone_date', ''),
            'project_end_date': sc_md.get('project_end_date', ''),
            'project_end_source': sc_md.get('project_end_source', ''),
        },
        'activities': activities,
        'paths': paths,
        'circular_dependencies': sc_md.get('circular_dependencies', []),
    }
    if default_view:
        out['default_view'] = default_view
    return out


# ---------------------------------------------------------------------------
# HTML Report
# ---------------------------------------------------------------------------

_WESTLAND_CSS = """
body { font-family: 'Segoe UI', Tahoma, sans-serif; margin: 0; padding: 0; background: #f5f5f5; }
.header { background: #1a3a4a; color: white; padding: 24px 32px; }
.header h1 { margin: 0 0 8px 0; font-size: 22px; font-weight: 600; }
.header .tracking { color: #8cc; font-size: 14px; margin-top: 4px; }
.header .meta { color: #acd; font-size: 13px; margin-top: 2px; }
.summary { display: flex; gap: 24px; padding: 16px 32px; background: white; border-bottom: 1px solid #ddd; }
.stat-box { text-align: center; padding: 12px 24px; }
.stat-box .num { font-size: 28px; font-weight: 700; }
.stat-box .label { font-size: 12px; color: #666; text-transform: uppercase; }
.critical .num { color: #c0392b; }
.near-crit .num { color: #e67e22; }
.healthy .num { color: #27ae60; }
table { width: 100%; border-collapse: collapse; margin: 0; font-size: 13px; }
th { background: #2c3e50; color: white; padding: 8px 10px; text-align: left; cursor: pointer;
     position: sticky; top: 0; user-select: none; }
th:hover { background: #34495e; }
td { padding: 6px 10px; border-bottom: 1px solid #eee; }
tr:hover { background: #f0f7ff; }
tr.critical { background: #fde8e8; }
tr.critical:hover { background: #fbd4d4; }
tr.near-critical { background: #fef3e2; }
tr.near-critical:hover { background: #fde8c8; }
.container { margin: 0 auto; background: white; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }
.float-val { font-weight: 600; }
.neg-float { color: #c0392b; }
.zero-float { color: #c0392b; }
.low-float { color: #e67e22; }
.ok-float { color: #27ae60; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: 600; }
.tag-critical { background: #c0392b; color: white; }
.tag-active { background: #2980b9; color: white; }
.tag-complete { background: #27ae60; color: white; }
.tag-notstart { background: #95a5a6; color: white; }
"""

_SORT_JS = """
function sortTable(n) {
  var table = document.getElementById('schedule');
  var rows = Array.from(table.tBodies[0].rows);
  var asc = table.getAttribute('data-sort-col') == n && table.getAttribute('data-sort-dir') == 'asc';
  rows.sort(function(a, b) {
    var va = a.cells[n].getAttribute('data-val') || a.cells[n].textContent;
    var vb = b.cells[n].getAttribute('data-val') || b.cells[n].textContent;
    var na = parseFloat(va), nb = parseFloat(vb);
    if (!isNaN(na) && !isNaN(nb)) return asc ? nb - na : na - nb;
    return asc ? vb.localeCompare(va) : va.localeCompare(vb);
  });
  var tbody = table.tBodies[0];
  rows.forEach(function(r) { tbody.appendChild(r); });
  table.setAttribute('data-sort-col', n);
  table.setAttribute('data-sort-dir', asc ? 'desc' : 'asc');
}
"""


def render_schedule_html(tasks, project_name, data_date, metadata, output_path):
    """
    Write standalone HTML schedule report.

    Args:
        tasks: List of task dicts (after schedule_forward_backward)
        project_name: Project name for header
        data_date: Data date string
        metadata: cpm_metadata dict from schedule_forward_backward
        output_path: Path to write HTML file
    """
    skip_types = {'TT_WBS', 'TT_LOE'}
    sched_tasks = [t for t in tasks if t.get('task_type', '') not in skip_types
                   and t.get('early_start_date', '')]

    # Stats
    total = len(sched_tasks)
    critical = sum(1 for t in sched_tasks if _safe_float(t.get('total_float_hr_cnt', 999)) <= 0)
    near_crit = sum(1 for t in sched_tasks if 0 < _safe_float(t.get('total_float_hr_cnt', 999)) <= 80)
    float_vals = [_safe_float(t.get('total_float_hr_cnt', 0)) / 8 for t in sched_tasks]
    avg_float = round(sum(float_vals) / max(len(float_vals), 1), 1)

    # Tracking info
    if metadata.get('sc_milestone_name'):
        tracking = (f"Tracking to: {metadata['sc_milestone_name']} "
                    f"[{metadata.get('sc_milestone_code', '')}] — {metadata.get('sc_milestone_date', '')}")
    else:
        tracking = f"No SC milestone found — tracking to latest activity finish ({metadata.get('sc_milestone_date', '')})"

    # Build rows
    rows_html = []
    for t in sched_tasks:
        tf_hrs = _safe_float(t.get('total_float_hr_cnt', 0))
        ff_hrs = _safe_float(t.get('free_float_hr_cnt', 0))
        tf_days = round(tf_hrs / 8, 1)
        ff_days = round(ff_hrs / 8, 1)

        # Row class
        if tf_hrs <= 0:
            row_class = 'critical'
        elif tf_hrs <= 80:
            row_class = 'near-critical'
        else:
            row_class = ''

        # Float styling
        if tf_hrs < 0:
            float_class = 'neg-float'
        elif tf_hrs == 0:
            float_class = 'zero-float'
        elif tf_hrs <= 80:
            float_class = 'low-float'
        else:
            float_class = 'ok-float'

        # Status tag
        status = t.get('status_code', '')
        if status == 'TK_Complete':
            status_tag = '<span class="tag tag-complete">Complete</span>'
        elif status == 'TK_Active':
            status_tag = '<span class="tag tag-active">Active</span>'
        else:
            status_tag = '<span class="tag tag-notstart">Not Started</span>'

        # Critical tag
        crit_tag = '<span class="tag tag-critical">CRITICAL</span>' if tf_hrs <= 0 else ''

        code = t.get('task_code', '') or t.get('task_id', '')
        name = t.get('task_name', '')
        es = t.get('early_start_date', '')[:10]
        ef = t.get('early_end_date', '')[:10]
        ls = t.get('late_start_date', '')[:10]
        lf = t.get('late_end_date', '')[:10]

        rows_html.append(
            f'<tr class="{row_class}">'
            f'<td>{code}</td>'
            f'<td>{name}</td>'
            f'<td>{es}</td><td>{ef}</td>'
            f'<td>{ls}</td><td>{lf}</td>'
            f'<td class="float-val {float_class}" data-val="{tf_days}">{tf_days}</td>'
            f'<td class="float-val" data-val="{ff_days}">{ff_days}</td>'
            f'<td>{status_tag}</td>'
            f'<td>{crit_tag}</td>'
            f'</tr>'
        )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Schedule Report — {project_name}</title>
<style>{_WESTLAND_CSS}</style></head><body>
<div class="container">
<div class="header">
  <h1>Schedule Report — {project_name}</h1>
  <div class="tracking">{tracking}</div>
  <div class="meta">Data Date: {data_date} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
</div>
<div class="summary">
  <div class="stat-box"><div class="num">{total}</div><div class="label">Activities</div></div>
  <div class="stat-box critical"><div class="num">{critical}</div><div class="label">Critical</div></div>
  <div class="stat-box near-crit"><div class="num">{near_crit}</div><div class="label">Near-Critical</div></div>
  <div class="stat-box healthy"><div class="num">{avg_float}d</div><div class="label">Avg Float</div></div>
</div>
<table id="schedule">
<thead><tr>
  <th onclick="sortTable(0)">Activity ID</th>
  <th onclick="sortTable(1)">Name</th>
  <th onclick="sortTable(2)">Early Start</th>
  <th onclick="sortTable(3)">Early Finish</th>
  <th onclick="sortTable(4)">Late Start</th>
  <th onclick="sortTable(5)">Late Finish</th>
  <th onclick="sortTable(6)">TF (days)</th>
  <th onclick="sortTable(7)">FF (days)</th>
  <th onclick="sortTable(8)">Status</th>
  <th onclick="sortTable(9)">Critical</th>
</tr></thead>
<tbody>
{''.join(rows_html)}
</tbody>
</table>
</div>
<script>{_SORT_JS}</script>
</body></html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return output_path
