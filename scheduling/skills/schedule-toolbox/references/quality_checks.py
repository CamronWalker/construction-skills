"""
quality_checks.py -- Individual Schedule Quality Check Functions

One function per SmartPM metric. Each returns a consistent JSON-serializable dict.
Pass already-parsed, already-scope-filtered tasks and preds for best results.
Scope filtering (exclude TK_Complete, TT_WBS, TT_LOE) happens automatically in CLI mode.

==============================================================================
!!!!!!!!!!!!!!!!!!  CRITICAL RULE -- NEVER WRITE XER FILES  !!!!!!!!!!!!!!!!!!
THIS MODULE IS READ-ONLY. IT ANALYZES PARSED XER DATA IN MEMORY ONLY.
NEVER WRITE, MODIFY, OR OVERWRITE ANY XER FILE UNDER ANY CIRCUMSTANCES.
HISTORICAL SCHEDULE RECORDS MUST NEVER BE ALTERED BY ANALYSIS TOOLS.
==============================================================================

CLI Usage:
  python quality_checks.py <check_name> <xer_path>
  python quality_checks.py all <xer_path>

Available check names:
  finish_to_start    start_to_start      finish_to_finish    start_to_finish
  critical_path_pct  avg_total_float     constraints         high_duration
  high_float         low_float           missing_logic       negative_lag
  positive_lag       total_relationships riding_data_date    missing_actual_finish
  convergence        dangling            divergence          duplicate_rels
  future_actual      hard_constraints    soft_constraints    unstatused
  negative_float     one_day             out_of_sequence     remaining_dur_discrepancy
  started_with_zero  sc_coverage         all

Output: JSON to stdout. tasks[] always includes task_id, task_code, task_name.
"""

from collections import defaultdict, Counter
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


def _task_rec(t):
    return {
        'task_id': t.get('task_id', ''),
        'task_code': t.get('task_code', ''),
        'task_name': t.get('task_name', ''),
    }


def _rel_rec(pred_task, succ_task, rel):
    return {
        'pred_id': rel.get('pred_task_id', ''),
        'pred_code': pred_task.get('task_code', '') if pred_task else '',
        'pred_name': pred_task.get('task_name', '') if pred_task else '',
        'succ_id': rel.get('task_id', ''),
        'succ_code': succ_task.get('task_code', '') if succ_task else '',
        'succ_name': succ_task.get('task_name', '') if succ_task else '',
        'pred_type': rel.get('pred_type', ''),
        'lag_days': round(_safe_float(rel.get('lag_hr_cnt', 0)) / 8, 2),
    }


def _result(check, label, scored, count, total, pct, threshold, status, deduction_pts=0, **extras):
    r = {
        'check': check,
        'label': label,
        'scored': scored,
        'deduction_pts': deduction_pts,
        'count': count,
        'total': total,
        'pct': pct,
        'threshold': threshold,
        'status': status,
    }
    r.update(extras)
    return r


def _is_fs(pt): return pt in ('FS', 'PR_FS')
def _is_ss(pt): return pt in ('SS', 'PR_SS')
def _is_ff(pt): return pt in ('FF', 'PR_FF')
def _is_sf(pt): return pt in ('SF', 'PR_SF')


# ==============================================================================
# PARSE XER (used in CLI mode only -- never writes)
# ==============================================================================

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


def _scope_filter(tasks, preds, sc_filter=True):
    """Return (filtered_tasks, filtered_preds, task_by_id). Excludes complete/WBS/LOE."""
    exc = {'TT_WBS', 'TT_LOE'}
    incomplete = [t for t in tasks
                  if t.get('status_code', '') != 'TK_Complete'
                  and t.get('task_type', '') not in exc]

    if sc_filter:
        sc_id = _find_sc(tasks)
        if sc_id:
            sc_scope = _sc_predecessors(sc_id, preds)
            incomplete = [t for t in incomplete if t['task_id'] in sc_scope]

    inc_ids = {t['task_id'] for t in incomplete}
    inc_preds = [p for p in preds
                 if p.get('task_id', '') in inc_ids
                 and p.get('pred_task_id', '') in inc_ids]
    task_by_id = {t['task_id']: t for t in incomplete}
    return incomplete, inc_preds, task_by_id


def _find_sc(tasks):
    """Find Substantial Completion milestone task_id."""
    exc = {'TT_WBS', 'TT_LOE'}
    mile = {'TT_Mile', 'TT_FinMile'}
    candidates = [t for t in tasks
                  if t.get('status_code', '') != 'TK_Complete'
                  and t.get('task_type', '') not in exc]
    # Priority 1: "Substantial Completion" + "Turnover"
    for t in candidates:
        n = t.get('task_name', '')
        if 'Substantial Completion' in n and ('Turnover' in n or 'Owner' in n):
            return t['task_id']
    # Priority 2: Exact milestone
    for t in candidates:
        if t.get('task_type', '') in mile and 'Substantial Completion' in t.get('task_name', ''):
            return t['task_id']
    # Priority 3: Any task with "Substantial Completion"
    for t in candidates:
        if 'Substantial Completion' in t.get('task_name', ''):
            return t['task_id']
    return None


def _sc_predecessors(sc_id, preds):
    """Return all transitive predecessor task_ids of sc_id."""
    succ_to_preds = defaultdict(set)
    for p in preds:
        succ_to_preds[p.get('task_id', '')].add(p.get('pred_task_id', ''))
    visited = set()
    queue = [sc_id]
    while queue:
        tid = queue.pop()
        if tid in visited:
            continue
        visited.add(tid)
        for pid in succ_to_preds.get(tid, set()):
            if pid not in visited:
                queue.append(pid)
    return visited


def _activities(tasks):
    """Non-milestone incomplete activities."""
    mile = {'TT_Mile', 'TT_FinMile'}
    return [t for t in tasks if t.get('task_type', '') not in mile]


