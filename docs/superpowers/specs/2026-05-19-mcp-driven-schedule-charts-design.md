# MCP-driven schedule charts + HTML-discipline hook

**Date:** 2026-05-19
**Branch:** `funny-babbage-446d9e` → `feat/mcp-driven-schedule-charts`
**Plugin scope:** `scheduling` (chart renderer + phase rewrite + hook)

## Motivation

The `screenshots` phase of the weekly schedule update is the temperamental piece of the pipeline. It uses Playwright to auto-log into SmartPM v2, find the project card, click into the Trends page, and screenshot each `<spm-card-container>`. It breaks in predictable ways: SmartPM still processing the XER, login flow changes, sign-in button stuck disabled, DOM layout shifts mid-capture, MFA/captcha prompts.

The SmartPM MCP now exposes the underlying data that powers every chart on the Trends page. We can swap the capture mechanism: instead of screenshotting SmartPM, fetch the numbers, draw the charts ourselves in matplotlib, save the PNGs.

Second motivation: HTML artifacts in this pipeline (`project-context.html`, `*-email-preview.html`) are managed by parse/generate Python scripts because direct Read/Write has corrupted them historically (W1177 base64 logo, 2026-05-07). The model still occasionally bypasses the discipline. An advisory hook in the scheduling plugin steers it back without hard-blocking.

## Goals

1. Replace Playwright-driven SmartPM screenshot capture for the 7 default trend graphs and the Summary Report with MCP fetch + matplotlib render.
2. Output PNGs land in `{dated_folder}/screenshots/` under the existing filename convention so nothing downstream (`email`, `report`, `draft`, `.eml`, Procore) has to change.
3. Summary Report ships as a **single composite PNG** (`smartpm-summary-report.png` — same filename as today) containing three vertically stacked subplots: 3 metric cards on top, Planned-vs-Actual curve middle, milestones table bottom. One file means zero changes to `generate_email_preview_html.py`, `generate_email_eml.py`, `parse_email_html.py`, or carry-forward.
4. Add a `scheduling` plugin PreToolUse hook that warns (advisory, not blocking) when Claude reads or writes the managed HTML files directly.
5. Delete the SmartPM Playwright capture path (`references/smartpm/capture-smartpm.js`, env-loader, tests) — no longer needed once the MCP path is in.

## Non-goals (out of scope this branch)

- Reshaping carry-forward, `email-template.md`, `generate_email_preview_html.py`, `generate_email_eml.py`, Procore steps, archive markdown.
- Replacing the 30-min "SmartPM might still be processing" wait — the MCP hits the same upstream so the wait is still real. Document the existing warning; don't try to engineer around it.
- Building anything Cowork-specific. The new path works equally in Claude Code CLI and Cowork because there's no browser automation.
- Auto-resolving `smartpm_project_name` / `scenario_id` from the project name. Out of scope here; track separately.

## High-level architecture

```
phases/screenshots.md  (rewritten — orchestrator lives in the markdown)
    │
    ├─ reads project-context.html
    ├─ calls SmartPM MCP per graph slug (one call per graph in graph_screenshots,
    │   plus one each for the 3 Summary Report parts)
    ├─ writes responses to {temp_dir}/{slug}.json
    └─ runs: python references/charts/render.py {temp_dir} {output_dir}

references/charts/
    style.py     # shared visual constants only — colors, fonts, fig dims, savefig kwargs
    charts.py    # one render function per graph, self-contained — pure (data, out_path) → PNG
    render.py    # CLI entry: payload dir + output dir → dispatches each {slug}.json
                 # to its render function via a registry
    __init__.py
    tests/
        fixtures/        # canned MCP JSON per endpoint
        test_charts.py   # golden-image regression — one test per render function
```

```
scheduling/hooks/
    check_html_discipline.py
    hooks.json
```

## Module-by-module

### `references/charts/style.py`

Shared visual constants only. **No functions that draw stuff** — those live in `charts.py`. This module is small and pure.

```python
# Colors picked to feel like SmartPM's chart palette
TEAL      = '#0E7C7B'   # primary (planned, target)
ORANGE    = '#D8732E'   # secondary (actual, variance)
RED       = '#C94444'   # alerts / behind
GREEN     = '#3A9E6B'   # ahead / good
GRAY      = '#6B7280'   # baseline / grid

FIGSIZE   = (10, 5)     # inches; matches roughly the aspect of SmartPM cards in email
DPI       = 144         # crisp on Outlook desktop; ~1440×720 px output
FONT      = 'Calibri'   # fall back to mpl default if missing on the host
TITLE_PAD = 14

SAVEFIG_KWARGS = dict(
    bbox_inches='tight',
    facecolor='white',
    edgecolor='none',
)
```

