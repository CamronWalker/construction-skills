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
    # Use rounded calendar-day delta. CPM produces timestamps with
    # times-of-day that drift when working-hour boundaries shift (e.g.
    # baseline ends 15:00 vs projected 10:00 after a fragnet pushes the
    # next activity onto a new workweek start); truncating the
    # fractional-day delta via ``_date_delta_days`` undercounts the
    # actual calendar-day shift by 1. Rounding to the nearest day
    # reflects the physical SC slip the way a delay consultant would
    # count it.
    net_delay_days = _rounded_date_delta_days(baseline_sc, projected_sc)

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
        delta = _rounded_date_delta_days(
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


def _rounded_date_delta_days(base_date_str: str, curr_date_str: str) -> int:
    """Return rounded calendar-day delta between two date strings.

    Unlike :func:`cross_baseline._date_delta_days`, which truncates via
    ``timedelta.days``, this rounds to the nearest whole day. CPM
    timestamps embed the calendar's hour-of-day; when a fragnet pushes a
    successor to a new workweek start (e.g. baseline ends 15:00, projected
    ends 10:00 of the following Wednesday) the truncated delta undercounts
    the physical calendar-day shift by 1. Rounding gives the consultant's
    intuitive answer.

    Accepts ``%Y-%m-%d %H:%M`` or ``%Y-%m-%d``. Returns 0 when either side
    is empty or unparseable.
    """
    from datetime import datetime

    def _parse(s: str):
        if not s:
            return None
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                return datetime.strptime(s.strip(), fmt)
            except ValueError:
                continue
        return None

    a = _parse(base_date_str)
    b = _parse(curr_date_str)
    if a is None or b is None:
        return 0
    seconds = (b - a).total_seconds()
    return int(round(seconds / 86400))


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
    raise NotImplementedError("compute_window_analysis is implemented in Task F3")


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

    Args:
        baseline_parsed: parsed dict for the baseline XER.
        current_parsed:  parsed dict for the current XER.
        baseline_cpm:    ``(results, metadata)`` for the baseline.
        current_cpm:     same for the current.
        change_event_date: ISO ``YYYY-MM-DD`` partition date.
        owner_activities: Optional explicit list of task_ids the owner is
            responsible for.
        milestone_id:    Optional terminal milestone task_id.

    Returns:
        ``{milestone_id, change_event_date, total_slip_days,
        attributable_to_change_event, attributable_to_other_causes,
        breakdown: [{task_code, attribution, days, cause_category}, ...]}``.
    """
    raise NotImplementedError("compute_change_order_delay is implemented in Task F4")


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

    Returns:
        ``{milestone_id, concurrent_pairs: [{activity_a, activity_b,
        shared_window: {start, end}, owner_a, owner_b}, ...]}``.
    """
    raise NotImplementedError("find_concurrent_delay_pairs is implemented in Task F5")