def _end_of_project(tasks):
    """True if schedule is in end-of-project state (< 50 incomplete activities).
    SmartPM uses looser thresholds in this state."""
    acts = _activities(tasks)
    return len(acts) < 50


# ==============================================================================
# ============================================================
# CHECK: FINISH TO START RELATIONSHIPS
# ============================================================

def check_finish_to_start(tasks, preds, data_date=None):
    """FS relationships as % of total. Target >= 90% (scored)."""
    acts = _activities(tasks)
    n_act = len(acts)
    n = len(preds)
    fs = sum(1 for p in preds if _is_fs(p.get('pred_type', '')))
    pct = round(fs / max(n, 1) * 100, 1)
    eop = _end_of_project(acts)
    target = 80 if eop else 90
    if pct >= target:
        ded, status = 0, 'PASS'
    elif pct >= (target - 10):
        ded, status = 1.0, 'FAIL'
    else:
        ded, status = 2.0, 'FAIL'
    return _result('finish_to_start', 'Finish to Start', True, fs, n, pct,
                   f'>= {target}%', status, ded,
                   note='Maximize FS ties. Low FS % means SS/FF overuse.')


# ============================================================
# CHECK: START TO START RELATIONSHIPS
# ============================================================

def check_start_to_start(tasks, preds, data_date=None):
    """SS relationships as % of total. Target <= 10% (scored)."""
    task_by_id = {t['task_id']: t for t in tasks}
    n = len(preds)
    ss_rels = [p for p in preds if _is_ss(p.get('pred_type', ''))]
    pct = round(len(ss_rels) / max(n, 1) * 100, 1)
    eop = _end_of_project(_activities(tasks))
    limit = 15 if eop else 10
    if pct <= limit:
        ded, status = 0, 'PASS'
    elif pct <= limit + 5:
        ded, status = 1.0, 'FAIL'
    else:
        ded, status = 2.0, 'FAIL'
    rels = [_rel_rec(task_by_id.get(p.get('pred_task_id', '')),
                     task_by_id.get(p.get('task_id', '')), p) for p in ss_rels]
    return _result('start_to_start', 'Start to Start', True, len(ss_rels), n, pct,
                   f'<= {limit}%', status, ded, relationships=rels,
                   note='High SS % indicates compressed or under-detailed schedule.')


# ============================================================
# CHECK: FINISH TO FINISH RELATIONSHIPS
# ============================================================

def check_finish_to_finish(tasks, preds, data_date=None):
    """FF relationships as % of total. Target <= 10% (scored)."""
    task_by_id = {t['task_id']: t for t in tasks}
    n = len(preds)
    ff_rels = [p for p in preds if _is_ff(p.get('pred_type', ''))]
    pct = round(len(ff_rels) / max(n, 1) * 100, 1)
    eop = _end_of_project(_activities(tasks))
    limit = 15 if eop else 10
    if pct <= limit:
        ded, status = 0, 'PASS'
    elif pct <= limit + 5:
        ded, status = 1.0, 'FAIL'
    else:
        ded, status = 2.0, 'FAIL'
    rels = [_rel_rec(task_by_id.get(p.get('pred_task_id', '')),
                     task_by_id.get(p.get('task_id', '')), p) for p in ff_rels]
    return _result('finish_to_finish', 'Finish to Finish', True, len(ff_rels), n, pct,
                   f'<= {limit}%', status, ded, relationships=rels,
                   note='High FF % indicates compressed or under-detailed schedule.')


# ============================================================
# CHECK: START TO FINISH RELATIONSHIPS
# ============================================================

def check_start_to_finish(tasks, preds, data_date=None):
    """SF relationships. Target: 0 (scored). SF logic is almost never appropriate."""
    task_by_id = {t['task_id']: t for t in tasks}
    n = len(preds)
    sf_rels = [p for p in preds if _is_sf(p.get('pred_type', ''))]
    pct = round(len(sf_rels) / max(n, 1) * 100, 1)
    ded = 2.0 if sf_rels else 0
    status = 'FAIL' if sf_rels else 'PASS'
    rels = [_rel_rec(task_by_id.get(p.get('pred_task_id', '')),
                     task_by_id.get(p.get('task_id', '')), p) for p in sf_rels]
    return _result('start_to_finish', 'Start to Finish', True, len(sf_rels), n, pct,
                   '0 relationships', status, ded, relationships=rels,
                   note='SF logic is bad practice. Replace with FS/SS/FF.')


# ============================================================
# CHECK: CRITICAL PATH PERCENT
# ============================================================

def check_critical_path_pct(tasks, preds, data_date=None):
    """% of incomplete tasks on critical path (float <= 1hr). Target 10-20% (scored)."""
    n = len(tasks)
    critical = [t for t in tasks if abs(_safe_float(t.get('total_float_hr_cnt', 0))) <= 8]
    pct = round(len(critical) / max(n, 1) * 100, 1)
    avg_float = sum(_safe_float(t.get('total_float_hr_cnt', 0)) for t in _activities(tasks))
    avg_float_days = avg_float / max(len(_activities(tasks)), 1) / 8
    if avg_float_days < 0:
        return _result('critical_path_pct', 'Critical Path %', True, len(critical), n, pct,
                       '10-20%', 'SKIP', 0,
                       tasks=[{**_task_rec(t), 'float_days': round(_safe_float(t.get('total_float_hr_cnt', 0)) / 8, 1)} for t in critical],
                       note='Skipped: negative avg float schedule.')
    eop = _end_of_project(_activities(tasks))
    lo, hi = (5, 60) if eop else (10, 40)
    if lo <= pct <= hi:
        ded, status = 0, 'PASS'
    elif (lo - 5) <= pct <= (hi + 15):
        ded, status = 1.5, 'FAIL'
    else:
        ded, status = 2.5, 'FAIL'
    return _result('critical_path_pct', 'Critical Path %', True, len(critical), n, pct,
                   f'{lo}-{hi}%', status, ded,
                   tasks=[{**_task_rec(t), 'float_days': round(_safe_float(t.get('total_float_hr_cnt', 0)) / 8, 1)} for t in critical],
                   note='Too few: sparse logic. Too many: compressed schedule.')


