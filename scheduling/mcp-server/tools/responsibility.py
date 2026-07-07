"""Responsibility (trade) assignment MCP tools.

``suggest_responsibility`` is the name-based first-pass accelerator: it runs
every activity name through the keyword matcher
(``schedule-toolbox/lib/responsibility_match.py``) against Westland's remembered
"Responsibility - Global" code list
(``references/responsibility-codes.json``) and returns two buckets:

* ``assigned`` — confident matches, safe to pre-fill.
* ``unsure``   — ambiguous / no-hit names, each with candidate codes for review.

This is *decision support*, not the final word: keyword matching alone tops out
~85% on real schedules (the gold labels themselves disagree across projects),
so the intended flow is Claude reviewing the buckets — accepting the confident
ones, picking from candidates (or the full ``all_codes`` list) for the rest, and
asking the human on genuine ambiguity — then writing the result with the
``set_responsibility`` change type of ``apply_xer_changes``.

No CPM: this is a pure name + existing-assignment read.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_LIB = Path(__file__).parent.parent.parent / "skills" / "schedule-toolbox" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

import activity_roster as ar  # noqa: E402
import responsibility_match as rm  # noqa: E402

from error_help import wrap_tool_errors  # noqa: E402

_LIB_SCRIPT = "scheduling/skills/schedule-toolbox/lib/responsibility_match.py"

# WBS summary / level-of-effort rows aren't real activities to code.
_NON_ACTIVITY_TYPES = {"TT_WBS", "TT_LOE"}


def _already_assigned_ids(parsed: dict, resp_type_id: Optional[str]) -> set:
    """Task ids that already carry a Responsibility assignment for the type."""
    if resp_type_id is None:
        return set()
    return {
        str(a.get("task_id"))
        for a in parsed.get("TASKACTV", [])
        if str(a.get("actv_code_type_id")) == str(resp_type_id)
    }


def suggest_responsibility_impl(xer_path: str, only_unassigned: bool,
                                code_type: Optional[str], cache) -> dict:
    parsed = cache.get_parsed(xer_path)
    codes = rm.load_codes()
    resp_type_id = ar.resolve_responsibility_type(parsed.get("ACTVTYPE", []), code_type)
    already = _already_assigned_ids(parsed, resp_type_id) if only_unassigned else set()

    tasks = [
        t for t in parsed.get("TASK", [])
        if t.get("task_type") not in _NON_ACTIVITY_TYPES
    ]
    out = rm.suggest_assignments(tasks, codes, already_assigned=already)
    return {
        "code_type_name": rm.load_reference_name(),
        "responsibility_type_present": resp_type_id is not None,
        "total_activities": len(tasks),
        "already_assigned": len(already),
        "assigned_count": len(out["assigned"]),
        "unsure_count": len(out["unsure"]),
        "assigned": out["assigned"],
        "unsure": out["unsure"],
        "all_codes": [{"code": c["code"], "name": c["name"]} for c in codes],
    }


def register(mcp, cache):
    """Register this module's tools on the given FastMCP instance."""

    @mcp.tool()
    @wrap_tool_errors(tool_name="suggest_responsibility", lib_script=_LIB_SCRIPT)
    def suggest_responsibility(xer_path: str, only_unassigned: bool = True,
                               code_type: str = None) -> dict:
        """First-pass Responsibility (trade) code suggestions from activity names.

        Runs every activity name against Westland's remembered "Responsibility -
        Global" code list and splits the result into confident ``assigned``
        suggestions and an ``unsure`` bucket (each with candidate codes). This is
        an accelerator — review the buckets, then write with
        ``apply_xer_changes`` ``set_responsibility`` changes. Keyword matching
        alone is ~85% on real schedules, so treat ``unsure`` (and low-signal
        ``assigned``) as needing your judgment; ``all_codes`` carries the full
        list to pick from.

        Args:
            xer_path: Path to the .xer file.
            only_unassigned: Skip activities that already carry a Responsibility
                code (default True) — the usual "fill in the blanks" pass. Set
                False to re-suggest for every activity.
            code_type: Activity-code type name to treat as Responsibility
                (default: auto — the "Responsibility - Global" global type).

        Returns:
            ``{ code_type_name, responsibility_type_present, total_activities,
            already_assigned, assigned_count, unsure_count, assigned:[{task_id,
            task_code, task_name, suggested_code, suggested_name, matched,
            score}], unsure:[{task_id, task_code, task_name, candidates:[{code,
            name, score, matched}]}], all_codes:[{code, name}] }``.
        """
        return suggest_responsibility_impl(xer_path, only_unassigned, code_type, cache)
