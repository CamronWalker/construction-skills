"""
XER Compare — Multi-schedule comparison engine.

Pure function library. Pass parsed XER tables in, get comparison results out.

Usage:
    from xer_compare import compare_schedules, render_comparison_html

    comparison = compare_schedules(current_tables, baseline_tables, previous_tables)
    render_comparison_html(comparison, 'comparison_report.html')
"""

from datetime import datetime, timedelta
from collections import defaultdict
import os
import sys
import importlib.util

# Milestone resolver — same-directory import. Try the regular `import
# milestones` first (when lib/ is already on sys.path, this gives the
# same class identity that path_analysis / score_schedule use, so
# `except MilestoneAmbiguousError` catches in user code keep working).
# Fall back to a spec_from_file_location load when lib/ isn't on the
# path (e.g. a tool that loads xer_compare via spec without first
# adjusting sys.path) -- in that case we *register* the loaded module
# under the name 'milestones' so any later `from milestones import ...`
# resolves to the same module object.
_dir = os.path.dirname(os.path.abspath(__file__))
try:
    if _dir not in sys.path:
        sys.path.insert(0, _dir)
    from milestones import MilestoneAmbiguousError, resolve_default_milestone  # noqa: E402
except ImportError:
    _ms_spec = importlib.util.spec_from_file_location(
        'milestones', os.path.join(_dir, 'milestones.py'))
    _ms_mod = importlib.util.module_from_spec(_ms_spec)
    sys.modules['milestones'] = _ms_mod
    _ms_spec.loader.exec_module(_ms_mod)
    MilestoneAmbiguousError = _ms_mod.MilestoneAmbiguousError
    resolve_default_milestone = _ms_mod.resolve_default_milestone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(date_str):
    """Parse date string to datetime."""
    if not date_str or not date_str.strip():
        return None
    s = date_str.strip()
    for fmt in ('%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _safe_float(val, default=0.0):
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def _resolve_milestone(tables, milestone_id=None, match_by=None,
                       other_lookup=None):
    """Resolve the terminal milestone for one schedule under comparison.

    ``milestone_id`` -- when provided directly, look it up by ``task_id`` first
    and fall back to ``task_code`` so callers can pass either. When omitted,
    delegate to :func:`milestones.resolve_default_milestone` to pick the
    unique terminal non-WBS / non-LOE / non-complete milestone; if multiple
    terminal milestones exist this raises :class:`MilestoneAmbiguousError`
    with the candidate list so the MCP-tool layer can prompt the user.

    ``match_by`` + ``other_lookup`` are an optional cross-schedule bridge: when
    a milestone_id was resolved against one side of the pair (typically the
    new/current schedule), this helper can find the matching task on the
    other side by its match key (task_code by default) so SC-slip numbers
    line up across schedules even when task_id renumbering happened between
    exports.
    """
    tasks = tables.get('TASK', [])
    if not tasks:
        return None

    resolved_task = None
    if milestone_id is not None:
        # Try task_id first (canonical), then task_code (so callers can pass
        # either form). This matters because compare_schedules' match_by
        # parameter is often task_code -- the F4 MCP tool may surface either.
        for t in tasks:
            if t.get('task_id', '') == milestone_id:
                resolved_task = t
                break
        if resolved_task is None:
            for t in tasks:
                if t.get('task_code', '') == milestone_id:
                    resolved_task = t
                    break

    # Cross-schedule bridge: if caller already resolved on the other side
    # and passed a lookup, mirror that match across.
    if resolved_task is None and other_lookup is not None and match_by:
        for key, other_task in other_lookup.items():
            if key:
                for t in tasks:
                    if t.get(match_by, '') == key:
                        resolved_task = t
                        break
                if resolved_task is not None:
                    break

    if resolved_task is None and milestone_id is None:
        preds = tables.get('TASKPRED', [])
        auto_id = resolve_default_milestone(tasks, preds)
        if auto_id is not None:
            for t in tasks:
                if t.get('task_id', '') == auto_id:
                    resolved_task = t
                    break

    if resolved_task is None:
        return None

    return {
        'task_id': resolved_task.get('task_id', ''),
        'task_code': resolved_task.get('task_code', ''),
        'task_name': resolved_task.get('task_name', ''),
        'date': resolved_task.get('early_end_date', '')
                or resolved_task.get('target_end_date', ''),
    }


def _get_data_date(tables):
    """Extract data date from PROJECT table."""
    projects = tables.get('PROJECT', [])
    if projects:
        return projects[0].get('data_date', '')
    return ''


def _build_task_lookup(tasks, match_by='task_code'):
    """Build {match_key: task_dict} from task list."""
    lookup = {}
    for t in tasks:
        key = t.get(match_by, '') or t.get('task_id', '')
        if key:
            lookup[key] = t
    return lookup


def _build_wbs_lookup(wbs_rows):
    """Build {wbs_id: wbs_name}."""
    return {w.get('wbs_id', ''): w.get('wbs_name', '') for w in wbs_rows}


# ---------------------------------------------------------------------------
# Pairwise comparison
# ---------------------------------------------------------------------------

def compare_xer_pair(old_tables, new_tables, match_by='task_code',
                     milestone_id=None):
    """
    Core pairwise comparison between two parsed XER datasets.

    ``milestone_id`` identifies the project's terminal milestone (e.g. the
    Substantial Completion finish marker) for the SC-slip output. Resolution
    happens against the *new* schedule (the comparison's anchor); the matching
    task on the old schedule is found by the same ``match_by`` key, so SC-slip
    numbers stay consistent across exports even if task_id renumbering
    occurred. When ``milestone_id`` is omitted, the function auto-resolves to
    the single terminal non-WBS / non-LOE / non-complete milestone in the new
    schedule; if multiple terminal milestones exist it raises
    :class:`MilestoneAmbiguousError` so the caller can prompt the user.

    Args:
        old_tables: Result of parse_xer() on the older XER
        new_tables: Result of parse_xer() on the newer XER
        match_by: 'task_code' or 'task_id'
        milestone_id: Optional explicit terminal milestone task_id (or
            match_by-key) to pin SC slip to. See above.

    Returns dict with comparison results.
    """
    old_tasks = old_tables.get('TASK', [])
    new_tasks = new_tables.get('TASK', [])
    old_preds = old_tables.get('TASKPRED', [])
    new_preds = new_tables.get('TASKPRED', [])
    old_wbs = _build_wbs_lookup(old_tables.get('PROJWBS', []))
    new_wbs = _build_wbs_lookup(new_tables.get('PROJWBS', []))

    skip_types = {'TT_WBS', 'TT_LOE'}
    old_filtered = [t for t in old_tasks if t.get('task_type', '') not in skip_types]
    new_filtered = [t for t in new_tasks if t.get('task_type', '') not in skip_types]

    old_lookup = _build_task_lookup(old_filtered, match_by)
    new_lookup = _build_task_lookup(new_filtered, match_by)

    old_keys = set(old_lookup.keys())
    new_keys = set(new_lookup.keys())

    matched = old_keys & new_keys
    added_keys = new_keys - old_keys
    removed_keys = old_keys - new_keys

    # Added tasks
    added_tasks = []
    for k in sorted(added_keys):
        t = new_lookup[k]
        wbs_name = new_wbs.get(t.get('wbs_id', ''), '')
        dur_hrs = _safe_float(t.get('target_drtn_hr_cnt', 0))
        added_tasks.append({
            'task_code': k,
            'task_name': t.get('task_name', ''),
            'duration_days': round(dur_hrs / 8, 1),
            'wbs_name': wbs_name,
        })

    # Removed tasks
    removed_tasks = []
    for k in sorted(removed_keys):
        t = old_lookup[k]
        wbs_name = old_wbs.get(t.get('wbs_id', ''), '')
        dur_hrs = _safe_float(t.get('target_drtn_hr_cnt', 0))
        removed_tasks.append({
            'task_code': k,
            'task_name': t.get('task_name', ''),
            'duration_days': round(dur_hrs / 8, 1),
            'wbs_name': wbs_name,
        })

    # Changed durations
    changed_durations = []
    for k in sorted(matched):
        old_dur = _safe_float(old_lookup[k].get('target_drtn_hr_cnt', 0)) / 8
        new_dur = _safe_float(new_lookup[k].get('target_drtn_hr_cnt', 0)) / 8
        if abs(old_dur - new_dur) >= 0.5:
            changed_durations.append({
                'task_code': k,
                'task_name': new_lookup[k].get('task_name', ''),
                'old_duration_days': round(old_dur, 1),
                'new_duration_days': round(new_dur, 1),
                'delta_days': round(new_dur - old_dur, 1),
            })

    # Date slippage
    date_slippage = []
    for k in sorted(matched):
        old_t = old_lookup[k]
        new_t = new_lookup[k]
        old_es = _parse_date(old_t.get('early_start_date', ''))
        new_es = _parse_date(new_t.get('early_start_date', ''))
        old_ef = _parse_date(old_t.get('early_end_date', ''))
        new_ef = _parse_date(new_t.get('early_end_date', ''))

        es_slip = (new_es - old_es).days if old_es and new_es else 0
        ef_slip = (new_ef - old_ef).days if old_ef and new_ef else 0

        if abs(es_slip) >= 1 or abs(ef_slip) >= 1:
            date_slippage.append({
                'task_code': k,
                'task_name': new_t.get('task_name', ''),
                'old_early_start': str(old_es.date()) if old_es else '',
                'new_early_start': str(new_es.date()) if new_es else '',
                'es_slip_days': es_slip,
                'old_early_finish': str(old_ef.date()) if old_ef else '',
                'new_early_finish': str(new_ef.date()) if new_ef else '',
                'ef_slip_days': ef_slip,
            })

    # Sort by largest slippage
    date_slippage.sort(key=lambda x: -max(abs(x['es_slip_days']), abs(x['ef_slip_days'])))

    # Status changes
    status_changes = []
    for k in sorted(matched):
        old_status = old_lookup[k].get('status_code', '')
        new_status = new_lookup[k].get('status_code', '')
        if old_status != new_status:
            status_changes.append({
                'task_code': k,
                'task_name': new_lookup[k].get('task_name', ''),
                'old_status': old_status,
                'new_status': new_status,
            })

    # Missed starts & finishes (against new data date)
    new_data_date = _parse_date(_get_data_date(new_tables))
    missed_starts = _find_missed_starts(new_filtered, new_data_date, old_lookup, match_by)
    missed_finishes = _find_missed_finishes(new_filtered, new_data_date, old_lookup, match_by)

    # Relationship changes
    changed_rels = _match_relationships(old_preds, new_preds, old_lookup, new_lookup, match_by)

    # SC dates -- resolve milestone against the new schedule (the anchor),
    # then mirror to the old schedule by match_by key so a task_id renumber
    # between exports doesn't break SC-slip alignment.
    new_sc = _resolve_milestone(new_tables, milestone_id=milestone_id)
    old_sc = _resolve_milestone(
        old_tables,
        milestone_id=(new_sc.get('task_code') if (match_by == 'task_code' and new_sc) else None)
                     or (new_sc.get('task_id') if new_sc else None),
    ) if new_sc else _resolve_milestone(old_tables, milestone_id=milestone_id)
    old_sc_date = old_sc['date'][:10] if old_sc and old_sc.get('date') else ''
    new_sc_date = new_sc['date'][:10] if new_sc and new_sc.get('date') else ''
    sc_slip = 0
    if old_sc_date and new_sc_date:
        d1 = _parse_date(old_sc_date)
        d2 = _parse_date(new_sc_date)
        if d1 and d2:
            sc_slip = (d2 - d1).days

    return {
        'old_data_date': _get_data_date(old_tables),
        'new_data_date': _get_data_date(new_tables),
        'added_tasks': added_tasks,
        'removed_tasks': removed_tasks,
        'changed_durations': changed_durations,
        'changed_relationships': changed_rels,
        'date_slippage': date_slippage,
        'missed_starts': missed_starts,
        'missed_finishes': missed_finishes,
        'status_changes': status_changes,
        'sc_date_old': old_sc_date,
        'sc_date_new': new_sc_date,
        'sc_slip_days': sc_slip,
        'sc_info_old': old_sc,
        'sc_info_new': new_sc,
    }


# ---------------------------------------------------------------------------
# Missed starts & finishes
# ---------------------------------------------------------------------------

def _find_missed_starts(tasks, data_date, ref_lookup=None, match_by='task_code'):
    """
    Activities planned to start by data_date but still TK_NotStart.
    Uses reference (old) schedule's ES if available, else own ES.
    """
    if not data_date:
        return []
    missed = []
    for t in tasks:
        if t.get('status_code', '') != 'TK_NotStart':
            continue
        key = t.get(match_by, '') or t.get('task_id', '')

        # Use reference schedule's planned start if available
        planned_es = None
        if ref_lookup and key in ref_lookup:
            planned_es = _parse_date(ref_lookup[key].get('early_start_date', ''))
        if not planned_es:
            planned_es = _parse_date(t.get('early_start_date', ''))

        if planned_es and planned_es <= data_date:
            missed.append({
                'task_code': key,
                'task_name': t.get('task_name', ''),
                'planned_start': str(planned_es.date()),
                'status': 'TK_NotStart',
            })
    return missed


def _find_missed_finishes(tasks, data_date, ref_lookup=None, match_by='task_code'):
    """
    Activities planned to finish by data_date but not TK_Complete.
    """
    if not data_date:
        return []
    missed = []
    for t in tasks:
        status = t.get('status_code', '')
        if status == 'TK_Complete':
            continue
        key = t.get(match_by, '') or t.get('task_id', '')

        planned_ef = None
        if ref_lookup and key in ref_lookup:
            planned_ef = _parse_date(ref_lookup[key].get('early_end_date', ''))
        if not planned_ef:
            planned_ef = _parse_date(t.get('early_end_date', ''))

        if planned_ef and planned_ef <= data_date:
            missed.append({
                'task_code': key,
                'task_name': t.get('task_name', ''),
                'planned_finish': str(planned_ef.date()),
                'status': status,
            })
    return missed


# ---------------------------------------------------------------------------
# Relationship matching
# ---------------------------------------------------------------------------

def _match_relationships(old_preds, new_preds, old_task_lookup, new_task_lookup, match_by):
    """Match relationships and find added, removed, changed."""
    def _rel_key(pred_row, task_lookup, match_by):
        succ_id = pred_row.get('task_id', '')
        pred_id = pred_row.get('pred_task_id', '')
        # Resolve to match_by key
        succ_task = None
        pred_task = None
        for k, v in task_lookup.items():
            if v.get('task_id') == succ_id:
                succ_task = k
            if v.get('task_id') == pred_id:
                pred_task = k
        if not succ_task or not pred_task:
            return None
        pred_type = pred_row.get('pred_type', '')
        return (pred_task, succ_task, pred_type)

    old_rels = {}
    for p in old_preds:
        key = _rel_key(p, old_task_lookup, match_by)
        if key:
            old_rels[key] = _safe_float(p.get('lag_hr_cnt', 0))

    new_rels = {}
    for p in new_preds:
        key = _rel_key(p, new_task_lookup, match_by)
        if key:
            new_rels[key] = _safe_float(p.get('lag_hr_cnt', 0))

    old_keys = set(old_rels.keys())
    new_keys = set(new_rels.keys())

    added = [{'pred_code': k[0], 'succ_code': k[1], 'type': k[2],
              'lag_days': round(new_rels[k] / 8, 1)} for k in sorted(new_keys - old_keys)]
    removed = [{'pred_code': k[0], 'succ_code': k[1], 'type': k[2],
                'lag_days': round(old_rels[k] / 8, 1)} for k in sorted(old_keys - new_keys)]

    # Check for lag changes on matched relationships
    changed = []
    for k in old_keys & new_keys:
        if abs(old_rels[k] - new_rels[k]) > 0.1:
            changed.append({
                'pred_code': k[0], 'succ_code': k[1], 'type': k[2],
                'old_lag_days': round(old_rels[k] / 8, 1),
                'new_lag_days': round(new_rels[k] / 8, 1),
            })

    return {'added_rels': added, 'removed_rels': removed, 'changed_rels': changed}


# ---------------------------------------------------------------------------
# Multi-schedule comparison (main entry point)
# ---------------------------------------------------------------------------

def compare_schedules(current_tables, baseline_tables=None, previous_tables=None,
                      match_by='task_code', milestone_id=None):
    """
    Flexible multi-schedule comparison.

    ``milestone_id`` identifies the project's terminal milestone (Substantial
    Completion finish marker, typically) for the cross-schedule SC-slip
    summary. Resolution happens against ``current_tables``; the matching task
    on each comparison schedule is found by ``match_by`` so SC dates align
    even when task_id renumbering occurred between exports. When omitted, the
    function auto-resolves to the single terminal non-WBS / non-LOE /
    non-complete milestone in ``current_tables``; multiple terminal
    milestones raise :class:`MilestoneAmbiguousError`.

    Args:
        current_tables: The current/updated schedule (required). Result of parse_xer().
        baseline_tables: Original baseline schedule (optional).
        previous_tables: Last week's/previous update (optional).
        match_by: 'task_code' or 'task_id'
        milestone_id: Optional explicit terminal milestone for SC-slip pinning.

    Returns dict with comparison results including SC tracking across all schedules.
    """
    result = {
        'current_data_date': _get_data_date(current_tables),
        'vs_baseline': None,
        'vs_previous': None,
        'current_missed_starts': [],
        'current_missed_finishes': [],
        'summary': {},
    }

    # Always compute missed starts/finishes against current schedule
    current_tasks = current_tables.get('TASK', [])
    skip_types = {'TT_WBS', 'TT_LOE'}
    current_filtered = [t for t in current_tasks if t.get('task_type', '') not in skip_types]
    data_date = _parse_date(_get_data_date(current_tables))

    result['current_missed_starts'] = _find_missed_starts(current_filtered, data_date)
    result['current_missed_finishes'] = _find_missed_finishes(current_filtered, data_date)

    # Resolve milestone on the current schedule (the anchor). If the caller
    # passed milestone_id, that pins the terminal; otherwise auto-resolve.
    # Cross-schedule SC pinning uses match_by so renumbered task_ids don't
    # break the comparison.
    current_sc = _resolve_milestone(current_tables, milestone_id=milestone_id)
    current_sc_date = current_sc['date'][:10] if current_sc and current_sc.get('date') else ''

    # The key we'll use to find the same milestone in baseline/previous --
    # task_code when match_by is task_code, otherwise task_id.
    cross_key = None
    if current_sc:
        cross_key = current_sc.get(match_by) or current_sc.get('task_id')

    baseline_sc_date = ''
    previous_sc_date = ''

    if baseline_tables:
        result['vs_baseline'] = compare_xer_pair(
            baseline_tables, current_tables, match_by, milestone_id=milestone_id)
        baseline_sc = _resolve_milestone(baseline_tables, milestone_id=cross_key)
        baseline_sc_date = baseline_sc['date'][:10] if baseline_sc and baseline_sc.get('date') else ''

    if previous_tables:
        result['vs_previous'] = compare_xer_pair(
            previous_tables, current_tables, match_by, milestone_id=milestone_id)
        previous_sc = _resolve_milestone(previous_tables, milestone_id=cross_key)
        previous_sc_date = previous_sc['date'][:10] if previous_sc and previous_sc.get('date') else ''

    # Summary
    sc_slip_baseline = 0
    sc_slip_previous = 0
    if baseline_sc_date and current_sc_date:
        d1, d2 = _parse_date(baseline_sc_date), _parse_date(current_sc_date)
        if d1 and d2:
            sc_slip_baseline = (d2 - d1).days
    if previous_sc_date and current_sc_date:
        d1, d2 = _parse_date(previous_sc_date), _parse_date(current_sc_date)
        if d1 and d2:
            sc_slip_previous = (d2 - d1).days

    result['summary'] = {
        'baseline_sc_date': baseline_sc_date,
        'previous_sc_date': previous_sc_date,
        'current_sc_date': current_sc_date,
        'sc_slip_from_baseline_days': sc_slip_baseline,
        'sc_slip_from_previous_days': sc_slip_previous,
        'sc_task_name': current_sc.get('task_name', '') if current_sc else '',
        'sc_task_code': current_sc.get('task_code', '') if current_sc else '',
        'total_added': len(result['vs_baseline']['added_tasks']) if result['vs_baseline'] else 0,
        'total_removed': len(result['vs_baseline']['removed_tasks']) if result['vs_baseline'] else 0,
        'missed_starts': len(result['current_missed_starts']),
        'missed_finishes': len(result['current_missed_finishes']),
    }

    return result


# ---------------------------------------------------------------------------
# HTML Report
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
.sc-timeline { display: flex; gap: 32px; padding: 20px 32px; background: #f8f9fa; border-bottom: 1px solid #ddd; flex-wrap: wrap; }
.sc-box { text-align: center; padding: 16px 24px; background: white; border-radius: 8px; box-shadow: 0 1px 2px rgba(0,0,0,0.1); min-width: 160px; }
.sc-box .label { font-size: 12px; color: #666; text-transform: uppercase; margin-bottom: 4px; }
.sc-box .date { font-size: 18px; font-weight: 700; color: #1a3a4a; }
.sc-box .slip { font-size: 13px; margin-top: 4px; }
.sc-box .slip.neg { color: #c0392b; }
.sc-box .slip.pos { color: #27ae60; }
.summary-grid { display: flex; gap: 24px; padding: 16px 32px; background: white; border-bottom: 1px solid #ddd; flex-wrap: wrap; }
.stat-box { text-align: center; padding: 12px 24px; }
.stat-box .num { font-size: 28px; font-weight: 700; }
.stat-box .label { font-size: 12px; color: #666; text-transform: uppercase; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th { background: #2c3e50; color: white; padding: 8px 10px; text-align: left; }
td { padding: 6px 10px; border-bottom: 1px solid #eee; }
tr:hover { background: #f0f7ff; }
tr.missed { background: #fde8e8; }
tr.missed:hover { background: #fbd4d4; }
.neg { color: #c0392b; font-weight: 600; }
.pos { color: #27ae60; font-weight: 600; }
.tag { display: inline-block; padding: 2px 8px; border-radius: 3px; font-size: 11px; font-weight: 600; }
.tag-added { background: #27ae60; color: white; }
.tag-removed { background: #c0392b; color: white; }
.tag-changed { background: #e67e22; color: white; }
.empty-note { color: #999; font-style: italic; padding: 16px 0; }
"""


def render_comparison_html(comparison, output_path):
    """
    Write standalone HTML comparison report.

    Args:
        comparison: Result from compare_schedules()
        output_path: File path to write
    """
    c = comparison
    s = c.get('summary', {})

    # Tracking info
    if s.get('sc_task_name'):
        tracking = f"Tracking to: {s['sc_task_name']} [{s.get('sc_task_code', '')}]"
    else:
        tracking = "No SC milestone found"

    # SC Timeline
    sc_boxes = []
    if s.get('baseline_sc_date'):
        sc_boxes.append(f"""<div class="sc-box">
            <div class="label">Baseline SC</div>
            <div class="date">{s['baseline_sc_date']}</div>
        </div>""")
    if s.get('previous_sc_date'):
        slip = s.get('sc_slip_from_previous_days', 0) - s.get('sc_slip_from_baseline_days', 0)
        sc_boxes.append(f"""<div class="sc-box">
            <div class="label">Previous Update SC</div>
            <div class="date">{s['previous_sc_date']}</div>
        </div>""")
    if s.get('current_sc_date'):
        slip_b = s.get('sc_slip_from_baseline_days', 0)
        slip_p = s.get('sc_slip_from_previous_days', 0)
        slips = []
        if s.get('baseline_sc_date'):
            cls = 'neg' if slip_b > 0 else 'pos'
            slips.append(f'<div class="slip {cls}">{slip_b:+d} days from baseline</div>')
        if s.get('previous_sc_date'):
            cls = 'neg' if slip_p > 0 else 'pos'
            slips.append(f'<div class="slip {cls}">{slip_p:+d} days from previous</div>')
        sc_boxes.append(f"""<div class="sc-box">
            <div class="label">Current SC</div>
            <div class="date">{s['current_sc_date']}</div>
            {''.join(slips)}
        </div>""")

    sc_timeline = f'<div class="sc-timeline">{"".join(sc_boxes)}</div>' if sc_boxes else ''

    # Summary stats
    summary_html = f"""<div class="summary-grid">
        <div class="stat-box"><div class="num" style="color:#c0392b">{s.get('missed_starts',0)}</div><div class="label">Missed Starts</div></div>
        <div class="stat-box"><div class="num" style="color:#c0392b">{s.get('missed_finishes',0)}</div><div class="label">Missed Finishes</div></div>
        <div class="stat-box"><div class="num" style="color:#27ae60">{s.get('total_added',0)}</div><div class="label">Added</div></div>
        <div class="stat-box"><div class="num" style="color:#e67e22">{s.get('total_removed',0)}</div><div class="label">Removed</div></div>
    </div>"""

    sections = []

    # Missed starts (always shown)
    ms = c.get('current_missed_starts', [])
    if ms:
        rows = ''.join(f'<tr class="missed"><td>{m["task_code"]}</td><td>{m["task_name"]}</td>'
                        f'<td>{m.get("planned_start","")}</td><td>{m.get("status","")}</td></tr>'
                        for m in ms)
        sections.append(f"""<div class="section"><h2>Missed Starts ({len(ms)})</h2>
        <table><thead><tr><th>Activity ID</th><th>Name</th><th>Planned Start</th><th>Status</th></tr></thead>
        <tbody>{rows}</tbody></table></div>""")

    # Missed finishes (always shown)
    mf = c.get('current_missed_finishes', [])
    if mf:
        rows = ''.join(f'<tr class="missed"><td>{m["task_code"]}</td><td>{m["task_name"]}</td>'
                        f'<td>{m.get("planned_finish","")}</td><td>{m.get("status","")}</td></tr>'
                        for m in mf)
        sections.append(f"""<div class="section"><h2>Missed Finishes ({len(mf)})</h2>
        <table><thead><tr><th>Activity ID</th><th>Name</th><th>Planned Finish</th><th>Status</th></tr></thead>
        <tbody>{rows}</tbody></table></div>""")

    # Comparison sections (vs baseline or vs previous)
    for comp_key, comp_label in [('vs_baseline', 'vs. Baseline'), ('vs_previous', 'vs. Previous Update')]:
        comp = c.get(comp_key)
        if not comp:
            continue

        # Date slippage
        slippage = comp.get('date_slippage', [])
        if slippage:
            rows = []
            for sl in slippage[:50]:  # Cap at 50
                es_cls = 'neg' if sl['es_slip_days'] > 0 else ('pos' if sl['es_slip_days'] < 0 else '')
                ef_cls = 'neg' if sl['ef_slip_days'] > 0 else ('pos' if sl['ef_slip_days'] < 0 else '')
                rows.append(
                    f'<tr><td>{sl["task_code"]}</td><td>{sl["task_name"]}</td>'
                    f'<td>{sl.get("old_early_start","")}</td><td>{sl.get("new_early_start","")}</td>'
                    f'<td class="{es_cls}">{sl["es_slip_days"]:+d}</td>'
                    f'<td>{sl.get("old_early_finish","")}</td><td>{sl.get("new_early_finish","")}</td>'
                    f'<td class="{ef_cls}">{sl["ef_slip_days"]:+d}</td></tr>'
                )
            sections.append(f"""<div class="section"><h2>Date Slippage {comp_label} ({len(slippage)})</h2>
            <table><thead><tr><th>Activity ID</th><th>Name</th><th>Old ES</th><th>New ES</th><th>ES Slip</th>
            <th>Old EF</th><th>New EF</th><th>EF Slip</th></tr></thead>
            <tbody>{''.join(rows)}</tbody></table></div>""")

        # Added/removed tasks
        added = comp.get('added_tasks', [])
        if added:
            rows = ''.join(f'<tr><td><span class="tag tag-added">NEW</span> {a["task_code"]}</td>'
                            f'<td>{a["task_name"]}</td><td>{a["duration_days"]}d</td><td>{a.get("wbs_name","")}</td></tr>'
                            for a in added)
            sections.append(f"""<div class="section"><h2>Added Activities {comp_label} ({len(added)})</h2>
            <table><thead><tr><th>Activity ID</th><th>Name</th><th>Duration</th><th>WBS</th></tr></thead>
            <tbody>{rows}</tbody></table></div>""")

        removed = comp.get('removed_tasks', [])
        if removed:
            rows = ''.join(f'<tr><td><span class="tag tag-removed">DEL</span> {r["task_code"]}</td>'
                            f'<td>{r["task_name"]}</td><td>{r["duration_days"]}d</td><td>{r.get("wbs_name","")}</td></tr>'
                            for r in removed)
            sections.append(f"""<div class="section"><h2>Removed Activities {comp_label} ({len(removed)})</h2>
            <table><thead><tr><th>Activity ID</th><th>Name</th><th>Duration</th><th>WBS</th></tr></thead>
            <tbody>{rows}</tbody></table></div>""")

        # Duration changes
        dur_changes = comp.get('changed_durations', [])
        if dur_changes:
            rows = []
            for d in dur_changes:
                cls = 'neg' if d['delta_days'] > 0 else 'pos'
                rows.append(f'<tr><td>{d["task_code"]}</td><td>{d["task_name"]}</td>'
                            f'<td>{d["old_duration_days"]}d</td><td>{d["new_duration_days"]}d</td>'
                            f'<td class="{cls}">{d["delta_days"]:+.1f}d</td></tr>')
            sections.append(f"""<div class="section"><h2>Duration Changes {comp_label} ({len(dur_changes)})</h2>
            <table><thead><tr><th>Activity ID</th><th>Name</th><th>Old Duration</th><th>New Duration</th><th>Change</th></tr></thead>
            <tbody>{''.join(rows)}</tbody></table></div>""")

        # Status changes
        status = comp.get('status_changes', [])
        if status:
            rows = ''.join(f'<tr><td>{sc["task_code"]}</td><td>{sc["task_name"]}</td>'
                            f'<td>{sc["old_status"]}</td><td>{sc["new_status"]}</td></tr>'
                            for sc in status)
            sections.append(f"""<div class="section"><h2>Status Changes {comp_label} ({len(status)})</h2>
            <table><thead><tr><th>Activity ID</th><th>Name</th><th>Old Status</th><th>New Status</th></tr></thead>
            <tbody>{rows}</tbody></table></div>""")

    if not sections:
        sections.append('<div class="section"><p class="empty-note">No changes detected.</p></div>')

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Schedule Comparison Report</title>
<style>{_WESTLAND_CSS}</style></head><body>
<div class="container">
<div class="header">
  <h1>Schedule Comparison Report</h1>
  <div class="tracking">{tracking}</div>
  <div class="meta">Current Data Date: {c.get('current_data_date','')} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}</div>
</div>
{sc_timeline}
{summary_html}
{''.join(sections)}
</div></body></html>"""

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return output_path
