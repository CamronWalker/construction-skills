"""PreToolUse hook: block Read/Edit/Write/MultiEdit/NotebookEdit/Glob/Grep
against schedule-toolbox/lib/*.py source files.

The Westland Scheduler Local MCP exposes the analysis surface that lib/
implements. Routine work must go through MCP tools (score_schedule,
get_critical_path, compare_activity_changes, ...). Reading or editing
the source directly defeats the seam — Claude starts reimplementing
existing logic, or proposes in-place tweaks that drift from the
canonical analysis behavior.

Improvement work on lib/ itself (the curator role) should happen in a
worktree where this hook is disabled. See the
westland-scheduler-mcp-troubleshoot skill for the workflow.

Blocks (exit 2) when the targeted path matches:
    **/schedule-toolbox/lib/**/*.py

For Glob and Grep, also blocks when the supplied `path` argument lives
under that directory, or when the `pattern` itself names that directory.
Other tools (Bash, Task, ...) are not matched.
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


BLOCK_MSG = """BLOCKED — schedule-toolbox/lib/*.py is fenced off from direct reads/edits.

Path: {path}

The Westland Scheduler Local MCP wraps everything lib/ does. Use the MCP
tools instead — e.g. score_schedule, get_critical_path, compare_activity_changes,
get_milestones, weekly_update_review, proposal_schedule_health. Run
`ToolSearch select:<tool_name>` to load any tool's schema.

If you are intentionally working on lib/ source (the curator role):
  1. Open a worktree with this hook disabled (see the
     westland-scheduler-mcp-troubleshoot skill — "Working on lib/ source").
  2. Make changes there, run tests, commit, and merge back.
"""


def _normalize(path):
    return path.replace('\\', '/') if path else ''


def _is_lib_py(path):
    return bool(_PY_RE.search(_normalize(path)))


def _references_lib(value):
    if not value:
        return False
    return bool(_LIB_REF_RE.search(str(value)))


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
            sys.stderr.write(BLOCK_MSG.format(path=path))
            sys.exit(2)

    elif tool == 'NotebookEdit':
        path = tool_input.get('notebook_path') or tool_input.get('file_path') or ''
        if _is_lib_py(path):
            sys.stderr.write(BLOCK_MSG.format(path=path))
            sys.exit(2)

    # Discovery tools: check both `path` and `pattern` arguments.
    elif tool in ('Glob', 'Grep'):
        path_arg = tool_input.get('path') or ''
        pattern_arg = tool_input.get('pattern') or ''
        if _references_lib(path_arg) or _references_lib(pattern_arg):
            label = path_arg or pattern_arg
            sys.stderr.write(BLOCK_MSG.format(path=label))
            sys.exit(2)

    sys.exit(0)


if __name__ == '__main__':
    main()
