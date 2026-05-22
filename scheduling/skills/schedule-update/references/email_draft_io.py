"""
Read email-draft.json (produced by the westland-mcps weekly-email cloud editor)
and orchestrate the existing .eml / COM email builders against it.

The cloud editor replaces the {YYYY-MM-DD}-email-preview.html round-trip.
This module is the local seam between the cloud-produced JSON and the existing
generate_update_email_eml / generate_update_email_msg functions in references/.

Three responsibilities:

    1. load_draft(path) -> dict
       Read + validate the JSON. Raises DraftError on missing top-level keys
       or unsupported schema_version.

    2. build_stacked_chart_page(graph_html, order) -> str
       Concatenate the canonical-order chart HTML chunks into one tall HTML
       page, scaled to 1200px viewport. Used as input to html_to_png.cjs.

    3. generate_email_from_draft(draft_path, output_eml_path,
                                  dated_folder, logo_path=None, ...) -> str
       Orchestrator: load draft, render stacked PNG via html_to_png.cjs,
       fan out the editorial fields as kwargs to generate_update_email_eml,
       return the .eml path.

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


SUPPORTED_SCHEMA_VERSIONS = {1}

REQUIRED_TOP_LEVEL_KEYS = {'project', 'report_date', 'editorial', 'graph_html', 'meta'}


class DraftError(Exception):
    """Raised when an email-draft.json is malformed or unsupported."""


def load_draft(path):
    """Read an email-draft.json off disk and validate top-level shape.

    Args:
        path: Absolute or relative path to the JSON file.

    Returns:
        Parsed dict with all top-level keys present.

    Raises:
        DraftError: if the file is missing required top-level keys, has an
                    unsupported schema_version, or is not valid JSON.
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
            f'email-draft.json at {path} missing required keys: {sorted(missing)}'
        )

    schema = draft.get('meta', {}).get('schema_version')
    if schema not in SUPPORTED_SCHEMA_VERSIONS:
        raise DraftError(
            f'Unsupported schema_version={schema!r} in {path}. '
            f'Supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}.'
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


def build_stacked_chart_page(graph_html, order):
    """Concatenate per-slug chart HTML chunks into one tall HTML document.

    Args:
        graph_html: Dict keyed by slug, values are {status, html, svgInner}.
                    Empty or missing entries are skipped silently.
        order:      List of slugs in canonical render order. Slugs not present
                    in graph_html are skipped.

    Returns:
        A complete HTML5 document string. Body has 1200px width so Playwright
        screenshots it at the email-column scale.
    """
    cards = []
    for slug in order:
        chunk = graph_html.get(slug)
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
        draft: Parsed email-draft.json dict (from load_draft).
        output_dir: Directory the PNG lands in. Filename is
                    {project}-{report_date}-all-graphs-stacked.png.

    Returns:
        Absolute path to the written PNG.

    Raises:
        DraftError: if html_to_png.cjs is missing or fails.
    """
    graph_html = draft['graph_html']
    order = draft['editorial']['graph_order']

    page_html = build_stacked_chart_page(graph_html, order)

    os.makedirs(output_dir, exist_ok=True)
    png_name = f'{draft["project"]}-{draft["report_date"]}-all-graphs-stacked.png'
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
    """Filter an item-list (successes / red_flags / etc.) for email rendering.

    The .eml + COM builders accept lists of markdown strings (the canonical
    rule: only `checked=True` and `status != 'archived'`). Matches
    parse_email_html.parse_preview_html()'s "list of markdown strings" shape.
    """
    out = []
    for item in items or []:
        if not item.get('checked'):
            continue
        if item.get('status') == 'archived':
            continue
        text = item.get('text', '').strip()
        if text:
            out.append(text)
    return out


def _custom_paragraphs_for_email_body(items):
    """Filter custom paragraphs to {label, text} dicts for the body builder."""
    out = []
    for item in items or []:
        if not item.get('checked'):
            continue
        label = item.get('label', '').strip()
        text = item.get('text', '').strip()
        if label or text:
            out.append({'label': label, 'text': text})
    return out


def _attachments_for_email_body(items):
    """Filter attachments for email-body inclusion (filenames only).

    Returns a list of FILENAMES (not absolute paths). The orchestrator
    `generate_email_from_draft` resolves these against the dated project
    folder before passing to the builders.
    """
    out = []
    for item in items or []:
        if not item.get('checked'):
            continue
        if item.get('status') == 'archived':
            continue
        filename = (item.get('filename') or '').strip()
        if filename:
            out.append(filename)
    return out


def editorial_to_kwargs(editorial):
    """Translate draft.editorial -> kwargs for generate_update_email_eml/msg.

    The shape generate_update_email_eml expects is documented in
    references/generate_email_eml.py::generate_update_email_eml's docstring;
    the shape parse_email_html.parse_preview_html() returns is the canonical
    source of truth (per scheduling/CLAUDE.md). This function bridges the
    JSON shape (which mirrors parse_preview_html's `_full` dict shape) to
    the builder kwargs (which want the filtered markdown-string shape for
    items, filtered filename list for attachments).

    Procore-related fields (`skip_procore`, `attachments[].share_to_procore`)
    are NOT in the returned kwargs — they're consumed by the procore phase,
    not the email body. The procore phase reads them straight off the
    draft.editorial dict.

    Args:
        editorial: The `editorial` sub-dict from a loaded draft.

    Returns:
        Dict suitable for `**kwargs` into generate_update_email_eml or
        generate_update_email_msg.
    """
    return {
        'project_info': dict(editorial.get('project_info') or {}),
        'days_behind': int(editorial.get('days_behind') or 0),
        'gain_loss': int(editorial.get('gain_loss') or 0),
        'successes':     _items_for_email_body(editorial.get('successes')),
        'red_flags':     _items_for_email_body(editorial.get('red_flags')),
        'stalled_tasks': _items_for_email_body(editorial.get('stalled_tasks')),
        'key_items':     _items_for_email_body(editorial.get('key_items')),
        'gain_loss_narrative': editorial.get('gain_loss_narrative', '') or '',
        'eot_recovery':        editorial.get('eot_recovery', '') or '',
        'logic_changes':       editorial.get('logic_changes', '') or '',
        'smartpm_changelog_url': editorial.get('smartpm_changelog_url', '') or '',
        'custom_paragraphs': _custom_paragraphs_for_email_body(
            editorial.get('custom_paragraphs')
        ),
        # Names only — orchestrator resolves paths.
        'attachment_paths': _attachments_for_email_body(editorial.get('attachments')),
        'subject':         editorial.get('subject', '') or '',
        'from_address':    editorial.get('from', '') or '',
        'to_recipients':   editorial.get('to', '') or '',
        'cc_recipients':   editorial.get('cc', '') or '',
        'signer_name':     editorial.get('signer_name', '') or '',
        'signer_title':    editorial.get('signer_title', '') or '',
        'signer_mobile':   editorial.get('signer_mobile', '') or '',
    }


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
        draft_path:        Path to email-draft.json (from MCP finalize_weekly_email).
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
    editorial = draft['editorial']

    # 1. Render the stacked-graphs PNG into the dated folder's screenshots/ dir.
    screenshots_dir = os.path.join(dated_folder, 'screenshots')
    stacked_png_path = render_stacked_png(draft, screenshots_dir)

    # 2. Translate editorial -> builder kwargs.
    kwargs = editorial_to_kwargs(editorial)

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
