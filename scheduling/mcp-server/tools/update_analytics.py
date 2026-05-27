"""Tier 1 update-analytics MCP tools.

Thin adapters around ``schedule-toolbox/lib/cross_baseline.py``. Each tool
fetches parsed tables + CPM results from ``CpmCache`` for both baseline
and current XER paths, hands them to the matching lib function, and
returns the result dict.

Naming convention mirrors the F4 ``compare_*`` tools:

* :func:`get_critical_path_changes` -- diff the critical path week over week.
* :func:`get_float_consumption` -- per-activity total_float delta.
* :func:`get_trade_slip_summary` -- per-trade slip aggregation.
* :func:`get_gain_loss_attribution` -- categorize SC slip drivers by cause.

All four lib functions take the same four positional inputs
(``baseline_parsed``, ``current_parsed``, ``baseline_cpm``, ``current_cpm``)
plus an optional ``milestone_id``; ``compute_trade_slip_summary`` adds an
optional ``trade_field``. The wrapper code is therefore nearly identical
across tools -- just the lib function name and the extra kwargs vary.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

# Inject schedule-toolbox/lib so cross_baseline imports as a top-level
# name. Mirrors what cache.py and the other tools/ modules do.
_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cross_baseline import (  # noqa: E402
    compute_critical_path_changes,
    compute_float_consumption,
    compute_gain_loss_attribution,
    compute_trade_slip_summary,
)

from error_help import wrap_tool_errors  # noqa: E402

# Lib script path surfaced in friendly error messages. All four Tier 1
# tools wrap cross_baseline.py, so one constant suffices.
_LIB_SCRIPT = "scheduling/skills/schedule-toolbox/lib/cross_baseline.py"


def get_critical_path_changes_impl(
    baseline_xer_path: str,
    current_xer_path: str,
    milestone_id: Optional[str],
    cache,
) -> dict:
    """Implementation -- called by both the MCP tool wrapper and tests.

    Fetches parsed tables + CPM results for both XERs through the cache
    and forwards to :func:`cross_baseline.compute_critical_path_changes`.
    """
    base_parsed = cache.get_parsed(baseline_xer_path)
    curr_parsed = cache.get_parsed(current_xer_path)
    base_cpm = cache.get_cpm(baseline_xer_path)
    curr_cpm = cache.get_cpm(current_xer_path)
    return compute_critical_path_changes(
        base_parsed, curr_parsed, base_cpm, curr_cpm,
        milestone_id=milestone_id,
    )


def get_float_consumption_impl(
    baseline_xer_path: str,
    current_xer_path: str,
    milestone_id: Optional[str],
    cache,
) -> dict:
    """Implementation -- called by both the MCP tool wrapper and tests.

    Forwards to :func:`cross_baseline.compute_float_consumption`. The lib
    function returns per-activity ``delta_hours`` rows (matched by
    ``task_code``) plus pre-sliced ``biggest_losers`` / ``biggest_gainers``
    convenience lists.
    """
    base_parsed = cache.get_parsed(baseline_xer_path)
    curr_parsed = cache.get_parsed(current_xer_path)
    base_cpm = cache.get_cpm(baseline_xer_path)
    curr_cpm = cache.get_cpm(current_xer_path)
    return compute_float_consumption(
        base_parsed, curr_parsed, base_cpm, curr_cpm,
        milestone_id=milestone_id,
    )


def get_trade_slip_summary_impl(
    baseline_xer_path: str,
    current_xer_path: str,
    milestone_id: Optional[str],
    trade_field: Optional[str],
    cache,
) -> dict:
    """Implementation -- called by both the MCP tool wrapper and tests.

    Forwards to :func:`cross_baseline.compute_trade_slip_summary`.
    ``trade_field`` is optional; when omitted the lib falls back to the
    first 1-2 alphabetic characters of ``task_code`` as the trade key.
    """
    base_parsed = cache.get_parsed(baseline_xer_path)
    curr_parsed = cache.get_parsed(current_xer_path)
    base_cpm = cache.get_cpm(baseline_xer_path)
    curr_cpm = cache.get_cpm(current_xer_path)
    return compute_trade_slip_summary(
        base_parsed, curr_parsed, base_cpm, curr_cpm,
        milestone_id=milestone_id,
        trade_field=trade_field,
    )


def get_gain_loss_attribution_impl(
    baseline_xer_path: str,
    current_xer_path: str,
    milestone_id: Optional[str],
    cache,
) -> dict:
    """Implementation -- called by both the MCP tool wrapper and tests.

    Forwards to :func:`cross_baseline.compute_gain_loss_attribution`.
    """
    base_parsed = cache.get_parsed(baseline_xer_path)
    curr_parsed = cache.get_parsed(current_xer_path)
    base_cpm = cache.get_cpm(baseline_xer_path)
    curr_cpm = cache.get_cpm(current_xer_path)
    return compute_gain_loss_attribution(
        base_parsed, curr_parsed, base_cpm, curr_cpm,
        milestone_id=milestone_id,
    )


def register(mcp, cache):
    """Register this module's tools on the given FastMCP instance."""

    @mcp.tool()
    @wrap_tool_errors(tool_name="get_critical_path_changes", lib_script=_LIB_SCRIPT)
    def get_critical_path_changes(
        baseline_xer_path: str,
        current_xer_path: str,
        milestone_id: Optional[str] = None,
    ) -> dict:
        """Diff the critical path between two XER snapshots.

        Returns activities that moved on or off the critical path, plus
        the full baseline and current critical-path lists. Answers
        "which trades just became critical this week?"

        Args:
            baseline_xer_path: Path to the older / baseline .xer file.
            current_xer_path: Path to the newer / current .xer file.
            milestone_id: Optional terminal milestone task_id. Omit on
                single-terminal schedules to auto-resolve; multi-terminal
                schedules raise ``MilestoneAmbiguousError``. Raises
                ``MilestoneNotFoundError`` when the id is provided but
                doesn't resolve on one side of the pair.

        Returns:
            ``{milestone_id, baseline_cp, current_cp, moved_on,
            moved_off, stable_count}``. ``baseline_cp`` and
            ``current_cp`` are full task-summary lists from
            ``extract_paths``. ``moved_on`` and ``moved_off`` are subsets
            carrying just the changed entries (matched by task_code).
        """
        return get_critical_path_changes_impl(
            baseline_xer_path, current_xer_path, milestone_id, cache,
        )

    @mcp.tool()
    @wrap_tool_errors(tool_name="get_float_consumption", lib_script=_LIB_SCRIPT)
    def get_float_consumption(
        baseline_xer_path: str,
        current_xer_path: str,
        milestone_id: Optional[str] = None,
    ) -> dict:
        """Per-activity total_float delta between two XER snapshots.

        Negative ``delta_hours`` means float was consumed (slip risk
        increased); positive means float was added back (schedule got
        healthier on that activity). Activities are matched by
        ``task_code`` so a task_id renumber between exports doesn't
        break alignment.

        Args:
            baseline_xer_path: Path to the older / baseline .xer file.
            current_xer_path: Path to the newer / current .xer file.
            milestone_id: Optional terminal milestone task_id; surfaces
                on the result for downstream traceability.

        Returns:
            ``{milestone_id, by_activity: [{task_code, task_name,
            baseline_float_hours, current_float_hours, delta_hours,
            delta_days}, ...], biggest_losers, biggest_gainers}``.
            ``by_activity`` is sorted by absolute ``delta_hours``
            descending; ``biggest_losers`` / ``biggest_gainers`` are
            top-N slices for quick triage.
        """
        return get_float_consumption_impl(
            baseline_xer_path, current_xer_path, milestone_id, cache,
        )

    @mcp.tool()
    @wrap_tool_errors(tool_name="get_trade_slip_summary", lib_script=_LIB_SCRIPT)
    def get_trade_slip_summary(
        baseline_xer_path: str,
        current_xer_path: str,
        milestone_id: Optional[str] = None,
        trade_field: Optional[str] = None,
    ) -> dict:
        """Aggregate per-activity date slip into per-trade totals.

        Answers "which trades drove the slip this week?" by grouping the
        ``compare_xer_pair`` ``date_slippage`` rows by trade key. The
        trade key resolves in priority order:

        1. The named ``trade_field`` on each TASK row (when provided).
           Activities lacking that field fall to ``"UNKNOWN"``.
        2. Otherwise: the first 1-2 alphabetic characters of
           ``task_code`` (the implicit Westland convention -- "EL" for
           electrical, "MEC" for mechanical, etc.).

        Args:
            baseline_xer_path: Path to the older / baseline .xer file.
            current_xer_path: Path to the newer / current .xer file.
            milestone_id: Optional terminal milestone task_id; surfaces
                on the result for downstream traceability.
            trade_field: Optional TASK-row field name used as the trade
                key (e.g. ``"phase_code"``). When omitted, the
                task_code-prefix fallback applies.

        Returns:
            ``{milestone_id, by_trade: [{trade, total_slip_days,
            activity_count, activities: [...]}, ...]}``. Sorted by
            absolute ``total_slip_days`` descending.
        """
        return get_trade_slip_summary_impl(
            baseline_xer_path, current_xer_path,
            milestone_id, trade_field, cache,
        )

    @mcp.tool()
    @wrap_tool_errors(tool_name="get_gain_loss_attribution", lib_script=_LIB_SCRIPT)
    def get_gain_loss_attribution(
        baseline_xer_path: str,
        current_xer_path: str,
        milestone_id: Optional[str] = None,
    ) -> dict:
        """Categorize the contributors to the terminal-milestone slip by
        cause.

        Walks the union of baseline-CP and current-CP, classifies each
        contributor into one of five categories (``operational_slip``,
        ``logic_change``, ``duration_change``, ``calendar_change``,
        ``scope_change``), and produces a scheduler-initiated
        ``needs_narrative`` shortlist plus a ``summary_paragraph_seed``
        string for the weekly email's gain/loss explanation.

        Args:
            baseline_xer_path: Path to the older / baseline .xer file.
            current_xer_path: Path to the newer / current .xer file.
            milestone_id: Optional terminal milestone task_id. Omit on
                single-terminal schedules to auto-resolve; multi-
                terminal schedules raise ``MilestoneAmbiguousError``.

        Returns:
            ``{milestone_id, baseline_completion, current_completion,
            net_slip_days, residual_days, summary,
            contributors_by_category: {operational_slip, logic_change,
            duration_change, calendar_change, scope_change},
            weekly_email_documentation: {needs_narrative,
            summary_paragraph_seed}}``. ``summary`` is one of
            ``"no_change"`` / ``"changed"``.
        """
        return get_gain_loss_attribution_impl(
            baseline_xer_path, current_xer_path, milestone_id, cache,
        )
