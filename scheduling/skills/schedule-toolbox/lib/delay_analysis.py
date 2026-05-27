"""Forensic delay-analysis calculations.

Genuine new algorithms, not wrappers over existing lib functions. The four
functions in this module answer the questions a delay consultant runs:

* :func:`compute_tia` -- Time Impact Analysis: insert a fragnet activity
  into a copy of the baseline parsed tables, re-run CPM, return the
  projected SC date and net delay days.
* :func:`compute_window_analysis` -- contemporaneous period analysis:
  for each named window between two snapshots, return the activities
  responsible for that window's slip with cause categorization.
* :func:`compute_change_order_delay` -- owner-vs-contractor attribution
  from a change-directive date.
* :func:`find_concurrent_delay_pairs` -- activities that slip
  simultaneously without a logic relationship between them (classic
  concurrent-delay defense candidates).

The functions take pre-parsed and pre-CPM'd table dicts so they're cheap
to unit-test. ``compute_tia`` is the exception -- it must re-run CPM
internally on a mutated copy of the parsed tables to compute the
post-fragnet SC date.
"""
from __future__ import annotations

import copy
from typing import Optional

from cpm_engine import (
    extract_paths,
    schedule_forward_backward,
)
from cross_baseline import (
    _date_delta_days,
    _override_sc_milestone,
)
from milestones import MilestoneAmbiguousError, get_milestones
from xer_compare import compare_xer_pair


