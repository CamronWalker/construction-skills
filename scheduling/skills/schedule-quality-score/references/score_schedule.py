"""
Schedule Quality Score — Scoring & Report Generation

This module contains all functions needed to score a Primavera P6 schedule
against best practice metrics and generate a Markdown quality report.

Usage:
    from score_schedule import compute_quality_score, generate_quality_report

    score, grade, scored, info, deductions, scope = compute_quality_score(tasks, preds, data_date)
    report = generate_quality_report(project_name, data_date, score, grade, scored, info, deductions, scope)
"""

from collections import defaultdict, Counter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def safe_float(val, default=0):
    try:
        return float(val) if val else default
    except (ValueError, TypeError):
        return default


def find_sc_milestone(tasks):
    """Find the Substantial Completion milestone (incomplete, non-WBS/LOE)."""
    exc = {'TT_WBS', 'TT_LOE'}

    # Priority 1: "Substantial Completion & Turnover to Owner"
    for t in tasks:
        if t.get('task_type', '') in exc:
            continue
        name = t.get('task_name', '')
        if 'Substantial Completion' in name and 'Turnover to Owner' in name:
            if t.get('status_code', '') != 'TK_Complete':
                return t['task_id']

    # Priority 2: Exact "Substantial Completion" milestone
    for t in tasks:
        if t.get('task_type', '') in exc:
            continue
        if t.get('task_name', '').strip() == 'Substantial Completion':
            if t.get('task_type', '') in ('TT_FinMile', 'TT_Mile'):
                if t.get('status_code', '') != 'TK_Complete':
                    return t['task_id']

    # Priority 3: Any milestone containing "Substantial Completion"
    for t in tasks:
        if t.get('task_type', '') in exc:
            continue
        if t.get('task_type', '') not in ('TT_FinMile', 'TT_Mile'):
            continue
        if 'Substantial Completion' in t.get('task_name', ''):
            if t.get('status_code', '') != 'TK_Complete':
                return t['task_id']

    return None  # No SC milestone found — use full incomplete scope


def get_predecessor_scope(sc_task_id, preds):
    """Walk backward from SC milestone to get all transitive predecessors."""
    succ_to_preds = defaultdict(set)
    for p in preds:
        succ_to_preds[p.get('task_id', '')].add(p.get('pred_task_id', ''))

    visited = set()
    queue = [sc_task_id]
    while queue:
        tid = queue.pop()
        if tid in visited:
            continue
        visited.add(tid)
        for pred_id in succ_to_preds.get(tid, set()):
            if pred_id not in visited:
                queue.append(pred_id)
    return visited


GRADE_SCALE = [
    (97, 'A+'), (93, 'A'), (90, 'A-'), (87, 'B+'), (83, 'B'), (80, 'B-'),
    (77, 'C+'), (73, 'C'), (70, 'C-'), (67, 'D+'), (65, 'D'), (0, 'D-')
]


def get_grade(score):
    for threshold, grade in GRADE_SCALE:
        if score >= threshold:
            return grade
    return 'D-'


# ---------------------------------------------------------------------------
# Main scoring function
# ---------------------------------------------------------------------------

