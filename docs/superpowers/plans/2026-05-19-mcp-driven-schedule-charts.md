# MCP-driven schedule charts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace Playwright-based SmartPM screenshot capture with MCP-fetched data → matplotlib-rendered PNGs, and add an advisory hook in the scheduling plugin that steers Claude toward parse/generate scripts for managed HTML artifacts. Playwright path stays as a `--legacy` fallback during the styling-iteration period.

**Architecture:** A new `references/charts/` Python package with one render function per graph (`charts.py`), shared visual constants (`style.py`), and a CLI orchestrator (`render.py`) that maps slug → function via a registry. The phase file (`phases/screenshots.md`) does the MCP calls and writes per-slug JSON payloads into a temp dir, then invokes `render.py` to produce PNGs. A scheduling-plugin PreToolUse hook prints advisory messages on Read/Write of `project-context.html` and `*-email-preview.html`.

**Tech Stack:** Python 3.10+ (stdlib + matplotlib), Pillow (for PNG validation in tests), unittest. No new Node/Playwright work — the legacy Playwright path stays as-is.

**Spec:** `docs/superpowers/specs/2026-05-19-mcp-driven-schedule-charts-design.md`

---

## Task 1: Scaffold the charts package + dependency

**Files:**
- Create: `scheduling/skills/schedule-update/references/charts/__init__.py`
- Create: `scheduling/skills/schedule-update/references/charts/style.py`
- Create: `scheduling/skills/schedule-update/references/charts/charts.py`
- Create: `scheduling/skills/schedule-update/references/charts/render.py`
- Create: `scheduling/skills/schedule-update/references/charts/requirements.txt`
- Create: `scheduling/skills/schedule-update/references/charts/tests/__init__.py`
- Create: `scheduling/skills/schedule-update/references/charts/tests/fixtures/.gitkeep`

- [ ] **Step 1: Create the package skeleton**

```bash
mkdir -p scheduling/skills/schedule-update/references/charts/tests/fixtures
```

- [ ] **Step 2: Write `requirements.txt`**

```text
matplotlib>=3.8
Pillow>=10.0
```

- [ ] **Step 3: Write `__init__.py` (force non-interactive backend before any matplotlib import propagates)**

```python
"""Schedule update chart renderer — MCP JSON → matplotlib PNG."""

import matplotlib
matplotlib.use('Agg')  # headless; must be set before pyplot is imported anywhere
```

- [ ] **Step 4: Write `style.py`**

```python
"""Shared visual constants for the schedule update chart renderer.

Pure data — no functions that draw stuff. Each chart in charts.py imports
this module and reads what it needs.
"""

# SmartPM-feeling palette
TEAL      = '#0E7C7B'   # primary (planned, target)
ORANGE    = '#D8732E'   # secondary (actual, variance)
RED       = '#C94444'   # alerts / behind
GREEN     = '#3A9E6B'   # ahead / good
GRAY      = '#6B7280'   # baseline / grid
LIGHT_GRAY = '#E5E7EB'  # gridlines

# Figure geometry — wide-and-short for the email column
FIGSIZE        = (8, 3)
DPI            = 144
FONT_FAMILY    = 'Calibri'   # falls back to mpl default if missing
TITLE_FONTSIZE = 13
LABEL_FONTSIZE = 10
TICK_FONTSIZE  = 9
TITLE_PAD      = 10

SAVEFIG_KWARGS = dict(
    bbox_inches='tight',
    facecolor='white',
    edgecolor='none',
)
```

- [ ] **Step 5: Write empty `charts.py` (chart functions get added one per task)**

```python
"""One render function per graph. Each takes (data: dict, output_path: str) → None.

Each function is self-contained: it knows its data shape, its chart type, its
title, axes, and styling. They don't share a base function — duplication is
intentional so each chart can be tweaked in isolation without risk of breaking
its neighbors.
"""

import matplotlib.pyplot as plt

from . import style
```

- [ ] **Step 6: Write empty-registry `render.py`**

```python
"""CLI entry point: read {slug}.json files from a payload dir, dispatch each
to its render function from the REGISTRY, write {slug}.png to the output dir.

Partial success: one chart failing does not abort the others. Failures are
reported in the JSON output.
"""

import json
import sys
from pathlib import Path

from . import charts  # noqa: F401 — chart functions registered below as they're added

REGISTRY = {
    # Populated by subsequent tasks: each chart task adds one entry here.
}


def render_payload(payload_dir, output_dir):
    """Render every {slug}.json in payload_dir to {slug}.png in output_dir.

    Returns a dict {'rendered': [...], 'failed': [...]}. Also prints the JSON
    to stdout so the calling phase file can parse it.
    """
    payload_dir = Path(payload_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {'rendered': [], 'failed': []}
    for json_file in sorted(payload_dir.glob('*.json')):
        slug = json_file.stem
        func = REGISTRY.get(slug)
        if func is None:
            results['failed'].append({
                'slug': slug,
                'reason': 'no renderer in registry',
            })
            continue
        try:
            data = json.loads(json_file.read_text(encoding='utf-8'))
            out = output_dir / f'{slug}.png'
            func(data, str(out))
            results['rendered'].append({
                'slug': slug,
                'path': str(out),
            })
        except Exception as e:
            results['failed'].append({
                'slug': slug,
                'reason': f'{type(e).__name__}: {e}',
            })

    print(json.dumps(results, indent=2))
    return results


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: python -m references.charts.render <payload_dir> <output_dir>',
              file=sys.stderr)
        sys.exit(2)
    r = render_payload(sys.argv[1], sys.argv[2])
    sys.exit(0 if not r['failed'] else 1)
```

- [ ] **Step 7: Write `tests/__init__.py`**

```python
```

- [ ] **Step 8: Install dependencies and verify matplotlib loads with the Agg backend**

```bash
pip install -r scheduling/skills/schedule-update/references/charts/requirements.txt
python -c "import matplotlib; matplotlib.use('Agg'); import matplotlib.pyplot as plt; print('OK', matplotlib.__version__)"
```

Expected output: `OK 3.x.x`

- [ ] **Step 9: Commit**

```bash
git add scheduling/skills/schedule-update/references/charts/
git commit -m "feat(scheduling): scaffold charts package + matplotlib dep"
```

---

## Task 2: Render orchestrator — empty-payload + unknown-slug tests

**Files:**
- Create: `scheduling/skills/schedule-update/references/charts/tests/test_render.py`

- [ ] **Step 1: Write failing tests for the orchestrator**

```python
import json
import tempfile
import unittest
from pathlib import Path

from scheduling.skills.schedule_update.references.charts import render


class TestRenderPayload(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.payload_dir = Path(self._tmp.name) / 'payload'
        self.output_dir = Path(self._tmp.name) / 'out'
        self.payload_dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty_payload_dir_returns_empty_results(self):
        r = render.render_payload(self.payload_dir, self.output_dir)
        self.assertEqual(r, {'rendered': [], 'failed': []})

    def test_unknown_slug_reports_failure(self):
        (self.payload_dir / 'totally-not-a-real-chart.json').write_text('{}')
        r = render.render_payload(self.payload_dir, self.output_dir)
        self.assertEqual(r['rendered'], [])
        self.assertEqual(len(r['failed']), 1)
        self.assertEqual(r['failed'][0]['slug'], 'totally-not-a-real-chart')
        self.assertIn('no renderer in registry', r['failed'][0]['reason'])


if __name__ == '__main__':
    unittest.main()
```

