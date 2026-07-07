"""PreToolUse hook: recommend MCP tools when Read/Edit/Write/MultiEdit/
NotebookEdit/Glob/Grep targets schedule-toolbox/lib/*.py source files.

The Westland Scheduler Local MCP exposes the analysis surface that lib/
implements. Routine work should go through MCP tools (score_schedule,
get_critical_path, compare_activity_changes, ...) — reading or editing
the source directly defeats the seam.

Historically (Plan 1) this hook hard-blocked those reads with exit 2.
As of 8.1 the hook is a *recommendation*: when a match fires it emits a
PreToolUse JSON decision of `allow` along with a `permissionDecisionReason`
that tells Claude (a) the canonical MCP workflow and (b) the specific MCP
tools that wrap the matched file. The tool is allowed to proceed so Claude
can still debug an MCP failure by reading the underlying implementation.

When no match fires the hook exits 0 silently.

Improvement work on lib/ itself (the curator role) should happen in a
worktree where this hook is disabled. See the
westland-scheduler-mcp-troubleshoot skill for the workflow.
"""

import json
import os
import re
import sys


# Match a `.py` file anywhere under any `schedule-toolbox/lib/` directory.
# Path is normalized to forward-slashes first; the regex is forward-slash only.
_PY_RE = re.compile(r'(^|/)schedule-toolbox/lib/.+\.py$', re.IGNORECASE)

# Match Glob/Grep arguments that name the lib directory (with or without a
# trailing slash, and at any nesting depth).
_LIB_REF_RE = re.compile(r'(^|/|\\)schedule-toolbox[/\\]lib(/|\\|$)', re.IGNORECASE)


# Map basename of a lib/ script -> list of MCP tools that wrap it.
# Tailored recommendation messages point Claude at the right tool first.
_FILE_TO_TOOLS = {
    'score_schedule.py': [
        'score_schedule (omnibus)',
        'get_quality_check (single check by name)',
        'get_high_float_activities',
        'get_missing_logic',
        'get_constraint_violations',
    ],
    'quality_checks.py': [
        'get_quality_check',
        'get_relationship_type_breakdown',
        'get_missing_logic',
        'get_high_float_activities',
        'get_negative_float_activities',
        'get_constraint_violations',
        'get_high_duration_activities',
        'get_duplicate_relationships',
        'get_circular_relationships',
        'get_invalid_dates',
    ],
    'cpm_engine.py': [
        'run_cpm',
        'get_critical_path',
        'get_near_critical_chains',
        'get_driving_paths',
        'get_parallel_branches',
        'get_anchor_conflicts',
        'get_anchor_absorption_suggestions',
        'get_gantt_json',
        'render_gantt_html',
    ],
    'path_analysis.py': [
        'get_milestone_path_coverage',
        'get_delay_impacts',
    ],
    'xer_compare.py': [
        'compare_activity_changes',
        'compare_date_slips',
        'compare_milestone_slip',
        'compare_missed_dates',
    ],
    'update_review.py': [
        'get_activities_to_start',
        'get_activities_to_finish',
        'get_in_progress_activities',
        'get_ride_data_date_violations',
    ],
    'milestones.py': [
        'get_milestones',
    ],
    'activity_roster.py': [
        'list_activities',
        'get_activity',
        'get_wbs_branch',
        'next_free_activity_code',
    ],
    'responsibility_match.py': [
        'suggest_responsibility',
    ],
    'cross_baseline.py': [
        'get_critical_path_changes',
        'get_float_consumption',
        'get_trade_slip_summary',
        'get_gain_loss_attribution',
    ],
    'delay_analysis.py': [
        'compute_tia',
        'compute_window_analysis',
        'compute_change_order_delay',
        'get_concurrent_delay_pairs',
    ],
}


def _normalize(path):
    return path.replace('\\', '/') if path else ''


def _is_lib_py(path):
    return bool(_PY_RE.search(_normalize(path)))


