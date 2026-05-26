"""Milestone enumeration helpers.

Provides a centralized, deterministic way to enumerate non-WBS, non-LOE
milestone tasks from a parsed XER. Replaces the brittle ``find_sc_milestone``
name-matching heuristic that lived in ``score_schedule`` and ``path_analysis``.

When a caller expects exactly one milestone but the schedule contains several
candidates, raise :class:`MilestoneAmbiguousError` with the candidate list so
the MCP-tool layer can surface a structured choice prompt to the user.
"""

from collections import defaultdict

EXCLUDE_TYPES = {"TT_WBS", "TT_LOE"}
MILESTONE_TYPES = {"TT_Mile", "TT_FinMile"}


class MilestoneAmbiguousError(Exception):
    """Raised when a function expecting one milestone gets multiple candidates."""

    def __init__(self, message: str, candidates: list):
        super().__init__(message)
        self.candidates = candidates


def get_milestones(tasks: list, include_complete: bool = False) -> list:
    """Return all non-WBS, non-LOE milestone tasks.

    Each result entry includes: task_id, task_name, task_type, calendar_id,
    early_finish, late_finish, status_code.

    Skips TK_Complete by default; pass include_complete=True to include them.
    """
    result = []
    for t in tasks:
        if t.get("task_type") in EXCLUDE_TYPES:
            continue
        if t.get("task_type") not in MILESTONE_TYPES:
            continue
        if not include_complete and t.get("status_code") == "TK_Complete":
            continue
        result.append({
            "task_id": t.get("task_id"),
            "task_name": t.get("task_name"),
            "task_type": t.get("task_type"),
            "calendar_id": t.get("clndr_id"),
            "early_finish": t.get("early_end_date"),
            "late_finish": t.get("late_end_date"),
            "status_code": t.get("status_code"),
        })
    return result


def resolve_default_milestone(tasks: list, preds: list):
    """Auto-resolve the project's terminal milestone when caller didn't pass one.

    A terminal milestone is a non-WBS / non-LOE / non-complete milestone with
    no successors among the incomplete-task graph. The convention is that a
    construction schedule should have exactly one — typically Substantial
    Completion. If zero are found we return None and the caller falls back to
    full-incomplete-scope mode (same behavior the old ``find_sc_milestone``
    heuristic gave when it couldn't find anything by name). If more than one
    is found we raise :class:`MilestoneAmbiguousError` so the MCP-tool layer
    can surface a structured choice prompt instead of silently picking the
    wrong one.
    """
    milestones = get_milestones(tasks)
    if not milestones:
        return None

    in_scope_ids = {
        t["task_id"]
        for t in tasks
        if t.get("status_code", "") != "TK_Complete"
        and t.get("task_type", "") not in EXCLUDE_TYPES
    }

    succ_count = defaultdict(int)
    for p in preds:
        pred_id = p.get("pred_task_id", "")
        succ_id = p.get("task_id", "")
        if pred_id in in_scope_ids and succ_id in in_scope_ids:
            succ_count[pred_id] += 1

    terminals = [m for m in milestones if succ_count.get(m["task_id"], 0) == 0]

    if len(terminals) == 1:
        return terminals[0]["task_id"]

    if not terminals:
        return None

    raise MilestoneAmbiguousError(
        f"Found {len(terminals)} terminal milestones; pass milestone_id "
        "explicitly to pick one.",
        candidates=terminals,
    )
