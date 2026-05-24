"""
Read {YYYY-MM-DD}-email.json (produced by the westland-mcps weekly-email
cloud editor) and orchestrate the existing .eml / COM email builders against
it.

The cloud editor replaces the legacy {YYYY-MM-DD}-email-preview.html round-trip.
This module is the local seam between the cloud-produced JSON and the existing
generate_update_email_eml / generate_update_email_msg functions in references/.

Three responsibilities:

    1. load_draft(path) -> dict
       Read + validate the JSON. Raises DraftError on missing top-level keys
       or unsupported version.

    2. build_stacked_chart_page(graphs, order) -> str
       Concatenate the canonical-order chart HTML chunks into one tall HTML
       page, scaled to 1200px viewport. Used as input to html_to_png.cjs.

    3. generate_email_from_draft(draft_path, output_eml_path,
                                  dated_folder, logo_path=None, ...) -> str
       Orchestrator: load draft, render stacked PNG via html_to_png.cjs,
       fan out the this_week fields as kwargs to generate_update_email_eml,
       return the .eml path.

The top-level JSON shape is canonical in scheduling/CLAUDE.md
"Email JSON shape — single source of truth" and the Worker schema at
https://westland-mcps.westland.workers.dev/westland-forms/weekly-schedule-update-email/schema.

Stdlib only for load_draft and build_stacked_chart_page. generate_email_from_draft
shells out to Node via subprocess. No new third-party deps.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path


SUPPORTED_VERSIONS = {2}

REQUIRED_TOP_LEVEL_KEYS = {'version', 'report_date', 'project_info', 'this_week'}


class DraftError(Exception):
    """Raised when an {YYYY-MM-DD}-email.json is malformed or unsupported."""


def load_draft(path):
    """Read an {YYYY-MM-DD}-email.json off disk and validate top-level shape.

    Args:
        path: Absolute or relative path to the JSON file.

    Returns:
        Parsed dict with all required top-level keys present:
            version, report_date, project_info, this_week.
        Optional top-level keys (last_week, smartpm, graphs) are passed
        through unchanged when present.

    Raises:
        DraftError: if the file is missing required top-level keys, has an
                    unsupported version, or is not valid JSON.
        FileNotFoundError: if path doesn't exist.
    """
    with open(path, 'r', encoding='utf-8') as f:
        try:
            draft = json.load(f)
        except json.JSONDecodeError as e:
            raise DraftError(f'Invalid JSON in {path}: {e}') from e

    missing = REQUIRED_TOP_LEVEL_KEYS - draft.keys()
    if missing:
        raise DraftError(
            f'{path} missing required top-level keys: {sorted(missing)}. '
            f'Expected the cloud-editor shape (version, report_date, '
            f'project_info, this_week). See scheduling/CLAUDE.md.'
        )

    version = draft.get('version')
    if version not in SUPPORTED_VERSIONS:
        raise DraftError(
            f'Unsupported version={version!r} in {path}. '
            f'Supported: {sorted(SUPPORTED_VERSIONS)}.'
        )

    return draft


_STACKED_PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=1200">
<title>Weekly schedule charts — stacked</title>
<style>
  /* CSS-scale 1728px native chart cards down to fit a 1200px viewport.
     SVG scales crisply so this loses no fidelity. */
  body {{
    margin: 0;
    padding: 0;
    width: 1200px;
    font-family: Inter, Arial, sans-serif;
    background: #ffffff;
  }}
  .chart-stack {{
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 16px;
  }}
  .chart-stack > .chart-card,
  .chart-stack > .chart-card--placeholder {{
    width: 100%;
    /* Charts render at 1728px native; scale to container width. */
    transform-origin: top left;
  }}
  .chart-stack > .chart-card svg,
  .chart-stack > .chart-card--placeholder svg {{
    width: 100%;
    height: auto;
    display: block;
  }}
</style>
</head>
<body>
<div class="chart-stack">
{cards}
</div>
</body>
</html>
"""


