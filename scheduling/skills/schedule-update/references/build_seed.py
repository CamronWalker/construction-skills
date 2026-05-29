"""
Build a v2 seed dict for the weekly schedule update email cloud editor.

The Worker schema at
    https://westland-mcps.westland.workers.dev/westland-forms/weekly-schedule-update-email/schema
is the contract. This helper's job is to produce a dict that satisfies it,
in one call, from the inputs the report flow has on hand:

    - project_context (from parse_project_context_html.load_project_context)
    - prev_draft      (from email_draft_io.load_draft on last week's email.json)
    - this week's XER comparison deltas (from the westland-scheduler-mcp tools)
    - this week's narrative content (from the meeting transcript or the colleague)
    - fresh attachment filenames (from globbing the dated folder)

Callers should treat the live schema URL as authoritative. If a POST returns
422, refetch the schema, diff against the seed at the violation's field path,
fix, and re-POST. Update this builder when the schema changes — don't paper
over schema drift inside the caller.

Stdlib only. No third-party deps. The schema-fetch helper is here so callers
that want a local sanity check can use it, but the canonical pre-POST validation
is the Worker itself.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from urllib.error import URLError

# Allow importing sibling references (carry_forward) when this module is
# imported by Claude's session — driving scripts add references/ to sys.path,
# but the helper is also useful in isolation.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

from carry_forward import (  # noqa: E402
    reconcile_items,
    reconcile_key_items,
    transition_attachments,
)


SCHEMA_URL = (
    'https://westland-mcps.westland.workers.dev/'
    'westland-forms/weekly-schedule-update-email/schema.json'
)

CANONICAL_GRAPH_ORDER = [
    # smartpm-summary-report is intentionally NOT in this list — it ships
    # as its own PNG at the top of the email body (Section 3) rather than
    # being stacked with the trend gallery (Section 11). The Worker still
    # emits its HTML chunk in `graphs['smartpm-summary-report']`; the email
    # pipeline pulls it via render_summary_png() in email_draft_io.py.
    '01-planned-vs-actual-percent-complete',
    '06-end-date-variance',
    '07-schedule-compression-index-over-time',
    '08-velocity',
    '09-spi-over-time',
    '10-activity-hit-rate',
    '11-window-start-accuracy',
    '12-window-finish-accuracy',
]

DEFAULT_CLOSING_PARAGRAPHS = [{
    'label': 'Questions',
    'checked': True,
    'text': '<div>Please let me know if you have any questions.</div>',
}]

DEFAULT_CLOSING_SALUTATION = 'Thanks,'


class SeedBuildError(Exception):
    """Raised when build_seed_dict can't produce a valid seed from its inputs."""


# Module-level schema cache. Lives for the lifetime of the Python process —
# the schema is small and immutable within a session.
_schema_cache = None


def fetch_schema(url=SCHEMA_URL, timeout=10):
    """Fetch the live Worker schema JSON. Cached per-process.

    Caller-visible so callers can do their own sanity checks. build_seed_dict
    does NOT call this internally — the Worker validates on POST and is the
    source of truth; a local validator would be a second contract that can drift.

    Raises:
        SeedBuildError: if the URL can't be reached.
    """
    global _schema_cache
    if _schema_cache is not None:
        return _schema_cache
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            _schema_cache = json.load(resp)
    except (URLError, json.JSONDecodeError) as e:
        raise SeedBuildError(
            f'Could not fetch live schema from {url}: {e}. '
            'WebFetch the URL from the calling session and pass it down if '
            'this helper is running in a sandbox without outbound network.'
        ) from e
    return _schema_cache


def _require(ctx, field):
    """Return ctx[field] or raise a SeedBuildError naming what's missing."""
    value = ctx.get(field)
    if value in (None, ''):
        raise SeedBuildError(
            f"project-context.html is missing required field '{field}'. "
            f"Run schedule-project-init to seed it, or fill the field in the "
            f"editor at the Schedules root."
        )
    return value