If `Calibri` isn't available (Linux dev machines), matplotlib falls back silently. We accept the visual delta; Windows hosts (where the actual emails ship from) will have it.

### `references/charts/charts.py`

One render function per graph. Each function is self-contained: data in, PNG out. **No shared chart-type base function.** If two graphs both happen to be line-with-markers, they each have their own ~25-line function. Cost: a little repetition. Benefit: each function is readable in isolation; tweaking #6 can never break #7.

```python
import matplotlib.pyplot as plt
from . import style

def render_end_date_variance(data, output_path):
    """
    Chart 06 — projected substantial-completion date over time, per schedule update.

    data shape:
      {
        "updates": [
          {"data_date": "YYYY-MM-DD", "projected_finish": "YYYY-MM-DD"},
          ...
        ],
        "contractual_completion": "YYYY-MM-DD"  # horizontal target line
      }
    """
    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
    ...  # plot logic specific to this chart
    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)

def render_schedule_compression_index(data, output_path):
    """Chart 07 — compression index over time, single line."""
    ...

def render_velocity(data, output_path):
    """Chart 08 — monthly start/finish stacked bars."""
    ...

def render_spi_over_time(data, output_path):
    """Chart 09 — SPI line; horizontal reference at 1.0."""
    ...

def render_activity_hit_rate(data, output_path):
    """Chart 10 — percentage line; y-axis clamped 0–100."""
    ...

def render_window_start_accuracy(data, output_path):
    """Chart 11 — percentage line, window-by-window."""
    ...

def render_window_finish_accuracy(data, output_path):
    """Chart 12 — percentage line, window-by-window."""
    ...

# Plus the 9 non-default trend graphs (01–05, 13–16) for projects with custom
# graph_screenshots lists. Same signature pattern. Tests only target the 7 defaults.

def render_summary_report(data, output_path):
    """
    Summary Report — single composite PNG with 3 vertically stacked subplots:
      top:    3 metric cards (Project Health, SPI, Days Behind)
      middle: Planned vs Actual % complete curve
      bottom: Milestones table

    Uses fig.subplots(3, 1, height_ratios=[1, 2, 2]) so the cards row is shorter
    than the curve and table. Output filename stays smartpm-summary-report.png
    so generate_email_preview_html.py and generate_email_eml.py don't change.

    data shape:
      {
        "cards": [
          {"label": "Project Health", "value": 78, "unit": "%", "delta": +3},
          {"label": "SPI",            "value": 0.92, "unit": "",  "delta": -0.02},
          {"label": "Days Behind",    "value": 14,  "unit": "d",  "delta": +2}
        ],
        "curve": {
          "planned": [{"date": "...", "pct": float}, ...],
          "actual":  [{"date": "...", "pct": float}, ...],
          "data_date": "YYYY-MM-DD"
        },
        "milestones": [
          {"name": "...", "planned": "...", "actual": "...", "variance_days": int},
          ...
        ]
      }
    """
    ...
```

### `references/charts/render.py`

The only file that knows the slug → function mapping and is the CLI entry point.

```python
import json, sys
from pathlib import Path
from . import charts

REGISTRY = {
    '06-end-date-variance':                 charts.render_end_date_variance,
    '07-schedule-compression-index-over-time': charts.render_schedule_compression_index,
    '08-velocity':                          charts.render_velocity,
    '09-spi-over-time':                     charts.render_spi_over_time,
    '10-activity-hit-rate':                 charts.render_activity_hit_rate,
    '11-window-start-accuracy':             charts.render_window_start_accuracy,
    '12-window-finish-accuracy':            charts.render_window_finish_accuracy,
    # ... 01–05, 13–16
    'smartpm-summary-report':               charts.render_summary_report,
}

def render_payload(payload_dir, output_dir):
    """Each {slug}.json in payload_dir gets rendered to {slug}.png in output_dir."""
    results = {'rendered': [], 'failed': []}
    for json_file in Path(payload_dir).glob('*.json'):
        slug = json_file.stem
        func = REGISTRY.get(slug)
        if not func:
            results['failed'].append({'slug': slug, 'reason': 'no renderer in registry'})
            continue
        try:
            data = json.loads(json_file.read_text(encoding='utf-8'))
            out = Path(output_dir) / f'{slug}.png'
            func(data, str(out))
            results['rendered'].append({'slug': slug, 'path': str(out)})
        except Exception as e:
            results['failed'].append({'slug': slug, 'reason': repr(e)})
    print(json.dumps(results, indent=2))
    return results

if __name__ == '__main__':
    render_payload(sys.argv[1], sys.argv[2])
```