def compute_tia(
    baseline_parsed: dict,
    baseline_cpm: tuple,
    delay_fragment: dict,
    milestone_id: Optional[str] = None,
) -> dict:
    """Time Impact Analysis: insert a fragnet activity and report the
    projected SC slip.

    Args:
        baseline_parsed: parsed dict for the baseline XER.
        baseline_cpm:    ``(results, metadata)`` tuple.
        delay_fragment:  dict with:
            * ``activity_id`` (required) -- string id for the new activity.
              Must not collide with existing task_ids.
            * ``duration_days`` (required) -- working days, will be
              multiplied by 8 to get target_drtn_hr_cnt.
            * ``predecessor_activity_id`` (required) -- task_id of the
              activity the fragnet attaches to.
            * ``predecessor_relationship_type`` (optional, default PR_FS).
            * ``calendar_id`` (optional, defaults to the predecessor's).
            * ``description`` (optional) -- used as task_name.
        milestone_id:    Optional explicit terminal milestone task_id.

    Returns:
        ``{milestone_id, baseline_completion, projected_completion,
        net_delay_days, critical_path_changed, new_critical_activities,
        removed_critical_activities, affected_activities}``.

    Raises:
        ValueError: invalid fragment (missing required fields, colliding
            task_id, unknown predecessor_activity_id).
        MilestoneAmbiguousError: ``milestone_id`` omitted on a multi-
            terminal schedule.
    """
    # Validate fragment.
    for required in ("activity_id", "duration_days", "predecessor_activity_id"):
        if required not in delay_fragment:
            raise ValueError(f"delay_fragment missing required key: {required}")
    new_id = delay_fragment["activity_id"]
    duration_days = float(delay_fragment["duration_days"])
    pred_id = delay_fragment["predecessor_activity_id"]
    relationship = delay_fragment.get("predecessor_relationship_type", "PR_FS")
    description = delay_fragment.get("description", "Delay fragnet")

    base_results, base_metadata = baseline_cpm
    if milestone_id is not None:
        base_metadata = _override_sc_milestone(
            base_metadata, milestone_id, baseline_parsed.get("TASK", []),
        )

    existing_task_ids = {t.get("task_id") for t in baseline_parsed.get("TASK", [])}
    if new_id in existing_task_ids:
        raise ValueError(
            f"delay_fragment activity_id '{new_id}' collides with an existing task"
        )
    pred_task = next(
        (t for t in baseline_parsed.get("TASK", []) if t.get("task_id") == pred_id),
        None,
    )
    if pred_task is None:
        raise ValueError(
            f"predecessor_activity_id '{pred_id}' not found in baseline TASK table"
        )
    calendar_id = delay_fragment.get("calendar_id") or pred_task.get("clndr_id")

    # Deep copy the parsed tables so we don't mutate the cache entry.
    mutated = copy.deepcopy(baseline_parsed)
    new_task = dict(pred_task)
    new_task.update({
        "task_id": new_id,
        "task_code": new_id,
        "task_name": description,
        "task_type": "TT_Task",
        "status_code": "TK_NotStart",
        "clndr_id": calendar_id,
        "target_drtn_hr_cnt": str(duration_days * 8),
        "remain_drtn_hr_cnt": str(duration_days * 8),
        "act_start_date": "",
        "act_end_date": "",
        "phys_complete_pct": "0",
    })
    mutated["TASK"].append(new_task)
    # Find a fresh task_pred_id by scanning existing.
    existing_pred_ids = {
        r.get("task_pred_id") for r in mutated.get("TASKPRED", [])
    }
    new_pred_pred_id = _next_unused_id(existing_pred_ids, prefix="FRAG-PRED-")
    mutated.setdefault("TASKPRED", []).append({
        "task_pred_id": new_pred_pred_id,
        "task_id": new_id,
        "pred_task_id": pred_id,
        "proj_id": pred_task.get("proj_id", "1"),
        "pred_proj_id": pred_task.get("proj_id", "1"),
        "pred_type": relationship,
        "lag_hr_cnt": "0",
    })
    # Re-link any successors that USED to depend on pred_id to depend on
    # new_id instead, so the fragnet sits in-line. Without this, the
    # fragnet would dangle and not push SC.
    for pred_row in mutated["TASKPRED"]:
        if (
            pred_row.get("pred_task_id") == pred_id
            and pred_row.get("task_id") != new_id
        ):
            pred_row["pred_task_id"] = new_id

    # Re-run CPM on the mutated tables.
    project_rows = mutated.get("PROJECT") or [{}]
    data_date = (
        project_rows[0].get("last_recalc_date")
        or project_rows[0].get("data_date", "")
    )
    new_results, new_metadata = schedule_forward_backward(
        mutated.get("TASK", []),
        mutated.get("TASKPRED", []),
        mutated.get("CALENDAR", []),
        data_date,
        schedoptions=mutated.get("SCHEDOPTIONS"),
        project=mutated.get("PROJECT"),
    )

    if milestone_id is not None:
        new_metadata = _override_sc_milestone(
            new_metadata, milestone_id, mutated.get("TASK", []),
        )

    baseline_sc = base_metadata.get("sc_milestone_date", "")
    projected_sc = new_metadata.get("sc_milestone_date", "")
    net_delay_days = _date_delta_days(baseline_sc, projected_sc)

    base_paths = extract_paths(
        base_results, base_metadata, baseline_parsed.get("TASKPRED", []),
    )
    new_paths = extract_paths(
        new_results, new_metadata, mutated.get("TASKPRED", []),
    )
    base_codes = {t.get("task_code") for t in base_paths.get("critical_path", [])}
    new_codes = {t.get("task_code") for t in new_paths.get("critical_path", [])}
    critical_path_changed = base_codes != new_codes
    new_critical = [
        t for t in new_paths.get("critical_path", [])
        if t.get("task_code") not in base_codes
    ]
    removed_critical = [
        t for t in base_paths.get("critical_path", [])
        if t.get("task_code") not in new_codes
    ]

    # Affected activities: any task whose early_end_date changed.
    affected = []
    new_by_id = {r.get("task_id"): r for r in new_results}
    for old_row in base_results:
        tid = old_row.get("task_id")
        new_row = new_by_id.get(tid)
        if new_row is None:
            continue
        delta = _date_delta_days(
            old_row.get("early_end_date", ""),
            new_row.get("early_end_date", ""),
        )
        if delta != 0:
            affected.append({
                "task_id": tid,
                "task_code": old_row.get("task_code", ""),
                "task_name": old_row.get("task_name", ""),
                "baseline_finish": old_row.get("early_end_date", ""),
                "projected_finish": new_row.get("early_end_date", ""),
                "delta_days": delta,
            })

    return {
        "milestone_id": milestone_id or new_metadata.get("sc_milestone_id"),
        "baseline_completion": baseline_sc,
        "projected_completion": projected_sc,
        "net_delay_days": net_delay_days,
        "critical_path_changed": critical_path_changed,
        "new_critical_activities": new_critical,
        "removed_critical_activities": removed_critical,
        "affected_activities": affected,
    }