def build_stacked_chart_page(graphs, order):
    """Concatenate per-slug chart HTML chunks into one tall HTML document.

    Args:
        graphs: Dict keyed by slug, values are {html, data} (per the
                Worker schema). Empty or missing entries are skipped silently.
        order:  List of slugs in canonical render order. Slugs not present
                in `graphs` are skipped.

    Returns:
        A complete HTML5 document string. Body has 1200px width so Playwright
        screenshots it at the email-column scale.
    """
    cards = []
    for slug in order:
        chunk = graphs.get(slug)
        if not chunk:
            continue
        html = (chunk.get('html') or '').strip()
        if not html:
            continue
        cards.append(html)
    return _STACKED_PAGE_TEMPLATE.format(cards='\n'.join(cards))


# Path to the renderer agent's Node rasterizer. Resolved relative to this file
# so the path works whether the skill is installed via plugin zip or from the repo.
_HTML_TO_PNG_CJS = (
    Path(__file__).resolve().parent / 'charts' / 'html_to_png.cjs'
)


def _run_html_to_png(html_path, png_path, width=1200, full_page=True):
    """Shell out to Node html_to_png.cjs to rasterize HTML to PNG.

    Separate function so tests can monkeypatch it cleanly.
    """
    if not _HTML_TO_PNG_CJS.is_file():
        raise DraftError(
            f'html_to_png.cjs not found at {_HTML_TO_PNG_CJS}. '
            'The renderer agent\'s commit 1 must have landed for this to work.'
        )

    cmd = [
        'node', str(_HTML_TO_PNG_CJS),
        str(html_path), str(png_path),
        f'--width={width}',
    ]
    if full_page:
        cmd.append('--full-page')

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=120)
    except subprocess.CalledProcessError as e:
        raise DraftError(
            f'html_to_png.cjs failed (exit {e.returncode}): '
            f'stderr={e.stderr!r}'
        ) from e
    except subprocess.TimeoutExpired as e:
        raise DraftError(f'html_to_png.cjs timed out after 120s') from e

    return str(png_path)


def render_stacked_png(draft, output_dir):
    """Render the draft's stacked chart HTML to a single PNG file.

    Writes a temp HTML file, shells out to html_to_png.cjs to rasterize,
    then deletes the temp HTML. Returns the absolute PNG path.

    Args:
        draft: Parsed {YYYY-MM-DD}-email.json dict (from load_draft).
        output_dir: Directory the PNG lands in. Filename is
                    {job_number}-{report_date}-all-graphs-stacked.png.

    Returns:
        Absolute path to the written PNG.

    Raises:
        DraftError: if html_to_png.cjs is missing or fails.
    """
    graphs = draft.get('graphs') or {}
    this_week = draft.get('this_week') or {}
    # Canonical order: this_week.graph_order if present, else dict-insertion
    # order of graphs. JSON preserves insertion order in Python 3.7+ and ES2015+.
    order = this_week.get('graph_order') or list(graphs.keys())

    page_html = build_stacked_chart_page(graphs, order)

    os.makedirs(output_dir, exist_ok=True)
    job_number = (draft.get('project_info') or {}).get('job_number', 'project')
    png_name = f'{job_number}-{draft["report_date"]}-all-graphs-stacked.png'
    png_path = os.path.abspath(os.path.join(output_dir, png_name))

    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.html', dir=output_dir, delete=False, encoding='utf-8'
    ) as tmp:
        tmp.write(page_html)
        tmp_html_path = tmp.name

    try:
        _run_html_to_png(tmp_html_path, png_path, width=1200, full_page=True)
    finally:
        try:
            os.unlink(tmp_html_path)
        except OSError:
            pass

    return png_path


def _items_for_email_body(items):
    """Filter an item-list for email rendering.

    Items rendered in the body: checked=True AND status in ('active', 'new').
    Removed and archived items are excluded.
    """
    out = []
    for item in items or []:
        if not item.get('checked'):
            continue
        if item.get('status') in ('removed', 'archived'):
            continue
        text = (item.get('text') or '').strip()
        if text:
            out.append(text)
    return out