def compute_quality_score(tasks, preds, data_date=None):
    """
    Compute schedule quality score and all metrics.
    Pass ALL tasks and ALL predecessors — filtering is handled internally.
    Returns: (score, grade, scored_metrics, info_metrics, deductions, scope)
    """
    # --- SCOPE FILTERING ---
    exclude_types = {'TT_WBS', 'TT_LOE'}
    milestone_types = {'TT_Mile', 'TT_FinMile'}

    incomplete = [t for t in tasks
                  if t.get('status_code', '') != 'TK_Complete'
                  and t.get('task_type', '') not in exclude_types]

    # SC scope filtering
    sc_id = find_sc_milestone(tasks)
    if sc_id:
        scope_ids = get_predecessor_scope(sc_id, preds)
        incomplete = [t for t in incomplete if t['task_id'] in scope_ids]

    inc_ids = {t['task_id'] for t in incomplete}
    inc_rels = [p for p in preds
                if p.get('task_id', '') in inc_ids
                and p.get('pred_task_id', '') in inc_ids]

    activities = [t for t in incomplete if t.get('task_type', '') not in milestone_types]
    milestones = [t for t in incomplete if t.get('task_type', '') in milestone_types]

    n_inc = len(incomplete)
    n_act = len(activities)
    n_rels = len(inc_rels)

    scored = {}
    info = {}
    deductions = {}
    score = 100.0

    # --- 1. RELATIONSHIP TYPES ---
    fs = sum(1 for p in inc_rels if p.get('pred_type', '') in ('FS', 'PR_FS'))
    ss = sum(1 for p in inc_rels if p.get('pred_type', '') in ('SS', 'PR_SS'))
    ff = sum(1 for p in inc_rels if p.get('pred_type', '') in ('FF', 'PR_FF'))
    sf = sum(1 for p in inc_rels if p.get('pred_type', '') in ('SF', 'PR_SF'))

    fs_pct = round(fs / max(n_rels, 1) * 100, 1)
    ss_pct = round(ss / max(n_rels, 1) * 100, 1)
    ff_pct = round(ff / max(n_rels, 1) * 100, 1)
    sf_pct = round(sf / max(n_rels, 1) * 100, 1)

    scored['fs'] = {'count': fs, 'total': n_rels, 'pct': fs_pct}
    scored['ss'] = {'count': ss, 'total': n_rels, 'pct': ss_pct}
    scored['ff'] = {'count': ff, 'total': n_rels, 'pct': ff_pct}
    scored['sf'] = {'count': sf, 'total': n_rels, 'pct': sf_pct}

    if fs_pct < 80:
        d = 2.0; deductions['FS %'] = d; score -= d
    elif fs_pct < 90:
        d = 1.0; deductions['FS %'] = d; score -= d
    if ss_pct > 10:
        d = 2.0; deductions['SS %'] = d; score -= d
    elif ss_pct > 5:
        d = 1.0; deductions['SS %'] = d; score -= d
    if ff_pct > 10:
        d = 2.0; deductions['FF %'] = d; score -= d
    elif ff_pct > 5:
        d = 1.0; deductions['FF %'] = d; score -= d
    if sf > 0 and sf_pct >= 1:
        d = 2.0; deductions['SF %'] = d; score -= d

    # --- 2. AVG FLOAT ---
    float_vals = [safe_float(t.get('total_float_hr_cnt', 0)) for t in activities]
    avg_float_days = round(sum(float_vals) / max(len(float_vals), 1) / 8, 1) if float_vals else 0
    scored['avg_float'] = {'value': avg_float_days, 'total': n_act}
    neg_float_schedule = avg_float_days < 0  # Used to skip CP and Ratio

    if avg_float_days < 10:
        d = 2.0; deductions['Avg Float'] = d; score -= d
    elif avg_float_days < 15:
        d = 1.0; deductions['Avg Float'] = d; score -= d
    elif avg_float_days > 44:
        d = 2.0; deductions['Avg Float'] = d; score -= d

    # --- 3. CRITICAL PATH % --- (skip for negative float schedules)
    critical = [t for t in incomplete if abs(safe_float(t.get('total_float_hr_cnt', 0))) <= 8]
    cp_pct = round(len(critical) / max(n_inc, 1) * 100, 1)
    scored['critical_path'] = {'count': len(critical), 'total': n_inc, 'pct': cp_pct,
                                'skipped': neg_float_schedule}

    if not neg_float_schedule:
        if cp_pct < 5 or cp_pct > 25:
            d = 2.5; deductions['Critical Path %'] = d; score -= d
        elif cp_pct < 10 or cp_pct > 20:
            d = 1.5; deductions['Critical Path %'] = d; score -= d

    # --- 4. HIGH FLOAT --- (>40% threshold)
    high_float = [t for t in activities if safe_float(t.get('total_float_hr_cnt', 0)) > 352]
    hf_pct = round(len(high_float) / max(n_inc, 1) * 100, 1)
    scored['high_float'] = {'count': len(high_float), 'total': n_inc, 'pct': hf_pct}
    if hf_pct > 40:
        d = 2.5
        deductions['High Float'] = d; score -= d

    # --- 5. MISSING LOGIC --- (all rels, proportional, total incomplete denom)
    # Build lookup from ALL relationships in the schedule (not just in-scope)
    all_succs = defaultdict(set)
    all_preds_map = defaultdict(set)
    for p in preds:
        all_succs[p.get('pred_task_id', '')].add(p.get('task_id', ''))
        all_preds_map[p.get('task_id', '')].add(p.get('pred_task_id', ''))

    open_ids = set()
    for t in activities:
        tid = t['task_id']
        if not all_succs.get(tid) or not all_preds_map.get(tid):
            open_ids.add(tid)

    ml_pct = round(len(open_ids) / max(n_inc, 1) * 100, 1)
    scored['missing_logic'] = {'count': len(open_ids), 'total': n_inc, 'pct': ml_pct}

    if ml_pct >= 3:
        d = min(10.0, round(ml_pct, 1))
        deductions['Missing Logic'] = d; score -= d

    # --- 6. TOTAL RELATIONSHIP RATIO --- (skip for negative float)
    ratio = round(n_rels / max(n_inc, 1), 1)
    scored['rel_ratio'] = {'count': n_rels, 'total': n_inc, 'ratio': ratio,
                            'skipped': neg_float_schedule}

    if not neg_float_schedule:
        if ratio < 1.25:
            d = 5.0; deductions['Rel Ratio'] = d; score -= d
        elif ratio < 1.5:
            d = 2.5; deductions['Rel Ratio'] = d; score -= d

    # --- 7. CONSTRAINTS --- (all types except ALAP, proportional)
    hard_codes = {'CS_MSO', 'CS_MFO', 'CS_MEO', 'CS_MANDSTART', 'CS_MANDEND', 'CS_MANDFIN'}
    soft_codes = {'CS_SNET', 'CS_SNLT', 'CS_FNET', 'CS_FNLT',
                  'CS_MSOA', 'CS_MSOB', 'CS_MEOA', 'CS_MEOB'}
    all_constraint_codes = hard_codes | soft_codes  # CS_ALAP intentionally excluded

    constrained = 0
    hard_count = 0
    soft_count = 0
    alap_count = 0
    for t in incomplete:
        c1 = t.get('cstr_type', t.get('constraint_type', ''))
        c2 = t.get('cstr_type2', t.get('constraint_type2', ''))
        if c1 in all_constraint_codes or c2 in all_constraint_codes:
            constrained += 1
        if c1 in hard_codes or c2 in hard_codes:
            hard_count += 1
        if c1 in soft_codes or c2 in soft_codes:
            soft_count += 1
        if c1 == 'CS_ALAP' or c2 == 'CS_ALAP':
            alap_count += 1

    cstr_pct = round(constrained / max(n_inc, 1) * 100, 1)
    scored['constraints'] = {'count': constrained, 'total': n_inc, 'pct': cstr_pct}

    if cstr_pct > 1:
        d = min(20.0, round(cstr_pct, 1))
        deductions['Constraints'] = d; score -= d

    info['hard_constraints'] = {'count': hard_count, 'pct': round(hard_count / max(n_inc, 1) * 100, 1)}
    info['soft_constraints'] = {'count': soft_count, 'pct': round(soft_count / max(n_inc, 1) * 100, 1)}
    info['alap_constraints'] = {'count': alap_count, 'pct': round(alap_count / max(n_inc, 1) * 100, 1)}

    # --- INFORMATIONAL METRICS ---

    # High Duration (informational only)
    high_dur = [t for t in activities
                if safe_float(t.get('target_drtn_hr_cnt', t.get('remain_drtn_hr_cnt', 0))) > 352]
    info['high_duration'] = {'count': len(high_dur),
                              'pct': round(len(high_dur) / max(n_act, 1) * 100, 1)}

    # Positive / Negative Lag (informational only)
    pos_lags = [p for p in inc_rels if safe_float(p.get('lag_hr_cnt', 0)) > 0]
    neg_lags = [p for p in inc_rels if safe_float(p.get('lag_hr_cnt', 0)) < 0]
    info['positive_lag'] = {'count': len(pos_lags),
                             'pct': round(len(pos_lags) / max(n_rels, 1) * 100, 1)}
    info['negative_lag'] = {'count': len(neg_lags),
                             'pct': round(len(neg_lags) / max(n_rels, 1) * 100, 1)}

    # Convergence / Divergence
    pred_cnt = defaultdict(int)
    succ_cnt = defaultdict(int)
    for p in inc_rels:
        pred_cnt[p.get('task_id', '')] += 1
        succ_cnt[p.get('pred_task_id', '')] += 1
    info['convergence'] = sum(1 for v in pred_cnt.values() if v >= 5)
    info['divergence'] = sum(1 for v in succ_cnt.values() if v >= 5)

    # Duplicates
    pairs = Counter()
    for p in inc_rels:
        pairs[(p.get('pred_task_id', ''), p.get('task_id', ''))] += 1
    info['duplicate_rels'] = sum(v - 1 for v in pairs.values() if v > 1)

    # Low / Negative float
    info['low_float'] = len([t for t in activities
                             if 0 < safe_float(t.get('total_float_hr_cnt', 0)) <= 80])
    info['negative_float'] = len([t for t in incomplete
                                   if safe_float(t.get('total_float_hr_cnt', 0)) < 0])

    # One day activities
    info['one_day'] = len([t for t in activities
                           if safe_float(t.get('target_drtn_hr_cnt', 0)) == 8])

    # Dangling
    fs_ss_pred = set()
    fs_ff_succ = set()
    for p in inc_rels:
        pt = p.get('pred_type', '')
        if pt in ('FS', 'PR_FS', 'SS', 'PR_SS'):
            fs_ss_pred.add(p.get('task_id', ''))
        if pt in ('FS', 'PR_FS', 'FF', 'PR_FF'):
            fs_ff_succ.add(p.get('pred_task_id', ''))
    info['dangling'] = len([t for t in activities
                            if t['task_id'] not in fs_ss_pred
                            or t['task_id'] not in fs_ff_succ])

    # Status metrics (need data_date)
    if data_date:
        from datetime import datetime

        def parse_dt(v):
            if not v or not v.strip():
                return None
            for fmt in ['%Y-%m-%d %H:%M', '%Y-%m-%d']:
                try:
                    return datetime.strptime(v.strip(), fmt)
                except ValueError:
                    pass
            return None

        active_ids = {t['task_id'] for t in tasks if t.get('status_code') in ('TK_Active', 'TK_Complete')}
        not_started = {t['task_id'] for t in tasks if t.get('status_code') == 'TK_NotStart'}
        info['out_of_sequence'] = sum(1 for p in preds
                                       if p.get('task_id', '') in active_ids
                                       and p.get('pred_task_id', '') in not_started)
        info['started_zero'] = len([t for t in incomplete
                                     if t.get('status_code') == 'TK_Active'
                                     and safe_float(t.get('phys_complete_pct', 0)) == 0])
        info['future_actual'] = sum(1 for t in tasks
                                     if (parse_dt(t.get('act_start_date', '')) or datetime.min) > data_date
                                     or (parse_dt(t.get('act_end_date', '')) or datetime.min) > data_date)
        info['missing_actual_finish'] = len([t for t in tasks
                                              if t.get('status_code') == 'TK_Complete'
                                              and not t.get('act_end_date', '').strip()])

    # Final score and grade
    score = round(max(0, score), 1)
    grade = get_grade(score)

    scope_info = {
        'total_tasks': len(tasks),
        'complete': len([t for t in tasks if t.get('status_code') == 'TK_Complete']),
        'incomplete_activities': n_act,
        'incomplete_milestones': len(milestones),
        'incomplete_total': n_inc,
        'total_relationships': n_rels,
        'sc_filtered': sc_id is not None,
        'neg_float_schedule': neg_float_schedule,
    }

    return score, grade, scored, info, deductions, scope_info


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def end_finding(key, scored, info):
    """Generate a one-line finding description for a deduction."""
    findings = {
        'Missing Logic': f"{scored['missing_logic']['count']} activities lack a predecessor or successor. Add logic ties to integrate them into the network.",
        'Constraints': f"{scored['constraints']['count']} activities ({scored['constraints']['pct']}%) have date constraints. Review whether constraints are necessary or if logic ties can replace them.",
        'Critical Path %': f"Critical path is {scored['critical_path']['pct']}% of the schedule (target: 10-20%). {'Too few activities are driving the finish date - logic may be sparse.' if scored['critical_path']['pct'] < 10 else 'Too many activities are critical - schedule may be over-compressed.'}",
        'High Float': f"{scored['high_float']['count']} activities ({scored['high_float']['pct']}%) have float > 44 days. Add missing logic ties to pull them into the network.",
        'FS %': f"Only {scored['fs']['pct']}% of relationships are Finish-to-Start (target: >= 90%). Review SS/FF usage for appropriateness.",
        'FF %': f"{scored['ff']['pct']}% of relationships are Finish-to-Finish (target: <= 5%). Excessive FF ties can obscure the critical path.",
        'SS %': f"{scored['ss']['pct']}% of relationships are Start-to-Start (target: <= 5%). Ensure SS ties represent genuine concurrent work.",
        'SF %': f"Start-to-Finish relationships found ({scored['sf']['count']}). SF logic is almost never appropriate - replace with standard FS/SS/FF.",
        'Avg Float': f"Average float is {scored['avg_float']['value']} days (target: 15-44). {'Schedule is too tight or behind - float is compressed.' if scored['avg_float']['value'] < 15 else 'Logic network is too loose - add ties to reduce float.'}",
        'Rel Ratio': f"Relationship ratio is {scored['rel_ratio']['ratio']}:1 (target: >= 1.5:1). The logic network is too sparse - add predecessor/successor ties.",
    }
    return findings.get(key, "Review this metric for improvement opportunities.")


