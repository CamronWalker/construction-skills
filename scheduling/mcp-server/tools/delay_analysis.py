"""Tier 2 forensic-delay-analysis MCP tools.

Thin adapters around ``schedule-toolbox/lib/delay_analysis.py``. Each tool
fetches cached parsed + CPM inputs and forwards to the matching lib
function:

* :func:`compute_tia` -- Time Impact Analysis (single XER + fragnet).
* :func:`compute_window_analysis` -- contemporaneous period analysis.
* :func:`compute_change_order_delay` -- owner-attribution.
* :func:`get_concurrent_delay_pairs` -- concurrent-slip pairs.

The first tool takes a single baseline XER and a delay fragment; the
other three take a baseline + current XER pair. ``find_concurrent_delay_pairs``
on the lib side is exposed here as ``get_concurrent_delay_pairs`` to match
the verb convention used by the other read-only MCP tools.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Inject schedule-toolbox/lib so delay_analysis imports as a top-level
# name. Mirrors what cache.py and the other tools/ modules do.
_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from delay_analysis import (  # noqa: E402
    compute_change_order_delay,
    compute_tia,
    compute_window_analysis,
    find_concurrent_delay_pairs,
)


def compute_tia_impl(
    baseline_xer_path: str,
    delay_fragment: dict,
    milestone_id: Optional[str],
    cache,
) -> dict:
    """Implementation -- called by both the MCP tool wrapper and tests.

    Fetches parsed tables + CPM results for the baseline XER through the
    cache and forwards to :func:`delay_analysis.compute_tia`.
    """
    parsed = cache.get_parsed(baseline_xer_path)
    cpm = cache.get_cpm(baseline_xer_path)
    return compute_tia(parsed, cpm, delay_fragment, milestone_id=milestone_id)


def compute_window_analysis_impl(
    baseline_xer_path: str,
    current_xer_path: str,
    windows: list,
    milestone_id: Optional[str],
    cache,
) -> dict:
    """Implementation -- called by both the MCP tool wrapper and tests.

    Forwards to :func:`delay_analysis.compute_window_analysis`. ``windows``
    is a list of ``{start, end, label}`` dicts; each window's
    ``activities_responsible`` carries a ``cause_category`` from the same
    classifier as :func:`cross_baseline.compute_gain_loss_attribution`.
    """
    base_parsed = cache.get_parsed(baseline_xer_path)
    curr_parsed = cache.get_parsed(current_xer_path)
    base_cpm = cache.get_cpm(baseline_xer_path)
    curr_cpm = cache.get_cpm(current_xer_path)
    return compute_window_analysis(
        base_parsed, curr_parsed, base_cpm, curr_cpm,
        windows=windows,
        milestone_id=milestone_id,
    )


def compute_change_order_delay_impl(
    baseline_xer_path: str,
    current_xer_path: str,
    change_event_date: str,
    owner_activities: Optional[list],
    milestone_id: Optional[str],
    cache,
) -> dict:
    """Implementation -- called by both the MCP tool wrapper and tests.

    Forwards to :func:`delay_analysis.compute_change_order_delay`.
    ``owner_activities`` is an optional explicit list of task_ids
    bucketed into ``change_event`` regardless of cause category.
    """
    base_parsed = cache.get_parsed(baseline_xer_path)
    curr_parsed = cache.get_parsed(current_xer_path)
    base_cpm = cache.get_cpm(baseline_xer_path)
    curr_cpm = cache.get_cpm(current_xer_path)
    return compute_change_order_delay(
        base_parsed, curr_parsed, base_cpm, curr_cpm,
        change_event_date=change_event_date,
        owner_activities=owner_activities,
        milestone_id=milestone_id,
    )


def get_concurrent_delay_pairs_impl(
    baseline_xer_path: str,
    current_xer_path: str,
    milestone_id: Optional[str],
    cache,
) -> dict:
    """Implementation -- called by both the MCP tool wrapper and tests.

    Forwards to :func:`delay_analysis.find_concurrent_delay_pairs`. The
    lib function name (``find_concurrent_delay_pairs``) differs from the
    MCP tool name (``get_concurrent_delay_pairs``); the impl follows the
    MCP tool name.
    """
    base_parsed = cache.get_parsed(baseline_xer_path)
    curr_parsed = cache.get_parsed(current_xer_path)
    base_cpm = cache.get_cpm(baseline_xer_path)
    curr_cpm = cache.get_cpm(current_xer_path)
    return find_concurrent_delay_pairs(
        base_parsed, curr_parsed, base_cpm, curr_cpm,
        milestone_id=milestone_id,
    )


def register(mcp, cache):
    """Register this module's tools on the given FastMCP instance."""

    @mcp.tool()
    def compute_tia(
        baseline_xer_path: str,
        delay_fragment: dict,
        milestone_id: Optional[str] = None,
    ) -> dict:
        """Time Impact Analysis: insert a delay fragnet, re-run CPM, report
        projected SC slip.

        Args:
            baseline_xer_path: Path to the baseline .xer file.
            delay_fragment: dict with required keys ``activity_id``,
                ``duration_days``, ``predecessor_activity_id``; optional
                ``predecessor_relationship_type`` (default ``"PR_FS"``),
                ``calendar_id`` (defaults to the predecessor's), and
                ``description``.
            milestone_id: Optional terminal milestone task_id. Omit on
                single-terminal schedules to auto-resolve.

        Returns:
            ``{milestone_id, baseline_completion, projected_completion,
            net_delay_days, critical_path_changed, new_critical_activities,
            removed_critical_activities, affected_activities}``.
        """
        return compute_tia_impl(
            baseline_xer_path, delay_fragment, milestone_id, cache,
        )

    @mcp.tool()
    def compute_window_analysis(
        baseline_xer_path: str,
        current_xer_path: str,
        windows: list,
        milestone_id: Optional[str] = None,
    ) -> dict:
        """Contemporaneous period analysis: per-window slip attribution.

        For each named time window, identify activities whose baseline
        early_finish fell inside the window AND that slipped between
        baseline and current. Categorize each activity's cause via the
        same algorithm as ``get_gain_loss_attribution``.

        Args:
            baseline_xer_path: Path to the older / baseline .xer file.
            current_xer_path: Path to the newer / current .xer file.
            windows: List of ``{start, end, label}`` dicts. Dates are
                ``YYYY-MM-DD`` strings.
            milestone_id: Optional terminal milestone task_id. Omit on
                single-terminal schedules to auto-resolve.

        Returns:
            ``{milestone_id, windows: [{label, start, end, slip_days,
            activities_responsible: [{task_id, task_code, task_name,
            slip_days, cause_category}, ...]}, ...]}``.
        """
        return compute_window_analysis_impl(
            baseline_xer_path, current_xer_path,
            windows, milestone_id, cache,
        )

    @mcp.tool()
    def compute_change_order_delay(
        baseline_xer_path: str,
        current_xer_path: str,
        change_event_date: str,
        owner_activities: Optional[list] = None,
        milestone_id: Optional[str] = None,
    ) -> dict:
        """Owner-vs-contractor attribution from a change-directive date.

        The change_event_date partitions the schedule: activities whose
        baseline_finish was on or after the change_event_date AND that
        appear in owner_activities (or that have a ``scope_change``
        cause-category post-event) are bucketed as attributable to the
        change event. Everything else is bucketed as other causes.

        Args:
            baseline_xer_path: Path to the older / baseline .xer file.
            current_xer_path: Path to the newer / current .xer file.
            change_event_date: ISO ``YYYY-MM-DD`` partition date.
            owner_activities: Optional explicit list of task_ids the
                owner is responsible for. When provided, these are
                treated as change-event-attributable regardless of
                cause category.
            milestone_id: Optional terminal milestone task_id.

        Returns:
            ``{milestone_id, change_event_date, total_slip_days,
            attributable_to_change_event, attributable_to_other_causes,
            breakdown: [{task_code, attribution, days, cause_category},
            ...]}``. ``attribution`` is one of ``"change_event"`` /
            ``"other"``.
        """
        return compute_change_order_delay_impl(
            baseline_xer_path, current_xer_path,
            change_event_date, owner_activities, milestone_id, cache,
        )

    @mcp.tool()
    def get_concurrent_delay_pairs(
        baseline_xer_path: str,
        current_xer_path: str,
        milestone_id: Optional[str] = None,
    ) -> dict:
        """Find pairs of slipping activities with no logic relationship.

        A "concurrent pair" is two activities (a, b) where:

        * Both slipped between baseline and current.
        * Neither is in the other's transitive-predecessor closure.
        * Their baseline (planned) ``[early_start, early_finish]`` ranges
          overlap -- the slips happened simultaneously.

        Concurrent delays are a classic contractor defense in delay
        claims: if owner-attributable delay X happened simultaneously
        with contractor-attributable delay Y, the contractor argues X
        doesn't extend the project beyond what Y was already doing.

        Args:
            baseline_xer_path: Path to the older / baseline .xer file.
            current_xer_path: Path to the newer / current .xer file.
            milestone_id: Optional terminal milestone task_id.

        Returns:
            ``{milestone_id, concurrent_pairs: [{activity_a, activity_b,
            shared_window: {start, end}, owner_a, owner_b}, ...]}``.
            ``owner_a`` / ``owner_b`` default to ``"unknown"`` -- layer
            owner attribution from ``compute_change_order_delay`` on top
            if needed.
        """
        return get_concurrent_delay_pairs_impl(
            baseline_xer_path, current_xer_path, milestone_id, cache,
        )