# ============================================================
# CHECK: AVERAGE ACTIVITY TOTAL FLOAT
# ============================================================

def check_avg_total_float(tasks, preds=None, data_date=None):
    """Average total float of incomplete activities in days (scored)."""
    acts = _activities(tasks)
    n = len(acts)
    if n == 0:
        return _result('avg_total_float', 'Average Activity Total Float', True, 0, 0, 0,
                       '15-44 days', 'PASS', 0, value_days=0)
    avg_days = round(sum(_safe_float(t.get('total_float_hr_cnt', 0)) for t in acts) / n / 8, 1)
    eop = _end_of_project(acts)
    if eop:
        ded = 1.0 if avg_days < 5 else 0
    else:
        if avg_days < 10:
            ded = 2.0
        elif avg_days < 15:
            ded = 1.0
        elif avg_days > 44:
            ded = 2.0
        else:
            ded = 0
    status = 'FAIL' if ded > 0 else 'PASS'
    return _result('avg_total_float', 'Average Activity Total Float', True, n, n, avg_days,
                   '15-44 days', status, ded, value_days=avg_days,
                   note='High avg float = missing logic. Low = compressed schedule.')


# ============================================================
# CHECK: CONSTRAINTS (SCORED -- HARD CONSTRAINTS ONLY)
# ============================================================

HARD_CONSTRAINT_CODES = {'CS_MSO', 'CS_MFO', 'CS_MEO', 'CS_MANDSTART', 'CS_MANDEND', 'CS_MANDFIN'}
SOFT_CONSTRAINT_CODES = {'CS_SNET', 'CS_SNLT', 'CS_FNET', 'CS_FNLT',
                          'CS_MSOA', 'CS_MSOB', 'CS_MEOA', 'CS_MEOB'}

def check_constraints(tasks, preds=None, data_date=None):
    """Hard constraints only (CS_MSO, CS_MFO). Soft constraints excluded from score.
    SmartPM excludes CS_ALAP and soft constraints from the scored Constraints metric."""
    n = len(tasks)
    flagged = []
    for t in tasks:
        c1 = t.get('cstr_type', t.get('constraint_type', ''))
        c2 = t.get('cstr_type2', t.get('constraint_type2', ''))
        if c1 in HARD_CONSTRAINT_CODES or c2 in HARD_CONSTRAINT_CODES:
            ctype = c1 if c1 in HARD_CONSTRAINT_CODES else c2
            flagged.append({**_task_rec(t), 'constraint_type': ctype,
                            'constraint_date': t.get('cstr_date', t.get('constraint_date', ''))})
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    if pct <= 1:
        ded, status = 0, 'PASS'
    elif pct <= 5:
        ded, status = 1.5, 'FAIL'
    else:
        ded, status = min(3.0, round(pct / 2, 1)), 'FAIL'
    return _result('constraints', 'Constraints (Hard)', True, len(flagged), n, pct,
                   '<= 1% hard constraints', status, ded, tasks=flagged,
                   note='Hard constraints (CS_MSO/MFO) override logic. Use sparingly.')


# ============================================================
# CHECK: HARD CONSTRAINTS (INFORMATIONAL DETAIL)
# ============================================================

def check_hard_constraints(tasks, preds=None, data_date=None):
    """Hard constraints -- informational breakdown (same as scored Constraints check)."""
    return check_constraints(tasks, preds, data_date)


# ============================================================
# CHECK: SOFT CONSTRAINTS (INFORMATIONAL)
# ============================================================

def check_soft_constraints(tasks, preds=None, data_date=None):
    """Soft constraints (SNET/SNLT/FNET/FNLT/MSOA etc.) -- informational only, not scored."""
    n = len(tasks)
    flagged = []
    for t in tasks:
        c1 = t.get('cstr_type', t.get('constraint_type', ''))
        c2 = t.get('cstr_type2', t.get('constraint_type2', ''))
        if c1 in SOFT_CONSTRAINT_CODES or c2 in SOFT_CONSTRAINT_CODES:
            ctype = c1 if c1 in SOFT_CONSTRAINT_CODES else c2
            flagged.append({**_task_rec(t), 'constraint_type': ctype,
                            'constraint_date': t.get('cstr_date', t.get('constraint_date', ''))})
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    return _result('soft_constraints', 'Soft Constraints', False, len(flagged), n, pct,
                   'Informational', 'INFO', 0, tasks=flagged,
                   note='Soft constraints are aspirational. Excessive use can mask CP.')


# ============================================================
# CHECK: HIGH DURATION ACTIVITIES
# ============================================================

def check_high_duration(tasks, preds=None, data_date=None):
    """Activities with planned duration > 44 working days (352 hrs) -- informational."""
    acts = _activities(tasks)
    n = len(acts)
    flagged = [t for t in acts if _safe_float(t.get('target_drtn_hr_cnt', 0)) > 352]
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    result_tasks = [{**_task_rec(t),
                     'duration_days': round(_safe_float(t.get('target_drtn_hr_cnt', 0)) / 8, 1)}
                    for t in flagged]
    return _result('high_duration', 'High Duration Activities', False, len(flagged), n, pct,
                   '<= 5% of activities', 'FAIL' if pct > 5 else 'PASS', 0,
                   tasks=result_tasks,
                   note='Activities > 44 days should be broken into smaller tasks.')


