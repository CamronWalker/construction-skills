# Weekly Email Cloud Editor — construction-skills Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing `.eml` builder, COM Outlook draft builder, and `phases/draft.md` consume `email-draft.json` produced by the new weekly-email cloud editor service, replacing the `*-email-preview.html` round-trip. Emit a single stacked graphs PNG instead of N per-chart inline images.

**Architecture:** The cloud editor (in westland-mcps, separate repo) produces `email-draft.json` — a JSON document whose `editorial` layer mirrors `parse_email_html.parse_preview_html()`'s shape and whose `graph_html` layer holds per-slug rendered HTML+SVG chunks. The integration work in construction-skills is: (1) a small helper that reads the draft JSON, stacks the chart HTML chunks into one tall page, shells out to Node `html_to_png.cjs` to rasterize to a single PNG, and calls the existing `generate_update_email_eml` / `generate_update_email_msg` functions; (2) phase docs that drive the new flow; (3) cleanup of vestigial preview-HTML scaffolding.

**Tech Stack:** Python 3 (stdlib only for new code; existing `generate_email_msg.py` / `generate_email_eml.py` use `email.message.EmailMessage` + `pywin32` for COM); Node 18+ via `subprocess.run` for `html_to_png.cjs`; Markdown for phase docs.

**Dependencies on other branches:**
- **Renderer agent (`claude/blissful-tharp-ad03c2`) commit 1** must land first so `references/charts/html_to_png.cjs` exists (renamed from `.js`). Tasks 1-4 below can be written against fixtures before then; task 5+ verify against the live `.cjs`.
- **westland-mcps weekly-email service** must be deployed for end-to-end testing. Tasks 1-9 don't require it (fixtures suffice); the end-to-end smoke test (task 10) does.

---

## File structure

| File | Role | Action |
|---|---|---|
| `scheduling/skills/schedule-update/references/email_draft_io.py` | New module — JSON load + stacked-PNG generation + a `generate_email_from_draft()` orchestrator that wraps the existing `.eml` / COM builders | Create |
| `scheduling/skills/schedule-update/references/generate_email_eml.py` | Existing `.eml` builder. Keep `generate_update_email_eml(...)` untouched; new flow is reached via `email_draft_io.generate_email_from_draft()` which calls it. | No change |
| `scheduling/skills/schedule-update/references/generate_email_msg.py` | Existing COM builder. Same story — keep `generate_update_email_msg(...)` and `_build_html_body(...)` untouched. | No change |
| `scheduling/skills/schedule-update/phases/draft.md` | Phase that drives the email-draft step | Rewrite (replaces the "edit email-preview.html" body) |
| `scheduling/skills/schedule-update/phases/email.md` | Phase that builds the `.eml` from the edited draft | Update to consume `email-draft.json` |
| `scheduling/skills/schedule-update/phases/_carry_forward.md` | Helper phase doc — describes how last-week's state feeds this-week's seed | Update to point at `email-draft.json` instead of email-preview.html |
| `scheduling/hooks/check_html_discipline.py` | Plugin hook | Remove the `*-email-preview.html` matcher; keep `project-context.html` matcher |
| `scheduling/skills/schedule-update/tests/test_email_draft_io.py` | New test file | Create |
| `scheduling/skills/schedule-update/tests/fixtures/email-draft-sample.json` | New fixture — full canonical editorial shape + 2 ready graphs + 1 placeholder + 1 error | Create |
| `scheduling/skills/schedule-update/tests/fixtures/expected-stacked-graphs.html` | New fixture — expected output of `build_stacked_chart_page()` for the sample draft | Create |
| `scheduling/.claude-plugin/plugin.json` | Plugin manifest | Bump minor version |
| `.claude-plugin/marketplace.json` | Marketplace entry | Bump scheduling plugin version (matched pair) |

**Files NOT touched by this plan:**
- `references/generate_email_preview_html.py` — left in place during this branch's life. Removal is a follow-up branch once the cloud flow is proven against real projects. (Marking it as superseded in docstrings is in scope; deletion is not.)
- `references/parse_email_html.py` — same reasoning. The shape it defines is consumed by `email_draft_io` going forward, so the file becomes "shape documentation + parser for legacy preview HTML." Document this in its docstring; don't delete.
- `references/charts/*` — entirely owned by the renderer agent's branch.
- All other phase files (`screenshots.md`, `report.md`, `procore.md`, `copy.md`, `status.md`, `_attachments.md`).

---

## Task 1: Sample fixture — `email-draft-sample.json`

**Files:**
- Create: `scheduling/skills/schedule-update/tests/fixtures/email-draft-sample.json`

**Purpose:** Synthetic but realistic email-draft.json the integration tests run against. Has to cover: full canonical editorial layer, three graph statuses (ready / processing / error), `svgInner: ''` for the summary report, all four item-list flavors (successes / red_flags / stalled_tasks / key_items) with `checked` and `status` variations, attachments with `share_to_procore` toggles, `skip_procore: false`, signer block.

- [ ] **Step 1: Create the fixture file**

```bash
mkdir -p scheduling/skills/schedule-update/tests/fixtures
```

Create `scheduling/skills/schedule-update/tests/fixtures/email-draft-sample.json`:

```json
{
  "project": "G2203",
  "report_date": "2026-05-21",
  "editorial": {
    "project_info": {
      "project_name": "Lubumbashi MTC",
      "job_number": "G2203",
      "contractual_completion": "April 30, 2027",
      "projected_completion": "May 14, 2027"
    },
    "subject": "G2203 — Lubumbashi MTC — Weekly Update — 2026-05-21",
    "from": "Camron Walker <camron@westlandconstruction.com>",
    "to": "owner@example.com; pm@example.com",
    "cc": "sub1@example.com; sub2@example.com",
    "days_behind": 14,
    "gain_loss": -3,
    "successes": [
      { "text": "Foundation pour complete on Building A.", "checked": true, "status": "active", "date_archived": "" },
      { "text": "Steel delivery confirmed for week of 2026-06-01.", "checked": true, "status": "new", "date_archived": "" },
      { "text": "Old success kept for history.", "checked": false, "status": "archived", "date_archived": "2026-05-07" }
    ],
    "red_flags": [
      { "text": "**MEP coordination behind two weeks** — see RFI 0142.", "checked": true, "status": "active", "date_archived": "" }
    ],
    "stalled_tasks": [
      { "text": "Roofing material approval pending owner sign-off.", "checked": true, "status": "active", "date_archived": "" }
    ],
    "key_items": [
      { "text": "Owner walkthrough scheduled 2026-05-28.", "checked": true, "status": "active", "date_archived": "" }
    ],
    "gain_loss_narrative": "Lost 3 days this week to weather delays on the south elevation.",
    "eot_recovery": "Filing EOT request 0017 for the weather impact; recovery plan attached.",
    "logic_changes": "Reordered MEP rough-in to allow steel erection to continue in parallel.",
    "smartpm_changelog_url": "https://app.smartpm.com/projects/12345/changelog",
    "custom_paragraphs": [
      { "label": "Owner directive 2026-05-19", "text": "Owner directed switch to alternate roofing material per email.", "checked": true }
    ],
    "attachments": [
      { "filename": "G2203 Weekly Report 2026-05-21.pdf", "checked": true, "status": "active", "date_archived": "", "share_to_procore": true },
      { "filename": "G2203 EOT Request 0017.pdf", "checked": true, "status": "new", "date_archived": "", "share_to_procore": false }
    ],
    "changes_report": { "include": true, "filename": "G2203 Changes Report 2026-05-21.pdf" },
    "skip_procore": false,
    "signer_name": "Camron Walker",
    "signer_title": "Scheduler",
    "signer_mobile": "555-0100",
    "graph_order": [
      "01-planned-vs-actual-percent-complete",
      "02-schedule-quality-grade-over-time",
      "03-project-health-index-over-time",
      "smartpm-summary-report"
    ]
  },
  "graph_data": {
    "01-planned-vs-actual-percent-complete": { "stub": "real SmartPM response here" },
    "02-schedule-quality-grade-over-time": null,
    "03-project-health-index-over-time": null,
    "smartpm-summary-report": { "stub": "real summary response here" }
  },
  "graph_html": {
    "01-planned-vs-actual-percent-complete": {
      "status": "ready",
      "html": "<div class=\"chart-card\" data-slug=\"01-planned-vs-actual-percent-complete\"><h3>Planned vs Actual % Complete</h3><svg viewBox=\"0 0 1728 432\"><g class=\"series\"><!-- real svg here --></g></svg></div>",
      "svgInner": "<g class=\"series\"><!-- real svg here --></g>"
    },
    "02-schedule-quality-grade-over-time": {
      "status": "processing",
      "html": "<div class=\"chart-card chart-card--placeholder\" data-slug=\"02-schedule-quality-grade-over-time\"><h3>Schedule Quality Grade Over Time</h3><svg viewBox=\"0 0 1728 432\"><!-- clock icon + 'Data not yet available' --></svg></div>",
      "svgInner": ""
    },
    "03-project-health-index-over-time": {
      "status": "error",
      "html": "<div class=\"chart-card chart-card--placeholder\" data-slug=\"03-project-health-index-over-time\"><h3>Project Health Index Over Time</h3><svg viewBox=\"0 0 1728 432\"><!-- warn icon + 'Render failed' --></svg></div>",
      "svgInner": ""
    },
    "smartpm-summary-report": {
      "status": "ready",
      "html": "<div class=\"chart-card\" data-slug=\"smartpm-summary-report\"><h3>Summary Report</h3><div><!-- 3 sections: cards + curve + milestones --></div></div>",
      "svgInner": ""
    }
  },
  "meta": {
    "schema_version": 1,
    "generated_at": "2026-05-21T20:14:33Z",
    "last_refreshed_at": "2026-05-21T20:14:33Z",
    "last_edited_at": "2026-05-21T21:02:11Z",
    "status": "finalized",
    "smartpm_import_status": "ready",
    "graphs_ready_count": 2,
    "graphs_total": 4
  }
}
```

- [ ] **Step 2: Validate it parses as JSON**

```bash
python -c "import json; json.load(open('scheduling/skills/schedule-update/tests/fixtures/email-draft-sample.json'))"
```

Expected: no output (exit 0).

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/tests/fixtures/email-draft-sample.json
git commit -m "test(scheduling): add email-draft.json fixture for cloud-editor integration"
```

---

## Task 2: `email_draft_io.load_draft()` — read + validate

**Files:**
- Create: `scheduling/skills/schedule-update/references/email_draft_io.py`
- Test: `scheduling/skills/schedule-update/tests/test_email_draft_io.py`

**Purpose:** Single function reads `email-draft.json` and returns the parsed dict, validating that the schema version and required top-level keys are present.

- [ ] **Step 1: Write the failing test**

Create `scheduling/skills/schedule-update/tests/test_email_draft_io.py`:

```python
"""Tests for email_draft_io — load, stack, generate-from-draft."""
from __future__ import annotations

import json
import os
import sys
import unittest
from pathlib import Path

# Make references/ importable for the tests
REFERENCES_DIR = Path(__file__).resolve().parent.parent / 'references'
sys.path.insert(0, str(REFERENCES_DIR))

import email_draft_io  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / 'fixtures'
SAMPLE_DRAFT_PATH = FIXTURES_DIR / 'email-draft-sample.json'


class LoadDraftTests(unittest.TestCase):
    def test_load_draft_returns_parsed_dict(self):
        draft = email_draft_io.load_draft(str(SAMPLE_DRAFT_PATH))
        self.assertEqual(draft['project'], 'G2203')
        self.assertEqual(draft['report_date'], '2026-05-21')
        self.assertEqual(draft['meta']['schema_version'], 1)

    def test_load_draft_raises_on_missing_top_level_keys(self):
        with self.assertRaises(email_draft_io.DraftError) as ctx:
            email_draft_io.load_draft.__wrapped__({'project': 'X'}) if hasattr(email_draft_io.load_draft, '__wrapped__') else None
        # If load_draft doesn't use a decorator, test against a tmp file:
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump({'project': 'X'}, f)
            path = f.name
        try:
            with self.assertRaises(email_draft_io.DraftError):
                email_draft_io.load_draft(path)
        finally:
            os.unlink(path)

    def test_load_draft_raises_on_unsupported_schema(self):
        import tempfile
        bad = json.loads(SAMPLE_DRAFT_PATH.read_text())
        bad['meta']['schema_version'] = 999
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump(bad, f)
            path = f.name
        try:
            with self.assertRaises(email_draft_io.DraftError) as ctx:
                email_draft_io.load_draft(path)
            self.assertIn('schema_version', str(ctx.exception))
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m unittest scheduling.skills.schedule-update.tests.test_email_draft_io -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'email_draft_io'`.

- [ ] **Step 3: Write minimal implementation**

Create `scheduling/skills/schedule-update/references/email_draft_io.py`:

```python
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
                                  charts_dir=None, logo_path=None) -> str
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
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m unittest scheduling.skills.schedule-update.tests.test_email_draft_io.LoadDraftTests -v
```

Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-update/references/email_draft_io.py \
        scheduling/skills/schedule-update/tests/test_email_draft_io.py
git commit -m "feat(scheduling): email_draft_io.load_draft + schema validation"
```

