"""Omnibus / composition MCP tools (F5 batch).

Three high-level tools that fan multiple library calls into one structured
response. Each tool calls the underlying library functions DIRECTLY -- never
through other MCP tools' ``_impl`` wrappers -- so the modules stay flat and
independent:

* :func:`score_schedule` -- unpacks the 7-tuple from
  ``score_schedule.compute_quality_score`` into a flat dict. Pass-through for
  the optional ``milestone_id``.
* :func:`weekly_update_review` -- composes one ``compare_xer_pair`` call
  (reused for both activity_changes and milestone_slip slices), one
  ``expected_updates`` call (reused for both activities_to_start and
  activities_to_finish slices), and a ``compute_quality_score`` on each side
  for a DCMA-style score delta. Plan-2 tools
  (``get_critical_path_changes`` / ``get_gain_loss_attribution``) ship in
  Plan 2; this output stubs those subkeys with ``None`` and sets
  ``pending_plan_2: True`` so callers can branch on it.
* :func:`proposal_schedule_health` -- composes ``compute_quality_score``,
  ``check_missing_logic``, ``check_high_float``, and ``check_anchor_dates``
  into one health snapshot focused on proposal-schedule fitness.

Reconciliations vs. the F5 plan:

* The plan mentions ``score_schedule.generate_quality_report`` as a
  composition partner. That function returns a Markdown text report; the
  structured 7-tuple already carries everything a Claude caller needs, so
  the MCP tool skips the text rendering to keep the payload clean. Add
  back under a ``report`` key only if a future caller has a strong reason
  to consume the formatted text.
* ``weekly_update_review`` catches ``MilestoneAmbiguousError`` from EITHER
  side of the DCMA score and sets ``dcma_delta = None`` (with the rest of
  the output intact). The function does not block the whole weekly review
  on a milestone-resolution problem.
* ``proposal_schedule_health`` accepts the anchors either inline
  (``anchors``) or via a JSON file path (``anchors_path``) -- not both.
  When neither is provided, ``anchor_conflicts`` is ``None`` (no anchors
  to check), not an empty slip list.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Inject schedule-toolbox/lib so the lib modules import as top-level names.
# Mirrors what cache.py and the other tools/ modules do.
_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from tools._common import (  # noqa: E402
    FUTURE_DATE_SENTINEL as _FUTURE_DATE_SENTINEL,
    data_date_dt as _data_date_dt,
    data_date_str as _data_date_str,
)

from cpm_engine import check_anchor_dates  # noqa: E402
from milestones import MilestoneAmbiguousError  # noqa: E402
from quality_checks import check_high_float, check_missing_logic  # noqa: E402
from score_schedule import compute_quality_score  # noqa: E402
from update_review import expected_updates  # noqa: E402
from xer_compare import compare_xer_pair  # noqa: E402


def score_schedule_impl(
    xer_path: str, milestone_id: Optional[str], cache
) -> dict:
    """Run the SmartPM-equivalent quality score and return the 7-tuple as a
    flat dict.

    Calls ``compute_quality_score(tasks, preds, data_date, milestone_id)``
    and unpacks ``(score, grade, scored, info, deductions, scope, details)``
    into a single response. The ``milestone_id`` parameter is passed through
    unchanged; when ``None`` the library auto-resolves the terminal
    milestone and raises ``MilestoneAmbiguousError`` on multi-terminal
    schedules.
    """
    parsed = cache.get_parsed(xer_path)
    tasks = parsed.get("TASK", [])
    preds = parsed.get("TASKPRED", [])
    data_date = _data_date_dt(parsed)
    score, grade, scored, info, deductions, scope, details = compute_quality_score(
        tasks, preds, data_date, milestone_id=milestone_id
    )
    return {
        "score": score,
        "grade": grade,
        "scored": scored,
        "info": info,
        "deductions": deductions,
        "scope": scope,
        "details": details,
    }


def _compute_dcma_delta(
    baseline_parsed: dict,
    current_parsed: dict,
    milestone_id: Optional[str],
) -> Optional[dict]:
    """Run ``compute_quality_score`` against the baseline and current
    schedules and return a {baseline_score, current_score, score_delta,
    baseline_grade, current_grade} dict.

    Returns ``None`` if ``MilestoneAmbiguousError`` is raised on either
    side -- callers asked for a weekly review of a multi-terminal schedule
    without specifying which milestone, and we'd rather drop the DCMA
    delta than fail the whole review.
    """
    try:
        baseline_tuple = compute_quality_score(
            baseline_parsed.get("TASK", []),
            baseline_parsed.get("TASKPRED", []),
            _data_date_dt(baseline_parsed),
            milestone_id=milestone_id,
        )
        current_tuple = compute_quality_score(
            current_parsed.get("TASK", []),
            current_parsed.get("TASKPRED", []),
            _data_date_dt(current_parsed),
            milestone_id=milestone_id,
        )
    except MilestoneAmbiguousError:
        return None
    return {
        "baseline_score": baseline_tuple[0],
        "current_score": current_tuple[0],
        "score_delta": current_tuple[0] - baseline_tuple[0],
        "baseline_grade": baseline_tuple[1],
        "current_grade": current_tuple[1],
    }


def weekly_update_review_impl(
    baseline_xer_path: str,
    current_xer_path: str,
    milestone_id: Optional[str],
    future_date: Optional[str],
    cache,
) -> dict:
    """Bundle every "what changed week over week?" question into one call.

    Calls ``compare_xer_pair`` ONCE on the (baseline, current) pair and
    projects activity_changes + milestone_slip slices from the same dict.
    Calls ``expected_updates`` ONCE on the current schedule and projects
    activities_to_start + activities_to_finish from the same dict. Calls
    ``compute_quality_score`` once on each side to compute a DCMA-style
    score delta; on a multi-terminal schedule where one side raises
    ``MilestoneAmbiguousError``, the delta is dropped (set to ``None``)
    rather than failing the whole review.

    Plan-2 tools (critical-path-changes, gain/loss attribution) ship later;
    those subkeys are stubbed with ``None`` and a ``pending_plan_2: True``
    flag so callers can branch on availability without checking individual
    fields.

    Args:
        baseline_xer_path: Path to the older / baseline .xer file.
        current_xer_path: Path to the newer / current .xer file.
        milestone_id: Optional terminal-milestone task_id; passed through
            to both ``compare_xer_pair`` and the two
            ``compute_quality_score`` calls.
        future_date: Optional ISO ``YYYY-MM-DD`` upper bound for the
            ``activities_to_start`` / ``activities_to_finish`` windows.
            When ``None`` a far-future sentinel (2099-12-31) is used so
            every candidate activity surfaces.
    """
    baseline_parsed = cache.get_parsed(baseline_xer_path)
    current_parsed = cache.get_parsed(current_xer_path)

    # One compare_xer_pair call, two projections.
    compare_result = compare_xer_pair(
        baseline_parsed, current_parsed,
        match_by="task_code", milestone_id=milestone_id,
    )
    activity_changes = {
        "added_tasks": compare_result["added_tasks"],
        "removed_tasks": compare_result["removed_tasks"],
        "changed_durations": compare_result["changed_durations"],
        "status_changes": compare_result["status_changes"],
    }
    milestone_slip = {
        "sc_date_old": compare_result["sc_date_old"],
        "sc_date_new": compare_result["sc_date_new"],
        "sc_slip_days": compare_result["sc_slip_days"],
        "sc_info_old": compare_result["sc_info_old"],
        "sc_info_new": compare_result["sc_info_new"],
    }

    # One expected_updates call on the current schedule, two projections.
    eff_future_date = future_date if future_date is not None else _FUTURE_DATE_SENTINEL
    updates = expected_updates(current_parsed, eff_future_date, resource_filter=None)
    activities_to_start = updates["to_start"]
    activities_to_finish = updates["to_finish"]

    # DCMA-style score delta across both schedules.
    dcma_delta = _compute_dcma_delta(
        baseline_parsed, current_parsed, milestone_id
    )

    return {
        "baseline_xer_path": baseline_xer_path,
        "current_xer_path": current_xer_path,
        "activity_changes": activity_changes,
        "milestone_slip": milestone_slip,
        "activities_to_start": activities_to_start,
        "activities_to_finish": activities_to_finish,
        "dcma_delta": dcma_delta,
        # Plan-2 stubs -- filled in by a later batch.
        "critical_path_changes": None,
        "gain_loss_attribution": None,
        "pending_plan_2": True,
    }


def proposal_schedule_health_impl(
    xer_path: str,
    milestone_id: Optional[str],
    anchors_path: Optional[str],
    anchors: Optional[list],
    cache,
) -> dict:
    """One-shot proposal-schedule fitness snapshot.

    Composes:

    * ``compute_quality_score`` -> ``score_summary`` (same 7-key shape as
      :func:`score_schedule_impl`).
    * ``check_missing_logic`` -> ``missing_logic`` (lib ``_result``
      envelope).
    * ``check_high_float`` -> ``high_float`` (lib ``_result`` envelope).
    * ``check_anchor_dates`` -> ``anchor_conflicts`` (``{slips: [...]}``
      or ``None`` when no anchors are provided).

    Anchor handling: pass anchors either inline as ``anchors=[...]`` or
    via a JSON file with ``anchors_path``. The JSON file shape is
    ``{"anchors": [...]}`` (matches ``proposal-anchors.json``). Passing
    both is an error. Passing neither sets ``anchor_conflicts`` to
    ``None`` -- there's nothing to check against.
    """
    if anchors is not None and anchors_path is not None:
        raise ValueError(
            "Pass exactly one of `anchors` or `anchors_path`, not both."
        )

    parsed = cache.get_parsed(xer_path)
    tasks = parsed.get("TASK", [])
    preds = parsed.get("TASKPRED", [])
    data_date_str = _data_date_str(parsed)
    data_date_dt = _data_date_dt(parsed)

    # 1) Score summary -- same 7-key shape as score_schedule.
    # compute_quality_score compares data_date as a datetime internally
    # (the future_actual info branch), so we pass the parsed datetime.
    score, grade, scored, info, deductions, scope, details = compute_quality_score(
        tasks, preds, data_date_dt, milestone_id=milestone_id
    )
    score_summary = {
        "score": score,
        "grade": grade,
        "scored": scored,
        "info": info,
        "deductions": deductions,
        "scope": scope,
        "details": details,
    }

    # 2) Missing logic. The helper takes the data_date as a string (it
    # only branches on truthiness for date-aware comparisons).
    # all_preds for in-scope/out-of-scope handling; we pass the same
    # list as preds (no pre-scoping).
    missing_logic = check_missing_logic(
        tasks, preds, data_date_str, all_preds=preds
    )

    # 3) High float activities (> 44 working days, hard-coded in the lib).
    high_float = check_high_float(tasks, preds, data_date_str)

    # 4) Anchor conflicts (if anchors provided).
    # Use a fresh local so the input parameter is never reassigned -- the
    # subsequent ``is None`` test then reads unambiguously against the
    # effective value, not against a parameter we mutated mid-function.
    # On the file-load branch, ``doc.get("anchors")`` (no default) returns
    # ``None`` for a missing key, which flows into ``anchor_conflicts: None``
    # rather than silently masquerading as ``{"slips": []}`` -- malformed
    # files now surface to the caller instead of looking like a clean run.
    anchor_conflicts: Optional[dict]
    effective_anchors = anchors
    if anchors_path is not None:
        with open(anchors_path, encoding="utf-8") as f:
            doc = json.load(f)
        effective_anchors = doc.get("anchors") if isinstance(doc, dict) else doc
    if effective_anchors is None:
        anchor_conflicts = None
    else:
        results, _metadata = cache.get_cpm(xer_path)
        slips = check_anchor_dates(results, effective_anchors, tolerance_days=0)
        anchor_conflicts = {"slips": slips}

    return {
        "xer_path": xer_path,
        "score_summary": score_summary,
        "missing_logic": missing_logic,
        "high_float": high_float,
        "anchor_conflicts": anchor_conflicts,
    }


def register(mcp, cache):
    """Register this module's tools on the given FastMCP instance."""

    @mcp.tool()
    def score_schedule(
        xer_path: str, milestone_id: Optional[str] = None
    ) -> dict:
        """SmartPM-equivalent schedule quality score -- 10 scored metrics +
        info metrics + per-deduction details.

        Args:
            xer_path: Path to the .xer file.
            milestone_id: Optional task_id of the terminal milestone to
                anchor scope filtering. Omit on single-terminal schedules
                to auto-resolve; multi-terminal schedules raise
                ``MilestoneAmbiguousError``.

        Returns:
            ``{ score, grade, scored, info, deductions, scope, details }``.
            ``score`` is a float in [0, 100]; ``grade`` is a letter grade
            (``A+`` through ``D-``). ``scored`` is the per-metric dict
            keyed by metric name (``fs``, ``ss``, ``ff``, ``sf``,
            ``avg_float``, ``critical_path``, ``high_float``,
            ``missing_logic``, ``rel_ratio``, ``constraints``).
            ``deductions`` is the deduction-points dict keyed by metric
            label. ``scope`` carries ``incomplete_activities``,
            ``incomplete_milestones``, ``total_relationships``, and
            ``milestone_id``. ``details`` carries human-readable lists for
            each deduction.
        """
        return score_schedule_impl(xer_path, milestone_id, cache)

    @mcp.tool()
    def weekly_update_review(
        baseline_xer_path: str,
        current_xer_path: str,
        milestone_id: Optional[str] = None,
        future_date: Optional[str] = None,
    ) -> dict:
        """Bundled "what changed week over week?" snapshot.

        Composition:

        * ``activity_changes`` -- added / removed tasks, changed durations,
          status transitions (from ``compare_xer_pair``).
        * ``milestone_slip`` -- terminal-milestone slip with old / new SC
          dates and signed ``sc_slip_days`` (from ``compare_xer_pair``).
        * ``activities_to_start`` / ``activities_to_finish`` -- expected
          updates over the next window (from ``expected_updates`` on the
          current schedule).
        * ``dcma_delta`` -- ``compute_quality_score`` score + grade on
          each side with the delta, or ``None`` when a side raises
          ``MilestoneAmbiguousError``.
        * ``critical_path_changes`` / ``gain_loss_attribution`` --
          stubbed ``None`` with ``pending_plan_2: True``; these arrive in
          a later batch.

        Args:
            baseline_xer_path: Path to the older / baseline .xer file.
            current_xer_path: Path to the newer / current .xer file.
            milestone_id: Optional terminal-milestone task_id. Passed
                through to both ``compare_xer_pair`` and the two DCMA
                ``compute_quality_score`` calls.
            future_date: Optional ISO ``YYYY-MM-DD`` upper bound for the
                activities-to-start / activities-to-finish windows.
                Defaults to a far-future sentinel so every candidate
                activity surfaces.

        Returns:
            ``{ baseline_xer_path, current_xer_path, activity_changes,
            milestone_slip, activities_to_start, activities_to_finish,
            dcma_delta, critical_path_changes, gain_loss_attribution,
            pending_plan_2 }``. See module docstring for sub-dict shapes.
        """
        return weekly_update_review_impl(
            baseline_xer_path, current_xer_path, milestone_id, future_date, cache
        )

    @mcp.tool()
    def proposal_schedule_health(
        xer_path: str,
        milestone_id: Optional[str] = None,
        anchors_path: Optional[str] = None,
        anchors: Optional[list] = None,
    ) -> dict:
        """One-shot proposal-schedule fitness snapshot: score + missing
        logic + high float + anchor conflicts.

        Args:
            xer_path: Path to the .xer file.
            milestone_id: Optional terminal-milestone task_id. Omit on
                single-terminal schedules to auto-resolve.
            anchors_path: Optional path to a JSON file with the
                ``{"anchors": [...]}`` top-level shape (matches
                ``proposal-anchors.json``). Mutually exclusive with
                ``anchors``.
            anchors: Optional inline list of anchor dicts. Each entry:
                ``task_code``, ``anchor_date``, ``anchor_kind`` (default
                ``"finish"``), ``kind_label``. Mutually exclusive with
                ``anchors_path``.

        Returns:
            ``{ xer_path, score_summary, missing_logic, high_float,
            anchor_conflicts }``. ``score_summary`` has the same 7-key
            shape as :func:`score_schedule`. ``missing_logic`` /
            ``high_float`` are the library's ``_result`` envelopes.
            ``anchor_conflicts`` is ``{slips: [...]}`` when anchors are
            provided, or ``None`` otherwise.
        """
        return proposal_schedule_health_impl(
            xer_path, milestone_id, anchors_path, anchors, cache
        )