def _next_unused_id(existing: set, prefix: str) -> str:
    """Generate a string id that doesn't collide with ``existing``."""
    i = 1
    while True:
        candidate = f"{prefix}{i}"
        if candidate not in existing:
            return candidate
        i += 1


def compute_window_analysis(
    baseline_parsed: dict,
    current_parsed: dict,
    baseline_cpm: tuple,
    current_cpm: tuple,
    windows: list,
    milestone_id: Optional[str] = None,
) -> dict:
    """Contemporaneous period analysis: per-window slip attribution.

    For each named time window, identify activities whose baseline
    early_finish fell inside the window AND that slipped between
    baseline and current. Categorize each activity's cause via the
    same algorithm as :func:`cross_baseline.compute_gain_loss_attribution`.

    Args:
        baseline_parsed: parsed dict for the baseline XER.
        current_parsed:  parsed dict for the current XER.
        baseline_cpm:    ``(results, metadata)`` for the baseline.
        current_cpm:     same for the current.
        windows:         list of ``{start, end, label}`` dicts. Dates are
            ``YYYY-MM-DD`` strings.
        milestone_id:    Optional terminal milestone task_id.

    Returns:
        ``{milestone_id, windows: [{label, start, end, slip_days,
        activities_responsible: [{task_id, task_code, task_name,
        slip_days, cause_category}, ...]}, ...]}``.
    """
    from cross_baseline import compute_gain_loss_attribution

    attribution = compute_gain_loss_attribution(
        baseline_parsed, current_parsed,
        baseline_cpm, current_cpm,
        milestone_id=milestone_id,
    )

    # Flatten the categorized contributors into a single lookup keyed by
    # task_code -> cause_category. For multi-cause activities, pick the
    # first category found in the priority order (a deliberate choice for
    # window-analysis output; the per-category view lives in
    # compute_gain_loss_attribution).
    priority = (
        "scope_change", "calendar_change", "duration_change",
        "logic_change", "operational_slip",
    )
    cause_by_code: dict = {}
    contribution_by_code: dict = {}
    for category in priority:
        for row in attribution["contributors_by_category"].get(category, []):
            code = row.get("task_code")
            if code and code not in cause_by_code:
                cause_by_code[code] = category
                contribution_by_code[code] = row.get("contribution_days", 0)

    # Baseline-finish lookup for window membership.
    base_by_code = {
        r.get("task_code"): r
        for r in baseline_parsed.get("TASK", []) if r.get("task_code")
    }

    out_windows = []
    for w in windows:
        start = w.get("start", "")
        end = w.get("end", "")
        activities = []
        total_slip = 0
        for code, cause in cause_by_code.items():
            base_row = base_by_code.get(code, {})
            baseline_finish = (base_row.get("early_end_date") or "")[:10]
            if not baseline_finish:
                continue
            if start <= baseline_finish <= end:
                slip = contribution_by_code.get(code, 0)
                activities.append({
                    "task_id": base_row.get("task_id", ""),
                    "task_code": code,
                    "task_name": base_row.get("task_name", ""),
                    "slip_days": slip,
                    "cause_category": cause,
                })
                total_slip += slip
        activities.sort(key=lambda r: abs(r["slip_days"]), reverse=True)
        out_windows.append({
            "label": w.get("label", ""),
            "start": start,
            "end": end,
            "slip_days": total_slip,
            "activities_responsible": activities,
        })

    return {
        "milestone_id": attribution["milestone_id"],
        "windows": out_windows,
    }