# ============================================================
# CHECK: HIGH FLOAT ACTIVITIES
# ============================================================

def check_high_float(tasks, preds=None, data_date=None):
    """Activities with total float > 44 working days (352 hrs) -- informational."""
    acts = _activities(tasks)
    n = len(acts)
    flagged = [t for t in acts if _safe_float(t.get('total_float_hr_cnt', 0)) > 352]
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    result_tasks = [{**_task_rec(t),
                     'float_days': round(_safe_float(t.get('total_float_hr_cnt', 0)) / 8, 1)}
                    for t in flagged]
    return _result('high_float', 'High Float Activities', False, len(flagged), n, pct,
                   '<= 0% target', 'FAIL' if flagged else 'PASS', 0,
                   tasks=result_tasks,
                   note='High float indicates missing logic. Add predecessor/successor ties.')


# ============================================================
# CHECK: LOW FLOAT ACTIVITIES
# ============================================================

def check_low_float(tasks, preds=None, data_date=None):
    """Activities with float 0-10 working days (0-80 hrs) -- informational."""
    acts = _activities(tasks)
    n = len(acts)
    flagged = [t for t in acts
               if 0 <= _safe_float(t.get('total_float_hr_cnt', 0)) <= 80]
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    result_tasks = [{**_task_rec(t),
                     'float_days': round(_safe_float(t.get('total_float_hr_cnt', 0)) / 8, 1)}
                    for t in flagged]
    return _result('low_float', 'Low Float Activities', False, len(flagged), n, pct,
                   'Informational', 'INFO', 0, tasks=result_tasks,
                   note='Low float activities are near-critical. Monitor closely.')


# ============================================================
# CHECK: MISSING LOGIC
# ============================================================

def check_missing_logic(tasks, preds, data_date=None, all_preds=None):
    """Activities missing a predecessor or successor (scored).
    Pass all_preds (full XER relationship list) for accurate results -- without it,
    scope-filtered preds cause false positives when predecessors are outside scope."""
    acts = _activities(tasks)
    n = len(tasks)
    lookup_preds = all_preds if all_preds is not None else preds
    all_preds_map = defaultdict(set)
    all_succs_map = defaultdict(set)
    for p in lookup_preds:
        all_preds_map[p.get('task_id', '')].add(p.get('pred_task_id', ''))
        all_succs_map[p.get('pred_task_id', '')].add(p.get('task_id', ''))
    no_pred = [t for t in acts if not all_preds_map.get(t['task_id'])]
    no_succ = [t for t in acts if not all_succs_map.get(t['task_id'])]
    open_ids = {t['task_id'] for t in no_pred} | {t['task_id'] for t in no_succ}
    pct = round(len(open_ids) / max(n, 1) * 100, 1)
    if pct < 3:
        ded, status = 0, 'PASS'
    else:
        ded = min(10.0, round(pct, 1))
        status = 'FAIL'
    return _result('missing_logic', 'Missing Logic', True, len(open_ids), n, pct,
                   '< 3% of activities', status, ded,
                   no_predecessor=[_task_rec(t) for t in no_pred],
                   no_successor=[_task_rec(t) for t in no_succ],
                   note='Every activity needs a predecessor AND successor (except project start/finish milestones).')


# ============================================================
# CHECK: NEGATIVE LAG
# ============================================================

def check_negative_lag(tasks, preds, data_date=None):
    """Relationships with negative lag (leads) -- informational."""
    task_by_id = {t['task_id']: t for t in tasks}
    n = len(preds)
    flagged = [p for p in preds if _safe_float(p.get('lag_hr_cnt', 0)) < 0]
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    rels = [_rel_rec(task_by_id.get(p.get('pred_task_id', '')),
                     task_by_id.get(p.get('task_id', '')), p) for p in flagged]
    return _result('negative_lag', 'Negative Lag', False, len(flagged), n, pct,
                   '0 relationships', 'FAIL' if flagged else 'PASS', 0,
                   relationships=rels,
                   note='Negative lag (leads) is bad practice. Replace with logic or explicit overlap activities.')


# ============================================================
# CHECK: POSITIVE LAG
# ============================================================

def check_positive_lag(tasks, preds, data_date=None):
    """Relationships with positive lag -- informational."""
    task_by_id = {t['task_id']: t for t in tasks}
    n = len(preds)
    flagged = [p for p in preds if _safe_float(p.get('lag_hr_cnt', 0)) > 0]
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    rels = [_rel_rec(task_by_id.get(p.get('pred_task_id', '')),
                     task_by_id.get(p.get('task_id', '')), p) for p in flagged]
    return _result('positive_lag', 'Positive Lag', False, len(flagged), n, pct,
                   '<= 5% of relationships', 'FAIL' if pct > 5 else 'PASS', 0,
                   relationships=rels,
                   note='Excessive positive lag hides work. Replace with explicit activities where possible.')


# ============================================================
# CHECK: TOTAL RELATIONSHIPS RATIO
# ============================================================

def check_total_relationships(tasks, preds, data_date=None):
    """Relationship to activity ratio. Target >= 1.5:1 (scored)."""
    n_inc = len(tasks)
    n_rels = len(preds)
    ratio = round(n_rels / max(n_inc, 1), 2)
    avg_float = sum(_safe_float(t.get('total_float_hr_cnt', 0)) for t in _activities(tasks))
    avg_days = avg_float / max(len(_activities(tasks)), 1) / 8
    if avg_days < 0:
        return _result('total_relationships', 'Total Relationships', True, n_rels, n_inc, ratio,
                       '>= 1.5:1', 'SKIP', 0, ratio=ratio,
                       note='Skipped: negative avg float schedule.')
    eop = _end_of_project(_activities(tasks))
    lo = 1.25 if eop else 1.5
    if ratio >= lo:
        ded, status = 0, 'PASS'
    elif ratio >= lo - 0.25:
        ded, status = 2.5, 'FAIL'
    else:
        ded, status = 5.0, 'FAIL'
    return _result('total_relationships', 'Total Relationships', True, n_rels, n_inc, ratio,
                   f'>= {lo}:1', status, ded, ratio=ratio,
                   note='Low ratio means sparse logic network. Add predecessor/successor ties.')


