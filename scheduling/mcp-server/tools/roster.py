"""Activity roster + adjacency MCP tools.

Thin adapters around ``schedule-toolbox/lib/activity_roster.py``. They give
Claude a queryable, WBS-pathed activity roster and per-activity / per-branch
adjacency lookup — the reconnaissance surface that previously forced a drop to
raw Python .xer parsing (bug report dd45d9d8).

Dates and total float are always **CPM-computed**: the tools pull the CPM'd
TASK dicts from the cache, so a roster call on a freshly-edited XER
(apply_xer_changes writes a new ``-v#.xer``) already reflects the new logic.
Pure-structure fields (WBS path, pred/succ counts) and
``next_free_activity_code`` don't trigger CPM.

Trades come from the P6 "Responsibility" global activity code
(ACTVTYPE -> ACTVCODE -> TASKACTV); every row surfaces the activity's
Responsibility value and ``trade_filter`` matches against it.
"""
from __future__ import annotations

import difflib
import sys
from pathlib import Path
from typing import Optional

# Inject schedule-toolbox/lib so the roster helpers import as top-level modules.
_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import activity_roster as ar  # noqa: E402

from error_help import wrap_tool_errors  # noqa: E402
from tools._common import data_date_str  # noqa: E402

_LIB_SCRIPT = "scheduling/skills/schedule-toolbox/lib/activity_roster.py"


def _calendars(parsed: dict) -> list:
    """CALENDAR in most exports, CLNDR in some."""
    return parsed.get("CALENDAR") or parsed.get("CLNDR") or []


def _roster_context(xer_path: str, cache, code_type: Optional[str]):
    """Assemble the shared inputs the lib functions need. Returns
    ``(cpm_tasks, preds, projwbs, wbs_index, task_resp, day_hr_index, parsed)``.

    ``cpm_tasks`` are the CPM-computed TASK dicts (dates/float populated).
    """
    parsed = cache.get_parsed(xer_path)
    cpm_tasks, _meta = cache.get_cpm(xer_path)
    projwbs = parsed.get("PROJWBS", [])
    preds = parsed.get("TASKPRED", [])
    wbs_index = ar.build_wbs_path_index(projwbs)
    day_hr_index = ar.build_day_hr_index(_calendars(parsed))
    resp_type_id = ar.resolve_responsibility_type(parsed.get("ACTVTYPE", []), code_type)
    task_resp = ar.build_task_responsibility(
        parsed.get("TASKACTV", []), parsed.get("ACTVCODE", []), resp_type_id)
    return cpm_tasks, preds, projwbs, wbs_index, task_resp, day_hr_index, parsed


def list_activities_impl(xer_path: str, wbs_filter: Optional[str],
                         trade_filter: Optional[str], code_type: Optional[str],
                         include_logic: bool, cache) -> dict:
    tasks, preds, _projwbs, wbs_index, task_resp, day_hr, parsed = \
        _roster_context(xer_path, cache, code_type)
    rows = ar.roster_rows(
        tasks, preds, wbs_index, task_resp, day_hr,
        wbs_filter=wbs_filter, trade_filter=trade_filter, include_logic=include_logic)
    return {
        "data_date": data_date_str(parsed),
        "activity_count": len(rows),
        "activities": rows,
    }


def get_activity_impl(xer_path: str, activity_id: str, cache) -> dict:
    tasks, preds, _projwbs, wbs_index, task_resp, day_hr, _parsed = \
        _roster_context(xer_path, cache, None)
    act = ar.expand_activity(activity_id, tasks, preds, wbs_index, task_resp, day_hr)
    if act is None:
        all_codes = [t.get("task_code", "") for t in tasks if t.get("task_code")]
        close = difflib.get_close_matches(str(activity_id), all_codes, n=5, cutoff=0.3)
        hint = f" Closest codes: {', '.join(close)}." if close else ""
        raise ValueError(
            f"No activity matches {activity_id!r} (by task_code or task_id). "
            f"{len(all_codes)} activities in this XER.{hint}"
        )
    return act


def get_wbs_branch_impl(xer_path: str, wbs_id: str, include_descendants: bool,
                        include_logic: bool, cache) -> dict:
    tasks, preds, projwbs, wbs_index, task_resp, day_hr, _parsed = \
        _roster_context(xer_path, cache, None)
    branch = ar.branch_activities(
        wbs_id, tasks, preds, projwbs, wbs_index, task_resp, day_hr,
        include_descendants=include_descendants, include_logic=include_logic)
    if branch is None:
        names = [w.get("wbs_name", "") for w in projwbs if w.get("wbs_name")]
        close = difflib.get_close_matches(str(wbs_id), names, n=5, cutoff=0.3)
        hint = f" Closest WBS names: {', '.join(close)}." if close else ""
        raise ValueError(
            f"No WBS node matches {wbs_id!r} (by wbs_id, short name, or name). "
            f"{len(projwbs)} WBS nodes in this XER.{hint}"
        )
    return branch