---

## Task 3: `build_stacked_chart_page()` — concatenate graph HTML chunks

**Files:**
- Modify: `scheduling/skills/schedule-update/references/email_draft_io.py`
- Modify: `scheduling/skills/schedule-update/tests/test_email_draft_io.py`

**Purpose:** Take `graph_html` (slug → {status, html, svgInner}) plus `graph_order`, emit one tall HTML page with all chart cards in order, ready for Playwright to screenshot at 1200px viewport width.

- [ ] **Step 1: Write the failing test**

Append to `test_email_draft_io.py`:

```python
class BuildStackedChartPageTests(unittest.TestCase):
    def setUp(self):
        self.draft = email_draft_io.load_draft(str(SAMPLE_DRAFT_PATH))
        self.graph_html = self.draft['graph_html']
        self.order = self.draft['editorial']['graph_order']

    def test_emits_html5_document(self):
        page = email_draft_io.build_stacked_chart_page(self.graph_html, self.order)
        self.assertTrue(page.startswith('<!DOCTYPE html>'))
        self.assertIn('<html', page)
        self.assertIn('</html>', page)

    def test_contains_every_slug_in_canonical_order(self):
        page = email_draft_io.build_stacked_chart_page(self.graph_html, self.order)
        positions = [page.find(slug) for slug in self.order]
        # All present
        self.assertTrue(all(p >= 0 for p in positions), f'positions: {positions}')
        # Ascending — appears in canonical order
        self.assertEqual(positions, sorted(positions))

    def test_viewport_width_is_1200(self):
        page = email_draft_io.build_stacked_chart_page(self.graph_html, self.order)
        # Either via meta viewport or explicit body width — either signal is fine
        self.assertTrue(
            'width=1200' in page or 'width:1200px' in page or 'max-width:1200px' in page,
            'expected a 1200px width signal in stacked page'
        )

    def test_skips_slugs_missing_from_graph_html(self):
        page = email_draft_io.build_stacked_chart_page(
            self.graph_html,
            self.order + ['nonexistent-slug-xyz']
        )
        # Doesn't crash; doesn't include the missing slug verbatim
        self.assertNotIn('nonexistent-slug-xyz', page)

    def test_skips_slugs_with_blank_html(self):
        graph_html = dict(self.graph_html)
        graph_html['02-schedule-quality-grade-over-time'] = {
            'status': 'ready',
            'html': '',
            'svgInner': ''
        }
        page = email_draft_io.build_stacked_chart_page(graph_html, self.order)
        # Other slugs still present
        self.assertIn('01-planned-vs-actual-percent-complete', page)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m unittest scheduling.skills.schedule-update.tests.test_email_draft_io.BuildStackedChartPageTests -v
```

Expected: 5 tests fail with `AttributeError: module 'email_draft_io' has no attribute 'build_stacked_chart_page'`.

- [ ] **Step 3: Add the implementation**

Append to `email_draft_io.py`:

```python
_STACKED_PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=1200">
<title>Weekly schedule charts — stacked</title>
<style>
  /* CSS-scale 1728px native chart cards down to fit a 1200px viewport.
     SVG scales crisply so this loses no fidelity. */
  body {
    margin: 0;
    padding: 0;
    width: 1200px;
    font-family: Inter, Arial, sans-serif;
    background: #ffffff;
  }
  .chart-stack {
    display: flex;
    flex-direction: column;
    gap: 16px;
    padding: 16px;
  }
  .chart-stack > .chart-card,
  .chart-stack > .chart-card--placeholder {
    width: 100%;
    /* Charts render at 1728px native; scale to container width. */
    transform-origin: top left;
  }
  .chart-stack > .chart-card svg,
  .chart-stack > .chart-card--placeholder svg {
    width: 100%;
    height: auto;
    display: block;
  }
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m unittest scheduling.skills.schedule-update.tests.test_email_draft_io -v
```

Expected: All 8 tests pass (3 from Task 2 + 5 from Task 3).

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-update/references/email_draft_io.py \
        scheduling/skills/schedule-update/tests/test_email_draft_io.py
git commit -m "feat(scheduling): build_stacked_chart_page concatenates graph chunks"
```

---

## Task 4: `render_stacked_png()` — shell out to Node html_to_png.cjs

**Files:**
- Modify: `scheduling/skills/schedule-update/references/email_draft_io.py`
- Modify: `scheduling/skills/schedule-update/tests/test_email_draft_io.py`

**Purpose:** Take the stacked HTML page, write it to a temp file, invoke Node `html_to_png.cjs` to rasterize, return the PNG path. This is the seam between Python and the renderer agent's Node rasterizer.

**Dependency note:** This task depends on the renderer agent's commit 1 landing — that commit renames `html_to_png.js` → `html_to_png.cjs` and ships the `package.json` with `"type": "module"`. If commit 1 hasn't landed when you start this task, you can: (a) wait, (b) pre-create a stub `.cjs` that mimics the contract, or (c) test with mocked subprocess only.

- [ ] **Step 1: Write the failing test**

Append to `test_email_draft_io.py`:

```python
class RenderStackedPngTests(unittest.TestCase):
    def setUp(self):
        self.draft = email_draft_io.load_draft(str(SAMPLE_DRAFT_PATH))

    def test_returns_path_to_existing_png(self):
        # Real integration: this requires html_to_png.cjs to exist + Node + Playwright
        # Use a fake renderer to keep the unit test hermetic.
        import unittest.mock as mock

        def fake_render(html_path, png_path, *args, **kwargs):
            Path(png_path).write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 16)
            return png_path

        with mock.patch.object(email_draft_io, '_run_html_to_png', side_effect=fake_render):
            with tempfile.TemporaryDirectory() as tmpdir:
                out = email_draft_io.render_stacked_png(
                    self.draft, output_dir=tmpdir
                )
                self.assertTrue(os.path.isfile(out))
                self.assertTrue(out.endswith('.png'))
                self.assertGreater(os.path.getsize(out), 0)

    def test_raises_if_html_to_png_fails(self):
        import unittest.mock as mock

        def failing_render(*args, **kwargs):
            raise email_draft_io.DraftError('html_to_png.cjs failed')

        with mock.patch.object(email_draft_io, '_run_html_to_png', side_effect=failing_render):
            with tempfile.TemporaryDirectory() as tmpdir:
                with self.assertRaises(email_draft_io.DraftError):
                    email_draft_io.render_stacked_png(self.draft, output_dir=tmpdir)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m unittest scheduling.skills.schedule-update.tests.test_email_draft_io.RenderStackedPngTests -v