def _references_lib(value):
    if not value:
        return False
    return bool(_LIB_REF_RE.search(str(value)))


def _basename(path):
    """Return the lowercased basename of a path, normalizing slashes."""
    norm = _normalize(path)
    if not norm:
        return ''
    return norm.rsplit('/', 1)[-1].lower()


def _build_reason(path, is_pattern=False):
    """Build the recommendation message Claude sees as permissionDecisionReason.

    `path` is the matched value (a file_path for Read/Edit/etc., a path or
    pattern for Glob/Grep). `is_pattern=True` switches the message to the
    discovery-tool variant.
    """
    if is_pattern:
        return (
            "You searched for `{label}` which references the fenced "
            "schedule-toolbox/lib directory.\n\n"
            "Routine analysis should go through the Westland Scheduler Local MCP "
            "tools that wrap the lib/ source — they hide the implementation so "
            "you don't have to load it into context. Browse the tool catalog "
            "with `ToolSearch` (no `select:` argument) to find a tool that "
            "matches your task, then load its schema with "
            "`ToolSearch select:<tool_name>`.\n\n"
            "If you're searching lib/ because an MCP tool failed and you need "
            "to debug the implementation, proceed — this call is allowed. The "
            "hook is letting you through intentionally for the debugging path."
        ).format(label=path)

    base = _basename(path)
    tools = _FILE_TO_TOOLS.get(base)

    if tools:
        bullet_list = "\n".join("  - {0}".format(t) for t in tools)
        tools_block = (
            "The relevant MCP tools for this file are:\n\n"
            "{bullets}\n\n"
        ).format(bullets=bullet_list)
    else:
        tools_block = (
            "This file's logic is part of the schedule-toolbox lib; check the "
            "MCP tool catalog (`ToolSearch` with no `select:` argument) for "
            "tools that match your task.\n\n"
        )

    return (
        "You're about to read/edit {path}.\n\n"
        "Routine analysis should go through the Westland Scheduler Local MCP "
        "tools that wrap this file's logic — they hide the lib so you don't "
        "have to load source into context. {tools_block}"
        "If you're reading this because an MCP tool failed and you need to "
        "debug the implementation, proceed — this access is allowed. The hook "
        "is letting you through intentionally for the debugging path.\n\n"
        "If you're not debugging and just want analysis results, prefer the "
        "MCP tools (`ToolSearch select:<tool_name>` to load schemas)."
    ).format(path=path, tools_block=tools_block)


def _emit_allow(reason):
    """Print the PreToolUse allow-with-reason JSON to stdout."""
    decision = {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
            "permissionDecisionReason": reason,
        }
    }
    sys.stdout.write(json.dumps(decision))


def main():
    try:
        payload = json.loads(sys.stdin.read() or '{}')
    except json.JSONDecodeError:
        sys.exit(0)

    tool = payload.get('tool_name', '')
    tool_input = payload.get('tool_input', {}) or {}

    # File-targeting tools: check file_path / notebook_path.
    if tool in ('Read', 'Edit', 'Write', 'MultiEdit'):
        path = tool_input.get('file_path') or ''
        if _is_lib_py(path):
            _emit_allow(_build_reason(path, is_pattern=False))
            sys.exit(0)

    elif tool == 'NotebookEdit':
        path = tool_input.get('notebook_path') or tool_input.get('file_path') or ''
        if _is_lib_py(path):
            _emit_allow(_build_reason(path, is_pattern=False))
            sys.exit(0)

    # Discovery tools: check both `path` and `pattern` arguments.
    elif tool in ('Glob', 'Grep'):
        path_arg = tool_input.get('path') or ''
        pattern_arg = tool_input.get('pattern') or ''
        if _references_lib(path_arg) or _references_lib(pattern_arg):
            label = path_arg or pattern_arg
            _emit_allow(_build_reason(label, is_pattern=True))
            sys.exit(0)

    sys.exit(0)


if __name__ == '__main__':
    main()