# ============================================================
# CHECK: RIDING DATA DATE
# ============================================================

def check_riding_data_date(tasks, preds, data_date=None):
    """Not-started activities whose logic is fully satisfied but are held by data date.
    Indicates missing or erroneous logic -- informational."""
    if data_date is None:
        return _result('riding_data_date', 'Activities Riding Data Date', False, 0, 0, 0,
                       'Informational', 'INFO', 0, tasks=[],
                       note='data_date required for this check.')
    dd = _parse_dt(data_date) if isinstance(data_date, str) else data_date
    if dd is None:
        return _result('riding_data_date', 'Activities Riding Data Date', False, 0, 0, 0,
                       'Informational', 'INFO', 0, tasks=[])

    task_by_id = {t['task_id']: t for t in tasks}
    complete_ids = {t['task_id'] for t in tasks if t.get('status_code', '') == 'TK_Complete'}
    # Build predecessor map for in-scope tasks
    pred_map = defaultdict(set)
    for p in preds:
        pred_map[p.get('task_id', '')].add(p.get('pred_task_id', ''))

    acts = _activities(tasks)
    n = len(acts)
    not_started = [t for t in acts if t.get('status_code', '') == 'TK_NotStart']
    riding = []
    for t in not_started:
        tid = t['task_id']
        task_preds = pred_map.get(tid, set())
        if not task_preds:
            continue  # No predecessors -- not "riding", just open start
        # Check if ALL predecessors are complete
        if task_preds and all(pid in complete_ids for pid in task_preds):
            # All logic satisfied -- only data date is holding this back
            es = _parse_dt(t.get('early_start_date', ''))
            if es and abs((es - dd).total_seconds()) < 86400:  # within 1 day of data date
                riding.append({**_task_rec(t), 'early_start': t.get('early_start_date', '')})
    pct = round(len(riding) / max(n, 1) * 100, 1)
    return _result('riding_data_date', 'Activities Riding Data Date', False, len(riding), n, pct,
                   'Informational', 'INFO', 0, tasks=riding,
                   note='These activities can start per logic but are blocked by data date. Review for missing logic.')


# ============================================================
# CHECK: ACTIVITIES LATER THAN SC (Tracked-To)
# ============================================================

def check_later_than_sc(tasks, preds, data_date=None):
    """Predecessor activities with early finish later than SC milestone finish -- informational."""
    sc_id = _find_sc(tasks)
    if not sc_id:
        return _result('later_than_sc', 'Activities Later Than SC', False, 0, 0, 0,
                       'Informational', 'INFO', 0, tasks=[], note='No SC milestone found.')
    task_by_id = {t['task_id']: t for t in tasks}
    sc_task = task_by_id.get(sc_id)
    sc_ef = _parse_dt(sc_task.get('early_end_date', '')) if sc_task else None
    if not sc_ef:
        return _result('later_than_sc', 'Activities Later Than SC', False, 0, 0, 0,
                       'Informational', 'INFO', 0, tasks=[], note='SC milestone has no early finish date.')
    sc_scope = _sc_predecessors(sc_id, preds)
    acts = [t for t in tasks if t['task_id'] in sc_scope and t['task_id'] != sc_id]
    n = len(acts)
    flagged = []
    for t in acts:
        ef = _parse_dt(t.get('early_end_date', ''))
        if ef and ef > sc_ef:
            flagged.append({**_task_rec(t), 'early_finish': t.get('early_end_date', ''),
                            'sc_finish': sc_task.get('early_end_date', '')})
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    return _result('later_than_sc', 'Activities Later Than SC', False, len(flagged), n, pct,
                   '0%', 'FAIL' if flagged else 'PASS', 0, tasks=flagged,
                   note='Logic inconsistency: predecessor finishes after SC milestone.')


# ============================================================
# CHECK: MISSING ACTUAL FINISH DATE
# ============================================================

def check_missing_actual_finish(tasks, preds=None, data_date=None):
    """Completed activities (100%) without an actual finish date -- informational."""
    complete = [t for t in tasks if t.get('status_code', '') == 'TK_Complete']
    n = len(complete)
    flagged = [t for t in complete if not t.get('act_end_date', '').strip()]
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    return _result('missing_actual_finish', 'Missing Actual Finish Date', False,
                   len(flagged), n, pct, '0%', 'FAIL' if flagged else 'PASS', 0,
                   tasks=[_task_rec(t) for t in flagged],
                   note='100% complete activities must have an actual finish date.')


# ============================================================
# CHECK: CONVERGENCE BOTTLENECKS
# ============================================================

def check_convergence(tasks, preds, data_date=None, threshold=5):
    """Activities with >= 5 predecessor relationships (convergence points) -- informational."""
    task_by_id = {t['task_id']: t for t in tasks}
    pred_cnt = Counter(p.get('task_id', '') for p in preds)
    n = len(tasks)
    flagged_ids = [tid for tid, cnt in pred_cnt.items() if cnt >= threshold]
    flagged = [{**_task_rec(task_by_id[tid]), 'predecessor_count': pred_cnt[tid]}
               for tid in flagged_ids if tid in task_by_id]
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    return _result('convergence', 'Convergence Bottlenecks', False, len(flagged), n, pct,
                   f'< {threshold} predecessors per activity', 'FAIL' if flagged else 'PASS', 0,
                   tasks=flagged, threshold_value=threshold,
                   note='High predecessor count = single points of delay propagation.')


