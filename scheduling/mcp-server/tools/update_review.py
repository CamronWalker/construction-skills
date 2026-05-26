"""Schedule-update-review MCP tools (F3 batch).

Thin adapters around ``schedule-toolbox/lib/update_review.py``. Three of the
four tools project a single sub-key out of one shared
``expected_updates(tables, future_date, resource_filter=None)`` call -- the
underlying library function returns a combined ``to_start`` / ``to_finish`` /
``in_progress`` payload, and the MCP layer fans that out into focused
single-purpose tools so callers don't have to filter the bundled result
themselves.

A handful of reconciliations vs. the F3 plan are worth flagging:

* The plan lists ``activities_to_start`` / ``activities_to_finish`` /
  ``in_progress_activities`` / ``ride_data_date_check`` as four distinct
  library functions. The library actually exposes one combined
  ``expected_updates`` (covering the first three) plus ``riding_data_date``
  (matching the fourth). The dispatch shape below reflects the library, not
  the plan.
* ``get_in_progress_activities`` does NOT expose ``future_date`` to its
  callers. ``expected_updates`` requires ``future_date`` positionally, but
  the ``in_progress`` list isn't filtered by it -- it's simply every
  ``TK_Active`` task. The wrapper passes a far-future sentinel internally so
  the tool signature stays focused on the question being asked.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Inject schedule-toolbox/lib so the update_review module imports as a
# top-level name. Mirrors what cache.py and the other tools/ modules do.
_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from update_review import (  # noqa: E402
    expected_updates,
    riding_data_date,
)

# Sentinel future_date used internally by get_in_progress_activities. The
# library's in_progress filter is "any TK_Active task" -- the future_date
# parameter only affects to_start / to_finish thresholds, so any date past
# every realistic schedule horizon works. 2099-12-31 is deliberately
# far-future and ISO-formatted to satisfy the library's _parse_dt regardless
# of locale.
_IN_PROGRESS_SENTINEL_DATE = "2099-12-31"


def get_activities_to_start_impl(
    xer_path: str,
    future_date: str,
    resource_filter: Optional[str],
    cache,
) -> dict:
    """Not-started activities scheduled to start between the data date and
    ``future_date``. Projects the ``to_start`` slice out of
    ``expected_updates``; ``to_finish`` and ``in_progress`` are dropped.
    """
    parsed = cache.get_parsed(xer_path)
    result = expected_updates(parsed, future_date, resource_filter=resource_filter)
    return {
        "data_date": result["data_date"],
        "future_date": result["future_date"],
        "resource_filter": result["resource_filter"],
        "to_start": result["to_start"],
    }


def get_activities_to_finish_impl(
    xer_path: str,
    future_date: str,
    resource_filter: Optional[str],
    cache,
) -> dict:
    """In-progress activities scheduled to finish between the data date and
    ``future_date``. Projects the ``to_finish`` slice out of
    ``expected_updates``.
    """
    parsed = cache.get_parsed(xer_path)
    result = expected_updates(parsed, future_date, resource_filter=resource_filter)
    return {
        "data_date": result["data_date"],
        "future_date": result["future_date"],
        "resource_filter": result["resource_filter"],
        "to_finish": result["to_finish"],
    }


def get_in_progress_activities_impl(
    xer_path: str,
    resource_filter: Optional[str],
    cache,
) -> dict:
    """Currently active (``TK_Active``) activities, regardless of scheduled
    finish.

    ``expected_updates`` requires a positional ``future_date`` arg, but the
    in_progress list isn't gated on it. The wrapper passes the
    ``_IN_PROGRESS_SENTINEL_DATE`` so the library is happy without burdening
    the tool's signature with an irrelevant date parameter.
    """
    parsed = cache.get_parsed(xer_path)
    result = expected_updates(
        parsed,
        _IN_PROGRESS_SENTINEL_DATE,
        resource_filter=resource_filter,
    )
    # Deliberately omit ``future_date`` from the output -- it's an internal
    # implementation detail of the lib call, not a tool input.
    return {
        "data_date": result["data_date"],
        "resource_filter": result["resource_filter"],
        "in_progress": result["in_progress"],
    }


def get_ride_data_date_violations_impl(xer_path: str, cache) -> dict:
    """Not-started activities whose predecessors are all complete -- only
    the data date is holding them back. Thin pass-through to
    :func:`riding_data_date`."""
    parsed = cache.get_parsed(xer_path)
    return riding_data_date(parsed)


def register(mcp, cache):
    """Register this module's tools on the given FastMCP instance."""

    @mcp.tool()
    def get_activities_to_start(
        xer_path: str,
        future_date: str,
        resource_filter: Optional[str] = None,
    ) -> dict:
        """Not-started activities scheduled to start between the data date
        and ``future_date``. Answers "what does the field need to actually
        get going on by <date>?"

        Args:
            xer_path: Path to the .xer file.
            future_date: ISO ``YYYY-MM-DD`` upper bound for the early-start
                window.
            resource_filter: Optional case-insensitive substring against
                resource short names (e.g. ``"ELEC"``) to scope the result
                to one trade.

        Returns:
            ``{ data_date, future_date, resource_filter, to_start: [
            {task_id, task_code, task_name, resources, early_start,
            early_finish, duration_days}, ...] }``. Sorted ascending by
            ``early_start``.
        """
        return get_activities_to_start_impl(
            xer_path, future_date, resource_filter, cache
        )

    @mcp.tool()
    def get_activities_to_finish(
        xer_path: str,
        future_date: str,
        resource_filter: Optional[str] = None,
    ) -> dict:
        """In-progress activities scheduled to finish between the data date
        and ``future_date``. Answers "what should the field be wrapping up by
        <date>?"

        Args:
            xer_path: Path to the .xer file.
            future_date: ISO ``YYYY-MM-DD`` upper bound for the early-finish
                window.
            resource_filter: Optional case-insensitive substring against
                resource short names (e.g. ``"MECH"``).

        Returns:
            ``{ data_date, future_date, resource_filter, to_finish: [
            {task_id, task_code, task_name, resources, pct_complete,
            early_finish, remaining_days}, ...] }``. Sorted ascending by
            ``early_finish``.
        """
        return get_activities_to_finish_impl(
            xer_path, future_date, resource_filter, cache
        )

    @mcp.tool()
    def get_in_progress_activities(
        xer_path: str,
        resource_filter: Optional[str] = None,
    ) -> dict:
        """All currently active (``TK_Active``) activities, regardless of
        scheduled finish.

        Unlike :func:`get_activities_to_finish`, this isn't windowed by
        ``future_date`` -- it returns every task currently being worked. The
        underlying library function takes a ``future_date`` argument but the
        in_progress list isn't filtered by it; the wrapper hides that detail.

        Args:
            xer_path: Path to the .xer file.
            resource_filter: Optional case-insensitive substring against
                resource short names.

        Returns:
            ``{ data_date, resource_filter, in_progress: [
            {task_id, task_code, task_name, resources, pct_complete,
            early_finish, remaining_days}, ...] }``. Sorted ascending by
            ``early_finish``.
        """
        return get_in_progress_activities_impl(
            xer_path, resource_filter, cache
        )

    @mcp.tool()
    def get_ride_data_date_violations(xer_path: str) -> dict:
        """Not-started activities whose predecessors are all complete --
        these are "riding the data date" (only the data date is holding
        them back; the schedule's logic says they could start now).

        Args:
            xer_path: Path to the .xer file.

        Returns:
            ``{ data_date, count, total_incomplete, pct, tasks: [
            {task_id, task_code, task_name, early_start}, ...], note }``.
            ``pct`` is the share of incomplete activities that are riding
            the data date.
        """
        return get_ride_data_date_violations_impl(xer_path, cache)