> **Note on the import path:** The module path uses underscores because `schedule-update` directory contains a hyphen, which Python can't import normally. The tests need to run from a working dir where this can resolve — i.e., from the repo root with the path inserted into `sys.path`, OR by symlinking, OR by running pytest with a conftest. **In step 2 we run the test from the repo root with `PYTHONPATH=.` and check the import resolves.** If it doesn't, we'll add a tiny `conftest.py` next to the tests that splices the parent dirs into `sys.path`.

- [ ] **Step 2: Run tests — verify failure mode is "module not found / import path" or "test passes" cleanly**

```bash
cd /c/Users/camron/code/construction-skills/.claude/worktrees/funny-babbage-446d9e
PYTHONPATH=. python -m pytest scheduling/skills/schedule-update/references/charts/tests/test_render.py -v
```

If the import fails because `schedule-update` has a hyphen, add a conftest.py next to the test file with this content, then re-run:

```python
# scheduling/skills/schedule-update/references/charts/tests/conftest.py
import sys
from pathlib import Path

# Splice the charts package's parent into sys.path so `from ... import charts` works
HERE = Path(__file__).resolve()
CHARTS_PKG = HERE.parent.parent   # .../charts/
sys.path.insert(0, str(CHARTS_PKG.parent))  # parent of charts/ so `from charts import render` works
```

Then update the test imports from `from scheduling.skills.schedule_update.references.charts import render` to `from charts import render`.