def build_seed_dict(
    ctx,
    prev_draft,
    today_iso,
    projected_completion_iso,
    days_metric_value,
    days_metric_direction,
    gain_loss_value,
    gain_loss_direction,
    gain_loss_narrative,
    eot_recovery,
    logic_changes,
    successes_html,
    red_flags_html,
    stalled_tasks_html,
    key_items_html,
    fresh_filenames,
    subject=None,
    changes_report_filename=None,
    include_changes_report=True,
):
    """Build a fully-formed v2 seed dict that the Worker will accept.

    All required top-level and this_week fields are populated unconditionally.
    Optional fields fall back to last week's value or a documented default.

    The shape this returns matches the Worker schema at SCHEMA_URL. If the
    schema changes, update this builder — do not band-aid in callers.

    Args:
        ctx: Parsed project-context.html (from parse_project_context_html).
            Must contain project_name, job_number, contractual_completion,
            to_recipients, signer_name, signer_title.
        prev_draft: Parsed last week's email.json (from email_draft_io.load_draft),
            or None for a week-1 project.
        today_iso: 'YYYY-MM-DD' for this update.
        projected_completion_iso: 'YYYY-MM-DD' projected completion from this
            week's XER (from compare_milestone_slip.sc_date_new).
        days_metric_value: Absolute days vs contractual_completion (non-negative).
        days_metric_direction: 'behind' if projected is past contractual,
            'ahead' if projected is before contractual.
        gain_loss_value: Absolute days slipped vs last week's projected completion
            (from compare_milestone_slip.sc_slip_days; abs value).
        gain_loss_direction: 'loss' if SC slipped, 'gain' if SC pulled in.
        gain_loss_narrative: One-paragraph HTML explaining the week-over-week move.
        eot_recovery: HTML; EOT / recovery narrative for this week.
        logic_changes: HTML; what logic moved this week.
        successes_html: list[str] of HTML item bodies.
        red_flags_html: list[str].
        stalled_tasks_html: list[str].
        key_items_html: list[str]; carry-forward applies and may add archived rows.
        fresh_filenames: list[basename] of attachment candidates in the dated folder.
        subject: Email subject; defaults to "Schedule Update - {project_name} - {today_iso}".
        changes_report_filename: Filename of this week's changes-report PDF, if any.
        include_changes_report: Master toggle for the changes-report attachment.

    Returns:
        A v2 seed dict ready to POST to generate_weekly_schedule_update_email_draft.

    Raises:
        SeedBuildError: if any required project_context field is missing.
        ValueError: if discriminator values are not in their valid enum.
    """
    if days_metric_direction not in ('behind', 'ahead'):
        raise ValueError(
            f"days_metric_direction must be 'behind' or 'ahead', got "
            f"{days_metric_direction!r}"
        )
    if gain_loss_direction not in ('gain', 'loss'):
        raise ValueError(
            f"gain_loss_direction must be 'gain' or 'loss', got "
            f"{gain_loss_direction!r}"
        )

    project_name = _require(ctx, 'project_name')
    job_number = _require(ctx, 'job_number')
    contractual_completion = _require(ctx, 'contractual_completion')

    to_recipients = ctx.get('to_recipients') or []
    if not to_recipients:
        raise SeedBuildError(
            'project-context.html has no to_recipients. Add at least one '
            'recipient row before running the report flow.'
        )

    prev_this_week = (prev_draft or {}).get('this_week') or {}

    successes_rows, _ = reconcile_items(
        prev_this_week.get('successes'),
        successes_html or [],
        today_iso=today_iso,
    )
    red_flags_rows, _ = reconcile_items(
        prev_this_week.get('red_flags'),
        red_flags_html or [],
        today_iso=today_iso,
    )
    stalled_rows, _ = reconcile_items(
        prev_this_week.get('stalled_tasks'),
        stalled_tasks_html or [],
        today_iso=today_iso,
    )
    key_items_rows, key_items_archived_rows, _ = reconcile_key_items(
        prev_this_week.get('key_items'),
        prev_this_week.get('key_items_archived'),
        key_items_html or [],
        today_iso=today_iso,
    )

    attachments_rows = transition_attachments(
        prev_this_week.get('attachments'),
        fresh_filenames or [],
        today_iso=today_iso,
    )

    if subject is None:
        subject = f'Schedule Update - {project_name} - {today_iso}'

    prev_gl_narrative = (
        ((prev_this_week.get('gain_loss') or {}).get('narrative') or '')
        .strip().lower()
    )
    narrative_changed = (
        (gain_loss_narrative or '').strip().lower() != prev_gl_narrative
    )

    this_week = {
        'subject': subject,
        'to_recipients': list(to_recipients),
        'cc_recipients': list(ctx.get('cc_recipients') or []),

        'days_metric': {
            'direction': days_metric_direction,
            'value': abs(int(days_metric_value)),
        },
        'gain_loss': {
            'direction': gain_loss_direction,
            'value': abs(int(gain_loss_value)),
            'narrative': gain_loss_narrative or '',
            'narrative_changed': narrative_changed,
        },

        'successes': successes_rows,
        'red_flags': red_flags_rows,
        'stalled_tasks': stalled_rows,
        'key_items': key_items_rows,
        'key_items_archived': key_items_archived_rows,

        'eot_recovery': eot_recovery or '',
        'logic_changes': logic_changes or '',
        'smartpm_changelog_url': ctx.get('smartpm_changelog_url') or '',

        'closing_paragraphs': (
            prev_this_week.get('closing_paragraphs')
            or list(DEFAULT_CLOSING_PARAGRAPHS)
        ),
        'closing_salutation': (
            prev_this_week.get('closing_salutation')
            or DEFAULT_CLOSING_SALUTATION
        ),

        'signer_name': ctx.get('signer_name') or '',
        'signer_title': ctx.get('signer_title') or '',
        'signer_mobile': ctx.get('signer_mobile') or '',

        'attachments': attachments_rows,
        'skip_procore': bool(prev_this_week.get('skip_procore', False)),
        'include_changes_report': bool(include_changes_report and changes_report_filename),
        'changes_report_filename': changes_report_filename or '',

        'graph_order': (
            prev_this_week.get('graph_order')
            or list(CANONICAL_GRAPH_ORDER)
        ),
    }

    return {
        'version': 2,
        'report_date': today_iso,
        'project_info': {
            'project_name': project_name,
            'job_number': job_number,
            'contractual_completion': contractual_completion,
            'projected_completion': projected_completion_iso or '',
        },
        'this_week': this_week,
        'last_week': prev_this_week if prev_draft else None,
    }
