"""Advisory hook: project-context.html is RETIRED. If Claude tries to
Read / Edit / Write a *legacy* project-context.html directly, steer it
toward the one-time lazy migration in schedule-project-init instead of
hand-editing — the embedded base64 logo corrupts under direct tool I/O.

Never blocks — always exits 0. Stderr goes to Claude as a system note.
"""

import json
import os
import re
import sys


# basename match: a legacy project-context.html. The file is RETIRED as a
# live source — project state lives in Supabase (wnd_projects / wnd_project_log),
# read via get_project and the weekly email in {YYYY-MM-DD}-email.json. Any
# project-context.html still on disk is a pre-migration legacy file.
PROTECTED_RE = re.compile(r'^project-context\.html$', re.IGNORECASE)


READ_MSG = """HEADS UP - direct Read on a legacy project-context.html ({path}).

project-context.html is RETIRED. Project state now lives in Supabase --
read bindings with the get_project(job_number) MCP tool and the project
log with list_project_log; the weekly email lives in {{YYYY-MM-DD}}-email.json.

A legacy project-context.html should be MIGRATED once by the
schedule-project-init skill, not read by hand. It is ~47 KB with an
embedded base64 logo that corrupts under direct tool I/O.
"""


WRITE_MSG = """HEADS UP - direct write to a legacy project-context.html ({path}).

project-context.html is RETIRED and is never regenerated -- the
generate_project_context_html generator is gone. W1177 (2026-05-07)
corrupted the embedded base64 logo via a direct Write.

A legacy project-context.html should be MIGRATED once by the
schedule-project-init skill (parse_project_context_html +
project_context_db_mapping -> upsert_project -> retire_context_html
renames it to project-context-migrated.html), never hand-edited or
regenerated. Write bindings with the upsert_project MCP tool instead.
"""


def main():
    try:
        payload = json.loads(sys.stdin.read() or '{}')
    except json.JSONDecodeError:
        sys.exit(0)

    tool = payload.get('tool_name', '')
    tool_input = payload.get('tool_input', {}) or {}
    path = tool_input.get('file_path') or tool_input.get('path') or ''

    if not path:
        sys.exit(0)

    if not PROTECTED_RE.search(os.path.basename(path)):
        sys.exit(0)

    if tool == 'Read':
        sys.stderr.write(READ_MSG.format(path=path))
    elif tool in ('Edit', 'Write', 'MultiEdit'):
        sys.stderr.write(WRITE_MSG.format(path=path))

    sys.exit(0)


if __name__ == '__main__':
    main()