Partial success is intentional — better to email with 6/7 trend graphs than to abort on one bad endpoint response.

### Phase file rewrite: `phases/screenshots.md`

The new Step 3 (replacing the Playwright capture) becomes roughly:

```
1. Read project-context.html via parse_project_context_html.
   Extract graph_screenshots list, smartpm_project_name, smartpm_url.

2. Resolve the SmartPM project_id and current scenario_id via:
     mcp__...__smartpm_list_projects → match by name
     mcp__...__smartpm_list_scenarios(project_id) → newest scenario

3. For each slug in graph_screenshots:
     - look up the MCP endpoint for that slug (table below)
     - call it, normalize the response to the canonical data shape
     - write the canonical shape to {dated_folder}/.chart-payload/{slug}.json

4. For the Summary Report (one slug, composite data):
     - call smartpm_get_scenario_project_health
     - call smartpm_get_scenario_spi
     - call smartpm_get_scenario_percent_complete_curve_v2
     - call smartpm_list_activities filtered to milestones
     - combine into one dict matching render_summary_report's data shape
     - write to .chart-payload/smartpm-summary-report.json

5. Run:
     python -m scheduling.skills.schedule-update.references.charts.render \
       {dated_folder}/.chart-payload {dated_folder}/screenshots

6. Verify each PNG in graph_screenshots + the 3 summary PNGs exist and >0 bytes.
   Report any failures from the renderer's JSON output. Do NOT auto-retry —
   surface the failure to the user.

7. Delete the .chart-payload temp dir.
```

### MCP endpoint mapping (registry inside the phase file as a table)

| Slug | MCP call | Normalization |
|------|----------|---------------|
| `06-end-date-variance` | `smartpm_list_scenario_schedules_v2(scenario_id)` | extract `data_date` + `projected_finish` per update |
| `07-schedule-compression-index-over-time` | `smartpm_get_scenario_schedule_compression_trend(scenario_id)` | direct |
| `08-velocity` | `smartpm_get_scenario_velocity(scenario_id)` | monthly bins {month, starts, finishes} |
| `09-spi-over-time` | `smartpm_get_scenario_spi_trend(scenario_id)` | direct |
| `10-activity-hit-rate` | `smartpm_get_scenario_should_start_finish_trend(scenario_id)` | extract hit-rate series |
| `11-window-start-accuracy` | same endpoint | extract start-accuracy series |
| `12-window-finish-accuracy` | same endpoint | extract finish-accuracy series |
| `smartpm-summary-report` | composite: `smartpm_get_scenario_project_health` + `smartpm_get_scenario_spi` + `smartpm_get_scenario_percent_complete_curve_v2` + `smartpm_list_activities(milestones)` | combine into the single data dict `render_summary_report` expects |

The phase file is the canonical mapping. `render.py` knows nothing about MCP — it only knows about canonical data shapes.

### Hook: `scheduling/hooks/check_html_discipline.py`

Lives in the **scheduling** plugin (not westland). Same shape as `westland/hooks/check_xer_write.py`.

- **Matcher**: `Read|Edit|Write|MultiEdit`
- **Filename match**: basename equals `project-context.html` OR matches `[0-9]{4}-[0-9]{2}-[0-9]{2}-email-preview.html`
- **Behavior**: always exit 0 (advisory, never block). Prints a contextual message to stderr that surfaces to the model as a system note.

Messages:

```
# Read:
HEADS UP — direct Read on a managed HTML file ({path}).
This file is 47–160 KB. Prefer the JSON parser:
  - project-context.html       → parse_project_context_html.load_project_context(schedules_root)
  - *-email-preview.html       → parse_email_html.parse_preview_html(path)
Reading via the parser gives you a dict and avoids token blow-up.
You can proceed if you have a reason, but most reads should go through the parser.

# Edit / Write / MultiEdit:
HEADS UP — direct write to a managed HTML file ({path}).
W1177 (2026-05-07) corrupted the embedded base64 logo via direct Write.
Prefer the matching generator:
  - project-context.html       → generate_project_context_html.generate_project_context_html(path, ctx)
  - *-email-preview.html       → generate_email_preview_html.generate_email_preview_html(...)
Not blocked, but pause: is this edit one the generator can do?
```

`hooks.json`:

```json
{
  "description": "Scheduling — advisory hook steering Claude toward the parse/generate scripts for managed HTML artifacts (project-context.html, *-email-preview.html).",
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Read|Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "python -c \"import os,re,runpy;r=os.environ['CLAUDE_PLUGIN_ROOT'];m=re.match(r'^/([a-zA-Z])/(.*)',r) if os.name=='nt' else None;r=(m.group(1).upper()+':/'+m.group(2)) if m else r;runpy.run_path(r+'/hooks/check_html_discipline.py',run_name='__main__')\""
          }
        ]
      }
    ]
  }
}
```