```

Expected: 2 tests fail with `AttributeError: module 'email_draft_io' has no attribute 'render_stacked_png'`.

- [ ] **Step 3: Add the implementation**

Append to `email_draft_io.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m unittest scheduling.skills.schedule-update.tests.test_email_draft_io.RenderStackedPngTests -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scheduling/skills/schedule-update/references/email_draft_io.py \
        scheduling/skills/schedule-update/tests/test_email_draft_io.py
git commit -m "feat(scheduling): render_stacked_png via Node html_to_png.cjs"
```

---

## Task 5: `editorial_to_kwargs()` — map JSON shape to builder kwargs

**Files:**
- Modify: `scheduling/skills/schedule-update/references/email_draft_io.py`
- Modify: `scheduling/skills/schedule-update/tests/test_email_draft_io.py`

**Purpose:** Translate `draft.editorial` into the kwargs `generate_update_email_eml` and `generate_update_email_msg` expect. The shapes match for the most part — same field names — but item-lists need filtering for the email body (only `checked=True` and `status != 'archived'`), and attachments need filtering + path resolution.

**Reference:** The shape `parse_email_html.parse_preview_html()` returns is the source of truth (per scheduling/CLAUDE.md). It already does this filter-for-email-body step; we mirror that logic against the JSON shape.

- [ ] **Step 1: Inspect what parse_email_html.parse_preview_html() emits for the .eml builder**

Read `scheduling/skills/schedule-update/references/parse_email_html.py` end-to-end. Focus on:
- The "Two shapes returned for lists" docstring at the top
- The filtering rule for items: `checked=True AND status != 'archived'`
- How `successes` (list of markdown strings) differs from `successes_full` (list of dicts)
- Attachment filtering — which attachments go to the email vs. all attachments

This pattern is what `editorial_to_kwargs` re-implements against the JSON.

- [ ] **Step 2: Write the failing test**

Append to `test_email_draft_io.py`:

```python
class EditorialToKwargsTests(unittest.TestCase):
    def setUp(self):
        self.draft = email_draft_io.load_draft(str(SAMPLE_DRAFT_PATH))
        self.kwargs = email_draft_io.editorial_to_kwargs(self.draft['editorial'])

    def test_passes_through_project_info_and_metrics(self):
        self.assertEqual(self.kwargs['project_info']['project_name'], 'Lubumbashi MTC')
        self.assertEqual(self.kwargs['project_info']['job_number'], 'G2203')
        self.assertEqual(self.kwargs['days_behind'], 14)
        self.assertEqual(self.kwargs['gain_loss'], -3)

    def test_passes_through_subject_and_recipients(self):
        self.assertIn('Lubumbashi', self.kwargs['subject'])
        self.assertEqual(self.kwargs['to_recipients'], 'owner@example.com; pm@example.com')
        self.assertEqual(self.kwargs['cc_recipients'], 'sub1@example.com; sub2@example.com')
        self.assertIn('camron@westlandconstruction.com', self.kwargs['from_address'])

    def test_passes_through_narrative_blocks(self):
        self.assertIn('weather delays', self.kwargs['gain_loss_narrative'])
        self.assertIn('EOT request 0017', self.kwargs['eot_recovery'])
        self.assertIn('Reordered MEP', self.kwargs['logic_changes'])
        self.assertEqual(self.kwargs['smartpm_changelog_url'],
                         'https://app.smartpm.com/projects/12345/changelog')

    def test_filters_item_lists_to_checked_and_not_archived(self):
        # Sample has 3 successes: 2 active+checked, 1 archived
        # The .eml builder receives only the 2 active checked items as markdown strings.
        successes = self.kwargs['successes']
        self.assertEqual(len(successes), 2)
        self.assertIn('Foundation pour', successes[0])
        self.assertIn('Steel delivery confirmed', successes[1])
        # Archived item is excluded
        self.assertFalse(any('Old success' in s for s in successes))

    def test_filters_attachments_to_checked_and_not_archived(self):
        # All 2 sample attachments are checked + active
        att = self.kwargs['attachment_paths']
        self.assertEqual(len(att), 2)
        # By default they are NAMES not paths — the orchestrator resolves to absolute
        # paths against a search root. editorial_to_kwargs returns just names.
        self.assertTrue(att[0].endswith('Weekly Report 2026-05-21.pdf'))
        self.assertTrue(att[1].endswith('EOT Request 0017.pdf'))

    def test_passes_signer_block(self):
        self.assertEqual(self.kwargs['signer_name'], 'Camron Walker')
        self.assertEqual(self.kwargs['signer_title'], 'Scheduler')
        self.assertEqual(self.kwargs['signer_mobile'], '555-0100')

    def test_passes_custom_paragraphs_filtered_to_checked(self):
        custom = self.kwargs['custom_paragraphs']
        # Sample has 1 custom paragraph, checked=True
        self.assertEqual(len(custom), 1)
        # Format expected by the builders: list of {label, text} dicts
        # (the existing _build_html_body iterates the same shape)
        self.assertEqual(custom[0]['label'], 'Owner directive 2026-05-19')

    def test_drops_skip_procore_and_share_to_procore_fields(self):
        # Those fields drive the procore phase, not the .eml body.
        self.assertNotIn('skip_procore', self.kwargs)
        self.assertNotIn('share_to_procore', self.kwargs)
