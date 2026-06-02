"""
project-context.html <-> Supabase (wnd_projects / wnd_project_log) mapping.

Phase-0 of the project-context-supabase refactor. This module is the pure,
stub-testable seam between the parsed project-context.html dict (produced by
parse_project_context_html) and the Supabase rows. No network, no MCP calls
live here -- the calling skill owns get_project / upsert / insert.

Why a mapping module at all? The parser emits a superset of what
wnd_projects stores. The approved spec DELIBERATELY drops several fields
from the projects table:

  * to_recipients / cc_recipients (+ the *_str compat forms)
  * signer_name / signer_title / signer_mobile
  * graph_screenshots / graph_order
  * contractual_completion

Those live elsewhere (the weekly-email JSON owns recipients, signer, graph
order; contractual_completion is sourced from Procore at email-build time).
The project_log entries map to the SEPARATE wnd_project_log table, not into
the wnd_projects row.

Functions:
  project_row_to_context(row)            -> binding dict (binding keys only)
  parsed_context_to_project_row(parsed)  -> wnd_projects UPSERT payload
  parsed_context_to_log_entries(parsed)  -> [wnd_project_log row dicts]
  retire_context_html(path)              -> migrated path (collision-safe)

Python 3.10+ (cowork ships 3.10). No PEP 701 f-string syntax.
No external deps -- stdlib only.
"""

import os

__all__ = [
    'BINDING_COLUMNS',
    'project_row_to_context',
    'parsed_context_to_project_row',
    'parsed_context_to_log_entries',
    'retire_context_html',
]


# The wnd_projects columns that double as parse_project_context_html
# binding keys -- i.e. the values the skill substitutes into templates and
# downstream tooling reads by these exact names. job_number is a key column
# but is NOT one of these binding keys, so it is handled separately in the
# upsert payload and intentionally absent from the binding dict.
BINDING_COLUMNS = (
    'project_name',
    'smartpm_url',
    'smartpm_trends_url',
    'smartpm_changelog_url',
    'smartpm_project_name',
    'procore_company_id',
    'procore_project_id',
    'procore_documents_folder_id',
)


def _as_str(value):
    """Normalize a missing / None column to '' so callers never see None in
    a binding slot. Non-string scalars (ints from the DB) are stringified --
    the parser/generator round-trip the Procore/SmartPM ids as strings."""
    if value is None:
        return ''
    return value if isinstance(value, str) else str(value)


def project_row_to_context(row):
    """Map a wnd_projects row (as get_project would return) into the binding
    dict under the SAME key names parse_project_context_html uses.

    Emits ONLY the binding set (BINDING_COLUMNS). Recipients / signer /
    graph / contractual keys are never emitted -- they are not stored in
    wnd_projects. Server-managed columns (id, spm_project_id, source,
    created_by_email, created_at, updated_at) and the job_number key column
    are ignored. Missing / None columns default to ''.
    """
    row = row or {}
    return {col: _as_str(row.get(col)) for col in BINDING_COLUMNS}


def parsed_context_to_project_row(parsed, job_number=None):
    """Map the parser's output dict into a wnd_projects UPSERT payload.

    The payload is exactly {job_number} + BINDING_COLUMNS. Every cut field
    (recipients, signer, graph_screenshots/graph_order, contractual_
    completion) is DROPPED. project_log is DROPPED here -- it maps to the
    separate wnd_project_log table via parsed_context_to_log_entries.

    job_number resolution: the explicit ``job_number`` argument wins; else
    the value present in ``parsed``; else ''. (The caller supplies it when
    the parsed dict lacks one.)
    """
    parsed = parsed or {}
    if job_number is None:
        job_number = parsed.get('job_number')
    payload = {'job_number': _as_str(job_number)}
    for col in BINDING_COLUMNS:
        payload[col] = _as_str(parsed.get(col))
    return payload


def parsed_context_to_log_entries(parsed):
    """Map parser project_log entries into wnd_project_log row dicts.

    Each entry -> {'body': str, 'created_at': <date str or None>,
    'category': 'note'}. The parser stores each entry as {'date', 'body'};
    its 'date' is preserved as created_at when present (a non-empty string),
    otherwise created_at is None. Order is preserved.
    """
    parsed = parsed or {}
    entries = parsed.get('project_log') or []
    rows = []
    for entry in entries:
        date = (entry.get('date') or '') if isinstance(entry, dict) else ''
        body = (entry.get('body') or '') if isinstance(entry, dict) else ''
        rows.append({
            'body': body,
            'created_at': date if date else None,
            'category': 'note',
        })
    return rows


def retire_context_html(path):
    """Rename project-context.html -> project-context-migrated.html in the
    same directory and return the new path.

    Collision-safe: if project-context-migrated.html already exists, append
    a numeric suffix (-2, -3, ...) until an unused name is found, so a prior
    migration is never clobbered. Raises FileNotFoundError if ``path`` does
    not exist. Pure os/pathlib; cross-platform.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(path)
    directory = os.path.dirname(os.path.abspath(path))
    base = 'project-context-migrated'
    ext = '.html'
    target = os.path.join(directory, base + ext)
    n = 2
    while os.path.exists(target):
        target = os.path.join(directory, base + '-' + str(n) + ext)
        n += 1
    os.replace(path, target)
    return target