Hook script logic (Python, stdin = JSON tool input from Claude):

```python
import json, os, re, sys, pathlib

ALLOWED = re.compile(r'(project-context\.html|\d{4}-\d{2}-\d{2}-email-preview\.html)$', re.I)

def main():
    payload = json.loads(sys.stdin.read() or '{}')
    tool   = payload.get('tool_name', '')
    inputs = payload.get('tool_input', {})
    path   = inputs.get('file_path') or inputs.get('path') or ''
    if not path or not ALLOWED.search(os.path.basename(path)):
        sys.exit(0)
    if tool == 'Read':
        print(READ_MSG.format(path=path), file=sys.stderr)
    elif tool in ('Edit', 'Write', 'MultiEdit'):
        print(WRITE_MSG.format(path=path), file=sys.stderr)
    sys.exit(0)  # advisory — never block

if __name__ == '__main__':
    main()
```

## Testing

### Chart functions — golden images

For each render function: fixture JSON + checked-in expected PNG. Test compares pixel hashes (or, more practically, file-size-in-tolerance + image-dimension exact match) to catch silent regressions.

- `references/charts/tests/fixtures/06-end-date-variance.json` — canned MCP payload
- `references/charts/tests/fixtures/06-end-date-variance.png` — committed golden
- `test_render_end_date_variance` — render, diff vs golden

Goldens regenerated by running the test with `UPDATE_GOLDENS=1` env var; that path is intentionally annoying to use so we don't accidentally rebaseline a broken chart.

### Hook

- Tool input with non-matching path → exit 0, no stderr output
- Read on `project-context.html` → exit 0, stderr contains "parse_project_context_html"
- Write on `2026-05-19-email-preview.html` → exit 0, stderr contains "generate_email_preview_html"
- Bash tool input → exit 0 silent (we don't match the bash tool — only file ops)

## Migration

Single commit per the repo's release convention:

1. Add `references/charts/` package (style + charts + render + tests).
2. Add `scheduling/hooks/check_html_discipline.py` + `scheduling/hooks/hooks.json`. Register hooks dir in `scheduling/.claude-plugin/plugin.json` if needed (check whether the plugin loader picks up hooks automatically from `hooks/` — it does for westland because of its hook config, mirror that).
3. Delete `references/smartpm/capture-smartpm.js`, `references/smartpm/env-loader.js`, `references/smartpm/smartpm-client.js`, `references/tests/smartpm.spec.js`, `references/tests/playwright.config.js`, `references/tests/full-page-debug.spec.js`, `take-screenshots.bat`. The Playwright dependency in `references/package.json` stays for now because `html-to-pdf.js` still uses it for the changes-report PDF.
4. Rewrite `phases/screenshots.md` per the orchestrator above.
5. Update `phases/email.md` and `phases/report.md` references: the "missing screenshots → run screenshots phase" wording stays the same; only the underlying mechanism changed.
6. Bump `scheduling/.claude-plugin/plugin.json` from `5.2.0` to `5.3.0` (new feature, not just a fix).
7. Bump matching entry in `.claude-plugin/marketplace.json` to `5.3.0`.
8. `python build.py scheduling` and distribute.

## Risks

- **MCP returns differ from what we modeled.** Mitigation: each extractor in the phase file's mapping table is the single point of normalization; if SmartPM's response shape differs, fix one line in the phase file's mapping description, plus one extractor in the canonicalization step. Chart functions don't change.
- **matplotlib fonts on a colleague's machine.** Calibri may be missing on non-Windows; matplotlib falls back to DejaVu silently. Visual delta is acceptable.
- **Hook misfires on unrelated HTML.** Filename regex is strict (exact basename match or dated-preview pattern). Other HTML files (e.g., the changes-report HTML) won't match.
- **Charts look "off" compared to SmartPM's.** The owners are used to SmartPM's exact look. Style.py is tunable; iterate after the first weekly email cycles back with feedback. Goldens make it safe to tune.

## Open questions to track post-merge (not blocking this design)

- If, after using this for a few weeks, the team finds the milestones table sub-figure too cramped, the Summary Report can be split into 3 separate PNGs in a follow-up branch. That follow-up would touch `generate_email_preview_html.py`, `generate_email_eml.py`, `parse_email_html.py`, and carry-forward — deferred until the visual problem is confirmed real.
- Wire matplotlib's font registration to install Calibri on Linux runners if we ever start running tests in CI. Out of scope now.