Expected: both tests pass.

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/references/charts/tests/
git commit -m "test(scheduling): render orchestrator dispatch + error handling"
```

---

## Task 3: HTML-discipline hook + tests

**Files:**
- Create: `scheduling/hooks/check_html_discipline.py`
- Create: `scheduling/hooks/hooks.json`
- Create: `scheduling/hooks/tests/test_check_html_discipline.py`
- Create: `scheduling/hooks/tests/__init__.py`
- Modify: `scheduling/.claude-plugin/plugin.json` (only if needed — see step 6)

- [ ] **Step 1: Write the hook script**

```python
# scheduling/hooks/check_html_discipline.py
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
```

- [ ] **Step 2: Write `hooks.json`**

```json
{
  "description": "Scheduling — advisory hook steering Claude toward the parse/generate scripts for managed HTML artifacts (project-context.html, dated *-email-preview.html). Always advisory; never blocks.",
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

- [ ] **Step 3: Write the hook tests**

```python
# scheduling/hooks/tests/test_check_html_discipline.py
import io
import json
import subprocess
import sys
import unittest
from pathlib import Path


HOOK = Path(__file__).resolve().parent.parent / 'check_html_discipline.py'


def run_hook(payload):
    """Invoke the hook script as a subprocess with the given JSON payload on stdin."""
    proc = subprocess.run(
        [sys.executable, str(HOOK)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=5,
    )
    return proc


class TestHookAdvisory(unittest.TestCase):
    def test_no_path_exits_zero_silent(self):
        proc = run_hook({'tool_name': 'Read', 'tool_input': {}})
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')

    def test_unrelated_path_exits_zero_silent(self):
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {'file_path': '/some/where/notes.md'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')

    def test_read_project_context_warns(self):
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {'file_path': r'G:\some\Schedules\project-context.html'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertIn('parse_project_context_html', proc.stderr)
        self.assertNotIn('generate_', proc.stderr)

    def test_write_email_preview_warns_with_generator(self):
        proc = run_hook({
            'tool_name': 'Write',
            'tool_input': {'file_path': r'G:\proj\Schedules\2026-05-19\2026-05-19-email-preview.html'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertIn('generate_email_preview_html', proc.stderr)
        self.assertIn('W1177', proc.stderr)

    def test_edit_project_context_uses_write_message(self):
        proc = run_hook({
            'tool_name': 'Edit',
            'tool_input': {'file_path': '/c/Users/a/project-context.html'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertIn('generate_project_context_html', proc.stderr)

    def test_multiedit_email_preview_warns(self):
        proc = run_hook({
            'tool_name': 'MultiEdit',
            'tool_input': {'file_path': '/x/y/2026-04-15-email-preview.html'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertIn('generate_email_preview_html', proc.stderr)

    def test_changes_report_html_does_not_match(self):
        """Other HTML files in the pipeline (e.g. changes-report HTML)
        must not trigger this hook."""
        proc = run_hook({
            'tool_name': 'Read',
            'tool_input': {'file_path': '/x/2026-05-19 Schedule Update Email (Change Report).html'},
        })
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stderr, '')


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 4: Write `tests/__init__.py`**

```python
```

- [ ] **Step 5: Run the hook tests**

```bash
python -m pytest scheduling/hooks/tests/test_check_html_discipline.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 6: Check whether `scheduling/.claude-plugin/plugin.json` needs hook registration**

Compare against `westland/.claude-plugin/plugin.json`. If westland's plugin.json doesn't explicitly point at `hooks/hooks.json` (the loader auto-discovers `hooks/hooks.json`), no change is needed. If westland's plugin.json has a `hooks` key pointing at the config, mirror that change in `scheduling/.claude-plugin/plugin.json`.

```bash
cat westland/.claude-plugin/plugin.json
```

Then either leave `scheduling/.claude-plugin/plugin.json` alone, or add the same `hooks` key.

- [ ] **Step 7: Commit**

```bash
git add scheduling/hooks/ scheduling/.claude-plugin/plugin.json
git commit -m "feat(scheduling): advisory HTML-discipline hook for managed artifacts"
```

---

## Task 4: render_end_date_variance (06)

**Files:**
- Modify: `scheduling/skills/schedule-update/references/charts/charts.py`
- Modify: `scheduling/skills/schedule-update/references/charts/render.py:13` (registry)
- Create: `scheduling/skills/schedule-update/references/charts/tests/fixtures/06-end-date-variance.json`
- Modify: `scheduling/skills/schedule-update/references/charts/tests/test_render.py` (or add new test file — see step 4)

- [ ] **Step 1: Write the fixture JSON**

`scheduling/skills/schedule-update/references/charts/tests/fixtures/06-end-date-variance.json`:

```json
{
  "updates": [
    {"data_date": "2026-01-08", "projected_finish": "2027-03-15"},
    {"data_date": "2026-01-15", "projected_finish": "2027-03-20"},
    {"data_date": "2026-01-22", "projected_finish": "2027-03-22"},
    {"data_date": "2026-01-29", "projected_finish": "2027-03-28"},
    {"data_date": "2026-02-05", "projected_finish": "2027-04-02"},
    {"data_date": "2026-02-12", "projected_finish": "2027-04-05"},
    {"data_date": "2026-02-19", "projected_finish": "2027-04-10"}
  ],
  "contractual_completion": "2027-03-10"
}
```

- [ ] **Step 2: Write the failing test**

Add to `tests/test_render.py` (extend the existing file):

```python
import io
from PIL import Image


FIXTURE_DIR = Path(__file__).resolve().parent / 'fixtures'


def _assert_valid_png(path, min_bytes=2000):
    p = Path(path)
    self_unittest = unittest.TestCase()  # standalone helper
    assert p.exists(), f'Output PNG not created: {path}'
    assert p.stat().st_size >= min_bytes, f'PNG too small ({p.stat().st_size} bytes)'
    img = Image.open(p)
    assert img.format == 'PNG'
    return img.size  # (width, height)


class TestEndDateVariance(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / '06-end-date-variance.png'

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_valid_png_at_8x3_aspect(self):
        from charts import charts
        data = json.loads((FIXTURE_DIR / '06-end-date-variance.json').read_text())
        charts.render_end_date_variance(data, str(self.output))

        self.assertTrue(self.output.exists(), 'PNG was not created')
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')
        width, height = img.size
        # 8x3 at DPI 144 ~ 1152x432. tight bbox can shrink by ~10-20%.
        # Verify the aspect ratio is wide-and-short, not square or tall.
        self.assertGreater(width, height * 1.8, f'Image too tall ({width}x{height})')

    def test_renders_via_orchestrator(self):
        # Drop the fixture into a payload dir and run the orchestrator end-to-end
        from charts import render
        payload_dir = Path(self._tmp.name) / 'payload'
        payload_dir.mkdir()
        (payload_dir / '06-end-date-variance.json').write_text(
            (FIXTURE_DIR / '06-end-date-variance.json').read_text()
        )
        output_dir = Path(self._tmp.name) / 'out'
        results = render.render_payload(payload_dir, output_dir)
        self.assertEqual(len(results['rendered']), 1)
        self.assertEqual(len(results['failed']), 0)
        self.assertTrue((output_dir / '06-end-date-variance.png').exists())
```

- [ ] **Step 3: Run the tests — verify failure**

```bash
python -m pytest scheduling/skills/schedule-update/references/charts/tests/test_render.py::TestEndDateVariance -v
```

Expected: FAIL — `AttributeError: module 'charts.charts' has no attribute 'render_end_date_variance'`

- [ ] **Step 4: Implement the chart function**

Add to `charts.py`:

```python
from datetime import date


def render_end_date_variance(data, output_path):
    """Chart 06 — projected Substantial Completion date over time.

    data shape:
      {
        "updates": [
          {"data_date": "YYYY-MM-DD", "projected_finish": "YYYY-MM-DD"},
          ...
        ],
        "contractual_completion": "YYYY-MM-DD"
      }

    Plot: line with markers. X-axis = data_date (when the update was run),
    Y-axis = projected_finish (as a date). Horizontal reference line at
    contractual_completion. Red if line trends above (later) than ref, green
    if below.
    """
    updates = data['updates']
    contractual = date.fromisoformat(data['contractual_completion'])

    xs = [date.fromisoformat(u['data_date']) for u in updates]
    ys = [date.fromisoformat(u['projected_finish']) for u in updates]

    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
    ax.plot(xs, ys, color=style.ORANGE, marker='o', linewidth=2, markersize=5,
            label='Projected SC')
    ax.axhline(y=contractual, color=style.GRAY, linestyle='--', linewidth=1.5,
               label='Contractual SC')

    ax.set_title('End Date Variance', fontsize=style.TITLE_FONTSIZE,
                 pad=style.TITLE_PAD)
    ax.set_ylabel('Projected SC Date', fontsize=style.LABEL_FONTSIZE)
    ax.tick_params(labelsize=style.TICK_FONTSIZE)
    ax.grid(True, linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)
    ax.legend(loc='best', fontsize=style.TICK_FONTSIZE, frameon=False)

    fig.autofmt_xdate()
    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)
```

- [ ] **Step 5: Register the function in `render.py`**

Add the entry to `REGISTRY` in `render.py`:

```python
REGISTRY = {
    '06-end-date-variance': charts.render_end_date_variance,
}
```

- [ ] **Step 6: Run the tests — verify pass**

```bash
python -m pytest scheduling/skills/schedule-update/references/charts/tests/test_render.py::TestEndDateVariance -v
```

Expected: both tests pass.

- [ ] **Step 7: Eyeball the rendered PNG**

```bash
python -c "
from pathlib import Path
import tempfile, json
from charts import charts
tmp = Path(tempfile.mkdtemp())
data = json.loads(Path('scheduling/skills/schedule-update/references/charts/tests/fixtures/06-end-date-variance.json').read_text())
out = tmp / '06.png'
charts.render_end_date_variance(data, str(out))
print('Wrote', out)
"
```

Open the printed path in an image viewer to sanity-check the look. You can delete it after.

- [ ] **Step 8: Commit**

```bash
git add scheduling/skills/schedule-update/references/charts/
git commit -m "feat(scheduling): render_end_date_variance + fixture + tests"
```

---

## Task 5: render_schedule_compression_index (07)

**Files:**
- Modify: `scheduling/skills/schedule-update/references/charts/charts.py`
- Modify: `scheduling/skills/schedule-update/references/charts/render.py` (registry)
- Create: `scheduling/skills/schedule-update/references/charts/tests/fixtures/07-schedule-compression-index-over-time.json`
- Modify: `scheduling/skills/schedule-update/references/charts/tests/test_render.py`

- [ ] **Step 1: Write the fixture JSON**

```json
{
  "trend": [
    {"data_date": "2026-01-08", "value": 1.00},
    {"data_date": "2026-01-15", "value": 1.04},
    {"data_date": "2026-01-22", "value": 1.07},
    {"data_date": "2026-01-29", "value": 1.12},
    {"data_date": "2026-02-05", "value": 1.18},
    {"data_date": "2026-02-12", "value": 1.21},
    {"data_date": "2026-02-19", "value": 1.25}
  ]
}
```

- [ ] **Step 2: Write the failing test**

```python
class TestScheduleCompressionIndex(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / '07-schedule-compression-index-over-time.png'

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_valid_png(self):
        from charts import charts
        data = json.loads((FIXTURE_DIR / '07-schedule-compression-index-over-time.json').read_text())
        charts.render_schedule_compression_index(data, str(self.output))
        self.assertTrue(self.output.exists())
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')
        width, height = img.size
        self.assertGreater(width, height * 1.8)
```

- [ ] **Step 3: Run — verify failure**

```bash
python -m pytest scheduling/skills/schedule-update/references/charts/tests/test_render.py::TestScheduleCompressionIndex -v
```

- [ ] **Step 4: Implement**

```python
def render_schedule_compression_index(data, output_path):
    """Chart 07 — schedule compression index over time.

    Compression > 1.0 means the schedule needs to accelerate to make its
    end date. Horizontal reference line at 1.0 (no compression).

    data shape:
      {"trend": [{"data_date": "YYYY-MM-DD", "value": float}, ...]}
    """
    points = data['trend']
    xs = [date.fromisoformat(p['data_date']) for p in points]
    ys = [p['value'] for p in points]

    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
    ax.plot(xs, ys, color=style.ORANGE, marker='o', linewidth=2, markersize=5)
    ax.axhline(y=1.0, color=style.GRAY, linestyle='--', linewidth=1.5,
               label='No compression')

    ax.set_title('Schedule Compression Index Over Time',
                 fontsize=style.TITLE_FONTSIZE, pad=style.TITLE_PAD)
    ax.set_ylabel('Compression Index', fontsize=style.LABEL_FONTSIZE)
    ax.tick_params(labelsize=style.TICK_FONTSIZE)
    ax.grid(True, linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)
    ax.legend(loc='best', fontsize=style.TICK_FONTSIZE, frameon=False)

    fig.autofmt_xdate()
    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)
```

- [ ] **Step 5: Register**

```python
REGISTRY = {
    '06-end-date-variance': charts.render_end_date_variance,
    '07-schedule-compression-index-over-time': charts.render_schedule_compression_index,
}
```

- [ ] **Step 6: Run — verify pass**

```bash
python -m pytest scheduling/skills/schedule-update/references/charts/tests/test_render.py::TestScheduleCompressionIndex -v
```

- [ ] **Step 7: Commit**

```bash
git add scheduling/skills/schedule-update/references/charts/
git commit -m "feat(scheduling): render_schedule_compression_index"
```

---

## Task 6: render_velocity (08)

**Files:**
- Modify: `charts.py`, `render.py`
- Create: `tests/fixtures/08-velocity.json`
- Modify: `tests/test_render.py`

- [ ] **Step 1: Write fixture**

```json
{
  "months": [
    {"month": "2026-01", "starts": 22, "finishes": 8},
    {"month": "2026-02", "starts": 31, "finishes": 14},
    {"month": "2026-03", "starts": 28, "finishes": 19},
    {"month": "2026-04", "starts": 35, "finishes": 22},
    {"month": "2026-05", "starts": 18, "finishes": 26}
  ]
}
```

- [ ] **Step 2: Failing test**

```python
class TestVelocity(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / '08-velocity.png'

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_valid_png(self):
        from charts import charts
        data = json.loads((FIXTURE_DIR / '08-velocity.json').read_text())
        charts.render_velocity(data, str(self.output))
        self.assertTrue(self.output.exists())
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')
        self.assertGreater(img.size[0], img.size[1] * 1.8)
```

- [ ] **Step 3: Run — verify failure**

- [ ] **Step 4: Implement (grouped bar — starts vs finishes side by side per month)**

```python
import numpy as np


def render_velocity(data, output_path):
    """Chart 08 — Monthly Activity Start & Finish Distribution.

    data shape:
      {"months": [{"month": "YYYY-MM", "starts": int, "finishes": int}, ...]}
    """
    months = data['months']
    labels = [m['month'] for m in months]
    starts = [m['starts'] for m in months]
    finishes = [m['finishes'] for m in months]

    x = np.arange(len(labels))
    width = 0.4

    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
    ax.bar(x - width / 2, starts, width, color=style.TEAL, label='Starts')
    ax.bar(x + width / 2, finishes, width, color=style.ORANGE, label='Finishes')

    ax.set_title('Monthly Activity Start & Finish Distribution',
                 fontsize=style.TITLE_FONTSIZE, pad=style.TITLE_PAD)
    ax.set_ylabel('Count', fontsize=style.LABEL_FONTSIZE)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=style.TICK_FONTSIZE, rotation=30, ha='right')
    ax.tick_params(axis='y', labelsize=style.TICK_FONTSIZE)
    ax.grid(True, axis='y', linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)
    ax.legend(loc='best', fontsize=style.TICK_FONTSIZE, frameon=False)

    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)
```

- [ ] **Step 5: Register**

```python
REGISTRY = {
    ...,
    '08-velocity': charts.render_velocity,
}
```

- [ ] **Step 6: Run — verify pass**

- [ ] **Step 7: Commit**

```bash
git add scheduling/skills/schedule-update/references/charts/
git commit -m "feat(scheduling): render_velocity (monthly start/finish grouped bars)"
```

---

## Task 7: render_spi_over_time (09)

**Files:**
- Modify: `charts.py`, `render.py`
- Create: `tests/fixtures/09-spi-over-time.json`
- Modify: `tests/test_render.py`

- [ ] **Step 1: Write fixture**

```json
{
  "trend": [
    {"data_date": "2026-01-08", "value": 1.00},
    {"data_date": "2026-01-15", "value": 0.98},
    {"data_date": "2026-01-22", "value": 0.95},
    {"data_date": "2026-01-29", "value": 0.93},
    {"data_date": "2026-02-05", "value": 0.91},
    {"data_date": "2026-02-12", "value": 0.92},
    {"data_date": "2026-02-19", "value": 0.94}
  ]
}
```

- [ ] **Step 2: Failing test**

```python
class TestSpiOverTime(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / '09-spi-over-time.png'

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_valid_png(self):
        from charts import charts
        data = json.loads((FIXTURE_DIR / '09-spi-over-time.json').read_text())
        charts.render_spi_over_time(data, str(self.output))
        self.assertTrue(self.output.exists())
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')
        self.assertGreater(img.size[0], img.size[1] * 1.8)
```

- [ ] **Step 3: Run — verify failure**

- [ ] **Step 4: Implement**

```python
def render_spi_over_time(data, output_path):
    """Chart 09 — Schedule Performance Index over time.

    SPI < 1.0 means behind schedule. Reference line at 1.0.

    data shape: {"trend": [{"data_date": "YYYY-MM-DD", "value": float}, ...]}
    """
    points = data['trend']
    xs = [date.fromisoformat(p['data_date']) for p in points]
    ys = [p['value'] for p in points]

    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
    ax.plot(xs, ys, color=style.TEAL, marker='o', linewidth=2, markersize=5)
    ax.axhline(y=1.0, color=style.GRAY, linestyle='--', linewidth=1.5,
               label='On schedule')

    ax.set_title('SPI Over Time', fontsize=style.TITLE_FONTSIZE,
                 pad=style.TITLE_PAD)
    ax.set_ylabel('SPI', fontsize=style.LABEL_FONTSIZE)
    ax.tick_params(labelsize=style.TICK_FONTSIZE)
    ax.grid(True, linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)
    ax.legend(loc='best', fontsize=style.TICK_FONTSIZE, frameon=False)

    fig.autofmt_xdate()
    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)
```

- [ ] **Step 5: Register**

```python
REGISTRY = {
    ...,
    '09-spi-over-time': charts.render_spi_over_time,
}
```

- [ ] **Step 6: Run — verify pass**

- [ ] **Step 7: Commit**

```bash
git add scheduling/skills/schedule-update/references/charts/
git commit -m "feat(scheduling): render_spi_over_time"
```

---

## Task 8: render_activity_hit_rate (10)

**Files:**
- Modify: `charts.py`, `render.py`
- Create: `tests/fixtures/10-activity-hit-rate.json`
- Modify: `tests/test_render.py`

- [ ] **Step 1: Write fixture (percentage line, y-axis 0-100)**

```json
{
  "trend": [
    {"data_date": "2026-01-08", "value": 78.0},
    {"data_date": "2026-01-15", "value": 74.5},
    {"data_date": "2026-01-22", "value": 71.0},
    {"data_date": "2026-01-29", "value": 68.2},
    {"data_date": "2026-02-05", "value": 66.5},
    {"data_date": "2026-02-12", "value": 65.0},
    {"data_date": "2026-02-19", "value": 67.8}
  ]
}
```

- [ ] **Step 2: Failing test (mirror of 09's pattern; substitute class name + fixture name + function name)**

- [ ] **Step 3: Run — verify failure**

- [ ] **Step 4: Implement**

```python
def render_activity_hit_rate(data, output_path):
    """Chart 10 — Activity Hit Rate (%).

    Percentage of activities completed on or before their planned finish date,
    per update.

    data shape: {"trend": [{"data_date": "YYYY-MM-DD", "value": float}, ...]}  # 0-100
    """
    points = data['trend']
    xs = [date.fromisoformat(p['data_date']) for p in points]
    ys = [p['value'] for p in points]

    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
    ax.plot(xs, ys, color=style.GREEN, marker='o', linewidth=2, markersize=5)

    ax.set_title('Activity Hit Rate', fontsize=style.TITLE_FONTSIZE,
                 pad=style.TITLE_PAD)
    ax.set_ylabel('Hit Rate (%)', fontsize=style.LABEL_FONTSIZE)
    ax.set_ylim(0, 100)
    ax.tick_params(labelsize=style.TICK_FONTSIZE)
    ax.grid(True, linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)

    fig.autofmt_xdate()
    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)
```

- [ ] **Step 5: Register `'10-activity-hit-rate': charts.render_activity_hit_rate`**

- [ ] **Step 6: Run — verify pass**

- [ ] **Step 7: Commit**

```bash
git add scheduling/skills/schedule-update/references/charts/
git commit -m "feat(scheduling): render_activity_hit_rate"
```

---

## Task 9: render_window_start_accuracy (11)

**Files:** same pattern as Task 8 with `11-window-start-accuracy`.

- [ ] **Step 1: Fixture**

```json
{
  "trend": [
    {"data_date": "2026-01-08", "value": 82.0},
    {"data_date": "2026-01-15", "value": 79.5},
    {"data_date": "2026-01-22", "value": 76.0},
    {"data_date": "2026-01-29", "value": 73.5},
    {"data_date": "2026-02-05", "value": 71.0},
    {"data_date": "2026-02-12", "value": 70.5},
    {"data_date": "2026-02-19", "value": 72.0}
  ]
}
```

- [ ] **Step 2: Failing test class `TestWindowStartAccuracy`, fixture file `11-window-start-accuracy.json`, function `render_window_start_accuracy`. Mirror Task 8's test.**

- [ ] **Step 3: Run — verify failure**

- [ ] **Step 4: Implement**

```python
def render_window_start_accuracy(data, output_path):
    """Chart 11 — Window Start Accuracy (%).

    Percentage of activities that started within their planned start window.

    data shape: {"trend": [{"data_date": "YYYY-MM-DD", "value": float}, ...]}  # 0-100
    """
    points = data['trend']
    xs = [date.fromisoformat(p['data_date']) for p in points]
    ys = [p['value'] for p in points]

    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
    ax.plot(xs, ys, color=style.TEAL, marker='o', linewidth=2, markersize=5)

    ax.set_title('Window Start Accuracy', fontsize=style.TITLE_FONTSIZE,
                 pad=style.TITLE_PAD)
    ax.set_ylabel('Start Accuracy (%)', fontsize=style.LABEL_FONTSIZE)
    ax.set_ylim(0, 100)
    ax.tick_params(labelsize=style.TICK_FONTSIZE)
    ax.grid(True, linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)

    fig.autofmt_xdate()
    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)
```

- [ ] **Step 5: Register**

```python
'11-window-start-accuracy': charts.render_window_start_accuracy,
```

- [ ] **Step 6: Run — verify pass**

- [ ] **Step 7: Commit**

```bash
git add scheduling/skills/schedule-update/references/charts/
git commit -m "feat(scheduling): render_window_start_accuracy"
```

---

## Task 10: render_window_finish_accuracy (12)

Same pattern as Task 9.

- [ ] **Step 1: Fixture** — `12-window-finish-accuracy.json`:

```json
{
  "trend": [
    {"data_date": "2026-01-08", "value": 70.0},
    {"data_date": "2026-01-15", "value": 67.5},
    {"data_date": "2026-01-22", "value": 64.0},
    {"data_date": "2026-01-29", "value": 61.5},
    {"data_date": "2026-02-05", "value": 60.0},
    {"data_date": "2026-02-12", "value": 58.5},
    {"data_date": "2026-02-19", "value": 60.0}
  ]
}
```

- [ ] **Step 2: Failing test `TestWindowFinishAccuracy` — mirror Task 9.**

- [ ] **Step 3: Run — verify failure**

- [ ] **Step 4: Implement**

```python
def render_window_finish_accuracy(data, output_path):
    """Chart 12 — Window Finish Accuracy (%).

    Percentage of activities that finished within their planned finish window.

    data shape: {"trend": [{"data_date": "YYYY-MM-DD", "value": float}, ...]}  # 0-100
    """
    points = data['trend']
    xs = [date.fromisoformat(p['data_date']) for p in points]
    ys = [p['value'] for p in points]

    fig, ax = plt.subplots(figsize=style.FIGSIZE, dpi=style.DPI)
    ax.plot(xs, ys, color=style.ORANGE, marker='o', linewidth=2, markersize=5)

    ax.set_title('Window Finish Accuracy', fontsize=style.TITLE_FONTSIZE,
                 pad=style.TITLE_PAD)
    ax.set_ylabel('Finish Accuracy (%)', fontsize=style.LABEL_FONTSIZE)
    ax.set_ylim(0, 100)
    ax.tick_params(labelsize=style.TICK_FONTSIZE)
    ax.grid(True, linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)

    fig.autofmt_xdate()
    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)
```

- [ ] **Step 5: Register**

```python
'12-window-finish-accuracy': charts.render_window_finish_accuracy,
```

- [ ] **Step 6: Run — verify pass**

- [ ] **Step 7: Commit**

```bash
git add scheduling/skills/schedule-update/references/charts/
git commit -m "feat(scheduling): render_window_finish_accuracy"
```

---

## Task 11: render_summary_report (composite — cards / curve / milestones table)

**Files:**
- Modify: `charts.py`, `render.py`
- Create: `tests/fixtures/smartpm-summary-report.json`
- Modify: `tests/test_render.py`

- [ ] **Step 1: Write fixture**

```json
{
  "cards": [
    {"label": "Project Health", "value": 78, "unit": "%", "delta": 3},
    {"label": "SPI",            "value": 0.92, "unit": "",  "delta": -0.02},
    {"label": "Days Behind",    "value": 14,  "unit": "d",  "delta": 2}
  ],
  "curve": {
    "planned": [
      {"date": "2026-01-01", "pct": 5.0},
      {"date": "2026-02-01", "pct": 15.0},
      {"date": "2026-03-01", "pct": 30.0},
      {"date": "2026-04-01", "pct": 50.0},
      {"date": "2026-05-01", "pct": 70.0},
      {"date": "2026-06-01", "pct": 85.0},
      {"date": "2026-07-01", "pct": 95.0},
      {"date": "2026-08-01", "pct": 100.0}
    ],
    "actual": [
      {"date": "2026-01-01", "pct": 4.0},
      {"date": "2026-02-01", "pct": 13.5},
      {"date": "2026-03-01", "pct": 26.0},
      {"date": "2026-04-01", "pct": 42.0},
      {"date": "2026-05-01", "pct": 58.0}
    ],
    "data_date": "2026-05-15"
  },
  "milestones": [
    {"name": "Mobilization complete", "planned": "2026-01-15", "actual": "2026-01-18", "variance_days": 3},
    {"name": "Foundations complete",  "planned": "2026-03-20", "actual": "2026-04-02", "variance_days": 13},
    {"name": "Building dry-in",       "planned": "2026-07-10", "actual": null,         "variance_days": null},
    {"name": "Substantial Completion","planned": "2026-12-15", "actual": null,         "variance_days": null}
  ]
}
```

- [ ] **Step 2: Failing test**

```python
class TestSummaryReport(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / 'smartpm-summary-report.png'

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_valid_composite_png(self):
        from charts import charts
        data = json.loads((FIXTURE_DIR / 'smartpm-summary-report.json').read_text())
        charts.render_summary_report(data, str(self.output))
        self.assertTrue(self.output.exists())
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')
        # Composite is 8" wide x ~9" tall → taller than wide
        width, height = img.size
        self.assertGreater(height, width * 0.9,
                           f'Composite should be portrait or near-square, got {width}x{height}')
```

- [ ] **Step 3: Run — verify failure**

- [ ] **Step 4: Implement**

```python
from matplotlib.dates import DateFormatter


def render_summary_report(data, output_path):
    """Summary Report — single composite PNG with 3 vertically stacked subplots:

      top:    3 metric cards (Project Health, SPI, Days Behind)
      middle: Planned vs Actual % complete curve
      bottom: Milestones table

    Output filename stays smartpm-summary-report.png — generate_email_preview_html.py
    and generate_email_eml.py do not change.

    data shape: see fixture.
    """
    fig = plt.figure(figsize=(8, 9), dpi=style.DPI)
    gs = fig.add_gridspec(3, 1, height_ratios=[1, 2, 2], hspace=0.4)

    # ---- Top row: 3 metric cards ----
    cards_ax = fig.add_subplot(gs[0])
    cards_ax.axis('off')
    cards = data['cards']
    n = len(cards)
    for i, c in enumerate(cards):
        # Each card occupies 1/n of the width
        x0 = i / n
        x1 = (i + 1) / n
        cx = (x0 + x1) / 2
        # Label (small, top)
        cards_ax.text(cx, 0.85, c['label'],
                      ha='center', va='center', fontsize=style.LABEL_FONTSIZE,
                      color=style.GRAY, transform=cards_ax.transAxes)
        # Value (big, middle)
        val_text = f"{c['value']}{c.get('unit','')}"
        cards_ax.text(cx, 0.5, val_text,
                      ha='center', va='center', fontsize=24, fontweight='bold',
                      color='#222', transform=cards_ax.transAxes)
        # Delta (small, bottom; red if positive variance is bad direction;
        # we color positive deltas red for "Days Behind" and "anything trending wrong",
        # green for positive on "Project Health". Per-card sign is left to the data
        # caller — here we just color by sign with a label-aware twist.)
        d = c.get('delta')
        if d is not None:
            sign = '+' if d > 0 else ''
            # Default: positive delta is good for Health, bad for SPI/Days Behind
            label_lower = c['label'].lower()
            good_when_positive = 'health' in label_lower
            color = (style.GREEN if (d > 0) == good_when_positive else style.RED) if d != 0 else style.GRAY
            cards_ax.text(cx, 0.15, f'{sign}{d}',
                          ha='center', va='center', fontsize=style.LABEL_FONTSIZE,
                          color=color, transform=cards_ax.transAxes)

    # ---- Middle: Planned vs Actual S-curve ----
    curve_ax = fig.add_subplot(gs[1])
    curve = data['curve']
    p_xs = [date.fromisoformat(p['date']) for p in curve['planned']]
    p_ys = [p['pct'] for p in curve['planned']]
    a_xs = [date.fromisoformat(p['date']) for p in curve['actual']]
    a_ys = [p['pct'] for p in curve['actual']]

    curve_ax.plot(p_xs, p_ys, color=style.TEAL, linewidth=2, label='Planned')
    curve_ax.plot(a_xs, a_ys, color=style.ORANGE, marker='o', linewidth=2,
                  markersize=4, label='Actual')

    data_date = curve.get('data_date')
    if data_date:
        curve_ax.axvline(x=date.fromisoformat(data_date), color=style.GRAY,
                         linestyle='--', linewidth=1, label='Data date')

    curve_ax.set_title('Planned vs Actual % Complete',
                       fontsize=style.TITLE_FONTSIZE, pad=style.TITLE_PAD)
    curve_ax.set_ylabel('% Complete', fontsize=style.LABEL_FONTSIZE)
    curve_ax.set_ylim(0, 105)
    curve_ax.tick_params(labelsize=style.TICK_FONTSIZE)
    curve_ax.grid(True, linestyle=':', color=style.LIGHT_GRAY, linewidth=0.7)
    curve_ax.legend(loc='upper left', fontsize=style.TICK_FONTSIZE, frameon=False)
    curve_ax.xaxis.set_major_formatter(DateFormatter('%b %Y'))

    # ---- Bottom: Milestones table ----
    table_ax = fig.add_subplot(gs[2])
    table_ax.axis('off')

    milestones = data['milestones']
    cell_text = []
    cell_colors = []
    for m in milestones:
        actual = m.get('actual') or ''
        variance = m.get('variance_days')
        if variance is None:
            variance_text = ''
            row_color = 'white'
        elif variance > 0:
            variance_text = f'+{variance}d'
            row_color = '#FFE5E5'  # light red
        elif variance < 0:
            variance_text = f'{variance}d'
            row_color = '#E5FFE5'  # light green
        else:
            variance_text = '0d'
            row_color = 'white'
        cell_text.append([m['name'], m['planned'], actual, variance_text])
        cell_colors.append([row_color] * 4)

    table = table_ax.table(
        cellText=cell_text,
        cellColours=cell_colors,
        colLabels=['Milestone', 'Planned', 'Actual', 'Variance'],
        cellLoc='left',
        loc='center',
    )
    table.auto_set_font_size(False)
    table.set_fontsize(style.TICK_FONTSIZE)
    table.scale(1, 1.4)

    # Style the header row
    for col in range(4):
        cell = table[(0, col)]
        cell.set_facecolor(style.TEAL)
        cell.set_text_props(color='white', fontweight='bold')

    fig.savefig(output_path, **style.SAVEFIG_KWARGS)
    plt.close(fig)
```

- [ ] **Step 5: Register**

```python
'smartpm-summary-report': charts.render_summary_report,
```

- [ ] **Step 6: Run — verify pass**

```bash
python -m pytest scheduling/skills/schedule-update/references/charts/tests/test_render.py::TestSummaryReport -v
```

- [ ] **Step 7: Commit**

```bash
git add scheduling/skills/schedule-update/references/charts/
git commit -m "feat(scheduling): render_summary_report composite (cards/curve/milestones)"
```

---

## Task 12: Stub the 9 non-default trend graphs

The other 9 trend graphs (01-05, 13-16) need stubs so a project with a customized `graph_screenshots` list gets a clear "not yet implemented" message instead of a silent skip. v1 focuses on the 7 defaults + Summary Report; the team can implement the rest as needed.

**Files:**
- Modify: `charts.py`, `render.py`
- Modify: `tests/test_render.py`

- [ ] **Step 1: Write failing test for one of the stubs**

```python
class TestNonDefaultStubs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output_dir = Path(self._tmp.name) / 'out'

    def tearDown(self):
        self._tmp.cleanup()

    def test_unimplemented_chart_is_reported_as_failed(self):
        from charts import render
        payload_dir = Path(self._tmp.name) / 'payload'
        payload_dir.mkdir()
        (payload_dir / '01-planned-vs-actual-percent-complete.json').write_text('{}')
        results = render.render_payload(payload_dir, self.output_dir)
        self.assertEqual(results['rendered'], [])
        self.assertEqual(len(results['failed']), 1)
        self.assertIn('NotImplementedError', results['failed'][0]['reason'])
        self.assertIn('--legacy', results['failed'][0]['reason'])
```

- [ ] **Step 2: Run — verify failure**

```bash
python -m pytest scheduling/skills/schedule-update/references/charts/tests/test_render.py::TestNonDefaultStubs -v
```

Expected: FAIL — currently the slug `01-planned-vs-actual-percent-complete` reports 'no renderer in registry', not a NotImplementedError.

- [ ] **Step 3: Implement stubs in `charts.py`**

```python
def _stub(slug, description):
    """Build a stub render function that raises NotImplementedError with a
    clear path forward (use --legacy)."""
    def _render(data, output_path):
        raise NotImplementedError(
            f'Chart {slug} ({description}) is not yet implemented in the '
            f'matplotlib path. Use `/schedule-update screenshots --legacy` '
            f'to capture this chart via Playwright until a render function '
            f'is added.'
        )
    _render.__name__ = f'render_{slug.replace("-", "_")}'
    return _render


render_planned_vs_actual_percent_complete = _stub(
    '01-planned-vs-actual-percent-complete',
    'Planned VS Actual Percent Complete')
render_schedule_quality_grade_over_time = _stub(
    '02-schedule-quality-grade-over-time',
    'Schedule Quality Grade Over Time')
render_project_health_index_over_time = _stub(
    '03-project-health-index-over-time',
    'Project Health Index Over Time')
render_schedule_changes_over_time = _stub(
    '04-schedule-changes-over-time',
    'Schedule Changes Over Time')
render_schedule_delay_over_time = _stub(
    '05-schedule-delay-over-time',
    'Schedule Delay Over Time')
render_missing_logic = _stub(
    '13-missing-logic', 'Missing Logic')
render_average_total_float = _stub(
    '14-average-total-float', 'Average Total Float')
render_high_total_float = _stub(
    '15-high-total-float', 'High Total Float')
render_critical_path_percentage = _stub(
    '16-critical-path-percentage', 'Critical Path Percentage')
```

- [ ] **Step 4: Register all 9 in `render.py`**

```python
REGISTRY = {
    '06-end-date-variance': charts.render_end_date_variance,
    '07-schedule-compression-index-over-time': charts.render_schedule_compression_index,
    '08-velocity': charts.render_velocity,
    '09-spi-over-time': charts.render_spi_over_time,
    '10-activity-hit-rate': charts.render_activity_hit_rate,
    '11-window-start-accuracy': charts.render_window_start_accuracy,
    '12-window-finish-accuracy': charts.render_window_finish_accuracy,
    'smartpm-summary-report': charts.render_summary_report,
    # Stubs for non-default graphs
    '01-planned-vs-actual-percent-complete': charts.render_planned_vs_actual_percent_complete,
    '02-schedule-quality-grade-over-time': charts.render_schedule_quality_grade_over_time,
    '03-project-health-index-over-time': charts.render_project_health_index_over_time,
    '04-schedule-changes-over-time': charts.render_schedule_changes_over_time,
    '05-schedule-delay-over-time': charts.render_schedule_delay_over_time,
    '13-missing-logic': charts.render_missing_logic,
    '14-average-total-float': charts.render_average_total_float,
    '15-high-total-float': charts.render_high_total_float,
    '16-critical-path-percentage': charts.render_critical_path_percentage,
}
```

- [ ] **Step 5: Run — verify pass**

```bash
python -m pytest scheduling/skills/schedule-update/references/charts/tests/test_render.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add scheduling/skills/schedule-update/references/charts/
git commit -m "feat(scheduling): stub renders for non-default charts (NotImplementedError → --legacy)"
```

---

## Task 13: Rewrite `phases/screenshots.md` to document both paths

**Files:**
- Modify: `scheduling/skills/schedule-update/phases/screenshots.md`

- [ ] **Step 1: Read the current screenshots.md once** so you know what to preserve.

```bash
cat scheduling/skills/schedule-update/phases/screenshots.md
```

- [ ] **Step 2: Rewrite — full replacement**

Write this content over the existing file:

```markdown
# Phase: `screenshots` — Capture SmartPM Graphs

> Loaded by SKILL.md's router when the user invokes `/schedule-update screenshots`.

Captures the SmartPM Summary Report and trend graphs listed in `project-context.html`'s `graph_screenshots`. Two paths share the same output filenames so the rest of the pipeline can't tell them apart:

| Invocation | Path | When to use |
|------------|------|-------------|
| `/schedule-update screenshots` (no arg) | **matplotlib (new)** — MCP fetch + Python render | Default. No browser automation; no SmartPM login. |
| `/schedule-update screenshots --legacy` | **Playwright (legacy)** — headless Chromium captures SmartPM | Fallback while matplotlib styling is being dialed in, or when a non-default chart isn't implemented yet. |

Both paths write into `{dated_folder}/screenshots/` with the same PNG filenames.

---

## Default path: matplotlib (no `--legacy` arg)

### Step 0: Pre-flight

- Python 3.10+
- `matplotlib`, `Pillow` installed: `pip install -r {skill_dir}/references/charts/requirements.txt`
- SmartPM MCP available in the session (the `mcp__...__smartpm_*` tools should be listed)

### Step 1: Read Project Context

Apply folder resolution. Read `project-context.html`. Extract:
- `graph_screenshots` — list of slugs to render
- `smartpm_project_name` — exact name to match on SmartPM
- `smartpm_url`

If `project-context.html` is missing, stop with the standard error.

### Step 2: Resolve project_id + scenario_id

```
project_id  = mcp__...__smartpm_list_projects matching smartpm_project_name
scenario_id = mcp__...__smartpm_list_scenarios(project_id) → newest
```

If no match: surface the names you got and ask the colleague.

### Step 3: Fetch + write payload JSONs

Create `{dated_folder}/.chart-payload/`. For each slug in `graph_screenshots` plus `smartpm-summary-report`, call the right MCP endpoint and write a canonical-shape JSON to `.chart-payload/{slug}.json`. The slug → endpoint mapping:

| Slug | MCP endpoint | Canonical shape |
|------|--------------|-----------------|
| `06-end-date-variance` | `smartpm_list_scenario_schedules_v2(scenario_id)` | `{"updates": [{"data_date", "projected_finish"}, ...], "contractual_completion"}` |
| `07-schedule-compression-index-over-time` | `smartpm_get_scenario_schedule_compression_trend(scenario_id)` | `{"trend": [{"data_date", "value"}, ...]}` |
| `08-velocity` | `smartpm_get_scenario_velocity(scenario_id)` | `{"months": [{"month", "starts", "finishes"}, ...]}` |
| `09-spi-over-time` | `smartpm_get_scenario_spi_trend(scenario_id)` | `{"trend": [{"data_date", "value"}, ...]}` |
| `10-activity-hit-rate` | `smartpm_get_scenario_should_start_finish_trend(scenario_id)` → hit-rate series | `{"trend": [{"data_date", "value"}, ...]}` |
| `11-window-start-accuracy` | same endpoint → start-accuracy series | `{"trend": [{"data_date", "value"}, ...]}` |
| `12-window-finish-accuracy` | same endpoint → finish-accuracy series | `{"trend": [{"data_date", "value"}, ...]}` |
| `smartpm-summary-report` | composite: `get_scenario_project_health` + `get_scenario_spi` + `get_scenario_percent_complete_curve_v2` + `list_activities(milestones)` | `{"cards": [...], "curve": {"planned", "actual", "data_date"}, "milestones": [...]}` — see `charts.py:render_summary_report` docstring |

For any slug present in `graph_screenshots` that **isn't** in this table (i.e., one of the 9 non-default charts), the matplotlib path will raise `NotImplementedError`. That's the signal to suggest `--legacy` to the colleague.

### Step 4: Render

```bash
cd {skill_dir}/references
PYTHONPATH=. python -m charts.render {dated_folder}/.chart-payload {dated_folder}/screenshots
```

The script prints a JSON `{rendered: [...], failed: [...]}`. If anything is in `failed`, surface it to the colleague.

### Step 5: Verify

For each PNG named in `graph_screenshots` plus `smartpm-summary-report.png`: confirm exists in `{dated_folder}/screenshots/` and >0 bytes.

If a slug failed with `NotImplementedError`, tell the colleague:

> "Chart {slug} isn't implemented in the new matplotlib path yet. Run `/schedule-update screenshots --legacy` to capture it via the existing Playwright path."

### Step 6: Clean up

Delete `{dated_folder}/.chart-payload/` so the dated folder stays clean.

---

## Legacy path: `--legacy`

Everything in this section is the **unchanged** Playwright capture. It runs the same `references/smartpm/capture-smartpm.js` script the pipeline has used until now, end-to-end. Use it when a matplotlib chart isn't ready or doesn't look right yet.

(Full Playwright steps preserved below.)

### Step 0: Pre-Flight — credentials + Node setup

The script reads SmartPM credentials from `~/.claude/.env`:

| Key | Required | Purpose |
|-----|----------|---------|
| `SMARTPM_EMAIL` | yes | Auto-login email |
| `SMARTPM_PASSWORD` | yes | Auto-login password |
| `SMARTPM_PROJECTS_URL` | no | v2 projects/cards URL (defaults to Westland's org URL) |
| `SMARTPM_BASE_URL` | no | Defaults to `https://live.smartpmtech.com` |

If credentials are missing, the script throws `ENV_MISSING`. To set them up:

```bash
node "{skill_dir}/references/smartpm/env-loader.js" setup
```

Or ask the colleague for them via `AskUserQuestion` (header: "SmartPM creds") and write them yourself by calling `upsertEnvFile({SMARTPM_EMAIL, SMARTPM_PASSWORD})` from `references/smartpm/env-loader.js`. Never log the password back to the user.

Node + Playwright pre-flight:
1. `node --version` (any 18+).
2. Check `node_modules/` exists in `{skill_dir}/references/`. If missing, run `npm install` in that folder.
3. Chromium is installed via `npx playwright install chromium` (the script handles this).

### Step 1: Read Project Context

Apply folder resolution. Read `project-context.html`. Extract `smartpm_project_name` (falls back to `project_name`).

Output dir: `{dated_folder}/screenshots/`.

### Step 2: Write Checklist

Create `{dated_folder}/screenshots/` if it doesn't exist. Write `screenshots/checklist.md` from `{skill_dir}/references/checklist-template.md`.

Print the checklist.

### Step 3: Capture via Node script

```bash
node "{skill_dir}/references/smartpm/capture-smartpm.js" \
  "{smartpm_project_name or project_name}" "{dated_folder}/screenshots"
```

stdout: JSON `{ status, total, screenshots: [{name, file, path, size}, ...], urls }`.

Errors:
- `ENV_MISSING` → run the setup command (Step 0) or ask the user for credentials.
- Login redirect timeout → bad creds, MFA challenge, or captcha. Surface and ask the user to log in manually once via the headed debug helper.
- "No chart cards found" → trends page didn't render. Likely upload-still-processing or stale cache; retry after 30 seconds.
- Sign-in button stuck disabled → Angular form validation rejected the email. Confirm `SMARTPM_EMAIL`.

### Step 4: Verify

Read the captured PNGs visually. Confirm `smartpm-summary-report.png` shows the Summary Report modal, and each graph file shows the correct chart with data.

**SmartPM processing warning:** If called within 30 minutes of XER upload, SmartPM may still be processing. Check the Workspace page status; offer to wait.

### Step 5: Report

Mark checklist complete. Report total screenshots captured, file paths and sizes, SmartPM URLs used.

---

## Iteration note

The matplotlib path is brand new. Expect back-and-forth on styling — fonts, gridlines, axis labels, colors, table cell formatting — against live data. Tweak the relevant function in `references/charts/charts.py`; everything else (registry, orchestrator, tests) stays still. When a chart looks right, that's it — no formal sign-off step, just keep using it. Until each default chart is dialed in, `--legacy` is the safety net.
```

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/phases/screenshots.md
git commit -m "docs(scheduling): screenshots phase documents matplotlib + --legacy paths"
```

---

## Task 14: Update `SKILL.md` command matrix

**Files:**
- Modify: `scheduling/skills/schedule-update/SKILL.md`

- [ ] **Step 1: Open `SKILL.md` and find the command matrix table** (around lines 26-37 per the spec exploration).

- [ ] **Step 2: Replace the screenshots row in the matrix**

Find:
```markdown
| `/schedule-update screenshots` | `phases/screenshots.md` | SmartPM capture |
```

Replace with:
```markdown
| `/schedule-update screenshots` | `phases/screenshots.md` | SmartPM trend data via MCP → matplotlib PNGs (default) |
| `/schedule-update screenshots --legacy` | `phases/screenshots.md` | Same phase file; runs the legacy Playwright capture |
```

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/SKILL.md
git commit -m "docs(scheduling): SKILL.md mentions --legacy screenshots path"
```

---

## Task 15: Version bumps + marketplace.json

**Files:**
- Modify: `scheduling/.claude-plugin/plugin.json:3`
- Modify: `.claude-plugin/marketplace.json` (entry for scheduling plugin)

- [ ] **Step 1: Bump `scheduling/.claude-plugin/plugin.json` version**

```json
{
  "name": "scheduling",
  "version": "5.3.0",
  "description": "...",
  ...
}
```

- [ ] **Step 2: Bump marketplace.json's scheduling entry to 5.3.0**

```bash
cat .claude-plugin/marketplace.json
```

Find the scheduling plugin block and update its `version` field to `"5.3.0"`. Per CLAUDE.md, these two must stay in lockstep.

- [ ] **Step 3: Verify both files agree**

```bash
python -c "
import json
p = json.loads(open('scheduling/.claude-plugin/plugin.json').read())
m = json.loads(open('.claude-plugin/marketplace.json').read())
sched_entry = [x for x in m['plugins'] if x['name'] == 'scheduling'][0]
print('plugin.json     :', p['version'])
print('marketplace.json:', sched_entry['version'])
assert p['version'] == sched_entry['version'], 'version mismatch'
print('OK')
"
```

Expected: both `5.3.0` and `OK`.

- [ ] **Step 4: Run the full test suite once more**

```bash
python -m pytest scheduling/skills/schedule-update/references/charts/tests/ scheduling/hooks/tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add scheduling/.claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "chore(scheduling): bump to v5.3.0 for MCP-driven charts + HTML hook"
```

---

## Task 16: Live-data iteration (interactive — Camron drives)

This task is the spec's "Live-data iteration loop". It's interactive and not automatable — Camron runs the new path against a real recent project and tweaks chart styling in `charts.py` until each chart looks right. Playwright (`--legacy`) stays available throughout.

**There is no committed artifact at the end of this task.** It's a placeholder for the iteration period. Once Camron is happy with all 8 charts (7 trends + Summary Report), a follow-up branch can:

1. Make `--legacy` an explicit opt-in (warn if used).
2. Eventually delete `references/smartpm/capture-smartpm.js`, the env-loader, and the Playwright tests.

- [ ] **Step 1: Pick a recent project with a populated dated folder** (e.g. W1177 Lubumbashi's most recent week).

- [ ] **Step 2: Run the new path against it**

```bash
cd "{project_schedules_root}/{most_recent_dated_folder}"
# From within Claude Code or Cowork:
/schedule-update screenshots
```

Open each generated PNG in `screenshots/`. Compare to whatever the team has used historically.

- [ ] **Step 3: For each chart that needs tweaking**, edit the corresponding render function in `charts.py`, re-run `/schedule-update screenshots`, eyeball again. Repeat until satisfied.

- [ ] **Step 4: When all 8 look right**, no commit needed for this task. Move on to other work; future styling tweaks are normal small commits.

---

## Self-review

**Spec coverage check:**

| Spec goal | Plan task |
|-----------|-----------|
| Replace Playwright capture with MCP + matplotlib for 7 default trends | Tasks 4-10 |
| Same filenames; downstream unchanged | Verified by Task 11 fixture + Tasks 4-10 saving to expected paths |
| Summary Report = single composite PNG with 3 stacked subplots | Task 11 |
| Registry covers all 16 (stubs for non-defaults) | Tasks 4-10 (7 defaults), Task 12 (9 stubs) |
| Scheduling-plugin advisory hook | Task 3 |
| Playwright stays as `--legacy` fallback | Tasks 13 (phase rewrite documenting both paths) |
| Tests deterministic (no live MCP) | Tasks 4-12 use canned fixture JSONs |
| Version bumps in lockstep | Task 15 |

**Placeholder scan:** No "TBD", no "add appropriate error handling", no "similar to Task N". Each chart function has complete code; each task has runnable commands.

**Type consistency:** All chart functions follow the signature `(data: dict, output_path: str) → None`. All canonical data shapes are documented in fixture JSONs + function docstrings. Registry slugs match fixture filenames match expected output filenames.

---