def _attachment_names_for_email(items):
    """Filter v2 attachment rows to a list of names for the email body.

    Items rendered: checked=True AND status != 'removed'.
    Returns basenames (no path). The orchestrator resolves them against
    dated_folder.
    """
    out = []
    for item in items or []:
        if not item.get('checked'):
            continue
        if item.get('status') == 'removed':
            continue
        name = (item.get('name') or item.get('filename') or '').strip()
        if name:
            out.append(name)
    return out


def _format_recipients(recipients):
    """[{name, email}] → 'Name <email>; Other <email2>' string.

    Empty / None → ''. Each entry: if name is non-empty, formats as
    'Name <email>'; if name is empty, just 'email'.
    """
    if not recipients:
        return ''
    parts = []
    for r in recipients:
        if not isinstance(r, dict):
            continue
        name = (r.get('name') or '').strip()
        email = (r.get('email') or '').strip()
        if not email:
            continue
        if name:
            parts.append(f'{name} <{email}>')
        else:
            parts.append(email)
    return '; '.join(parts)


def _join_closing_paragraphs(paragraphs):
    """closing_paragraphs[checked].text concatenated as HTML.

    Empty / None → ''. Each paragraph's text is HTML from the Trix editor.
    Joined with no separator (paragraphs already wrap themselves).
    """
    if not paragraphs:
        return ''
    parts = []
    for p in paragraphs:
        if not isinstance(p, dict):
            continue
        if not p.get('checked'):
            continue
        text = (p.get('text') or '').strip()
        if text:
            parts.append(text)
    return ''.join(parts)


def _flatten_days_metric(dm):
    """days_metric {direction, value} → signed int.

    'behind' → +value, 'ahead' → -value. Missing/empty → 0.
    """
    if not dm:
        return 0
    direction = (dm.get('direction') or '').lower()
    value = int(dm.get('value') or 0)
    return value if direction == 'behind' else -value


def _flatten_gain_loss(gl):
    """gain_loss {direction, value, ...} → signed int.

    'loss' → -value, 'gain' → +value. Missing/empty → 0.
    """
    if not gl:
        return 0
    direction = (gl.get('direction') or '').lower()
    value = int(gl.get('value') or 0)
    return -value if direction == 'loss' else value


def editorial_to_kwargs(this_week, project_info=None, last_week=None):
    """Translate v2 this_week + project_info (+ optional last_week) -> kwargs
    for generate_update_email_eml / generate_update_email_msg.

    All v2 → builder flattening lives here so the builder signatures stay stable.

    Args:
        this_week:    v2 `this_week` sub-dict from a loaded draft.
        project_info: top-level `project_info` dict.
        last_week:    optional frozen-copy of last week's this_week for
                      prev_days_behind/prev_gain_loss strikethrough badges.

    Returns:
        Dict suitable for `**kwargs` into the .eml or COM builder.
    """
    this_week = this_week or {}
    pi = project_info or {}

    to_str = _format_recipients(this_week.get('to_recipients'))
    cc_str = _format_recipients(this_week.get('cc_recipients'))

    days_behind = _flatten_days_metric(this_week.get('days_metric'))
    gain_loss = _flatten_gain_loss(this_week.get('gain_loss'))
    gl = this_week.get('gain_loss') or {}
    gain_loss_narrative = gl.get('narrative', '') or ''

    closing_html = _join_closing_paragraphs(this_week.get('closing_paragraphs'))

    kwargs = {
        'project_info': dict(pi),
        'subject': this_week.get('subject', '') or '',
        'to_recipients': to_str,
        'cc_recipients': cc_str,
        'days_behind': days_behind,
        'gain_loss': gain_loss,
        'gain_loss_narrative': gain_loss_narrative,
        'successes':     _items_for_email_body(this_week.get('successes')),
        'red_flags':     _items_for_email_body(this_week.get('red_flags')),
        'stalled_tasks': _items_for_email_body(this_week.get('stalled_tasks')),
        'key_items':     _items_for_email_body(this_week.get('key_items')),
        # key_items_archived: deliberately NOT rendered in the body.
        'eot_recovery':        this_week.get('eot_recovery', '') or '',
        'logic_changes':       this_week.get('logic_changes', '') or '',
        'smartpm_changelog_url': this_week.get('smartpm_changelog_url', '') or '',
        'closing_paragraphs_html': closing_html,
        'salutation':            this_week.get('closing_salutation', '') or '',
        'signer_name':  this_week.get('signer_name', '') or '',
        'signer_title': this_week.get('signer_title', '') or '',
        'signer_mobile': this_week.get('signer_mobile', '') or '',
        'attachment_paths': _attachment_names_for_email(this_week.get('attachments')),
        'from_address':    this_week.get('from', '') or '',
    }

    if last_week:
        kwargs['prev_days_behind'] = _flatten_days_metric(last_week.get('days_metric'))
        kwargs['prev_gain_loss']   = _flatten_gain_loss(last_week.get('gain_loss'))
    else:
        kwargs['prev_days_behind'] = None
        kwargs['prev_gain_loss'] = None

    return kwargs


