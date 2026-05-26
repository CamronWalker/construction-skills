"""Quality and scoring MCP tools (F2 batch).

Thin adapters around ``schedule-toolbox/lib/quality_checks.py``. Each tool
function pulls the parsed TASK and TASKPRED tables from the ``CpmCache`` and
forwards them to the underlying ``check_*`` helper unchanged, then returns the
dict the helper produced.

A handful of reconciliations vs. the F2 plan are worth flagging up front:

* ``get_quality_check`` is implemented as a router that dispatches by
  ``check_name`` to the ``ALL_CHECKS`` registry in ``quality_checks``. There is
  no single ``run_check(name, ...)`` entry point in the library.
* ``get_relationship_type_breakdown`` composes the four per-type helpers
  (``check_finish_to_start``, ``check_start_to_start``, ``check_finish_to_finish``,
  ``check_start_to_finish``) into one ``{FS, SS, FF, SF}`` summary; there is no
  pre-built breakdown in the library.
* ``get_high_float_activities`` and ``get_high_duration_activities`` are fixed
  to "> 44 working days (= 352 hrs)". The underlying ``check_high_float`` and
  ``check_high_duration`` helpers hard-code that cap and don't accept a
  parameter; the MCP wrappers therefore don't expose a threshold knob -- doing
  so previously was misleading because no value < 44 could filter (the base
  list is already > 44) and values > 44 just clamped back to 44.
* ``get_circular_relationships`` reads
  ``metadata['circular_dependencies']`` from the cached CPM result. Cycles are
  detected during the CPM topological sort, not by a dedicated quality check.
* ``get_invalid_dates`` wraps ``check_future_actual`` -- the closest match in
  the library is the actual-date-after-data-date check.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Inject schedule-toolbox/lib so the quality_checks module imports as a
# top-level name. Mirrors what cache.py and tools/cpm_path.py do.
_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from tools._common import data_date_str as _data_date  # noqa: E402

from quality_checks import (  # noqa: E402
    ALL_CHECKS,
    check_constraints,
    check_duplicate_rels,
    check_finish_to_finish,
    check_finish_to_start,
    check_future_actual,
    check_high_duration,
    check_high_float,
    check_missing_logic,
    check_negative_float,
    check_start_to_finish,
    check_start_to_start,
)


def get_quality_check_impl(xer_path: str, check_name: str, cache) -> dict:
    """Dispatch to one of the 28+ ``check_<name>`` functions in
    ``quality_checks.ALL_CHECKS`` by string name.

    ``missing_logic`` is special-cased to pass the full (unfiltered) TASKPRED
    list as ``all_preds`` -- the library helper needs the unfiltered relations
    to avoid false positives when a predecessor is outside the in-scope task
    set. For the MCP we don't pre-scope, so ``preds == all_preds``, but we
    pass both through to keep the contract explicit.

    Raises:
        ValueError: ``check_name`` is not a known check.
    """
    if check_name not in ALL_CHECKS:
        raise ValueError(
            f"Unknown quality check '{check_name}'. "
            f"Available: {sorted(ALL_CHECKS.keys())}"
        )
    parsed = cache.get_parsed(xer_path)
    tasks = parsed.get("TASK", [])
    preds = parsed.get("TASKPRED", [])
    data_date = _data_date(parsed)
    if check_name == "missing_logic":
        return check_missing_logic(tasks, preds, data_date, all_preds=preds)
    return ALL_CHECKS[check_name](tasks, preds, data_date)


def get_relationship_type_breakdown_impl(xer_path: str, cache) -> dict:
    """Run the four per-type relationship checks and combine into one
    ``{FS, SS, FF, SF}`` summary. Each sub-key holds the full result dict the
    underlying ``check_*`` function returned, so callers can drill into counts,
    percentages, pass/fail status, and the offending relationships list.
    """
    parsed = cache.get_parsed(xer_path)
    tasks = parsed.get("TASK", [])
    preds = parsed.get("TASKPRED", [])
    data_date = _data_date(parsed)
    return {
        "FS": check_finish_to_start(tasks, preds, data_date),
        "SS": check_start_to_start(tasks, preds, data_date),
        "FF": check_finish_to_finish(tasks, preds, data_date),
        "SF": check_start_to_finish(tasks, preds, data_date),
    }


def get_missing_logic_impl(xer_path: str, cache) -> dict:
    """Activities missing either a predecessor or a successor. Passes the
    full TASKPRED list as ``all_preds`` so the library can correctly handle
    in-scope/out-of-scope predecessor edge cases."""
    parsed = cache.get_parsed(xer_path)
    tasks = parsed.get("TASK", [])
    preds = parsed.get("TASKPRED", [])
    data_date = _data_date(parsed)
    return check_missing_logic(tasks, preds, data_date, all_preds=preds)


def get_high_float_activities_impl(xer_path: str, cache) -> dict:
    """Activities with total float > 44 working days (= 352 hrs).

    The threshold is fixed by the underlying ``check_high_float`` helper and
    is not user-configurable -- the helper's flagged list only contains tasks
    whose ``total_float_hr_cnt`` is strictly greater than 352 hours.
    """
    parsed = cache.get_parsed(xer_path)
    tasks = parsed.get("TASK", [])
    preds = parsed.get("TASKPRED", [])
    data_date = _data_date(parsed)
    return check_high_float(tasks, preds, data_date)


def get_negative_float_activities_impl(xer_path: str, cache) -> dict:
    """Activities with total float < -1 working day (the library uses < -8hrs
    to filter out floating-point noise around zero)."""
    parsed = cache.get_parsed(xer_path)
    tasks = parsed.get("TASK", [])
    preds = parsed.get("TASKPRED", [])
    data_date = _data_date(parsed)
    return check_negative_float(tasks, preds, data_date)


def get_constraint_violations_impl(xer_path: str, cache) -> dict:
    """Hard-constraint violations (CS_MSO / CS_MFO / CS_MEO etc.). Wraps
    ``check_constraints``, the umbrella scored check; soft constraints are
    excluded by design."""
    parsed = cache.get_parsed(xer_path)
    tasks = parsed.get("TASK", [])
    preds = parsed.get("TASKPRED", [])
    data_date = _data_date(parsed)
    return check_constraints(tasks, preds, data_date)


def get_high_duration_activities_impl(xer_path: str, cache) -> dict:
    """Activities with planned duration > 44 working days (= 352 hrs).

    Same fixed-threshold story as :func:`get_high_float_activities_impl`: the
    underlying ``check_high_duration`` helper hard-codes the 352-hour cap and
    only emits tasks above it, so the wrapper doesn't expose a knob.
    """
    parsed = cache.get_parsed(xer_path)
    tasks = parsed.get("TASK", [])
    preds = parsed.get("TASKPRED", [])
    data_date = _data_date(parsed)
    return check_high_duration(tasks, preds, data_date)


def get_duplicate_relationships_impl(xer_path: str, cache) -> dict:
    """Activity pairs connected by more than one TASKPRED row (e.g. both FS
    and SS between the same two tasks)."""
    parsed = cache.get_parsed(xer_path)
    tasks = parsed.get("TASK", [])
    preds = parsed.get("TASKPRED", [])
    data_date = _data_date(parsed)
    return check_duplicate_rels(tasks, preds, data_date)


def get_circular_relationships_impl(xer_path: str, cache) -> dict:
    """Logic cycles detected during CPM forward-pass topological sort.

    The library doesn't expose a dedicated check_circular() helper -- cycle
    detection happens inside ``cpm_engine._topological_sort`` and the
    offending edges are surfaced via ``metadata['circular_dependencies']``.
    This function reads that field from the cached CPM metadata.

    Returns ``{cycles: [...]}`` (empty list when the schedule is acyclic).
    """
    _results, metadata = cache.get_cpm(xer_path)
    return {"cycles": metadata.get("circular_dependencies", [])}


def get_invalid_dates_impl(xer_path: str, cache) -> dict:
    """Activities with actual start or actual finish dates after the project
    data date. Wraps ``check_future_actual``."""
    parsed = cache.get_parsed(xer_path)
    tasks = parsed.get("TASK", [])
    preds = parsed.get("TASKPRED", [])
    data_date = _data_date(parsed)
    return check_future_actual(tasks, preds, data_date)


def register(mcp, cache):
    """Register this module's tools on the given FastMCP instance."""

    @mcp.tool()
    def get_quality_check(xer_path: str, check_name: str) -> dict:
        """Run a single named quality check from the SmartPM-equivalent suite.

        This is a generic router; prefer the individual ``get_<name>`` tools
        (``get_high_float_activities``, ``get_missing_logic``, ...) when a
        stable, documented response shape matters -- this router returns the
        raw check output, whose shape varies by ``check_name``.

        Args:
            xer_path: Path to the .xer file.
            check_name: One of the 28+ check identifiers defined in
                ``quality_checks.ALL_CHECKS`` -- e.g. ``finish_to_start``,
                ``high_float``, ``missing_logic``, ``sc_coverage``.

        Returns:
            The result dict the underlying ``check_<name>`` function produced:
            ``{check, label, scored, deduction_pts, count, total, pct,
            threshold, status, note, ...check-specific keys}``.

        Raises:
            ValueError: ``check_name`` is not a known check.
        """
        return get_quality_check_impl(xer_path, check_name, cache)

    @mcp.tool()
    def get_relationship_type_breakdown(xer_path: str) -> dict:
        """Per-type relationship summary (FS / SS / FF / SF).

        Args:
            xer_path: Path to the .xer file.

        Returns:
            ``{ FS: {...}, SS: {...}, FF: {...}, SF: {...} }`` where each
            value is the full result dict from the matching ``check_*`` helper
            (count, percentage, status, list of offending relationships).
        """
        return get_relationship_type_breakdown_impl(xer_path, cache)

    @mcp.tool()
    def get_missing_logic(xer_path: str) -> dict:
        """Activities missing a predecessor or successor.

        Args:
            xer_path: Path to the .xer file.

        Returns:
            ``{ check, label, count, total, pct, status, no_predecessor: [...],
            no_successor: [...], ... }``.
        """
        return get_missing_logic_impl(xer_path, cache)

    @mcp.tool()
    def get_high_float_activities(xer_path: str) -> dict:
        """Activities with total float > 44 working days (the library's hard
        cap; the threshold isn't user-configurable here because the underlying
        check doesn't parameterize it).

        Args:
            xer_path: Path to the .xer file.

        Returns:
            ``{ check, label, count, total, pct, status, tasks: [
            {task_id, task_code, task_name, float_days}, ...] }``.
        """
        return get_high_float_activities_impl(xer_path, cache)

    @mcp.tool()
    def get_negative_float_activities(xer_path: str) -> dict:
        """Activities with negative total float (schedule cannot meet deadline
        without acceleration).

        Args:
            xer_path: Path to the .xer file.

        Returns:
            ``{ check, label, count, total, pct, status, tasks: [
            {task_id, task_code, task_name, float_days}, ...] }``.
        """
        return get_negative_float_activities_impl(xer_path, cache)

    @mcp.tool()
    def get_constraint_violations(xer_path: str) -> dict:
        """Activities with hard date constraints (CS_MSO / CS_MFO / CS_MEO).
        Soft constraints (CS_SNET / CS_FNLT etc.) are excluded by design --
        they're aspirational, not violations.

        Args:
            xer_path: Path to the .xer file.

        Returns:
            The standard ``_result`` envelope from ``check_constraints``:
            ``{check: "constraints", label, scored: True, deduction_pts,
            count, total, pct, threshold, status, note, tasks: [...]}``.
            Each entry in ``tasks`` is whatever the library's ``_task_rec``
            emits (``task_id``, ``task_code``, ``task_name``) plus the
            constraint-specific keys ``constraint_type`` and
            ``constraint_date``. Field set is determined by the library, not
            this wrapper.
        """
        return get_constraint_violations_impl(xer_path, cache)

    @mcp.tool()
    def get_high_duration_activities(xer_path: str) -> dict:
        """Activities with planned duration > 44 working days (the library's
        hard cap; the threshold isn't user-configurable here because the
        underlying check doesn't parameterize it).

        Args:
            xer_path: Path to the .xer file.

        Returns:
            ``{ check, label, count, total, pct, status, tasks: [
            {task_id, task_code, task_name, duration_days}, ...] }``.
        """
        return get_high_duration_activities_impl(xer_path, cache)

    @mcp.tool()
    def get_duplicate_relationships(xer_path: str) -> dict:
        """Activity pairs connected by more than one TASKPRED row (redundant
        logic that obscures the critical path).

        Args:
            xer_path: Path to the .xer file.

        Returns:
            ``{ check, label, count, total, pct, status, relationships: [
            {pred_id, pred_code, pred_name, succ_id, succ_code, succ_name,
            relationship_types: [...]}, ...] }``.
        """
        return get_duplicate_relationships_impl(xer_path, cache)

    @mcp.tool()
    def get_circular_relationships(xer_path: str) -> dict:
        """Logic cycles detected during the CPM topological sort.

        Args:
            xer_path: Path to the .xer file.

        Returns:
            ``{ cycles: [...] }``. Each entry describes one cycle (the format
            is whatever ``cpm_engine`` writes into ``metadata
            ['circular_dependencies']``; empty list on acyclic schedules).
        """
        return get_circular_relationships_impl(xer_path, cache)

    @mcp.tool()
    def get_invalid_dates(xer_path: str) -> dict:
        """Activities whose actual start or finish dates are after the
        project data date (i.e. fake actuals).

        Args:
            xer_path: Path to the .xer file.

        Returns:
            ``{ check, label, count, total, pct, status, tasks: [
            {task_id, task_code, task_name, act_start, act_finish}, ...] }``.
        """
        return get_invalid_dates_impl(xer_path, cache)