# ============================================================
# CHECK: DANGLING ACTIVITIES
# ============================================================

def check_dangling(tasks, preds, data_date=None):
    """Activities missing FS/SS predecessor OR FS/FF successor -- informational."""
    task_by_id = {t['task_id']: t for t in tasks}
    acts = _activities(tasks)
    n = len(acts)
    fs_ss_pred = set()  # tasks that have a FS or SS predecessor
    fs_ff_succ = set()  # tasks that have a FS or FF successor
    for p in preds:
        pt = p.get('pred_type', '')
        if _is_fs(pt) or _is_ss(pt):
            fs_ss_pred.add(p.get('task_id', ''))
        if _is_fs(pt) or _is_ff(pt):
            fs_ff_succ.add(p.get('pred_task_id', ''))
    flagged = []
    for t in acts:
        tid = t['task_id']
        issues = []
        if tid not in fs_ss_pred:
            issues.append('no_fs_ss_predecessor')
        if tid not in fs_ff_succ:
            issues.append('no_fs_ff_successor')
        if issues:
            flagged.append({**_task_rec(t), 'issues': issues})
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    return _result('dangling', 'Dangling Activities', False, len(flagged), n, pct,
                   '0%', 'FAIL' if flagged else 'PASS', 0, tasks=flagged,
                   note='Dangling activities are not impacted by delays elsewhere in the network.')


# ============================================================
# CHECK: DIVERGENCE BOTTLENECKS
# ============================================================

def check_divergence(tasks, preds, data_date=None, threshold=5):
    """Activities with >= 5 successor relationships (flashpoints) -- informational."""
    task_by_id = {t['task_id']: t for t in tasks}
    succ_cnt = Counter(p.get('pred_task_id', '') for p in preds)
    n = len(tasks)
    flagged_ids = [tid for tid, cnt in succ_cnt.items() if cnt >= threshold]
    flagged = [{**_task_rec(task_by_id[tid]), 'successor_count': succ_cnt[tid]}
               for tid in flagged_ids if tid in task_by_id]
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    return _result('divergence', 'Divergence Bottlenecks', False, len(flagged), n, pct,
                   f'< {threshold} successors per activity', 'FAIL' if flagged else 'PASS', 0,
                   tasks=flagged, threshold_value=threshold,
                   note='High successor count = single points of failure in the network.')


# ============================================================
# CHECK: DUPLICATE RELATIONSHIPS
# ============================================================

def check_duplicate_rels(tasks, preds, data_date=None):
    """Pairs of activities with multiple relationships between them -- informational."""
    task_by_id = {t['task_id']: t for t in tasks}
    pairs = defaultdict(list)
    for p in preds:
        key = (p.get('pred_task_id', ''), p.get('task_id', ''))
        pairs[key].append(p.get('pred_type', ''))
    dups = [(k, v) for k, v in pairs.items() if len(v) > 1]
    n = len(preds)
    rels = []
    for (pred_id, succ_id), types in dups:
        rels.append({
            'pred_id': pred_id,
            'pred_code': task_by_id.get(pred_id, {}).get('task_code', ''),
            'pred_name': task_by_id.get(pred_id, {}).get('task_name', ''),
            'succ_id': succ_id,
            'succ_code': task_by_id.get(succ_id, {}).get('task_code', ''),
            'succ_name': task_by_id.get(succ_id, {}).get('task_name', ''),
            'relationship_types': types,
        })
    pct = round(len(dups) / max(n, 1) * 100, 1)
    return _result('duplicate_rels', 'Duplicate Relationships', False, len(dups), n, pct,
                   '0 pairs', 'FAIL' if dups else 'PASS', 0, relationships=rels,
                   note='Duplicate relationships create redundant logic that can obscure the CP.')


# ============================================================
# CHECK: FUTURE ACTUAL DATES
# ============================================================

def check_future_actual(tasks, preds=None, data_date=None):
    """Activities with actual start or finish dates in the future -- informational."""
    if data_date is None:
        return _result('future_actual', 'Future Actual Dates', False, 0, 0, 0,
                       'Informational', 'INFO', 0, tasks=[], note='data_date required.')
    dd = _parse_dt(data_date) if isinstance(data_date, str) else data_date
    if dd is None:
        return _result('future_actual', 'Future Actual Dates', False, 0, 0, 0,
                       'Informational', 'INFO', 0, tasks=[])
    all_tasks = tasks
    n = len(all_tasks)
    flagged = []
    for t in all_tasks:
        as_ = _parse_dt(t.get('act_start_date', ''))
        af = _parse_dt(t.get('act_end_date', ''))
        if (as_ and as_ > dd) or (af and af > dd):
            flagged.append({**_task_rec(t),
                            'act_start': t.get('act_start_date', ''),
                            'act_finish': t.get('act_end_date', '')})
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    return _result('future_actual', 'Future Actual Dates', False, len(flagged), n, pct,
                   '0%', 'FAIL' if flagged else 'PASS', 0, tasks=flagged,
                   note='Future actual dates are approximations, not real actuals.')


# ============================================================
# CHECK: UNSTATUSED ACTIVITIES
# ============================================================

def check_unstatused(tasks, preds=None, data_date=None):
    """Incomplete activities whose scheduled start is before data date -- informational."""
    if data_date is None:
        return _result('unstatused', 'Unstatused Activities', False, 0, 0, 0,
                       'Informational', 'INFO', 0, tasks=[], note='data_date required.')
    dd = _parse_dt(data_date) if isinstance(data_date, str) else data_date
    acts = _activities(tasks)
    n = len(acts)
    flagged = []
    for t in acts:
        if t.get('status_code', '') != 'TK_NotStart':
            continue
        es = _parse_dt(t.get('early_start_date', ''))
        if es and es < dd:
            flagged.append({**_task_rec(t), 'early_start': t.get('early_start_date', '')})
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    return _result('unstatused', 'Unstatused Activities', False, len(flagged), n, pct,
                   '0%', 'FAIL' if flagged else 'PASS', 0, tasks=flagged,
                   note='Should have started per the schedule but have no progress recorded.')


