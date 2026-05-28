"""Schedule structure tools.

Currently exposes :func:`get_milestones` -- a thin MCP wrapper around the
existing ``get_milestones()`` helper in ``schedule-toolbox/lib/milestones.py``
that enriches each milestone with two derived fields:

* ``predecessor_count`` -- number of TASKPRED rows where this task is the
  successor. Useful for spotting open-ended milestones.
* ``is_terminal`` -- True if every successor (if any) is a WBS / LOE task.
  The convention is that exactly one terminal milestone (typically Substantial
  Completion) exists per construction schedule.

Both fields are computed at the MCP layer; the underlying helper stays
deterministic and side-effect free.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Inject schedule-toolbox/lib so we can import the milestones helper without
# packaging it. Mirrors what cache.py does.
_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from milestones import get_milestones as _get_milestones_helper  # noqa: E402

from error_help import wrap_tool_errors  # noqa: E402

# Lib script path surfaced in friendly error messages. The decorator
# attaches this string to every error raised through a tool wrapper so
# Claude can find the source file when debugging.
_LIB_SCRIPT = "scheduling/skills/schedule-toolbox/lib/milestones.py"


# Task types that should not count as real successors when determining whether
# a milestone is terminal. WBS rollups and LOE activities aren't real logic.
_NON_TERMINAL_SUCC_TYPES = {"TT_WBS", "TT_LOE"}


def get_milestones_impl(xer_path: str, include_complete: bool, cache) -> dict:
    """Implementation -- called by both the test and the MCP tool wrapper.

    Pulls parsed TASK + TASKPRED tables from the cache, asks the milestones
    helper for the base list, then enriches each row with ``predecessor_count``
    and ``is_terminal``.
    """
    parsed = cache.get_parsed(xer_path)
    tasks = parsed.get("TASK", [])
    preds = parsed.get("TASKPRED", [])

    milestones = _get_milestones_helper(tasks, include_complete=include_complete)

    # Build the lookups once -- O(tasks + preds) -- then reuse across milestones.
    task_type_by_id: dict = {}
    for t in tasks:
        task_type_by_id[t.get("task_id")] = t.get("task_type")

    pred_count_by_task: dict = {}
    succs_by_task: dict = {}
    for p in preds:
        succ_id = p.get("task_id")
        pred_id = p.get("pred_task_id")
        pred_count_by_task[succ_id] = pred_count_by_task.get(succ_id, 0) + 1
        succs_by_task.setdefault(pred_id, []).append(succ_id)

    for m in milestones:
        mid = m["task_id"]
        m["predecessor_count"] = pred_count_by_task.get(mid, 0)
        successors = succs_by_task.get(mid, [])
        # all() on an empty list is True, which is the behavior we want:
        # a milestone with zero successors is terminal.
        m["is_terminal"] = all(
            task_type_by_id.get(s) in _NON_TERMINAL_SUCC_TYPES for s in successors
        )

    return {"milestones": milestones}


def invalidate_cache_for_impl(xer_path: str, cache) -> dict:
    """Drop the cache entry for xer_path. Returns {invalidated: bool}.

    Used when an XER has been edited outside the MCP (e.g., directly in P6)
    and the caller wants to force a fresh parse on the next tool call.
    Schedulers normally don't need this — the cache's (path, size, mtime)
    key catches every legitimate overwrite — but it's belt-and-suspenders.
    """
    return {"invalidated": cache.invalidate(str(xer_path))}


def register(mcp, cache):
    """Register this module's tools on the given FastMCP instance."""

    @mcp.tool()
    @wrap_tool_errors(tool_name="get_milestones", lib_script=_LIB_SCRIPT)
    def get_milestones(xer_path: str, include_complete: bool = False) -> dict:
        """List all non-WBS, non-LOE milestones in the XER.

        Args:
            xer_path: Path to the .xer file.
            include_complete: If True, include milestones already marked complete.

        Returns:
            ``{ milestones: [{ task_id, task_name, task_type, calendar_id,
            early_finish, late_finish, status_code, predecessor_count,
            is_terminal }, ...] }``
        """
        return get_milestones_impl(xer_path, include_complete, cache)

    @mcp.tool()
    @wrap_tool_errors(
        tool_name="invalidate_cache_for",
        lib_script="scheduling/mcp-server/cache.py",
    )
    def invalidate_cache_for(xer_path: str) -> dict:
        """Drop the cache entry for the given XER path.

        Use when an XER has been edited outside the MCP (e.g., directly in P6)
        and you want to force a fresh parse on the next tool call.

        Args:
            xer_path: Path to the .xer file whose cache entry should be dropped.

        Returns:
            ``{invalidated: bool}`` -- True if an entry was removed, False if
            the path wasn't in the cache.
        """
        return invalidate_cache_for_impl(xer_path, cache)