def next_free_activity_code_impl(xer_path: str, prefix: str, step: int, cache) -> dict:
    # No CPM needed — this is a pure task_code scan.
    parsed = cache.get_parsed(xer_path)
    return ar.next_free_code(parsed.get("TASK", []), prefix, step)


def register(mcp, cache):
    """Register this module's tools on the given FastMCP instance."""

    @mcp.tool()
    @wrap_tool_errors(tool_name="list_activities", lib_script=_LIB_SCRIPT)
    def list_activities(xer_path: str, wbs_filter: str = None,
                        trade_filter: str = None, code_type: str = None,
                        include_logic: bool = True) -> dict:
        """List every activity with its full WBS path, CPM-computed dates,
        type, float, Responsibility (trade), and predecessor/successor counts.

        The queryable activity roster for reconnaissance before batch logic
        edits: "show me all activities with full WBS context." Dates and total
        float are CPM-computed (re-run automatically when the XER changes).

        Args:
            xer_path: Path to the .xer file.
            wbs_filter: Case-insensitive substring on the WBS path — keeps
                activities in that branch and its descendants (e.g. "Steel").
            trade_filter: Case-insensitive substring on the activity's
                Responsibility activity-code value (e.g. "concrete").
            code_type: Activity-code type name to use for the trade
                (default "Responsibility", global scope preferred).
            include_logic: Include pred_count / succ_count per row (default True).

        Returns:
            ``{ data_date, activity_count, activities: [{ task_code, task_name,
            task_type, status_code, wbs_id, wbs_path, responsibility,
            responsibility_short, early_start, early_finish, late_start,
            late_finish, total_float_days, total_float_hr_cnt, pred_count,
            succ_count }, ...] }`` (counts omitted when include_logic=False).
        """
        return list_activities_impl(
            xer_path, wbs_filter, trade_filter, code_type, include_logic, cache)

    @mcp.tool()
    @wrap_tool_errors(tool_name="get_activity", lib_script=_LIB_SCRIPT)
    def get_activity(xer_path: str, activity_id: str) -> dict:
        """Fetch one activity with its full WBS path plus expanded
        predecessors and successors — for building relationships and verifying
        each new link is logical.

        Args:
            xer_path: Path to the .xer file.
            activity_id: The Activity ID (task_code, e.g. "CVMC-7380");
                falls back to the internal task_id.

        Returns:
            The roster row for the activity plus ``predecessors`` /
            ``successors`` arrays, each entry ``{ task_code, task_name,
            wbs_path, responsibility, rel_type (FS/SS/FF/SF), lag_days,
            lag_hr_cnt }``. Raises with the closest codes if not found.
        """
        return get_activity_impl(xer_path, activity_id, cache)

    @mcp.tool()
    @wrap_tool_errors(tool_name="get_wbs_branch", lib_script=_LIB_SCRIPT)
    def get_wbs_branch(xer_path: str, wbs_id: str,
                       include_descendants: bool = True,
                       include_logic: bool = True) -> dict:
        """List the activities within a WBS branch — the "adjacent activities
        in this WBS" view for designing and verifying relationships.

        Args:
            xer_path: Path to the .xer file.
            wbs_id: A WBS id, short name, or full WBS name (e.g. "Structure").
            include_descendants: Include activities in child WBS nodes
                (default True).
            include_logic: Expand each activity's predecessors / successors
                inline (default True).

        Returns:
            ``{ wbs_id, wbs_path, activity_count, activities: [row, ...] }``
            where each row has the roster fields and (when include_logic)
            expanded predecessors / successors. Raises with the closest WBS
            names if the branch isn't found.
        """
        return get_wbs_branch_impl(
            xer_path, wbs_id, include_descendants, include_logic, cache)

    @mcp.tool()
    @wrap_tool_errors(tool_name="next_free_activity_code", lib_script=_LIB_SCRIPT)
    def next_free_activity_code(xer_path: str, prefix: str, step: int = 10) -> dict:
        """Find the next collision-free activity code for a prefix, so new
        activities don't clash with existing codes.

        Scans task codes starting with ``prefix`` that end in a number and
        returns the max + ``step``, formatted with the max code's separator and
        zero-pad width.

        Args:
            xer_path: Path to the .xer file.
            prefix: Code prefix to scan (e.g. "CVMC" or "CVMC-").
            step: Increment from the highest existing number (default 10;
                pass 1 for dense sequential codes).

        Returns:
            ``{ prefix, matched_count, max_existing_code, max_existing_number,
            next_code, step }``. ``next_code`` is null when nothing matches.
        """
        return next_free_activity_code_impl(xer_path, prefix, step, cache)