# ============================================================
# CHECK: NEGATIVE FLOAT ACTIVITIES
# ============================================================

def check_negative_float(tasks, preds=None, data_date=None):
    """Activities with negative total float -- informational."""
    n = len(tasks)
    flagged = [t for t in tasks if _safe_float(t.get('total_float_hr_cnt', 0)) < -8]
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    result_tasks = [{**_task_rec(t),
                     'float_days': round(_safe_float(t.get('total_float_hr_cnt', 0)) / 8, 1)}
                    for t in flagged]
    return _result('negative_float', 'Negative Float Activities', False, len(flagged), n, pct,
                   '0%', 'FAIL' if flagged else 'PASS', 0, tasks=result_tasks,
                   note='Negative float means the schedule cannot meet its deadline without acceleration.')


# ============================================================
# CHECK: ONE DAY ACTIVITIES
# ============================================================

def check_one_day(tasks, preds=None, data_date=None):
    """Activities with exactly 1 working day duration (8 hrs) -- informational."""
    acts = _activities(tasks)
    n = len(acts)
    flagged = [t for t in acts if _safe_float(t.get('target_drtn_hr_cnt', 0)) == 8.0]
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    return _result('one_day', 'One Day Activities', False, len(flagged), n, pct,
                   'Informational', 'INFO', 0, tasks=[_task_rec(t) for t in flagged],
                   note='Review 1-day activities for validity. Too many can indicate over-detailed schedule.')


# ============================================================
# CHECK: OUT OF SEQUENCE
# ============================================================

def check_out_of_sequence(tasks, preds, data_date=None):
    """Active activities with not-started predecessors -- informational."""
    task_by_id = {t['task_id']: t for t in tasks}
    active_ids = {t['task_id'] for t in tasks if t.get('status_code', '') == 'TK_Active'}
    not_started_ids = {t['task_id'] for t in tasks if t.get('status_code', '') == 'TK_NotStart'}
    n = len(tasks)
    flagged = []
    seen = set()
    for p in preds:
        succ_id = p.get('task_id', '')
        pred_id = p.get('pred_task_id', '')
        if succ_id in active_ids and pred_id in not_started_ids and succ_id not in seen:
            seen.add(succ_id)
            t = task_by_id.get(succ_id, {})
            pt = task_by_id.get(pred_id, {})
            flagged.append({
                **_task_rec(t),
                'not_started_predecessor': _task_rec(pt),
            })
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    return _result('out_of_sequence', 'Out of Sequence', False, len(flagged), n, pct,
                   '0%', 'FAIL' if flagged else 'PASS', 0, tasks=flagged,
                   note='Work is being performed before prerequisite activities are complete.')


# ============================================================
# CHECK: REMAINING DURATION DISCREPANCY
# ============================================================

def check_remaining_dur_discrepancy(tasks, preds=None, data_date=None):
    """Remaining duration inconsistent with % complete and planned duration -- informational."""
    acts = _activities(tasks)
    n = len(acts)
    flagged = []
    for t in acts:
        if t.get('status_code', '') not in ('TK_Active', 'TK_NotStart'):
            continue
        planned = _safe_float(t.get('target_drtn_hr_cnt', 0))
        remain = _safe_float(t.get('remain_drtn_hr_cnt', 0))
        pct_complete = _safe_float(t.get('phys_complete_pct', 0))
        if planned <= 0:
            continue
        expected_remain = planned * (1 - pct_complete / 100)
        if expected_remain > 0 and abs(remain - expected_remain) / expected_remain > 0.15:
            flagged.append({
                **_task_rec(t),
                'planned_days': round(planned / 8, 1),
                'remaining_days': round(remain / 8, 1),
                'expected_remaining_days': round(expected_remain / 8, 1),
                'pct_complete': pct_complete,
            })
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    return _result('remaining_dur_discrepancy', 'Remaining Duration Discrepancy', False,
                   len(flagged), n, pct, '0%', 'FAIL' if flagged else 'PASS', 0,
                   tasks=flagged,
                   note='Remaining duration does not match % complete. Review update methodology.')


# ============================================================
# CHECK: STARTED WITH 0% COMPLETE
# ============================================================

def check_started_with_zero(tasks, preds=None, data_date=None):
    """Active activities (status TK_Active) with 0% complete -- informational."""
    all_tasks = tasks
    n = len(all_tasks)
    flagged = [t for t in all_tasks
               if t.get('status_code', '') == 'TK_Active'
               and _safe_float(t.get('phys_complete_pct', 0)) == 0]
    pct = round(len(flagged) / max(n, 1) * 100, 1)
    return _result('started_with_zero', 'Started with 0%', False, len(flagged), n, pct,
                   '0%', 'FAIL' if flagged else 'PASS', 0,
                   tasks=[_task_rec(t) for t in flagged],
                   note='Activity is marked started but has no progress. Review update practices.')


# ============================================================
# CHECK: SC COVERAGE (Westland / Boss Metric)
# ============================================================