def generate_quality_report(project_name, data_date, score, grade, scored, info, deductions, scope):
    """Generate a Markdown schedule quality report."""
    lines = []
    lines.append(f"# Schedule Quality Report — {project_name}")
    lines.append("")
    lines.append(f"**Data Date:** {data_date}")

    scope_note = ""
    if scope.get('sc_filtered'):
        scope_note = " (SC-filtered)"
    lines.append(f"**Scope{scope_note}:** {scope['incomplete_activities']} activities | "
                 f"{scope['incomplete_milestones']} milestones | "
                 f"{scope['total_relationships']} relationships")
    lines.append(f"**Relationship Ratio:** {scored['rel_ratio']['ratio']}:1")
    if scope.get('neg_float_schedule'):
        lines.append(f"**Note:** Schedule has negative average float ({scored['avg_float']['value']} days) — CP% and Ratio metrics skipped")
    lines.append("")

    # Grade box
    lines.append(f"## Best Practice Score: {grade} ({score}/100)")
    lines.append("")
    if deductions:
        total_ded = sum(deductions.values())
        lines.append(f"*{len(deductions)} deduction(s) totaling -{total_ded} points*")
    else:
        lines.append("*No deductions — perfect score*")
    lines.append("")

    # Scored Metrics Table
    lines.append("## Scored Metrics")
    lines.append("")
    lines.append("| # | Metric | Value | Threshold | Deduction | Status |")
    lines.append("|---|--------|-------|-----------|-----------|--------|")

    def row(num, name, value_str, threshold, ded_key, skipped=False):
        if skipped:
            lines.append(f"| {num} | {name} | {value_str} | {threshold} | — | ⏭️ SKIP |")
            return
        ded = deductions.get(ded_key, 0)
        status = "PASS" if ded == 0 else "FAIL"
        ded_str = f"-{ded} pts" if ded > 0 else "—"
        emoji = "✅" if ded == 0 else "❌"
        lines.append(f"| {num} | {name} | {value_str} | {threshold} | {ded_str} | {emoji} {status} |")

    s = scored
    row(1, "Finish to Start", f"{s['fs']['count']}/{s['fs']['total']} ({s['fs']['pct']}%)", ">= 90%", "FS %")
    row(2, "Start to Start", f"{s['ss']['count']} ({s['ss']['pct']}%)", "<= 5%", "SS %")
    row(3, "Finish to Finish", f"{s['ff']['count']} ({s['ff']['pct']}%)", "<= 5%", "FF %")
    row(4, "Start to Finish", f"{s['sf']['count']} ({s['sf']['pct']}%)", "0%", "SF %")
    row(5, "Avg Activity Total Float", f"{s['avg_float']['value']} days", "15-44 days", "Avg Float")
    row(6, "Critical Path %",
        f"{s['critical_path']['count']}/{s['critical_path']['total']} ({s['critical_path']['pct']}%)",
        "10-20%", "Critical Path %", skipped=s['critical_path'].get('skipped', False))
    row(7, "High Float Activities", f"{s['high_float']['count']}/{s['high_float']['total']} ({s['high_float']['pct']}%)", "<= 40%", "High Float")
    row(8, "Missing Logic", f"{s['missing_logic']['count']}/{s['missing_logic']['total']} ({s['missing_logic']['pct']}%)", "< 3%", "Missing Logic")
    row(9, "Total Relationships", f"{s['rel_ratio']['count']} ({s['rel_ratio']['ratio']}:1)", ">= 1.5:1",
        "Rel Ratio", skipped=s['rel_ratio'].get('skipped', False))
    row(10, "Constraints", f"{s['constraints']['count']}/{s['constraints']['total']} ({s['constraints']['pct']}%)", "<= 1%", "Constraints")

    lines.append("")

    # Key Findings
    if deductions:
        lines.append("## Key Findings")
        lines.append("")
        priority_order = ['Missing Logic', 'Constraints', 'Critical Path %',
                          'High Float', 'FS %', 'FF %', 'SS %', 'SF %',
                          'Avg Float', 'Rel Ratio']
        for key in priority_order:
            if key in deductions:
                d = deductions[key]
                lines.append(f"- **{key}** (-{d} pts): {end_finding(key, scored, info)}")
        lines.append("")

    # Informational Metrics
    lines.append("## Informational Metrics")
    lines.append("")
    lines.append("These metrics provide additional context but do not affect the score.")
    lines.append("")
    lines.append("| Metric | Value | Notes |")
    lines.append("|--------|-------|-------|")
    lines.append(f"| Low Float Activities | {info.get('low_float', 0)} | Float 0-10 days |")
    lines.append(f"| Negative Float | {info.get('negative_float', 0)} | Schedule can't make deadline |")
    lines.append(f"| Hard Constraints | {info.get('hard_constraints', {}).get('count', 0)} ({info.get('hard_constraints', {}).get('pct', 0)}%) | Mandatory date locks |")
    lines.append(f"| Soft Constraints | {info.get('soft_constraints', {}).get('count', 0)} ({info.get('soft_constraints', {}).get('pct', 0)}%) | Directional boundaries |")
    lines.append(f"| ALAP Constraints | {info.get('alap_constraints', {}).get('count', 0)} ({info.get('alap_constraints', {}).get('pct', 0)}%) | Not scored |")
    lines.append(f"| High Duration | {info.get('high_duration', {}).get('count', 0)} ({info.get('high_duration', {}).get('pct', 0)}%) | > 44 working days |")
    lines.append(f"| Positive Lag | {info.get('positive_lag', {}).get('count', 0)} ({info.get('positive_lag', {}).get('pct', 0)}%) | — |")
    lines.append(f"| Negative Lag | {info.get('negative_lag', {}).get('count', 0)} ({info.get('negative_lag', {}).get('pct', 0)}%) | — |")
    lines.append(f"| Convergence Bottlenecks | {info.get('convergence', 0)} | >= 5 predecessors |")
    lines.append(f"| Divergence Bottlenecks | {info.get('divergence', 0)} | >= 5 successors |")
    lines.append(f"| Duplicate Relationships | {info.get('duplicate_rels', 0)} | — |")
    lines.append(f"| Dangling Activities | {info.get('dangling', 0)} | Unbounded start or finish |")
    lines.append(f"| One Day Activities | {info.get('one_day', 0)} | Duration = 1 day |")
    if 'out_of_sequence' in info:
        lines.append(f"| Out of Sequence | {info['out_of_sequence']} | — |")
        lines.append(f"| Started with 0% | {info.get('started_zero', 0)} | — |")
        lines.append(f"| Future Actual Dates | {info.get('future_actual', 0)} | — |")
        lines.append(f"| Missing Actual Finish | {info.get('missing_actual_finish', 0)} | — |")
    lines.append("")

    return '\n'.join(lines)
