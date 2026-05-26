"""XER-pair comparison MCP tools (F4 batch).

Thin adapters around ``schedule-toolbox/lib/xer_compare.py``. All four tools
wrap a single underlying library function -- ``compare_xer_pair(old, new,
match_by='task_code', milestone_id=None)`` -- and project different subsets
of its unified return dict so callers get a focused payload per question
asked:

* :func:`compare_activity_changes` -> added / removed / duration-changed /
  status-changed tasks (plus the two ``*_data_date`` metadata keys).
* :func:`compare_date_slips` -> per-task early-start / early-finish slip
  rows.
* :func:`compare_milestone_slip` -> terminal-milestone (SC) date delta,
  with both the resolved milestone info dicts for context.
* :func:`compare_missed_dates` -> activities whose planned start/finish
  fell on or before the new data date without progress.

A few reconciliations vs. the F4 plan are worth flagging:

* The plan listed ``activity_changes`` / ``date_slips`` / ``milestone_slip``
  / ``missed_dates`` as four distinct library functions. The library
  actually exposes one combined ``compare_xer_pair`` whose return dict
  contains all four sub-payloads side-by-side; this module fans that out
  into focused single-purpose tools.
* The plan suggested ``compare_milestone_slip`` returns ``{days_change: 14}``;
  the lib's actual key is ``sc_slip_days``. The wrappers expose the lib's
  key name verbatim (no rename) so the contract stays grep-able against the
  underlying function.
* All four tools accept ``match_by`` ('task_code' default, 'task_id' also
  supported) because the underlying lib honors it. Different XER exports
  from the same source schedule can renumber task_ids, so 'task_code' is
  the usual choice for week-over-week comparisons.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Inject schedule-toolbox/lib so the xer_compare module imports as a
# top-level name. Mirrors what cache.py and the other tools/ modules do.
_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from xer_compare import compare_xer_pair  # noqa: E402


def compare_activity_changes_impl(
    baseline_xer_path: str,
    current_xer_path: str,
    match_by: str,
    cache,
) -> dict:
    """Project the four activity-set sub-keys (``added_tasks``,
    ``removed_tasks``, ``changed_durations``, ``status_changes``) out of
    one ``compare_xer_pair`` call.

    The metadata keys ``old_data_date`` / ``new_data_date`` are surfaced so
    callers can sanity-check which XER was treated as baseline vs current
    without re-parsing.
    """
    old = cache.get_parsed(baseline_xer_path)
    new = cache.get_parsed(current_xer_path)
    result = compare_xer_pair(old, new, match_by=match_by)
    return {
        "old_data_date": result["old_data_date"],
        "new_data_date": result["new_data_date"],
        "added_tasks": result["added_tasks"],
        "removed_tasks": result["removed_tasks"],
        "changed_durations": result["changed_durations"],
        "status_changes": result["status_changes"],
    }


def compare_date_slips_impl(
    baseline_xer_path: str,
    current_xer_path: str,
    match_by: str,
    cache,
) -> dict:
    """Project the per-task ``date_slippage`` sub-key out of one
    ``compare_xer_pair`` call.

    Each row carries ``task_code``, ``task_name``, the old/new early
    start+finish dates, and signed ``es_slip_days`` / ``ef_slip_days``.
    Rows where both slip values round to 0 are filtered by the lib; the
    list is sorted by max-abs-slip descending.
    """
    old = cache.get_parsed(baseline_xer_path)
    new = cache.get_parsed(current_xer_path)
    result = compare_xer_pair(old, new, match_by=match_by)
    return {
        "old_data_date": result["old_data_date"],
        "new_data_date": result["new_data_date"],
        "date_slippage": result["date_slippage"],
    }


def compare_milestone_slip_impl(
    baseline_xer_path: str,
    current_xer_path: str,
    milestone_id: Optional[str],
    match_by: str,
    cache,
) -> dict:
    """Project the terminal-milestone slip sub-keys out of one
    ``compare_xer_pair`` call.

    ``milestone_id`` resolves against the *new* (current) schedule -- the
    comparison's anchor -- and the lib then mirrors to the old schedule via
    the same ``match_by`` key, so task_id renumbering between exports
    doesn't break alignment. Omit ``milestone_id`` on single-terminal
    schedules to auto-resolve; multi-terminal schedules raise
    ``MilestoneAmbiguousError`` (propagated from the lib).

    Returns ``sc_date_old`` / ``sc_date_new`` as ``YYYY-MM-DD`` strings (or
    empty when the milestone is missing on one side), ``sc_slip_days`` as a
    signed int, and ``sc_info_old`` / ``sc_info_new`` as the raw milestone
    info dicts the lib produced (handy for surfacing task_name/task_code).
    """
    old = cache.get_parsed(baseline_xer_path)
    new = cache.get_parsed(current_xer_path)
    result = compare_xer_pair(
        old, new, match_by=match_by, milestone_id=milestone_id
    )
    return {
        "sc_date_old": result["sc_date_old"],
        "sc_date_new": result["sc_date_new"],
        "sc_slip_days": result["sc_slip_days"],
        "sc_info_old": result["sc_info_old"],
        "sc_info_new": result["sc_info_new"],
    }


def compare_missed_dates_impl(
    baseline_xer_path: str,
    current_xer_path: str,
    match_by: str,
    cache,
) -> dict:
    """Project the ``missed_starts`` / ``missed_finishes`` sub-keys out of
    one ``compare_xer_pair`` call.

    Missed dates are computed against the *new* data date: a task is
    "missed" if its old-schedule planned start (or finish) is on or before
    the new data date but no actual start (or finish) was recorded.
    """
    old = cache.get_parsed(baseline_xer_path)
    new = cache.get_parsed(current_xer_path)
    result = compare_xer_pair(old, new, match_by=match_by)
    return {
        "old_data_date": result["old_data_date"],
        "new_data_date": result["new_data_date"],
        "missed_starts": result["missed_starts"],
        "missed_finishes": result["missed_finishes"],
    }


def register(mcp, cache):
    """Register this module's tools on the given FastMCP instance."""

    @mcp.tool()
    def compare_activity_changes(
        baseline_xer_path: str,
        current_xer_path: str,
        match_by: str = "task_code",
    ) -> dict:
        """Activity-set deltas between two XER exports: added / removed
        tasks, changed durations, and status transitions.

        Answers "what tasks appeared, disappeared, or changed shape between
        these two schedule snapshots?" Date / milestone / missed-date
        analysis lives on sibling tools.

        Args:
            baseline_xer_path: Path to the older / baseline .xer file.
            current_xer_path: Path to the newer / current .xer file.
            match_by: ``"task_code"`` (default) or ``"task_id"``. Use
                ``"task_code"`` for week-over-week comparisons where P6 may
                have renumbered ``task_id`` between exports.

        Returns:
            ``{ old_data_date, new_data_date, added_tasks: [...],
            removed_tasks: [...], changed_durations: [...],
            status_changes: [...] }``. Each list item carries
            ``task_code``, ``task_name``, and check-specific deltas
            (e.g. ``old_duration_days`` / ``new_duration_days`` /
            ``delta_days`` for ``changed_durations``).
        """
        return compare_activity_changes_impl(
            baseline_xer_path, current_xer_path, match_by, cache
        )

    @mcp.tool()
    def compare_date_slips(
        baseline_xer_path: str,
        current_xer_path: str,
        match_by: str = "task_code",
    ) -> dict:
        """Per-task early-start / early-finish slip between two XER
        exports.

        Sorted by max-abs-slip descending. Rows where both slips round to
        zero days are filtered by the lib (sub-day jitter doesn't count).

        Args:
            baseline_xer_path: Path to the older / baseline .xer file.
            current_xer_path: Path to the newer / current .xer file.
            match_by: ``"task_code"`` (default) or ``"task_id"``.

        Returns:
            ``{ old_data_date, new_data_date, date_slippage: [
            {task_code, task_name, old_early_start, new_early_start,
            es_slip_days, old_early_finish, new_early_finish,
            ef_slip_days}, ...] }``. ``*_slip_days`` are signed ints
            (positive = slipped later, negative = pulled in).
        """
        return compare_date_slips_impl(
            baseline_xer_path, current_xer_path, match_by, cache
        )

    @mcp.tool()
    def compare_milestone_slip(
        baseline_xer_path: str,
        current_xer_path: str,
        milestone_id: Optional[str] = None,
        match_by: str = "task_code",
    ) -> dict:
        """Terminal-milestone (Substantial Completion) date delta between
        two XER exports.

        The milestone is resolved against the *new* (current) schedule and
        mirrored to the baseline by ``match_by`` key, so a task_id renumber
        between exports doesn't break SC-slip alignment.

        Args:
            baseline_xer_path: Path to the older / baseline .xer file.
            current_xer_path: Path to the newer / current .xer file.
            milestone_id: Optional explicit terminal milestone task_id (or
                ``match_by``-key) to pin SC slip to. Omit on single-
                terminal schedules to auto-resolve; multi-terminal
                schedules raise ``MilestoneAmbiguousError``.
            match_by: ``"task_code"`` (default) or ``"task_id"``.

        Returns:
            ``{ sc_date_old, sc_date_new, sc_slip_days, sc_info_old,
            sc_info_new }``. Dates are ``YYYY-MM-DD`` strings (empty when
            missing on one side); ``sc_slip_days`` is a signed int
            (positive = SC slipped later). The two ``sc_info_*`` dicts
            carry the raw milestone metadata (task_name, task_code,
            task_type, ...) from each schedule.
        """
        return compare_milestone_slip_impl(
            baseline_xer_path, current_xer_path,
            milestone_id, match_by, cache,
        )

    @mcp.tool()
    def compare_missed_dates(
        baseline_xer_path: str,
        current_xer_path: str,
        match_by: str = "task_code",
    ) -> dict:
        """Activities whose planned start (or finish) per the baseline
        schedule fell on or before the current schedule's data date but
        haven't actually started (or finished).

        Args:
            baseline_xer_path: Path to the older / baseline .xer file.
            current_xer_path: Path to the newer / current .xer file.
            match_by: ``"task_code"`` (default) or ``"task_id"``.

        Returns:
            ``{ old_data_date, new_data_date, missed_starts: [
            {task_code, task_name, planned_start, ...}, ...],
            missed_finishes: [{task_code, task_name, planned_finish, ...},
            ...] }``. Row shape is determined by the underlying lib's
            ``_find_missed_starts`` / ``_find_missed_finishes`` helpers.
        """
        return compare_missed_dates_impl(
            baseline_xer_path, current_xer_path, match_by, cache
        )
