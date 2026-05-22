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