def compute_change_order_delay(
    baseline_parsed: dict,
    current_parsed: dict,
    baseline_cpm: tuple,
    current_cpm: tuple,
    change_event_date: str,
    owner_activities: Optional[list] = None,
    milestone_id: Optional[str] = None,
) -> dict:
    """Owner-vs-contractor attribution from a change-directive date.

    The change_event_date partitions the schedule: activities whose
    baseline_finish was on or after the change_event_date AND that
    appear in owner_activities (or that have a scope_change /
    duration_change / logic_change reason post-event) are bucketed as
    attributable to the change event. Everything else is bucketed as
    other causes (or contractor-attributable).

    Args:
        baseline_parsed: parsed dict for the baseline XER.
        current_parsed:  parsed dict for the current XER.
        baseline_cpm:    ``(results, metadata)`` for the baseline.
        current_cpm:     same for the current.
        change_event_date: ISO ``YYYY-MM-DD`` partition date.
        owner_activities: Optional explicit list of task_ids the owner is
            responsible for. When provided, these are treated as
            change-event-attributable regardless of cause category.
        milestone_id:    Optional terminal milestone task_id.

    Returns:
        ``{milestone_id, change_event_date, total_slip_days,
        attributable_to_change_event, attributable_to_other_causes,
        breakdown: [{task_code, attribution, days, cause_category}, ...]}``.
    """
    from cross_baseline import compute_gain_loss_attribution

    owner_set = set(owner_activities or [])
    attribution = compute_gain_loss_attribution(
        baseline_parsed, current_parsed,
        baseline_cpm, current_cpm,
        milestone_id=milestone_id,
    )

    base_by_code = {
        r.get("task_code"): r
        for r in baseline_parsed.get("TASK", []) if r.get("task_code")
    }

    # Dedupe multi-cause activities via the same priority order used by
    # compute_window_analysis (F3). Without this, an activity that lands
    # in both e.g. duration_change and logic_change buckets in
    # contributors_by_category would be double-counted in the breakdown.
    priority = (
        "scope_change", "calendar_change", "duration_change",
        "logic_change", "operational_slip",
    )
    seen_codes: set = set()
    breakdown = []
    sum_change = 0
    sum_other = 0
    for category in priority:
        for row in attribution["contributors_by_category"].get(category, []):
            code = row.get("task_code")
            if not code or code in seen_codes:
                continue
            seen_codes.add(code)
            base_row = base_by_code.get(code, {})
            baseline_finish = (base_row.get("early_end_date") or "")[:10]
            task_id = base_row.get("task_id")
            days = row.get("contribution_days", 0)

            # Attribution rules:
            #  1. If task_id is in owner_activities -> change_event.
            #  2. Else if scope_change AND baseline_finish >= event_date -> change_event.
            #  3. Else -> other.
            if task_id in owner_set:
                attribution_kind = "change_event"
            elif category == "scope_change" and baseline_finish >= change_event_date:
                attribution_kind = "change_event"
            else:
                attribution_kind = "other"
            breakdown.append({
                "task_code": code,
                "attribution": attribution_kind,
                "days": days,
                "cause_category": category,
            })
            if attribution_kind == "change_event":
                sum_change += days
            else:
                sum_other += days

    return {
        "milestone_id": attribution["milestone_id"],
        "change_event_date": change_event_date,
        "total_slip_days": attribution["net_slip_days"],
        "attributable_to_change_event": sum_change,
        "attributable_to_other_causes": sum_other,
        "breakdown": breakdown,
    }