def check_sc_coverage(tasks, preds, data_date=None):
    """Westland metric: % of incomplete activities tracking to Substantial Completion.
    Low coverage means many activities are disconnected from the SC milestone."""
    exc = {'TT_WBS', 'TT_LOE'}
    all_incomplete = [t for t in tasks
                      if t.get('status_code', '') != 'TK_Complete'
                      and t.get('task_type', '') not in exc]
    n = len(all_incomplete)
    sc_id = _find_sc(tasks)
    if not sc_id:
        return _result('sc_coverage', 'SC Coverage', False, 0, n, 0,
                       '>= 80%', 'INFO', 0, tasks=[], sc_milestone=None,
                       note='No Substantial Completion milestone found.')
    task_by_id = {t['task_id']: t for t in tasks}
    sc_task = task_by_id.get(sc_id, {})
    sc_scope = _sc_predecessors(sc_id, preds)
    on_path = [t for t in all_incomplete if t['task_id'] in sc_scope]
    off_path = [t for t in all_incomplete if t['task_id'] not in sc_scope]
    pct = round(len(on_path) / max(n, 1) * 100, 1)
    status = 'PASS' if pct >= 80 else ('FAIL' if pct < 60 else 'WARN')
    return _result('sc_coverage', 'SC Coverage', False, len(on_path), n, pct,
                   '>= 80% tracking to SC', status, 0,
                   sc_milestone={'task_id': sc_id,
                                 'task_code': sc_task.get('task_code', ''),
                                 'task_name': sc_task.get('task_name', ''),
                                 'early_finish': sc_task.get('early_end_date', '')},
                   off_path_tasks=[_task_rec(t) for t in off_path],
                   note='Westland metric: activities not tied to SC are floating and unmanaged.')


# ==============================================================================
# RUN ALL CHECKS
# ==============================================================================

ALL_CHECKS = {
    'finish_to_start':            check_finish_to_start,
    'start_to_start':             check_start_to_start,
    'finish_to_finish':           check_finish_to_finish,
    'start_to_finish':            check_start_to_finish,
    'critical_path_pct':          check_critical_path_pct,
    'avg_total_float':            check_avg_total_float,
    'constraints':                check_constraints,
    'high_duration':              check_high_duration,
    'high_float':                 check_high_float,
    'low_float':                  check_low_float,
    'missing_logic':              check_missing_logic,
    'negative_lag':               check_negative_lag,
    'positive_lag':               check_positive_lag,
    'total_relationships':        check_total_relationships,
    'riding_data_date':           check_riding_data_date,
    'missing_actual_finish':      check_missing_actual_finish,
    'convergence':                check_convergence,
    'dangling':                   check_dangling,
    'divergence':                 check_divergence,
    'duplicate_rels':             check_duplicate_rels,
    'future_actual':              check_future_actual,
    'hard_constraints':           check_hard_constraints,
    'soft_constraints':           check_soft_constraints,
    'unstatused':                 check_unstatused,
    'negative_float':             check_negative_float,
    'one_day':                    check_one_day,
    'out_of_sequence':            check_out_of_sequence,
    'remaining_dur_discrepancy':  check_remaining_dur_discrepancy,
    'started_with_zero':          check_started_with_zero,
    'later_than_sc':              check_later_than_sc,
    'sc_coverage':                check_sc_coverage,
}


def run_all_checks(tasks, preds, data_date=None, all_preds=None):
    """Run every check and return dict keyed by check name.
    all_preds: full unfiltered relationship list for accurate missing_logic check."""
    results = {}
    for name, fn in ALL_CHECKS.items():
        try:
            if name == 'missing_logic':
                results[name] = check_missing_logic(tasks, preds, data_date,
                                                     all_preds=all_preds)
            else:
                results[name] = fn(tasks, preds, data_date)
        except Exception as e:
            results[name] = {'check': name, 'error': str(e)}
    return results


# ==============================================================================
# CLI ENTRY POINT
# ==============================================================================

if __name__ == '__main__':
    import sys
    import json

    if len(sys.argv) < 3:
        print(json.dumps({
            'error': 'Usage: python quality_checks.py <check_name> <xer_path>',
            'available': list(ALL_CHECKS.keys()) + ['all'],
        }))
        sys.exit(1)

    check_name = sys.argv[1].lower()
    xer_path = sys.argv[2]

    # PARSE -- READ ONLY, NEVER WRITES
    tables = _parse_xer(xer_path)
    all_tasks = tables.get('TASK', [])
    all_preds = tables.get('TASKPRED', [])
    proj = tables.get('PROJECT', [{}])
    data_date_str = proj[0].get('last_recalc_date') or proj[0].get('data_date', '')
    data_date_dt = _parse_dt(data_date_str)

    # Scope filter: exclude complete/WBS/LOE but do NOT filter to SC path.
    # SmartPM quality checks run on all incomplete activities, not just SC-path activities.
    # SC path filtering causes false-positive missing_logic hits (predecessors outside SC scope).
    tasks, preds, _ = _scope_filter(all_tasks, all_preds, sc_filter=False)

    if check_name == 'all':
        out = run_all_checks(tasks, preds, data_date_dt)
        # missing_logic always gets full preds for accurate predecessor lookup
        out['missing_logic'] = check_missing_logic(tasks, preds, data_date_dt, all_preds=all_preds)
        # Add project metadata
        out['_meta'] = {
            'xer_path': xer_path,
            'data_date': data_date_str,
            'project_name': proj[0].get('proj_short_name', ''),
            'total_tasks': len(all_tasks),
            'scope_tasks': len(tasks),
            'scope_rels': len(preds),
            'end_of_project': _end_of_project(_activities(tasks)),
        }
    elif check_name in ALL_CHECKS:
        if check_name == 'missing_logic':
            out = check_missing_logic(tasks, preds, data_date_dt, all_preds=all_preds)
        else:
            out = ALL_CHECKS[check_name](tasks, preds, data_date_dt)
        out['_meta'] = {
            'xer_path': xer_path,
            'data_date': data_date_str,
            'scope_tasks': len(tasks),
        }
    else:
        out = {
            'error': f'Unknown check: {check_name}',
            'available': list(ALL_CHECKS.keys()) + ['all'],
        }

    print(json.dumps(out, indent=2, default=str))