def _call_generate_update_email_eml(output_path, **kwargs):
    """Thin indirection so tests can monkeypatch the .eml builder call."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from generate_email_eml import generate_update_email_eml
    finally:
        try:
            sys.path.remove(str(Path(__file__).resolve().parent))
        except ValueError:
            pass
    return generate_update_email_eml(output_path, **kwargs)


def _resolve_attachment_paths(filenames, dated_folder):
    """Resolve attachment filenames against dated_folder. Skip missing files."""
    resolved = []
    for filename in filenames or []:
        candidate = os.path.abspath(os.path.join(dated_folder, filename))
        if os.path.isfile(candidate):
            resolved.append(candidate)
        # Missing files are silently skipped — same policy as the existing
        # generate_update_email_eml's attachment loop.
    return resolved


def generate_email_from_draft(draft_path, output_eml_path, dated_folder,
                              logo_path=None, smartpm_project_url='',
                              smartpm_trends_url=''):
    """Build a .eml file from an email-draft.json.

    This is the new entry point that replaces the parse-preview-html flow.
    Reads the draft, renders the stacked chart PNG, resolves attachment
    filenames to absolute paths under dated_folder, fans the editorial
    fields out as kwargs to generate_update_email_eml.

    Args:
        draft_path:        Path to {YYYY-MM-DD}-email.json (from
                           finalize_weekly_schedule_update_email).
        output_eml_path:   Absolute path the .eml gets written to (typically
                           {dated_folder}/{YYYY-MM-DD}-update-email.eml).
        dated_folder:      The dated project folder — attachment filenames
                           in the draft resolve against this.
        logo_path:         Optional override; defaults to DEFAULT_LOGO_PATH.
        smartpm_project_url, smartpm_trends_url: passed through to the builder.

    Returns:
        Absolute path to the written .eml.

    Raises:
        DraftError on JSON / schema / rasterization failures.
    """
    draft = load_draft(draft_path)
    this_week = draft['this_week']
    project_info = draft.get('project_info')
    last_week = draft.get('last_week')   # may be None for week-1 projects

    # 1. Render the stacked-graphs PNG into the dated folder's screenshots/ dir.
    screenshots_dir = os.path.join(dated_folder, 'screenshots')
    stacked_png_path = render_stacked_png(draft, screenshots_dir)

    # 2. Translate this_week -> builder kwargs.
    kwargs = editorial_to_kwargs(this_week, project_info=project_info,
                                 last_week=last_week)

    # 3. Resolve attachment filenames -> absolute paths.
    kwargs['attachment_paths'] = _resolve_attachment_paths(
        kwargs['attachment_paths'], dated_folder
    )

    # 4. Plug the stacked PNG into the builder's `summary_screenshot_path` slot.
    #    The old per-chart graph_screenshot_paths list is empty in the new
    #    flow — one image holds all charts.
    kwargs['summary_screenshot_path'] = stacked_png_path
    kwargs['graph_screenshot_paths'] = []

    # 5. SmartPM URLs + logo.
    kwargs['smartpm_project_url'] = smartpm_project_url
    kwargs['smartpm_trends_url'] = smartpm_trends_url
    if logo_path is not None:
        kwargs['logo_path'] = logo_path

    # 6. Build the .eml.
    return _call_generate_update_email_eml(output_eml_path, **kwargs)