```

- [ ] **Step 3: Run test to verify it fails**

```bash
python -m unittest scheduling.skills.schedule-update.tests.test_email_draft_io.EditorialToKwargsTests -v
```

Expected: 7 tests fail with AttributeError.

- [ ] **Step 4: Add the implementation**

Append to `email_draft_io.py`:

```python
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
    """Translate draft.editorial → kwargs for generate_update_email_eml/msg.

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
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m unittest scheduling.skills.schedule-update.tests.test_email_draft_io.EditorialToKwargsTests -v
```

Expected: 7 tests pass.

- [ ] **Step 6: Commit**

```bash
git add scheduling/skills/schedule-update/references/email_draft_io.py \
        scheduling/skills/schedule-update/tests/test_email_draft_io.py
git commit -m "feat(scheduling): editorial_to_kwargs maps draft JSON to builder kwargs"
```

---

## Task 6: `generate_email_from_draft()` — full orchestrator

**Files:**
- Modify: `scheduling/skills/schedule-update/references/email_draft_io.py`
- Modify: `scheduling/skills/schedule-update/tests/test_email_draft_io.py`

**Purpose:** The end-user-facing function. Loads the draft, renders the stacked PNG, resolves attachment filenames to absolute paths against a search root, and calls `generate_update_email_eml` (and optionally `generate_update_email_msg` for COM).

- [ ] **Step 1: Write the failing test**

Append to `test_email_draft_io.py`:

```python
class GenerateEmailFromDraftTests(unittest.TestCase):
    def setUp(self):
        self.draft = email_draft_io.load_draft(str(SAMPLE_DRAFT_PATH))

    def test_full_orchestration_writes_eml_and_invokes_builder(self):
        import unittest.mock as mock
        captured = {}

        def fake_render_stacked_png(draft, output_dir):
            path = os.path.join(output_dir, 'fake-stacked.png')
            Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 16)
            return path

        def fake_generate_eml(output_path, **kwargs):
            captured['kwargs'] = kwargs
            captured['output_path'] = output_path
            Path(output_path).write_text('fake eml')
            return os.path.abspath(output_path)

        with mock.patch.object(email_draft_io, 'render_stacked_png',
                               side_effect=fake_render_stacked_png), \
             mock.patch.object(email_draft_io, '_call_generate_update_email_eml',
                               side_effect=fake_generate_eml):
            with tempfile.TemporaryDirectory() as tmpdir:
                # Pretend the .pdf attachments are present in the dated folder
                for att in self.draft['editorial']['attachments']:
                    Path(tmpdir, att['filename']).write_bytes(b'%PDF stub')
                Path(tmpdir, self.draft['editorial']['changes_report']['filename']).write_bytes(b'%PDF stub')

                eml_path = email_draft_io.generate_email_from_draft(
                    draft_path=str(SAMPLE_DRAFT_PATH),
                    output_eml_path=os.path.join(tmpdir, 'out.eml'),
                    dated_folder=tmpdir,
                )

                self.assertTrue(os.path.isfile(eml_path))
                # Builder received the stacked PNG via summary_screenshot_path
                self.assertIn('summary_screenshot_path', captured['kwargs'])
                self.assertTrue(captured['kwargs']['summary_screenshot_path'].endswith('.png'))
                # No per-graph paths — stacked PNG replaces them
                self.assertEqual(captured['kwargs'].get('graph_screenshot_paths', []), [])
                # Attachment paths are absolute and exist
                for att_path in captured['kwargs']['attachment_paths']:
                    self.assertTrue(os.path.isabs(att_path))
                    self.assertTrue(os.path.isfile(att_path))

    def test_skips_attachments_that_dont_exist_on_disk(self):
        import unittest.mock as mock

        def fake_render_stacked_png(draft, output_dir):
            path = os.path.join(output_dir, 'fake-stacked.png')
            Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 16)
            return path

        captured = {}

        def fake_generate_eml(output_path, **kwargs):
            captured['kwargs'] = kwargs
            Path(output_path).write_text('fake eml')
            return os.path.abspath(output_path)

        with mock.patch.object(email_draft_io, 'render_stacked_png',
                               side_effect=fake_render_stacked_png), \
             mock.patch.object(email_draft_io, '_call_generate_update_email_eml',
                               side_effect=fake_generate_eml):
            with tempfile.TemporaryDirectory() as tmpdir:
                # NO attachment files placed in tmpdir
                email_draft_io.generate_email_from_draft(
                    draft_path=str(SAMPLE_DRAFT_PATH),
                    output_eml_path=os.path.join(tmpdir, 'out.eml'),
                    dated_folder=tmpdir,
                )
                # Builder receives empty attachment list (missing files skipped)
                self.assertEqual(captured['kwargs']['attachment_paths'], [])
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m unittest scheduling.skills.schedule-update.tests.test_email_draft_io.GenerateEmailFromDraftTests -v
```

Expected: 2 tests fail.

- [ ] **Step 3: Add the implementation**

Append to `email_draft_io.py`:

```python
def _call_generate_update_email_eml(output_path, **kwargs):
    """Thin indirection so tests can monkeypatch the .eml builder call."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from generate_email_eml import generate_update_email_eml
    finally:
        # Best-effort cleanup of the path mutation. Idempotent — safe to skip
        # if the path was already there.
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
        # generate_update_email_eml's attachment loop (line 232 in
        # generate_email_eml.py).
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

    # 2. Translate editorial → builder kwargs.
    kwargs = editorial_to_kwargs(editorial)

    # 3. Resolve attachment filenames → absolute paths.
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m unittest scheduling.skills.schedule-update.tests.test_email_draft_io.GenerateEmailFromDraftTests -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Run the full test suite to make sure nothing regressed**

```bash
python -m unittest discover -s scheduling/skills/schedule-update/tests -v
```

Expected: All tests in the suite pass (existing tests + the 14 new ones from tasks 2-6).

- [ ] **Step 6: Commit**

```bash
git add scheduling/skills/schedule-update/references/email_draft_io.py \
        scheduling/skills/schedule-update/tests/test_email_draft_io.py
git commit -m "feat(scheduling): generate_email_from_draft full orchestrator"
```

---

## Task 7: Rewrite `phases/draft.md`

**Files:**
- Modify: `scheduling/skills/schedule-update/phases/draft.md`

**Purpose:** Drive the new flow. The phase replaces the old "edit `*-email-preview.html`" body with: synthesize the seed JSON locally from last week's draft + this week's XER + meeting transcript, call MCP `generate_weekly_email_draft`, return the editor URL to the colleague, wait, call MCP `finalize_weekly_email`, save `email-draft.json` to the dated folder.

- [ ] **Step 1: Read the current draft.md to understand the existing flow**

```bash
cat scheduling/skills/schedule-update/phases/draft.md
```

Capture: the existing inputs / outputs / "wait for human" cues / cross-references to `phases/email.md` and `phases/_carry_forward.md`.

- [ ] **Step 2: Replace the entire phase doc**

Overwrite `scheduling/skills/schedule-update/phases/draft.md` with:

```markdown
# Phase: draft

## Goal

Produce `{dated_folder}/email-draft.json` — the complete state Claude and the colleague will iterate on in the browser before the `.eml` build step.

## Inputs

- `{dated_folder}/project-context.html` — recipients, signer info, SmartPM IDs (via `parse_project_context_html`).
- Last week's `{prev_dated_folder}/email-draft.json` — for carry-forward of items and narratives. If the previous week's run still has a `{prev_dated_folder}/*-email-preview.html` instead (legacy flow), fall back to `parse_email_html.parse_preview_html()` for the carry-forward shape.
- This week's `{dated_folder}/*.xer` + last week's XER for delta analysis (use the schedule plugin's XER parser).
- This week's meeting transcript at `{dated_folder}/meeting-transcript.md` if present.

## Outputs

- `{dated_folder}/email-draft.seed.json` — Claude's synthesized seed (carry-forward + new content). Persisted before the MCP call so Refresh can re-render against the same seed.
- `{dated_folder}/email-draft.json` — the cloud-finalized state (editorial + graph_data + graph_html).

## Process

### 1. Read prior state + this week's signals

Use the existing parsers. Do not Read the HTML files directly (see scheduling/CLAUDE.md's "HTML CRUD goes through the parse/generate pair" rule):

```python
import sys; sys.path.insert(0, 'scheduling/skills/schedule-update/references')
from parse_project_context_html import load_project_context
from email_draft_io import load_draft

ctx = load_project_context(schedules_root)            # current project context
prev_draft = None
if os.path.isfile(prev_dated_folder + '/email-draft.json'):
    prev_draft = load_draft(prev_dated_folder + '/email-draft.json')
elif os.path.isfile(prev_dated_folder + f'/{prev_date}-email-preview.html'):
    # Legacy fallback for the first run after this branch lands.
    from parse_email_html import parse_preview_html
    prev_draft = {'editorial': parse_preview_html(prev_dated_folder + f'/{prev_date}-email-preview.html')}
```

Read the XERs and the meeting transcript with the standard tools (Read + the XER parser).

### 2. Synthesize the seed

Build a dict matching the canonical editorial shape (per scheduling/CLAUDE.md "Email-preview JSON shape" + the cloud-editor spec's seed shape). The rule is **carry-forward then revise**: copy `prev_draft['editorial']` field-by-field, then apply this week's deltas. Standard moves:

- **Subject:** swap last week's date for this week's; keep project name + job number.
- **Items (successes / red_flags / stalled_tasks / key_items):** carry forward each entry's `text` + `status` + `date_archived`; reset `checked=True` for items that are still active; set `checked=False` for items that already shipped last week.
- **Narrative blocks (gain_loss_narrative, eot_recovery, logic_changes):** rewrite based on this week's XER deltas + transcript. Leave smartpm_changelog_url unchanged unless the URL pattern has shifted.
- **Attachments:** carry forward last week's attachments; mark items that no longer exist on disk as `status='archived'`. Add this week's new attachments (changes report PDF, etc.). Preserve `share_to_procore` flags from last week.
- **Signer block:** unchanged unless the colleague has rotated.
- **days_behind / gain_loss:** compute from XER comparison (week-over-week delta on contractual completion + schedule variance).
- **graph_order:** unchanged unless the colleague has reordered. Default order is the `graph_screenshots` list from project-context.html plus `smartpm-summary-report` last.

Write the seed JSON to disk:

```python
with open(dated_folder + '/email-draft.seed.json', 'w') as f:
    json.dump({'project': ctx['project']['job_number'],
                'report_date': report_date_iso,
                'editorial': seed_editorial,
                'smartpm': {'project_name': ctx['project']['smartpm_project_name'],
                            'scenario_id': None}},  # MCP resolves
              f, indent=2)
```

### 3. Generate the cloud draft

Call the `generate_weekly_email_draft` MCP tool (mounted at `/weekly-email/mcp` on westland-mcps):

```
mcp.generate_weekly_email_draft(
    project=ctx['project']['job_number'],
    report_date=report_date_iso,
    seed_json=<loaded seed>
)
```

The tool returns `{editor_url, expires_at, graphs_ready_count, graphs_total, smartpm_import_status}`.

### 4. Hand the URL to the colleague

Print the editor URL clearly. Tell them:
- Click it to open the editor in their browser.
- Edits autosave; no Save button needed.
- If `smartpm_import_status == 'processing'`, graphs are placeholders right now — they can start editing the narrative; ask Claude to refresh once SmartPM finishes (~20 min after XER upload).
- When done editing, come back here and say "done" (or equivalent — the next phase polls status).

### 5. (Optional, on colleague request) Refresh graphs

If the colleague asks Claude to refresh — typically because SmartPM was still processing at generate time — call `generate_weekly_email_draft` again with the **same seed** (read `email-draft.seed.json` from disk). The MCP tool preserves the editorial layer server-side and only refreshes graph_data + graph_html. Returns a new URL with a fresh signed token (same draft, new bookmark).

```python
seed = json.load(open(dated_folder + '/email-draft.seed.json'))
mcp.generate_weekly_email_draft(**seed)
```

The colleague's open browser tab keeps working; if it had been left open, autosaves continue against the same `(project, report_date)` key. They can hit Refresh in the editor (the button calls `/refresh-graphs` directly — no need to come back to Claude for the typical case). The Claude-driven path is the fallback when the URL has expired.

### 6. Wait for the colleague to finish

The colleague tells Claude they're done. Optionally call `get_weekly_email_status` to verify `status == 'editing'` and `last_edited_at` is recent enough to be plausible.

### 7. Finalize

Call `finalize_weekly_email`. Save the returned working JSON to disk:

```python
result = mcp.finalize_weekly_email(
    project=ctx['project']['job_number'],
    report_date=report_date_iso,
)
with open(dated_folder + '/email-draft.json', 'w') as f:
    json.dump(result['working_json'], f, indent=2)
```

`result['graphs_ready_count'] < result['graphs_total']` means some charts are still placeholders or errored — warn the colleague before proceeding to `phases/email.md`. They can choose to ship with placeholders (rare; only if the data is truly unavailable) or wait + re-run from step 3.

## What this phase replaces

The old flow wrote `{dated_folder}/{YYYY-MM-DD}-email-preview.html` and asked the colleague to open it in a browser to edit. That artifact is no longer produced. `references/generate_email_preview_html.py` and `references/parse_email_html.py` remain in the repo for one release cycle as a fallback for reading legacy preview HTML during the carry-forward step.

## What this phase explicitly does NOT do

- Build the `.eml` (that's `phases/email.md`).
- Upload to Procore (that's `phases/procore.md` — and it reads `email-draft.json` directly for `skip_procore` + `attachments[].share_to_procore`).
- Render chart PNGs in isolation (the cloud function renders + stores HTML+SVG chunks; the `.eml` build stacks them into one PNG).

## Cross-references

- Shape canonical to all email-related artifacts: scheduling/CLAUDE.md "Email-preview JSON shape — single source of truth".
- The MCP tools and HTTP routes: docs/superpowers/specs/2026-05-21-weekly-email-cloud-editor-design.md.
- The chart renderer package the cloud function uses: docs/superpowers/specs/2026-05-22-html-svg-chart-migration-javascript-design.md.
```

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/phases/draft.md
git commit -m "docs(scheduling): rewrite phases/draft.md for cloud-editor flow"
```

---

## Task 8: Update `phases/email.md`

**Files:**
- Modify: `scheduling/skills/schedule-update/phases/email.md`

**Purpose:** Build the `.eml` from `email-draft.json` instead of parsing the preview HTML.

- [ ] **Step 1: Read the current email.md**

```bash
cat scheduling/skills/schedule-update/phases/email.md
```

Capture: the existing structure, cross-references to other phases, the colleague-facing language.

- [ ] **Step 2: Update the doc — replace the "read preview HTML → parse → build .eml" section with the new flow**

The minimum required edit (preserve everything else):

```markdown
## Process

### 1. Read the finalized draft

```python
import sys; sys.path.insert(0, 'scheduling/skills/schedule-update/references')
from email_draft_io import load_draft

draft = load_draft(dated_folder + '/email-draft.json')
```

### 2. Build the .eml

```python
from email_draft_io import generate_email_from_draft

eml_path = generate_email_from_draft(
    draft_path=dated_folder + '/email-draft.json',
    output_eml_path=dated_folder + f'/{report_date_iso}-update-email.eml',
    dated_folder=dated_folder,
    smartpm_project_url=draft['editorial'].get('smartpm_project_url', ''),
    smartpm_trends_url=draft['editorial'].get('smartpm_trends_url', ''),
)
```

This orchestrator does three things end-to-end:
- Renders the stacked-graphs PNG into `{dated_folder}/screenshots/{project}-{report_date}-all-graphs-stacked.png` via the renderer agent's `html_to_png.cjs`.
- Resolves `editorial.attachments` filenames against `dated_folder` (skipping files that aren't on disk).
- Calls the existing `generate_update_email_eml` with the resolved kwargs, including `summary_screenshot_path=<stacked PNG>` and `graph_screenshot_paths=[]`.

### 3. Verify the .eml opens in Outlook

Double-click `eml_path`. Outlook should open in compose mode with To/Cc/Subject editable. Inline images (logo + stacked graphs PNG) render. Attachments appear in the attachment pane.
```

Preserve everything else in the file (intro, cross-references, troubleshooting tips). If the file has explicit instructions about per-chart screenshots, replace them with: "All charts are embedded as one stacked PNG; per-chart artifacts are not used in the `.eml` body." If the file references `parse_email_html.parse_preview_html()` as the input source, replace with `email_draft_io.load_draft()`.

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/phases/email.md
git commit -m "docs(scheduling): phases/email.md consumes email-draft.json"
```

---

## Task 9: Update `phases/_carry_forward.md`

**Files:**
- Modify: `scheduling/skills/schedule-update/phases/_carry_forward.md`

**Purpose:** The carry-forward doc currently describes reading from last week's email-preview HTML. Point it at last week's `email-draft.json` (with the parse_preview_html fallback for legacy weeks).

- [ ] **Step 1: Read the current carry-forward doc**

```bash
cat scheduling/skills/schedule-update/phases/_carry_forward.md
```

- [ ] **Step 2: Update the input description + code snippets**

Anywhere the doc references `*-email-preview.html` or `parse_email_html.parse_preview_html()` as the primary source, replace with `email-draft.json` and `email_draft_io.load_draft()`. Add a small "Legacy fallback" subsection that documents the parse_preview_html path for weeks where last week's run pre-dates this branch (one-off, deprecates with the second week post-merge).

- [ ] **Step 3: Commit**

```bash
git add scheduling/skills/schedule-update/phases/_carry_forward.md
git commit -m "docs(scheduling): _carry_forward.md reads email-draft.json"
```

---

## Task 10: Update the HTML-discipline hook

**Files:**
- Modify: `scheduling/hooks/check_html_discipline.py`

**Purpose:** The hook warns when Claude Reads/Writes managed HTML artifacts directly. The `*-email-preview.html` pattern is no longer produced by the new flow, but legacy weeks may still have them. Keep the matcher (for legacy reads) but **soften** the message: point at `email_draft_io.load_draft()` as the new path, with parse_preview_html as the legacy fallback.

- [ ] **Step 1: Read the current hook**

```bash
cat scheduling/hooks/check_html_discipline.py
```

- [ ] **Step 2: Update the `*-email-preview.html` write-warning message**

Currently the write message says "use generate_email_preview_html.py". Replace with:

```
HEADS UP — direct write to a managed HTML file ({path}).
This file is part of the LEGACY preview-HTML flow. The new flow uses
email-draft.json instead — see scheduling/skills/schedule-update/references/
email_draft_io.py. If you're carrying forward from a pre-2026-05-XX week,
read via parse_email_html.parse_preview_html() (don't Edit). Otherwise this
file shouldn't be getting written at all.
```

The read message can stay similar — point at `parse_email_html.parse_preview_html()` for legacy reads, note that fresh weeks won't have this file.

- [ ] **Step 3: Verify the hook still exits 0 (advisory, not blocking)**

Re-read the script to confirm: no logic change to the exit code, only the message text.

- [ ] **Step 4: Smoke test the hook**

```bash
echo '{"tool_name": "Read", "tool_input": {"file_path": "/foo/2026-05-21-email-preview.html"}}' | \
  python scheduling/hooks/check_html_discipline.py
echo "Exit: $?"
```

Expected: exit 0, stderr message mentions either `parse_email_html.parse_preview_html` or `email_draft_io.load_draft`.

- [ ] **Step 5: Commit**

```bash
git add scheduling/hooks/check_html_discipline.py
git commit -m "fix(scheduling): html-discipline hook points at email_draft_io for fresh weeks"
```

---

## Task 11: Bump the plugin version + marketplace entry

**Files:**
- Modify: `scheduling/.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json`

**Purpose:** Per the repo-root CLAUDE.md release convention, every commit that touches a plugin must bump both manifest files (matched pair). This is the FINAL commit on this branch before merging to main — represents the cloud-editor integration as one minor version.

- [ ] **Step 1: Check the current version**

```bash
grep version scheduling/.claude-plugin/plugin.json
grep -A 2 '"name": "scheduling"' .claude-plugin/marketplace.json
```

Capture both numbers; they must match.

- [ ] **Step 2: Bump both manifests by one minor**

Edit `scheduling/.claude-plugin/plugin.json`: bump the minor version (e.g., 5.4.0 → 5.5.0).

Edit `.claude-plugin/marketplace.json`: bump the matching scheduling entry's version to the same number.

- [ ] **Step 3: Verify the pre-commit hook accepts the change**

```bash
bash .githooks/test_pre_commit.sh
```

Expected: passes. If it fails with "plugin/marketplace version mismatch", you missed one — re-check.

- [ ] **Step 4: Commit**

Stage everything from prior tasks that hasn't been committed yet (there shouldn't be anything — each task commits its own changes — but double-check):

```bash
git status
```

Then commit the manifest bumps. Stage the plan doc itself if it's not already in:

```bash
git add scheduling/.claude-plugin/plugin.json .claude-plugin/marketplace.json
git add docs/superpowers/plans/2026-05-21-weekly-email-cloud-editor-integration.md
git commit -m "feat(scheduling): weekly-email cloud editor integration

Replaces the *-email-preview.html round-trip with email-draft.json
produced by the new westland-mcps weekly-email service. Adds
email_draft_io.py to wire the JSON shape into the existing
generate_update_email_eml and generate_update_email_msg builders.
Stacks the cloud-rendered chart HTML chunks into a single PNG via
the renderer agent's html_to_png.cjs.

phases/draft.md drives the new MCP-call flow.
phases/email.md and phases/_carry_forward.md consume the JSON.
HTML-discipline hook softened for the legacy preview-HTML pattern.

Depends on:
  - claude/blissful-tharp-ad03c2 commit 1 (html_to_png.cjs rename).
  - westland-mcps feat/weekly-email-service deploy."
```

---

## Task 12: End-to-end smoke test (gated on cross-repo dependencies)

**Files:**
- (No source changes — verification only.)

**Purpose:** Validate the full local pipeline once both dependencies have landed. **Do not run this task until** the renderer agent's commit 1+ and a deployed westland-mcps service are both available.

- [ ] **Step 1: Confirm dependencies**

```bash
# Renderer agent's html_to_png.cjs exists
ls scheduling/skills/schedule-update/references/charts/html_to_png.cjs

# westland-mcps service is deployed
curl -s -o /dev/null -w "%{http_code}" \
  "https://westland-mcps.westland.workers.dev/weekly-email/status/test/2026-01-01?sig=test" \
  | grep -E '401|404'  # Either auth-rejected or no-such-draft → endpoint reachable
```

Expected: html_to_png.cjs file present; curl returns 401 (sig invalid) or 404 (no such draft), NOT a 503 or connection error.

- [ ] **Step 2: Run a real generate_weekly_email_draft against a test project**

Pick a real recent project (Wellington NZ Temple 113385 is data-rich enough to exercise every chart). Synthesize a small seed JSON by hand or carry one forward from a prior week's email-draft.json. Call the MCP tool.

```python
import json
seed = json.load(open('test-seed.json'))
result = mcp.generate_weekly_email_draft(**seed)
print(result['editor_url'])
```

- [ ] **Step 3: Open the editor URL + make a small edit**

Click the URL. Edit the subject line. Wait for green checkmark. Refresh the page. Confirm the edit persists.

- [ ] **Step 4: Click ↻ Refresh graphs in the editor**

Confirm: each chart card gets a spinner overlay, dimensions don't shift; after the call returns, cards swap in place; header `Last refreshed` updates.

- [ ] **Step 5: Finalize + build the .eml**

```python
result = mcp.finalize_weekly_email(project='113385', report_date='2026-05-21')
import json
json.dump(result['working_json'], open(dated_folder + '/email-draft.json', 'w'), indent=2)
```

Then run the .eml build:

```python
from email_draft_io import generate_email_from_draft
eml_path = generate_email_from_draft(
    draft_path=dated_folder + '/email-draft.json',
    output_eml_path=dated_folder + '/2026-05-21-update-email.eml',
    dated_folder=dated_folder,
)
print(eml_path)
```

- [ ] **Step 6: Open the .eml in Outlook and visually verify**

- All four narrative blocks render.
- Stacked graphs PNG inlines below the narrative (one image, all charts in order).
- Attachments appear in the attachment pane.
- Logo renders in the signature.
- Recipients populate To/Cc.

- [ ] **Step 7: If everything passes, build + distribute per the release convention**

From the **main repo working tree** (NOT this worktree):

```bash
git switch main
git pull --ff-only
python build.py scheduling
```

Upload `src/scheduling.zip` to the enterprise plugin distribution.

---

## Self-review checklist

After writing the plan, I reviewed it against the spec end-to-end:

**1. Spec coverage:**

| Spec section | Plan task(s) |
|---|---|
| Three MCP tools | Driven by phases/draft.md (Task 7) — implementation is westland-mcps' scope, not this plan |
| Cloud function routes | westland-mcps' scope |
| Cloud-side rendering | Task 4 (stacked-PNG path) consumes the cloud's output |
| Browser editor | westland-mcps' scope |
| Graceful "still processing" | phases/draft.md handles status messaging (Task 7) |
| Hybrid auth | westland-mcps' scope; phases/draft.md is identity-federation client |
| Local finalize → .eml | Tasks 2-6 (email_draft_io.py end-to-end) |
| Portability hedge | N/A for this slice |
| Repo split | Documented in this plan's header |
| Editorial shape (canonical) | Task 5 (editorial_to_kwargs) |
| Refresh contract | phases/draft.md step 5 (Task 7) |
| Stacked PNG | Tasks 3, 4 (build_stacked_chart_page + render_stacked_png) |

**2. Placeholder scan:** None. Every task has the actual code, file paths, and verification commands.

**3. Type consistency:** Function names match across tasks (`load_draft`, `build_stacked_chart_page`, `render_stacked_png`, `editorial_to_kwargs`, `generate_email_from_draft`, `_call_generate_update_email_eml`, `_resolve_attachment_paths`, `_items_for_email_body`, `_custom_paragraphs_for_email_body`, `_attachments_for_email_body`, `_run_html_to_png`). Test class names map 1:1 to tasks.

**4. Cross-repo dependency notes:** Task 4 (html_to_png.cjs) and Task 12 (end-to-end) explicitly call out the renderer-agent and westland-mcps-agent dependencies. Tasks 1-3 and 5-11 are fully executable without those dependencies landing (fixture-based testing).
