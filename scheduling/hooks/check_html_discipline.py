"""Advisory hook: when Claude reads or writes one of the managed HTML
artifacts in the schedule update pipeline, print a steer toward the
matching parse/generate Python script.

Never blocks — always exits 0. Stderr goes to Claude as a system note.
"""

import json
import os
import re
import sys


# basename match: project-context.html  OR  YYYY-MM-DD-email-preview.html
PROTECTED_RE = re.compile(
    r'(?:^project-context\.html$|^\d{4}-\d{2}-\d{2}-email-preview\.html$)',
    re.IGNORECASE,
)


READ_MSG = """HEADS UP — direct Read on a managed HTML file ({path}).

This file is 47-160 KB. Prefer the JSON parser:
  - project-context.html        -> parse_project_context_html.load_project_context(schedules_root)
  - *-email-preview.html        -> parse_email_html.parse_preview_html(path)

Reading via the parser gives you a dict and avoids token blow-up. You can
proceed if you have a reason, but most reads should go through the parser.
"""


WRITE_MSG = """HEADS UP — direct write to a managed HTML file ({path}).

W1177 (2026-05-07) corrupted the embedded base64 logo via a direct Write.
Prefer the matching generator:
  - project-context.html        -> generate_project_context_html.generate_project_context_html(path, ctx)
  - *-email-preview.html        -> generate_email_preview_html.generate_email_preview_html(...)

Not blocked, but pause: is this an edit the generator can do?
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
