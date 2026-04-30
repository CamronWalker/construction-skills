"""
build_gantt_html.py -- render a self-contained Gantt review HTML from
schedule-activities.json.

Reads `schedule-activities.json` (emitted alongside the XER by the
schedule-toolbox CPM step), inlines:

  - frappe-gantt UMD JS + CSS (vendored at scheduling/lib/frappe-gantt/)
  - the Westland-branded template (scheduling/templates/gantt-review.html)
  - the Westland logo (scheduling/assets/westland-logo.png) as a base64 data URI
  - the activity JSON itself (embedded in a <script type=application/json> tag)

...and writes the result as `schedule-review.html` (overwriting in place).
The HTML opens straight from disk -- no server, no CDN, no external assets.

Usage:
    python build_gantt_html.py schedule-activities.json
    python build_gantt_html.py schedule-activities.json -o my-review.html
    python build_gantt_html.py schedule-activities.json --project "Murray Apex"

If --project is omitted, the project.name field from the JSON is used.
"""

import argparse
import base64
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# -------------------------------------------------------------------------
# Path discovery
# -------------------------------------------------------------------------

_THIS_DIR = Path(__file__).resolve().parent
_SCHEDULING_DIR = _THIS_DIR.parent  # construction-skills/scheduling/

TEMPLATE_PATH = _SCHEDULING_DIR / 'templates' / 'gantt-review.html'
GANTT_JS_PATH = _SCHEDULING_DIR / 'lib' / 'frappe-gantt' / 'frappe-gantt.umd.js'
GANTT_CSS_PATH = _SCHEDULING_DIR / 'lib' / 'frappe-gantt' / 'frappe-gantt.css'
LOGO_PATH = _SCHEDULING_DIR / 'assets' / 'westland-logo.png'


# -------------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------------

def _read_text(path):
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def _read_bytes(path):
    with open(path, 'rb') as f:
        return f.read()


def _logo_inline_html(logo_path=LOGO_PATH):
    """Return the <img> tag for the Westland logo, embedded as data URI."""
    if not logo_path.exists():
        return ('<span style="font-weight:bold;font-size:18pt;color:#0B4F66;'
                'letter-spacing:1px">WESTLAND</span>')
    raw = _read_bytes(logo_path)
    suffix = logo_path.suffix.lower().lstrip('.')
    mime = {
        'png': 'image/png',
        'svg': 'image/svg+xml',
        'jpg': 'image/jpeg',
        'jpeg': 'image/jpeg',
        'gif': 'image/gif',
        'webp': 'image/webp',
    }.get(suffix, 'application/octet-stream')
    encoded = base64.b64encode(raw).decode('ascii')
    return ('<img class="wl-logo-img" alt="Westland" '
            'src="data:{m};base64,{b64}">'.format(m=mime, b64=encoded))


def _safe_json_for_script(data):
    """Serialize data as JSON safe for embedding inside <script> tags.

    Replaces "</" so a stray </script> in a string can't end the tag, and
    escapes line separators that browsers treat as line terminators in JS.
    """
    text = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    return (text
            .replace('</', '<\\/')
            .replace(' ', '\\u2028')
            .replace(' ', '\\u2029'))


def _escape_html_text(s):
    return (str(s)
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;'))


# -------------------------------------------------------------------------
# Build
# -------------------------------------------------------------------------

def build_gantt_html(activities_json_path, output_path=None,
                     project_name_override=None,
                     template_path=TEMPLATE_PATH,
                     gantt_js_path=GANTT_JS_PATH,
                     gantt_css_path=GANTT_CSS_PATH,
                     logo_path=LOGO_PATH):
    """
    Render schedule-review.html from schedule-activities.json.

    Args:
        activities_json_path: path to schedule-activities.json
        output_path: where to write the HTML (default: same folder, schedule-review.html)
        project_name_override: optional project name (overrides JSON's project.name)

    Returns:
        Path to the written HTML file.
    """
    activities_json_path = Path(activities_json_path)
    if not activities_json_path.exists():
        raise FileNotFoundError('Activities JSON not found: ' + str(activities_json_path))

    with open(activities_json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # Resolve output path
    if output_path is None:
        output_path = activities_json_path.parent / 'schedule-review.html'
    output_path = Path(output_path)

    # Resolve project name
    project = data.get('project') or {}
    project_name = (project_name_override
                    or project.get('name')
                    or activities_json_path.stem)

    template = _read_text(template_path)
    gantt_js = _read_text(gantt_js_path)
    gantt_css = _read_text(gantt_css_path)
    logo_html = _logo_inline_html(logo_path)
    activities_payload = _safe_json_for_script(data)
    built_at = datetime.now().strftime('%Y-%m-%d %H:%M')

    substitutions = {
        '<<<PROJECT_NAME>>>': _escape_html_text(project_name),
        '<<<BUILT_AT>>>': _escape_html_text(built_at),
        '<<<LOGO_INLINE>>>': logo_html,
        '<<<FRAPPE_GANTT_CSS>>>': gantt_css,
        '<<<FRAPPE_GANTT_JS>>>': gantt_js,
        '<<<ACTIVITIES_JSON>>>': activities_payload,
    }

    html = template
    for token, value in substitutions.items():
        html = html.replace(token, value)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)

    return output_path


# -------------------------------------------------------------------------
# CLI
# -------------------------------------------------------------------------

def _main(argv=None):
    parser = argparse.ArgumentParser(
        description='Render schedule-review.html from schedule-activities.json'
    )
    parser.add_argument('activities_json',
                        help='Path to schedule-activities.json')
    parser.add_argument('-o', '--output',
                        help='Output HTML path (default: same folder, schedule-review.html)')
    parser.add_argument('--project',
                        help='Override project name (default: project.name from JSON)')
    args = parser.parse_args(argv)

    out = build_gantt_html(args.activities_json,
                           output_path=args.output,
                           project_name_override=args.project)
    print('Wrote: ' + str(out))
    return 0


if __name__ == '__main__':
    sys.exit(_main())