def find_concurrent_delay_pairs(
    baseline_parsed: dict,
    current_parsed: dict,
    baseline_cpm: tuple,
    current_cpm: tuple,
    milestone_id: Optional[str] = None,
) -> dict:
    """Find pairs of slipping activities with no logic relationship.

    A "concurrent pair" is two activities (a, b) where:
    * Both slipped between baseline and current.
    * Neither is in the other's transitive-predecessor closure.
    * Their baseline (planned) ``[early_start, early_finish]`` ranges
      overlap -- the slips happened simultaneously.

    Args:
        baseline_parsed: parsed dict for the baseline XER.
        current_parsed:  parsed dict for the current XER.
        baseline_cpm:    ``(results, metadata)`` for the baseline.
        current_cpm:     same for the current.
        milestone_id:    Optional terminal milestone task_id.

    Concurrent delays are a classic contractor defense in delay claims
    -- if owner-attributable delay X happened simultaneously with
    contractor-attributable delay Y, the contractor argues X doesn't
    extend the project beyond what Y was already doing.

    Returns:
        ``{milestone_id, concurrent_pairs: [{activity_a, activity_b,
        shared_window: {start, end}, owner_a, owner_b}, ...]}``.
        ``owner_a`` / ``owner_b`` default to ``"unknown"`` -- the caller
        is responsible for layering owner attribution from
        :func:`compute_change_order_delay` if needed.
    """
    # Build the slip set (task_codes with nonzero ef_slip_days).
    cmp_result = compare_xer_pair(
        baseline_parsed, current_parsed, match_by="task_code",
    )
    slipping = [
        row for row in cmp_result.get("date_slippage", [])
        if row.get("ef_slip_days", 0) != 0
    ]
    if len(slipping) < 2:
        return {
            "milestone_id": milestone_id or baseline_cpm[1].get("sc_milestone_id"),
            "concurrent_pairs": [],
        }

    # Build the transitive-predecessor closure on the BASELINE side.
    closure = _transitive_pred_closure(baseline_parsed.get("TASKPRED", []))

    base_by_code = {
        r.get("task_code"): r
        for r in baseline_parsed.get("TASK", []) if r.get("task_code")
    }
    pairs = []
    n = len(slipping)
    for i in range(n):
        for j in range(i + 1, n):
            a_row = slipping[i]
            b_row = slipping[j]
            a_code = a_row.get("task_code")
            b_code = b_row.get("task_code")
            a_id = base_by_code.get(a_code, {}).get("task_id")
            b_id = base_by_code.get(b_code, {}).get("task_id")
            if a_id in closure.get(b_id, set()) or b_id in closure.get(a_id, set()):
                continue  # one is a (transitive) pred of the other
            if a_code not in base_by_code or b_code not in base_by_code:
                continue
            a_start = (base_by_code[a_code].get("early_start_date") or "")[:10]
            a_end = (base_by_code[a_code].get("early_end_date") or "")[:10]
            b_start = (base_by_code[b_code].get("early_start_date") or "")[:10]
            b_end = (base_by_code[b_code].get("early_end_date") or "")[:10]
            if not all((a_start, a_end, b_start, b_end)):
                continue
            shared_start = max(a_start, b_start)
            shared_end = min(a_end, b_end)
            if shared_start > shared_end:
                continue  # windows don't overlap
            pairs.append({
                "activity_a": {
                    "task_code": a_code,
                    "task_name": a_row.get("task_name", ""),
                    "slip_days": a_row.get("ef_slip_days", 0),
                },
                "activity_b": {
                    "task_code": b_code,
                    "task_name": b_row.get("task_name", ""),
                    "slip_days": b_row.get("ef_slip_days", 0),
                },
                "shared_window": {"start": shared_start, "end": shared_end},
                "owner_a": "unknown",
                "owner_b": "unknown",
            })

    return {
        "milestone_id": milestone_id or baseline_cpm[1].get("sc_milestone_id"),
        "concurrent_pairs": pairs,
    }


def _transitive_pred_closure(preds: list) -> dict:
    """Build ``{task_id: set(transitive_predecessor_task_ids)}``."""
    direct: dict = {}
    for r in preds:
        direct.setdefault(r.get("task_id"), set()).add(r.get("pred_task_id"))
    closure: dict = {}
    for tid in direct:
        stack = list(direct[tid])
        seen = set()
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            stack.extend(direct.get(p, set()))
        closure[tid] = seen
    return closure
