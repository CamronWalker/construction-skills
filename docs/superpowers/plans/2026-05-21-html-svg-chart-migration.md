# HTML+SVG chart migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate every chart renderer in the schedule-update skill from matplotlib to HTML+SVG cloned from SmartPM's Highcharts CSS, then delete matplotlib and the legacy Playwright capture path.

**Architecture:** Per-chart Python render function emits a self-contained HTML+SVG document; a Node helper (`html_to_png.js`) rasterises via headless Chromium. Shared SVG plumbing extracted to `charts/svg_lib.py` mid-way through. Summary report collapses three matplotlib parts into one HTML document with three sections, one PNG.

**Tech Stack:** Python 3.12+ (rendering + tests), Playwright 1.52+ via Node (rasterisation), Chrome MCP (DOM inspection of SmartPM), SmartPM MCP (chart data fetch).

**Reference:** See [the design spec](../specs/2026-05-21-html-svg-chart-migration-design.md) for motivation, architecture rationale, and out-of-scope items.

---

## File Structure

**Created:**
- `scheduling/skills/schedule-update/references/charts/svg_lib.py` — shared SVG plumbing (Task 9)
- `scheduling/skills/schedule-update/references/charts/tests/test_svg_lib.py` — svg_lib unit tests (Task 9)
- `scheduling/skills/schedule-update/references/charts/tests/fixtures/02-…16-*.json` — one fixture per chart (Tasks 1-8, 10-16)
- `scheduling/skills/schedule-update/references/charts/tests/fixtures/smartpm-summary-report.json` — combined payload (Task 17)
- `chart-previews/` — untracked, gitignored render previews

**Modified:**
- `scheduling/skills/schedule-update/references/charts/charts.py` — replace every renderer; remove matplotlib imports (every task touches it)
- `scheduling/skills/schedule-update/references/charts/render.py` — update REGISTRY, delete `_composite_summary_report` (Task 17 + 18)
- `scheduling/skills/schedule-update/references/charts/tests/test_render.py` — add per-chart tests, update summary test (every task)
- `scheduling/skills/schedule-update/references/charts/requirements.txt` — drop matplotlib + Pillow (Task 18)
- `scheduling/skills/schedule-update/phases/screenshots.md` — per-chart recipes + remove `--legacy` (every task touches it; Task 18 finalises)
- `scheduling/.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json` — version bumps per batch
- `.gitignore` — add `chart-previews/` (Task 0)

**Deleted (Task 18):**
- `scheduling/skills/schedule-update/references/smartpm/capture-smartpm.js` — legacy chart-screenshot CLI
- Chart-screenshot portions of `scheduling/skills/schedule-update/references/smartpm/smartpm-client.js`
- Chart-screenshot tests in `scheduling/skills/schedule-update/references/tests/smartpm.spec.js`

---

## Conventions used in every chart task

These appear in every Task 1-17 — the steps that follow describe how to do them once.

### Chrome MCP inspection of one card

The MCP tab is already on the SmartPM trends URL for the SGRWRF project (project 141462, scenario 1963). When inspecting a chart card, use this JS template — substitute the chart title regex per chart:

```javascript
// CHART_TITLE_REGEX is the chart-specific title pattern, e.g.:
//   /Schedule Quality Grade Over Time/i
const cards = Array.from(document.querySelectorAll('spm-card-container'));
const target = cards.find(c => CHART_TITLE_REGEX.test(c.textContent));
const svg = target.querySelector('svg.highcharts-root');
const series = Array.from(svg.querySelectorAll('g.highcharts-series')).map((g, i) => {
  const cls = g.getAttribute('class') || '';
  const path = g.querySelector('path.highcharts-graph');
  const area = g.querySelector('path.highcharts-area, .highcharts-area');
  return {
    i,
    type: (cls.match(/highcharts-(\w+)-series/) || [])[1] || 'unknown',
    stroke: path?.getAttribute('stroke'),
    dasharray: path?.getAttribute('stroke-dasharray') || '',
    strokeWidth: path?.getAttribute('stroke-width'),
    areaFill: area?.getAttribute('fill'),
    areaOpacity: area?.getAttribute('fill-opacity'),
  };
});
const legend = Array.from(svg.querySelectorAll('.highcharts-legend-item')).map(li => li.textContent.trim());
const plotLines = Array.from(svg.querySelectorAll('.highcharts-plot-line')).map(pl => ({
  stroke: pl.getAttribute('stroke'),
  dash: pl.getAttribute('stroke-dasharray'),
  width: pl.getAttribute('stroke-width'),
}));
const xLabels = Array.from(svg.querySelectorAll('.highcharts-xaxis-labels text')).slice(0, 3).map(t => t.textContent);
const yLabels = Array.from(svg.querySelectorAll('.highcharts-yaxis-labels text')).slice(0, 5).map(t => t.textContent);
JSON.stringify({ series, legend, plotLines, xLabels, yLabels }, null, 2);
```

Save the result to `chart-previews/inspection-<slug>.json` for reference; it documents the visual contract for the regression tests.

### Fetching the MCP fixture

```python
# Tool name resolves via ToolSearch first if not preloaded:
#   ToolSearch query="select:smartpm_get_scenario_<endpoint>"
# Then call the resolved mcp__<uuid>__smartpm_get_scenario_<endpoint> tool with
# projectId=141462, scenarioId=1963 (SGRWRF Final Inspections milestone).
# Save the JSON response to the fixtures folder.
```

The exact tool name is listed per chart. SGRWRF is the canonical fixture project (chart 01 already uses it). For batches 5-7 (replacing working matplotlib renderers), reuse the existing fixture file in `charts/tests/fixtures/` if present; supplement with SGRWRF if needed.

### Render preview command

```bash
cd scheduling/skills/schedule-update/references
python -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '.')
from charts import charts
data = json.loads(Path('charts/tests/fixtures/<SLUG>.json').read_text())
out = Path('../../../../chart-previews') / 'SGRWRF-<SLUG>.png'
out.parent.mkdir(exist_ok=True)
charts.render_<slug_underscored>(data, str(out.resolve()))
print('PNG :', out.resolve())
print('HTML:', out.with_suffix('.html').resolve())
"
```

Open the PNG in an image viewer; open the HTML in a browser. Compare against SmartPM in the Chrome MCP tab side-by-side. Iterate on the renderer if the visual doesn't match — palette wrong, marker glyph wrong, plotline missing, series order wrong.

### Test-running command

```bash
cd scheduling/skills/schedule-update/references
python -m unittest charts.tests.test_render -v
```

For one specific test class:

```bash
python -m unittest charts.tests.test_render.Test<ChartClassName> -v
```

### Batch-end commit ceremony

At the end of each batch (the last chart task in the batch), bump versions and commit:

```bash
# In scheduling/.claude-plugin/plugin.json — increment the patch:
#   "version": "5.4.8"  →  "version": "5.4.9"
# Same in .claude-plugin/marketplace.json (the scheduling entry):
#   "version": "5.4.8"  →  "version": "5.4.9"

git add scheduling/skills/schedule-update/references/charts/charts.py \
        scheduling/skills/schedule-update/references/charts/tests/test_render.py \
        scheduling/skills/schedule-update/references/charts/tests/fixtures/<chart>.json \
        scheduling/skills/schedule-update/references/charts/tests/fixtures/<other-chart>.json \
        scheduling/skills/schedule-update/phases/screenshots.md \
        scheduling/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json

git commit -m "$(cat <<'EOF'
feat(scheduling): HTML+SVG charts <SLUG_LIST>

Batch N of the matplotlib → HTML+SVG migration. Clones SmartPM Highcharts
palette + dasharrays directly from inspected DOM. <one-line per chart>.

See [the migration spec](docs/superpowers/specs/2026-05-21-html-svg-chart-migration-design.md).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

The pre-commit hook in `.githooks/pre-commit` enforces matched version bumps; if it complains, fix the version mismatch and re-commit.

---

## Task 0: Pre-flight — commit chart 01, gitignore previews, baseline tests

The working tree currently has chart 01's renderer + Node rasteriser uncommitted. Commit it as a proper release with version bump before starting any new charts.

**Files:**
- Create: `.gitignore` (add line)
- Modify: `scheduling/.claude-plugin/plugin.json:3` (version)
- Modify: `.claude-plugin/marketplace.json:17` (scheduling version entry)
- Touch: every file currently in `git status`

- [ ] **0.1: Add `chart-previews/` to .gitignore**

The previews folder holds throwaway artifacts; never commit it.

```bash
cd "<repo-root>"
printf '\n# Chart renderer previews (HTML+PNG artifacts, regenerated on demand)\nchart-previews/\n' >> .gitignore
git diff .gitignore
```

Expected diff shows the new lines appended at end of file.

- [ ] **0.2: Bump scheduling plugin version 5.4.8 → 5.4.9**

Edit `scheduling/.claude-plugin/plugin.json`:

```json
{
  "name": "scheduling",
  "version": "5.4.9",
  ...
}
```

- [ ] **0.3: Bump marketplace scheduling entry to match**

Edit `.claude-plugin/marketplace.json`, the `"name": "scheduling"` entry:

```json
{
  "name": "scheduling",
  "source": "./scheduling",
  "description": "...",
  "version": "5.4.9"
}
```

The two version values MUST match — the pre-commit hook checks this.

- [ ] **0.4: Confirm Playwright is installed in references/**

```bash
cd scheduling/skills/schedule-update/references
ls node_modules/playwright >/dev/null && echo "ok"
# If missing:
npm install
npx playwright install chromium
```

Expected: prints `ok`. If `node_modules/playwright` doesn't exist, `npm install` populates it; `npx playwright install chromium` downloads the Chromium binary.

- [ ] **0.5: Run the full test suite, confirm 15/15 pass**

```bash
cd scheduling/skills/schedule-update/references
python -m unittest discover -s charts/tests -v 2>&1 | tail -5
```

Expected last line: `OK` (15 tests, 0 failures, 0 errors). If anything fails, investigate before proceeding — Task 0 must establish a clean baseline.

- [ ] **0.6: Commit chart 01 + version bump**

```bash
cd "<repo-root>"
git add .gitignore \
        scheduling/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json \
        scheduling/skills/schedule-update/phases/screenshots.md \
        scheduling/skills/schedule-update/references/charts/charts.py \
        scheduling/skills/schedule-update/references/charts/html_to_png.js \
        scheduling/skills/schedule-update/references/charts/tests/test_render.py \
        scheduling/skills/schedule-update/references/charts/tests/fixtures/01-planned-vs-actual-percent-complete.json

git commit -m "$(cat <<'EOF'
feat(scheduling): HTML+SVG chart 01 renderer + Node rasteriser

Chart 01 (Planned VS Actual Percent Complete) now renders as HTML+SVG
that clones SmartPM's Highcharts CSS exactly — palette, dasharrays,
markers all copied from inspected DOM. Rasterises to PNG via headless
Chromium with no element-clip, fixing the dashed-line drop that the
legacy Playwright capture path suffered from.

New Node helper `html_to_png.js` reuses references/node_modules/playwright
(already there for capture-smartpm.js). Sibling .html artifact lands next
to the .png for QA in a browser.

Phase doc updates: chart 01 has a per-slug recipe now, removed from the
non-default-stub list, added to the default `graph_screenshots`. The
remaining 8 stubs (02-05, 13-16) are still on the legacy --legacy path
until the HTML+SVG migration completes.

See [the migration spec](docs/superpowers/specs/2026-05-21-html-svg-chart-migration-design.md).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Expected: pre-commit hook passes (versions match), commit lands, `git status` shows clean working tree.

---

## Task 1: Chart 02 — Schedule Quality Grade Over Time (Batch 1, part 1)

Line chart of the schedule's quality grade (A+ through F, plotted as numeric 0-100) over time. SmartPM uses bands (green/yellow/red) for visual grade ranges.

**Files:**
- Modify: `scheduling/skills/schedule-update/references/charts/charts.py` (replace stub with renderer)
- Modify: `scheduling/skills/schedule-update/references/charts/tests/test_render.py` (add test class)
- Create: `scheduling/skills/schedule-update/references/charts/tests/fixtures/02-schedule-quality-grade-over-time.json`
- Modify: `scheduling/skills/schedule-update/phases/screenshots.md` (add recipe)

- [ ] **1.1: Inspect chart 02 in Chrome MCP**

In the SmartPM trends tab (already loaded), run the inspection JS with title regex `/Schedule Quality Grade/i`:

```javascript
const cards = Array.from(document.querySelectorAll('spm-card-container'));
const target = cards.find(c => /Schedule Quality Grade/i.test(c.textContent));
const svg = target.querySelector('svg.highcharts-root');
const series = Array.from(svg.querySelectorAll('g.highcharts-series')).map((g, i) => ({
  i,
  type: (g.getAttribute('class').match(/highcharts-(\w+)-series/) || [])[1],
  stroke: g.querySelector('path.highcharts-graph')?.getAttribute('stroke'),
  dasharray: g.querySelector('path.highcharts-graph')?.getAttribute('stroke-dasharray') || '',
  strokeWidth: g.querySelector('path.highcharts-graph')?.getAttribute('stroke-width'),
}));
const legend = Array.from(svg.querySelectorAll('.highcharts-legend-item')).map(li => li.textContent.trim());
const plotBands = Array.from(svg.querySelectorAll('.highcharts-plot-band')).map(pb => ({
  fill: pb.getAttribute('fill'),
  opacity: pb.getAttribute('fill-opacity'),
}));
const plotLines = Array.from(svg.querySelectorAll('.highcharts-plot-line')).map(pl => ({
  stroke: pl.getAttribute('stroke'),
  dash: pl.getAttribute('stroke-dasharray'),
}));
JSON.stringify({ series, legend, plotBands, plotLines }, null, 2);
```

Save the output to `chart-previews/inspection-02-schedule-quality-grade.json`. It captures the visual contract — palette colors, dash patterns, plotbands — that the regression tests will assert on.

- [ ] **1.2: Resolve the MCP endpoint via ToolSearch**

```
ToolSearch query="select:smartpm_get_scenario_schedule_quality,smartpm_get_scenario_schedule_quality_metric_details"
```

The trend chart pulls historical quality grade per scenario update. The endpoint that returns historical data is likely `smartpm_get_scenario_schedule_quality` returning a trend list. Confirm the exact shape (it might be a single-scenario value; in that case use `smartpm_get_scenario` and read `scheduleQualityGrade` per scenario, looping over `smartpm_list_scenarios`).

- [ ] **1.3: Fetch the fixture from SGRWRF**

Call the resolved endpoint with `projectId=141462, scenarioId=1963` and save the JSON response to `scheduling/skills/schedule-update/references/charts/tests/fixtures/02-schedule-quality-grade-over-time.json`. Pretty-print with `json.dumps(resp, indent=2)`.

- [ ] **1.4: Add palette constants + render function to charts.py**

Insert after the chart-01 renderer block (after the `# ---- Chart 01: Planned VS Actual Percent Complete ----` section, before the stub block).

Use the palette + dasharrays captured in step 1.1. Replace the `_PVA02_*` placeholders below with the inspected values:

```python
# ---- Chart 02: Schedule Quality Grade Over Time ----

# Colors copied from Chrome MCP inspection of SmartPM's chart 02 DOM on 2026-05-21.
_PVA02_LINE_COLOR    = '<inspected stroke>'     # primary line series
_PVA02_GRADE_A_BAND  = '<inspected plot-band fill (green)>'    # A+/A/A- range
_PVA02_GRADE_B_BAND  = '<inspected plot-band fill (yellow)>'   # B range
_PVA02_GRADE_C_BAND  = '<inspected plot-band fill (red)>'      # C and below
_PVA02_AXIS_TEXT     = '#666'
_PVA02_TITLE_TEXT    = '#181d27'


def render_schedule_quality_grade_over_time(data, output_path):
    """Chart 02 — Schedule Quality Grade Over Time (HTML+SVG → PNG).

    Line chart of historical schedule quality grade per scenario update.
    Background grade bands (A green / B yellow / C+ red) make the trend
    direction obvious at a glance.

    Consumes the SmartPM MCP shape from <ENDPOINT> directly:
      {"trend": [
        {"dataDate": "YYYY-MM-DDTHH:MM:SS", "scheduleQualityGrade": "<grade str>",
         "qualityScore": float},
        ...
      ]}
    """
    rows = (data.get('trend') or [])
    output_path = Path(output_path)
    html_path = output_path.with_suffix('.html')
    title = 'Schedule Quality Grade Over Time'

    if not rows:
        html_path.write_text(_pva01_empty_html(title), encoding='utf-8')
        _html_to_png(html_path, output_path)
        return

    # Plot geometry — identical proportions to chart 01 for layout consistency.
    svg_w, svg_h = 1692, 312
    pad_t, pad_r, pad_b, pad_l = 14, 32, 30, 56
    x0, x1 = pad_l, svg_w - pad_r
    y0, y1 = pad_t, svg_h - pad_b

    # Build series, axes, plot bands, plotlines — populated from the
    # palette and series shape captured in 1.1.
    # See chart-01 implementation for the SVG composition pattern.
    ...  # full body filled by engineer using chart 01 as template
```

The full SVG composition follows the same shape as `render_planned_vs_actual_percent_complete`: gridlines, axes, plot bands, line series, markers, legend, then HTML envelope + rasterise.

- [ ] **1.5: Replace the stub binding in charts.py**

Find the stub assignment near the bottom of `charts.py`:

```python
render_schedule_quality_grade_over_time = _stub(
    '02-schedule-quality-grade-over-time',
    'Schedule Quality Grade Over Time')
```

Delete those three lines. The `def render_schedule_quality_grade_over_time(...)` written in step 1.4 is now the active binding for that name.

- [ ] **1.6: Add HTML contract test to test_render.py**

After `TestPlannedVsActualPercentComplete`, add:

```python
@unittest.skipIf(shutil.which('node') is None,
                 'node executable not on PATH — HTML→PNG rasterisation needs it')
class TestScheduleQualityGradeOverTime(unittest.TestCase):
    """Chart 02 — line + grade bands. Asserts SmartPM-cloned palette + plot-band fills."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / '02-schedule-quality-grade-over-time.png'
        self.html = self.output.with_suffix('.html')
        self.data = json.loads(
            (FIXTURE_DIR / '02-schedule-quality-grade-over-time.json').read_text()
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_html_with_smartpm_palette(self):
        original = charts._html_to_png
        try:
            charts._html_to_png = lambda *a, **kw: None
            charts.render_schedule_quality_grade_over_time(self.data, str(self.output))
        finally:
            charts._html_to_png = original

        self.assertTrue(self.html.exists())
        body = self.html.read_text(encoding='utf-8')

        # Palette colors captured from SmartPM DOM inspection (1.1).
        # Replace the placeholders with the actual hex strings.
        for color in ('<line color>', '<grade A band>', '<grade B band>', '<grade C+ band>'):
            self.assertIn(color, body, f'palette color {color} missing from HTML')

        self.assertIn('Schedule Quality Grade Over Time', body)

    def test_full_pipeline_writes_png_via_chromium(self):
        try:
            charts.render_schedule_quality_grade_over_time(self.data, str(self.output))
        except RuntimeError as e:
            msg = str(e)
            if 'Playwright is not installed' in msg or 'Executable doesn' in msg:
                self.skipTest(f'Playwright/Chromium not installed: {msg.splitlines()[0]}')
            raise

        self.assertTrue(self.output.exists())
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')
        w, h = img.size
        self.assertGreater(w, h * 1.8, f'expected wide PNG, got {w}x{h}')
        img.close()
```

- [ ] **1.7: Run the tests, confirm green**

```bash
cd scheduling/skills/schedule-update/references
python -m unittest charts.tests.test_render.TestScheduleQualityGradeOverTime -v
```

Expected: both tests pass (HTML contract test fast; Chromium test ~30s). If the HTML contract test fails because a palette color is wrong, re-check 1.1 inspection output; if the Chromium test fails because the PNG is < 5KB, the SVG isn't rendering — open the HTML in a browser to debug.

- [ ] **1.8: Render preview to chart-previews/**

```bash
cd scheduling/skills/schedule-update/references
python -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '.')
from charts import charts
data = json.loads(Path('charts/tests/fixtures/02-schedule-quality-grade-over-time.json').read_text())
out = Path('../../../../chart-previews/SGRWRF-02-schedule-quality-grade.png')
out.parent.mkdir(exist_ok=True)
charts.render_schedule_quality_grade_over_time(data, str(out.resolve()))
print('PNG :', out.resolve())
print('HTML:', out.with_suffix('.html').resolve())
"
```

Open the PNG; open the HTML in a browser. Compare side-by-side against SmartPM's chart 02 in the Chrome MCP tab. Tweak palette / spacing / labels if the visual doesn't match.

- [ ] **1.9: Add per-slug recipe to phases/screenshots.md**

Under `#### Recipe per slug`, after the chart-01 recipe and before chart 06, add:

```markdown
##### `02-schedule-quality-grade-over-time`

\`\`\`
resp = smartpm_get_scenario_schedule_quality_trend(
    projectId=project_id, scenarioId=default_scenario_id)
# resp shape: {"trend": [{"dataDate": ..., "scheduleQualityGrade": ..., "qualityScore": ...}, ...]}

payload = resp   # pass through as-is
\`\`\`
```

Replace the endpoint name with whatever was confirmed in 1.2.

Then add `"02-schedule-quality-grade-over-time"` to the default `graph_screenshots` list in step 1.

- [ ] **1.10: Wait for next chart**

Don't commit yet — chart 03 (Task 2) is in the same batch. Commit at the end of Task 2.

---

## Task 2: Chart 03 — Project Health Index Over Time (Batch 1, part 2)

Line chart of the SmartPM Project Health Index™ (0-100 scalar) over time. Visually similar to SPI chart but the value range is 0-100 and the band thresholds differ.

**Files:**
- Modify: `scheduling/skills/schedule-update/references/charts/charts.py` (replace stub)
- Modify: `scheduling/skills/schedule-update/references/charts/tests/test_render.py` (add test class)
- Create: `scheduling/skills/schedule-update/references/charts/tests/fixtures/03-project-health-index-over-time.json`
- Modify: `scheduling/skills/schedule-update/phases/screenshots.md` (add recipe)
- Modify: version files (Task 2 ends Batch 1)

- [ ] **2.1: Inspect chart 03 in Chrome MCP** — title regex `/Project Health Index Over Time/i`. Same JS as Task 1.1. Save to `chart-previews/inspection-03-project-health.json`.

- [ ] **2.2: Resolve MCP endpoint**

```
ToolSearch query="select:smartpm_get_scenario_project_health_trend,smartpm_get_scenario_project_health"
```

The trend endpoint returns historical values per data date.

- [ ] **2.3: Fetch fixture from SGRWRF** — call the endpoint with `projectId=141462, scenarioId=1963`. Save to `charts/tests/fixtures/03-project-health-index-over-time.json`.

- [ ] **2.4: Add palette + render function to charts.py**

Insert after the chart-02 renderer:

```python
# ---- Chart 03: Project Health Index Over Time ----

# Colors copied from Chrome MCP inspection 2026-05-21.
_PVA03_LINE_COLOR     = '<inspected line stroke>'
_PVA03_HEALTHY_BAND   = '<inspected band fill (green, 75-100)>'
_PVA03_WARNING_BAND   = '<inspected band fill (yellow, 50-75)>'
_PVA03_DANGER_BAND    = '<inspected band fill (red, 0-50)>'


def render_project_health_index_over_time(data, output_path):
    """Chart 03 — Project Health Index Over Time (HTML+SVG → PNG).

    Line chart of the 0-100 Project Health Index™ scalar over schedule
    updates. Background bands (green 75-100, yellow 50-75, red 0-50)
    make the at-a-glance read trivial. Y-axis pinned 0-100.

    Consumes the SmartPM MCP shape from get_scenario_project_health_trend:
      {"trend": [{"dataDate": ..., "health": int}, ...]}
    """
    # ... (full implementation following chart 01 / chart 02 pattern)
```

- [ ] **2.5: Remove chart-03 stub** — delete the `render_project_health_index_over_time = _stub(...)` block.

- [ ] **2.6: Add tests** — follow the same `TestPlannedVsActualPercentComplete` pattern, asserting the chart-03 palette colors appear in HTML.

- [ ] **2.7: Run tests** — `python -m unittest charts.tests.test_render.TestProjectHealthIndexOverTime -v`. Both pass.

- [ ] **2.8: Render preview** — same command as 1.8, with slug `03-project-health-index-over-time`. Eyeball against SmartPM.

- [ ] **2.9: Add recipe to phases/screenshots.md** — same shape as 1.9. Add to default `graph_screenshots` list.

- [ ] **2.10: Bump versions for Batch 1**

Edit `scheduling/.claude-plugin/plugin.json:3` → `"version": "5.5.0"` (minor bump since two new features land).
Edit `.claude-plugin/marketplace.json` scheduling entry → `"version": "5.5.0"`.

- [ ] **2.11: Commit Batch 1**

```bash
cd "<repo-root>"
git add scheduling/skills/schedule-update/references/charts/charts.py \
        scheduling/skills/schedule-update/references/charts/tests/test_render.py \
        scheduling/skills/schedule-update/references/charts/tests/fixtures/02-schedule-quality-grade-over-time.json \
        scheduling/skills/schedule-update/references/charts/tests/fixtures/03-project-health-index-over-time.json \
        scheduling/skills/schedule-update/phases/screenshots.md \
        scheduling/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json

git commit -m "$(cat <<'EOF'
feat(scheduling): HTML+SVG charts 02 + 03 (Batch 1)

Schedule Quality Grade Over Time + Project Health Index Over Time both
migrate from stub-NotImplementedError to real HTML+SVG renderers. Each
clones SmartPM's Highcharts palette directly from inspected DOM —
including the green/yellow/red grade and health bands.

Phase doc updates: per-slug recipes added; both slugs added to the
default graph_screenshots list.

Batch 1 of 8. See [the migration spec](docs/superpowers/specs/2026-05-21-html-svg-chart-migration-design.md).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **2.12: Render Batch 1 preview gallery**

Render all three completed charts (01 from baseline + 02 + 03) for human review:

```bash
cd scheduling/skills/schedule-update/references
for slug in 01-planned-vs-actual-percent-complete \
            02-schedule-quality-grade-over-time \
            03-project-health-index-over-time; do
  fn=$(echo "$slug" | sed 's/-/_/g' | sed 's/^[0-9_]*_//')
  python -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '.')
from charts import charts
slug = '$slug'
data = json.loads(Path(f'charts/tests/fixtures/{slug}.json').read_text())
out = Path('../../../../chart-previews') / f'SGRWRF-{slug}.png'
out.parent.mkdir(exist_ok=True)
fn_name = 'render_' + slug.split('-', 1)[1].replace('-', '_')
getattr(charts, fn_name)(data, str(out.resolve()))
print(out.resolve())
"
done
```

Stop here for human review. The user looks at `chart-previews/SGRWRF-*.png` and either approves or asks for tweaks before Batch 2.

---

## Task 3: Chart 04 — Schedule Changes Over Time (Batch 2, part 1)

Likely a stacked-bar chart of change-log entries per period (e.g., schedule updates), grouped by change type (added activities, modified durations, etc.).

**Files:** same template — `charts.py`, `test_render.py`, new fixture, `phases/screenshots.md`.

- [ ] **3.1: Inspect chart 04 in Chrome MCP** — title regex `/Schedule Changes Over Time/i`. Use the inspection JS template, capturing series classes (look for `highcharts-column-series` indicating bars), per-series fills, legend labels, and any X-axis sample labels (likely data dates per update).

- [ ] **3.2: Resolve MCP endpoint**

```
ToolSearch query="select:smartpm_list_scenario_change_log_by_type,smartpm_get_scenario_change_log_summary,smartpm_list_scenario_change_log"
```

Likely `smartpm_get_scenario_change_log_summary` returns per-period counts grouped by type — confirm shape via tool description before fetching.

- [ ] **3.3: Fetch fixture** — `projectId=141462, scenarioId=1963`. Save to `charts/tests/fixtures/04-schedule-changes-over-time.json`.

- [ ] **3.4: Add palette + render function to charts.py**

Bar charts need new geometry helpers vs. lines. The general approach:

```python
# ---- Chart 04: Schedule Changes Over Time ----

# Per-change-type palette from inspection.
_PVA04_ADDED_FILL     = '<inspected fill>'
_PVA04_DELETED_FILL   = '<inspected fill>'
_PVA04_MODIFIED_FILL  = '<inspected fill>'
# ... one per change-type series shown in SmartPM's legend


def render_schedule_changes_over_time(data, output_path):
    """Chart 04 — Schedule Changes Over Time (HTML+SVG → PNG).

    Stacked bars: one bar per scenario data date, segments per change
    type (added activities, deleted activities, modified durations, ...).
    Total label above each bar.
    """
    # Geometry: X is ordinal (per-update index), not date-linear.
    # Each bar is sized by total count of that update's changes.
    # Stack from bottom-up by change-type severity.
    # Legend lists all change types with their fill colors.
    # ... (full SVG composition)
```

The bar-positioning math:
- `bar_w = (x1 - x0) / n_updates * 0.7` (70% of available slot)
- `bar_x = x0 + (i + 0.15) * (x1 - x0) / n_updates` for update i
- Stack segments by accumulating height per change-type

- [ ] **3.5: Remove chart-04 stub** — delete `render_schedule_changes_over_time = _stub(...)`.

- [ ] **3.6: Add tests** — same shape; assert change-type fill colors appear in HTML and X-axis update dates render.

- [ ] **3.7: Run tests** — both pass.

- [ ] **3.8: Render preview** — eyeball against SmartPM.

- [ ] **3.9: Add recipe to phases/screenshots.md**.

- [ ] **3.10: Wait for chart 05** (same batch).

---

## Task 4: Chart 05 — Schedule Delay Over Time (Batch 2, part 2)

Line chart of cumulative schedule delay (days) over time. Likely red-shaded above baseline.

**Files:** same template.

- [ ] **4.1: Inspect chart 05 in Chrome MCP** — title regex `/Schedule Delay Over Time/i`. Capture line color, fill (if area), threshold lines.

- [ ] **4.2: Resolve MCP endpoint**

```
ToolSearch query="select:smartpm_get_scenario_delay"
```

Returns delay history per update.

- [ ] **4.3: Fetch fixture** — save to `charts/tests/fixtures/05-schedule-delay-over-time.json`.

- [ ] **4.4: Add palette + render function to charts.py**

```python
# ---- Chart 05: Schedule Delay Over Time ----

_PVA05_DELAY_LINE     = '<inspected stroke>'
_PVA05_DELAY_FILL     = '<inspected area fill (pink/red shading)>'
_PVA05_BASELINE_LINE  = '#000000'  # confirm via inspection


def render_schedule_delay_over_time(data, output_path):
    """Chart 05 — Schedule Delay Over Time (HTML+SVG → PNG).

    Single-series line: cumulative critical-path delay days per scenario
    update. Positive = delay (drawn red); zero = baseline (drawn as
    horizontal reference line); negative = ahead of baseline (drawn green).
    Optional area fill below the line for visual weight.
    """
    # ... (full implementation)
```

- [ ] **4.5: Remove chart-05 stub**.

- [ ] **4.6: Add tests** — assert delay-line color and area fill appear in HTML.

- [ ] **4.7: Run tests**.

- [ ] **4.8: Render preview**.

- [ ] **4.9: Add recipe to phases/screenshots.md**.

- [ ] **4.10: Bump versions for Batch 2** — `5.5.0` → `5.5.1` (patch — bugfix-shaped: two more stubs filled). Update both files.

- [ ] **4.11: Commit Batch 2** — same ceremony as Task 2.11, slugs `04` and `05`.

- [ ] **4.12: Render Batch 2 preview gallery** — same pattern as 2.12 for charts 04 + 05; pause for human review.

---

## Task 5: Chart 13 — Missing Logic (Batch 3, part 1)

Likely a bar count of activities with missing predecessors and missing successors over time. SmartPM might use one bar per update (stacked: missing-pred / missing-succ).

**Files:** same template.

- [ ] **5.1: Inspect chart 13 in Chrome MCP** — title regex `/Missing Logic/i`. Capture chart type from `highcharts-(column|spline|bar)-series` class.

- [ ] **5.2: Resolve MCP endpoint** — SmartPM exposes missing-predecessor / missing-successor counts as part of the schedule quality metric details. Try:

```
ToolSearch query="select:smartpm_get_scenario_schedule_quality_metric_details"
```

If that returns scalar counts per scenario, the trend assembles by calling it across scenarios. Alternatively, the data may be in `smartpm_get_scenario_schedule_quality_trend` if it exposes the missing-logic sub-metrics.

- [ ] **5.3: Fetch fixture** — save to `charts/tests/fixtures/13-missing-logic.json`.

- [ ] **5.4: Add palette + render function to charts.py**

```python
# ---- Chart 13: Missing Logic ----

_PVA13_MISSING_PRED   = '<inspected fill>'
_PVA13_MISSING_SUCC   = '<inspected fill>'


def render_missing_logic(data, output_path):
    """Chart 13 — Missing Logic (HTML+SVG → PNG).

    Stacked bars per scenario update: count of activities missing a
    predecessor, count missing a successor. Total label above each bar.
    """
    # ... (full implementation, bar-positioning math from chart 04)
```

- [ ] **5.5: Remove chart-13 stub**.

- [ ] **5.6: Add tests**.

- [ ] **5.7: Run tests**.

- [ ] **5.8: Render preview**.

- [ ] **5.9: Add recipe to phases/screenshots.md**.

- [ ] **5.10: Wait for chart 14**.

---

## Task 6: Chart 14 — Average Total Float (Batch 3, part 2)

Line chart of average total float (days) across all activities per update.

**Files:** same template.

- [ ] **6.1: Inspect chart 14 in Chrome MCP** — title regex `/Average Total Float/i`.

- [ ] **6.2: Resolve MCP endpoint** — likely a metric returned by `smartpm_get_scenario_schedule_quality_metric_details` or its trend variant.

- [ ] **6.3: Fetch fixture**.

- [ ] **6.4: Add palette + render function to charts.py**

```python
# ---- Chart 14: Average Total Float ----

_PVA14_LINE     = '<inspected stroke>'
_PVA14_THRESHOLD_LOW   = '<inspected band/line (high-float warning band)>'
_PVA14_THRESHOLD_HIGH  = '<inspected band/line>'


def render_average_total_float(data, output_path):
    """Chart 14 — Average Total Float (HTML+SVG → PNG).

    Line chart of mean activity total float (days) per scenario update.
    Threshold bands flag values outside expected ranges (too low = no
    schedule slack; too high = padded schedule).
    """
    # ... (full implementation, line+thresholds shape like chart 09 SPI)
```

- [ ] **6.5: Remove chart-14 stub**.

- [ ] **6.6: Add tests**.

- [ ] **6.7: Run tests**.

- [ ] **6.8: Render preview**.

- [ ] **6.9: Add recipe to phases/screenshots.md**.

- [ ] **6.10: Bump versions for Batch 3** — `5.5.1` → `5.5.2`.

- [ ] **6.11: Commit Batch 3** — slugs `13` + `14`.

- [ ] **6.12: Render Batch 3 preview gallery**, pause for human review.

---

## Task 7: Chart 15 — High Total Float (Batch 4, part 1)

Bar (or line) count of activities whose total float exceeds a threshold, over time. High-float activities often indicate missing logic.

**Files:** same template.

- [ ] **7.1: Inspect chart 15 in Chrome MCP** — title regex `/High Total Float/i`.

- [ ] **7.2: Resolve MCP endpoint** — metric details endpoint.

- [ ] **7.3: Fetch fixture**.

- [ ] **7.4: Add palette + render function to charts.py**

```python
# ---- Chart 15: High Total Float ----

_PVA15_BAR_FILL   = '<inspected fill>'


def render_high_total_float(data, output_path):
    """Chart 15 — High Total Float (HTML+SVG → PNG).

    Count of activities with total float above threshold per scenario
    update. Visualised as bars (per inspection) — confirm chart type
    in 7.1 before implementing.
    """
    # ... (full implementation)
```

- [ ] **7.5: Remove chart-15 stub**.

- [ ] **7.6: Add tests**.

- [ ] **7.7: Run tests**.

- [ ] **7.8: Render preview**.

- [ ] **7.9: Add recipe to phases/screenshots.md**.

- [ ] **7.10: Wait for chart 16**.

---

## Task 8: Chart 16 — Critical Path Percentage (Batch 4, part 2)

Line chart of percentage of activities on the critical path over time. Healthy schedules show a reasonable critical-path size; outliers (10% one week, 60% the next) signal logic problems.

**Files:** same template.

- [ ] **8.1: Inspect chart 16 in Chrome MCP** — title regex `/Critical Path Percentage|Critical Path %/i`.

- [ ] **8.2: Resolve MCP endpoint** — likely a metric returned by quality-metric-details over scenarios.

- [ ] **8.3: Fetch fixture**.

- [ ] **8.4: Add palette + render function to charts.py**

```python
# ---- Chart 16: Critical Path Percentage ----

_PVA16_LINE  = '<inspected stroke>'
_PVA16_BAND  = '<inspected band fill, if any>'


def render_critical_path_percentage(data, output_path):
    """Chart 16 — Critical Path Percentage (HTML+SVG → PNG).

    Percent of activities on the critical path per scenario update.
    Line chart with Y-axis 0-100. Optional band for "healthy" range.
    """
    # ... (full implementation)
```

- [ ] **8.5: Remove chart-16 stub**.

- [ ] **8.6: Add tests**.

- [ ] **8.7: Run tests**.

- [ ] **8.8: Render preview**.

- [ ] **8.9: Add recipe to phases/screenshots.md**.

- [ ] **8.10: Bump versions for Batch 4** — `5.5.2` → `5.5.3`.

- [ ] **8.11: Commit Batch 4** — slugs `15` + `16`.

- [ ] **8.12: Render Batch 4 preview gallery**, pause for human review.

At this point all 8 stubs are filled with HTML+SVG renderers. No chart in the registry returns NotImplementedError anymore — the `--legacy` Playwright path is no longer needed for those slugs.

---

## Task 9: Refactor — extract `charts/svg_lib.py`

After 9 HTML+SVG renderers (chart 01 + the 8 new ones), the common SVG plumbing is clear. Factor it out so charts.py shrinks to per-chart palette + composition, and Tasks 10-17 build on the shared library instead of copy-pasting helpers.

**Files:**
- Create: `scheduling/skills/schedule-update/references/charts/svg_lib.py`
- Create: `scheduling/skills/schedule-update/references/charts/tests/test_svg_lib.py`
- Modify: `scheduling/skills/schedule-update/references/charts/charts.py` — every renderer

- [ ] **9.1: Create `svg_lib.py` with the shared API surface**

Move these from `charts.py` (currently prefixed `_pva01_*`):

```python
"""Shared SVG plumbing for the HTML+SVG chart path.

Per-chart render functions in charts.py use this module for the boring,
chart-agnostic infrastructure: HTML envelope, marker glyphs, scale
helpers, Catmull-Rom spline smoother, X-tick picker, rasterisation
shell-out. Each chart still owns its own palette, axis ranges, and
series ordering — the parts that vary are kept in the chart's render
function; the parts that don't are here.
"""

import html as _html_lib
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

# Path to the Node rasteriser (sibling of this module).
_HTML_TO_PNG_SCRIPT = Path(__file__).resolve().parent / 'html_to_png.js'

# Standard card geometry (matches 12in × 3in × 144dpi for layout parity
# with the matplotlib-era PNGs).
CARD_W = 1728
CARD_H = 432
SCALE  = 2

# Standard SVG inner geometry.
SVG_W = 1692
SVG_H = 312
PAD_T = 14
PAD_R = 32
PAD_B = 30
PAD_L = 56

# Common style colors (gridlines, axis text, title text).
COLOR_GRID       = '#e6e6e6'
COLOR_AXIS_TEXT  = '#666'
COLOR_TITLE_TEXT = '#181d27'


def html_to_png(html_path, png_path, width=CARD_W, height=CARD_H, scale=SCALE):
    """Rasterise an HTML file to PNG by shelling out to html_to_png.js."""
    if shutil.which('node') is None:
        raise RuntimeError('node is required to rasterise HTML→PNG but was not found on PATH')
    if not _HTML_TO_PNG_SCRIPT.is_file():
        raise RuntimeError(f'rasteriser missing: {_HTML_TO_PNG_SCRIPT}')

    result = subprocess.run(
        ['node', str(_HTML_TO_PNG_SCRIPT), str(html_path), str(png_path),
         str(width), str(height), str(scale)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f'html_to_png.js failed (exit {result.returncode}):\n'
            f'  stdout: {result.stdout.strip()}\n'
            f'  stderr: {result.stderr.strip()}'
        )


def date_to_x(d, dmin, dmax, x0, x1):
    span = (dmax - dmin).days or 1
    return x0 + ((d - dmin).days / span) * (x1 - x0)


def pct_to_y(p, y0, y1, p_min=0.0, p_max=100.0):
    """Map a percent (p_min..p_max) to inverted y-pixel inside [y0..y1]."""
    return y1 - (max(p_min, min(p_max, p)) - p_min) / (p_max - p_min) * (y1 - y0)


def smooth_path(pts):
    """Catmull-Rom → cubic-Bezier smoothing. Same as the chart-01 _pva01_smooth_path."""
    # ... (copy from charts.py _pva01_smooth_path)


def x_ticks(dmin, dmax, max_ticks=10):
    """Pick ~max_ticks evenly-spaced dates between dmin and dmax."""
    # ... (copy from charts.py _pva01_x_ticks)


def series_pts(rows, field, dmin, dmax, x0, x1, y0, y1, p_min=0.0, p_max=100.0):
    """Series → list of (x, y) pixel positions; null entries skipped, dates parsed."""
    # ... (copy from charts.py _pva01_series_pts, supplemented with p_min/p_max)


def marker(kind, x, y, color, size=4):
    """Inline SVG marker glyph at (x, y). kind ∈ {'circle','square','diamond','triangle','invtri'}."""
    # ... (copy from charts.py _pva01_marker_svg)


def legend_item(kind, color, dash, label):
    """One legend chip: SVG swatch + escaped text label."""
    # ... (copy from charts.py _pva01_legend_item_html)


def html_envelope(title, svg_inner, legend_html, *,
                  card_w=CARD_W, card_h=CARD_H, svg_w=SVG_W, svg_h=SVG_H):
    """Wrap SVG + legend in a styled card; self-contained, no external CSS/JS."""
    # ... (copy from charts.py _pva01_html_envelope, parameterising the card size)


def empty_html(title, card_w=CARD_W, card_h=CARD_H):
    """Minimal HTML card used when the data payload is empty."""
    # ... (copy from charts.py _pva01_empty_html, parameterising)
```

Each helper here is a 1-for-1 lift from the `_pva01_*` versions in charts.py — same logic, no behavior change. Where the chart-01 version had a hardcoded color (`_PVA01_GRID`), substitute the new `COLOR_GRID` constant defined here.

- [ ] **9.2: Create `tests/test_svg_lib.py` with unit tests**

```python
import unittest
from datetime import date, timedelta

from charts import svg_lib


class TestDateToX(unittest.TestCase):
    def test_midpoint(self):
        # Halfway between Jan 1 and Jan 31 → halfway between x=100 and x=200.
        d = date(2026, 1, 16)
        x = svg_lib.date_to_x(d, date(2026, 1, 1), date(2026, 1, 31), 100, 200)
        self.assertAlmostEqual(x, 150.0, places=1)

    def test_dmin_equals_dmax(self):
        # Zero-span shouldn't divide by zero.
        d = date(2026, 1, 1)
        x = svg_lib.date_to_x(d, d, d, 100, 200)
        self.assertEqual(x, 100)


class TestPctToY(unittest.TestCase):
    def test_zero_at_bottom(self):
        self.assertEqual(svg_lib.pct_to_y(0, 50, 200), 200)

    def test_hundred_at_top(self):
        self.assertEqual(svg_lib.pct_to_y(100, 50, 200), 50)

    def test_clamps_negative(self):
        self.assertEqual(svg_lib.pct_to_y(-10, 50, 200), 200)

    def test_clamps_above_max(self):
        self.assertEqual(svg_lib.pct_to_y(150, 50, 200), 50)


class TestSmoothPath(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(svg_lib.smooth_path([]), '')

    def test_single_point(self):
        self.assertEqual(svg_lib.smooth_path([(10, 20)]), 'M 10.00,20.00')

    def test_two_points_is_straight(self):
        result = svg_lib.smooth_path([(0, 0), (10, 10)])
        self.assertIn('M 0.00,0.00', result)
        self.assertIn('L 10.00,10.00', result)

    def test_three_points_uses_bezier(self):
        result = svg_lib.smooth_path([(0, 0), (10, 10), (20, 0)])
        self.assertTrue(result.startswith('M '))
        self.assertIn(' C ', result)


class TestXTicks(unittest.TestCase):
    def test_one_week_uses_7_day_stride(self):
        ticks = svg_lib.x_ticks(date(2026, 1, 1), date(2026, 1, 8))
        self.assertEqual(len(ticks), 2)

    def test_one_year_uses_60_day_stride(self):
        ticks = svg_lib.x_ticks(date(2026, 1, 1), date(2027, 1, 1))
        self.assertLessEqual(len(ticks), 11)
        self.assertGreaterEqual(len(ticks), 6)


class TestMarker(unittest.TestCase):
    def test_all_kinds_emit_svg(self):
        for kind in ('circle', 'square', 'diamond', 'triangle', 'invtri'):
            svg = svg_lib.marker(kind, 10, 20, '#ff0000')
            self.assertTrue(svg.startswith('<'), f'{kind} did not emit svg')

    def test_unknown_kind_returns_empty(self):
        self.assertEqual(svg_lib.marker('xyz', 10, 20, '#000'), '')


class TestHtmlEnvelope(unittest.TestCase):
    def test_contains_no_script_tag(self):
        # Rasterisation runs with JS disabled-friendly; no scripts allowed.
        html = svg_lib.html_envelope('Test', '<svg/>', '<span/>')
        self.assertNotIn('<script', html.lower())

    def test_contains_title(self):
        html = svg_lib.html_envelope('My Chart Title', '<svg/>', '<span/>')
        self.assertIn('My Chart Title', html)

    def test_escapes_title(self):
        html = svg_lib.html_envelope('A & B', '<svg/>', '<span/>')
        self.assertIn('A &amp; B', html)


if __name__ == '__main__':
    unittest.main()
```

- [ ] **9.3: Run svg_lib tests, confirm green**

```bash
cd scheduling/skills/schedule-update/references
python -m unittest charts.tests.test_svg_lib -v
```

Expected: all tests pass.

- [ ] **9.4: Update charts.py — import from svg_lib, remove `_pva01_*` helpers**

In charts.py, at the top (after `from . import style`):

```python
from . import svg_lib
```

Then delete these helper functions (they now live in svg_lib):
- `_PVA01_PROGRESS_TARGET_FILL`, `_PVA01_LATE_DATE_PLANNED`, ... (palette stays — those are chart-specific)
- `_html_to_png` (replaced by `svg_lib.html_to_png`)
- `_pva01_x`, `_pva01_y`, `_pva01_smooth_path`, `_pva01_x_ticks`, `_pva01_series_pts` (geometry → svg_lib)
- `_pva01_marker_svg`, `_pva01_legend_item_html` (glyphs → svg_lib)
- `_pva01_html_envelope`, `_pva01_empty_html` (envelope → svg_lib)

Keep the palette constants (`_PVA01_*` etc.) — those are chart-specific.

Update each renderer to call `svg_lib.*` where it previously called `_pva01_*` or `_html_to_png`. Example, in `render_planned_vs_actual_percent_complete`:

```python
# Before:
pts_late = _pva01_series_pts(rows, 'LATE_DATE_PLANNED', dmin, dmax, x0, x1, y0, y1)
# After:
pts_late = svg_lib.series_pts(rows, 'LATE_DATE_PLANNED', dmin, dmax, x0, x1, y0, y1)
```

Do this for all 9 renderers (chart 01 + the 8 from Batches 1-4).

- [ ] **9.5: Re-run the full test suite, confirm no regressions**

```bash
cd scheduling/skills/schedule-update/references
python -m unittest discover -s charts/tests -v 2>&1 | tail -5
```

Expected: all tests pass (including svg_lib tests + every chart test). If any chart test fails, the refactor has introduced a regression — the helper signatures aren't quite identical between the `_pva01_*` originals and the `svg_lib.*` versions. Diff carefully.

- [ ] **9.6: Re-render previews for all 9 charts, compare against pre-refactor baseline**

```bash
cd scheduling/skills/schedule-update/references
for slug in 01-planned-vs-actual-percent-complete \
            02-schedule-quality-grade-over-time \
            03-project-health-index-over-time \
            04-schedule-changes-over-time \
            05-schedule-delay-over-time \
            13-missing-logic \
            14-average-total-float \
            15-high-total-float \
            16-critical-path-percentage; do
  python -c "
import json, sys
from pathlib import Path
sys.path.insert(0, '.')
from charts import charts
slug = '$slug'
data = json.loads(Path(f'charts/tests/fixtures/{slug}.json').read_text())
out = Path('../../../../chart-previews') / f'SGRWRF-{slug}.png'
fn_name = 'render_' + slug.split('-', 1)[1].replace('-', '_')
getattr(charts, fn_name)(data, str(out.resolve()))
print(out)
"
done
```

Visually diff against the pre-refactor previews — they should be PIXEL-IDENTICAL. The refactor is a pure code reorganisation; any visual change indicates a bug.

- [ ] **9.7: Bump versions for refactor** — `5.5.3` → `5.5.4`.

- [ ] **9.8: Commit refactor**

```bash
git add scheduling/skills/schedule-update/references/charts/svg_lib.py \
        scheduling/skills/schedule-update/references/charts/charts.py \
        scheduling/skills/schedule-update/references/charts/tests/test_svg_lib.py \
        scheduling/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json

git commit -m "$(cat <<'EOF'
refactor(scheduling): extract svg_lib.py from chart renderers

Lifts the chart-agnostic SVG plumbing (HTML envelope, marker glyphs,
Catmull-Rom smoother, geometry helpers, X-tick picker, html_to_png
shell-out) out of charts.py into a new svg_lib module. Per-chart
renderers now reuse svg_lib for the boring parts; palette and series
composition stay inlined per chart (existing "each chart self-contained"
doctrine preserved for the parts that matter).

Zero visual change — chart PNGs are byte-identical before and after.
Unit tests added for svg_lib geometry helpers.

See [the migration spec](docs/superpowers/specs/2026-05-21-html-svg-chart-migration-design.md).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Chart 06 — End Date Variance (Batch 5, part 1)

**Replacing an existing matplotlib renderer.** The matplotlib version (`render_end_date_variance`) works — we're replacing it for visual consistency with the rest of the suite. Chart shows projected finish date variance from contractual completion over time, with pink-shaded "behind" band above zero and green-shaded "ahead" band below.

**Files:** charts.py (replace function body), test_render.py (update test class to assert HTML+SVG palette instead of matplotlib output), reuse existing fixture `charts/tests/fixtures/06-end-date-variance.json`.

- [ ] **10.1: Inspect chart 06 in Chrome MCP** — title regex `/End Date Variance/i`. Note: SmartPM may render this differently than the current matplotlib approximation; copy the exact palette regardless of what we had before.

- [ ] **10.2: Pull contractual_completion from project context**

The chart needs a contractual_completion baseline. The existing fixture should already have it (the matplotlib renderer reads `data['contractual_completion']`). Confirm shape:

```bash
cat scheduling/skills/schedule-update/references/charts/tests/fixtures/06-end-date-variance.json | python -m json.tool | head -20
```

If the shape is missing fields needed for the HTML+SVG version (e.g., per-update labels), refresh the fixture from MCP.

- [ ] **10.3: Replace `render_end_date_variance` body**

Delete the existing matplotlib implementation (currently ~95 lines around `charts.py:54`); replace with an HTML+SVG version that uses svg_lib:

```python
# ---- Chart 06: End Date Variance (HTML+SVG replacement) ----

# Palette from Chrome MCP inspection 2026-05-21 — likely:
_PVA06_PINK_FILL     = '<inspected area-above-zero fill>'
_PVA06_GREEN_FILL    = '<inspected area-below-zero fill>'
_PVA06_VARIANCE_LINE = '<inspected variance-line stroke>'
_PVA06_LABEL_BG      = '<inspected per-point label background>'


def render_end_date_variance(data, output_path):
    """Chart 06 — End Date Variance (HTML+SVG → PNG).

    Y-axis is days of variance from contractual completion. Pink area
    fills the "behind" zone above zero, green fills the "ahead" zone
    below. Bold zero line, single red variance series with date label
    next to each data point showing the projected finish.

    Consumes the same shape as the matplotlib version:
      {"updates": [{"dataDate": ..., "sourceEndDate": ...}, ...],
       "contractual_completion": "YYYY-MM-DD"}
    """
    # ... full SVG implementation using svg_lib helpers
```

- [ ] **10.4: Update the existing chart-06 test class**

The current `TestEndDateVariance` test asserts wide-aspect-ratio PNG. Replace with a test class matching chart-01's pattern (HTML contract test + Chromium smoke test).

- [ ] **10.5: Run tests** — confirm both pass.

- [ ] **10.6: Render preview** — eyeball against SmartPM's actual chart 06.

- [ ] **10.7: Update phases/screenshots.md** — the existing chart-06 recipe stays (same MCP endpoint), no doc change needed unless the data shape changed.

- [ ] **10.8: Wait for chart 07** (same batch).

---

## Task 11: Chart 07 — Schedule Compression Index (Batch 5, part 2)

**Replacing matplotlib renderer.** Line with green/yellow/red threshold bands (existing matplotlib version uses LineCollection for per-segment color; HTML+SVG version can do the same via multiple `<path>` elements).

**Files:** same template, replacing existing.

- [ ] **11.1: Inspect chart 07** — title regex `/Schedule Compression Index/i`.

- [ ] **11.2: Reuse existing fixture** `07-schedule-compression-index-over-time.json` or refresh from MCP if shape differs.

- [ ] **11.3: Replace `render_schedule_compression_index` body**

```python
# ---- Chart 07: Schedule Compression Index (HTML+SVG replacement) ----

_PVA07_GOOD_COLOR    = '<inspected stroke (green)>'
_PVA07_FINE_COLOR    = '<inspected stroke (yellow)>'
_PVA07_BAD_COLOR     = '<inspected stroke (red)>'
_PVA07_WARN_LINE     = '<inspected threshold-line stroke (yellow dashed)>'
_PVA07_DANGER_LINE   = '<inspected threshold-line stroke (red dashed)>'


def render_schedule_compression_index(data, output_path):
    """Chart 07 — Schedule Compression Index™ (HTML+SVG → PNG).

    Y-axis is percent compression (0-100+). Per-segment line color
    matches SmartPM's GOOD/FINE/BAD indicator: green/yellow/red. Dashed
    horizontal thresholds at 15% (warn) and 25% (danger).
    """
    # ... full SVG implementation
```

For per-segment color: build N `<path>` elements (one per data-point pair), each with its own stroke matching the worse of the two endpoints' indicator.

- [ ] **11.4: Update test class to HTML contract pattern**.

- [ ] **11.5: Run tests**.

- [ ] **11.6: Render preview**.

- [ ] **11.7: Bump versions for Batch 5** — `5.5.4` → `5.5.5`.

- [ ] **11.8: Commit Batch 5** — slugs `06` + `07` (note: replaces matplotlib, not stub).

```bash
git commit -m "$(cat <<'EOF'
refactor(scheduling): HTML+SVG charts 06 + 07 (Batch 5, replaces matplotlib)

End Date Variance + Schedule Compression Index migrate from matplotlib
to HTML+SVG. Visual style matches SmartPM's rendering more closely than
the matplotlib approximation. Same MCP data shape; tests updated to
assert HTML+SVG palette regression.

Batch 5 of 8. See [the migration spec](docs/superpowers/specs/2026-05-21-html-svg-chart-migration-design.md).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **11.9: Render Batch 5 preview gallery**, pause for human review.

---

## Task 12: Chart 08 — Velocity (Batch 6, part 1)

**Replacing matplotlib renderer.** The most complex chart in the suite: 6 bar series side-by-side per month (Current Starts Actual/Planned, Current Finishes Actual/Planned, Baseline Starts/Finishes), plus an orange average-line and a black data-date marker.

**Files:** same template, plus possibly a new `svg_lib.grouped_bars(...)` helper if the bar-positioning math is reusable.

- [ ] **12.1: Inspect chart 08** — title regex `/Velocity|Monthly Activity Start.*Finish/i`. Capture all 6 series fills, the average-line stroke, the data-date marker stroke.

- [ ] **12.2: Reuse existing fixture** `08-velocity.json`.

- [ ] **12.3: Replace `render_velocity` body**

```python
# ---- Chart 08: Velocity (HTML+SVG replacement) ----

_PVA08_CURR_START_ACTUAL   = '<inspected>'
_PVA08_CURR_FINISH_ACTUAL  = '<inspected>'
_PVA08_BASELINE_START      = '<inspected>'
_PVA08_BASELINE_FINISH     = '<inspected>'
_PVA08_CURR_START_PLANNED  = '<inspected>'
_PVA08_CURR_FINISH_PLANNED = '<inspected>'
_PVA08_AVERAGE_LINE        = '<inspected (orange)>'
_PVA08_DATA_DATE_LINE      = '<inspected (black)>'


def render_velocity(data, output_path):
    """Chart 08 — Monthly Activity Start & Finish Distribution (HTML+SVG → PNG).

    Six bar series per month, grouped side-by-side: Current Starts/Finishes
    split into Actual (≤ data date) and Planned (> data date), plus
    Baseline Starts/Finishes. Orange horizontal average line (mean of
    current finishes for actual months). Black vertical data-date line.
    Last 12 months window (matches matplotlib behavior).
    """
    # Bar geometry:
    #   n_months = number of monthly buckets
    #   slot_w = (x1 - x0) / n_months
    #   bar_w = slot_w * 0.13
    #   offsets = [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5] * bar_w
    #   bar i for month j: x = x0 + (j + 0.5) * slot_w + offsets[i]
    # ... full SVG implementation
```

If the bar-positioning math feels ready for sharing (e.g., chart 04 used a similar approach), extract a `svg_lib.grouped_bars_x(n_groups, n_bars, slot_x0, slot_w, bar_pad=0.0)` helper as part of this task. Otherwise inline.

- [ ] **12.4: Update test class to HTML contract pattern**.

- [ ] **12.5: Run tests**.

- [ ] **12.6: Render preview** — Velocity has many bars; double-check the rendering at full 1728×432 vs at the smaller browser zoom. Bar widths should be visible at full resolution.

- [ ] **12.7: Wait for chart 09**.

---

## Task 13: Chart 09 — SPI Over Time (Batch 6, part 2)

**Replacing matplotlib renderer.** Line + thresholds, similar shape to compression index but with the threshold direction flipped (higher = better).

**Files:** same template.

- [ ] **13.1: Inspect chart 09** — title regex `/SPI Over Time/i`.

- [ ] **13.2: Reuse existing fixture** `09-spi-over-time.json`.

- [ ] **13.3: Replace `render_spi_over_time` body**

```python
# ---- Chart 09: SPI Over Time (HTML+SVG replacement) ----

_PVA09_GOOD_COLOR    = '<inspected>'
_PVA09_FINE_COLOR    = '<inspected>'
_PVA09_BAD_COLOR     = '<inspected>'
_PVA09_GREEN_THRESH  = '<inspected stroke for 0.9 threshold>'
_PVA09_YELLOW_THRESH = '<inspected stroke for 0.8 threshold>'


def render_spi_over_time(data, output_path):
    """Chart 09 — Schedule Performance Index Over Time (HTML+SVG → PNG).

    Line chart of SPI per scenario update. Per-segment color by value:
    >= 0.9 green, >= 0.8 yellow, < 0.8 red. Dashed thresholds at 0.9
    (green dashed) and 0.8 (yellow dashed). Y-axis 0-1.30 with 0.25 ticks.
    """
    # ... full SVG implementation
```

- [ ] **13.4: Update test class**.

- [ ] **13.5: Run tests**.

- [ ] **13.6: Render preview**.

- [ ] **13.7: Bump versions for Batch 6** — `5.5.5` → `5.5.6`.

- [ ] **13.8: Commit Batch 6** — slugs `08` + `09`.

- [ ] **13.9: Render Batch 6 preview gallery**, pause for human review.

---

## Task 14: Chart 10 — Activity Hit Rate (Batch 7, part 1)

**Replacing matplotlib renderer.** Stacked bars per data date: on-time (green) / late (yellow) / missed (red) activities, with total label above each bar. Three charts (10, 11, 12) share the exact same shape, just different field names.

**Files:** charts.py (replace `render_activity_hit_rate` + shared helper).

- [ ] **14.1: Inspect chart 10** — title regex `/Activity Hit Rate/i`. Capture stack fills (green/yellow/red), total-label positioning, X-axis label format.

- [ ] **14.2: Reuse existing fixture** `10-activity-hit-rate.json`.

- [ ] **14.3: Create shared `_render_hit_rate_bars` helper, then thin wrapper**

Because charts 10/11/12 are the same shape with different field names, factor a shared helper. The matplotlib version already does this (`_render_hit_rate_chart`); follow the same pattern in HTML+SVG.

```python
# ---- Charts 10/11/12: Hit-rate trio (HTML+SVG replacement) ----

_PVA_HIT_ONTIME  = '<inspected green fill>'
_PVA_HIT_LATE    = '<inspected yellow fill>'
_PVA_HIT_MISSED  = '<inspected red fill>'


def _render_hit_rate_bars(data, output_path, *, prefix, title, labels):
    """Shared renderer for the three hit-rate charts (10/11/12).

    prefix selects the field set:
      - 'total'    → totalOnTime/totalLate/totalMissed (chart 10)
      - 'started'  → startedOnTime/startedLate/didNotStart (chart 11)
      - 'finished' → finishedOnTime/finishedLate/didNotFinish (chart 12)
    """
    # ... full SVG implementation: stacked bars + total labels + bottom legend


def render_activity_hit_rate(data, output_path):
    """Chart 10 — Activity Hit Rate (HTML+SVG → PNG)."""
    _render_hit_rate_bars(
        data, output_path,
        prefix='total',
        title='Activity Hit Rate (%)',
        labels={'on_time': 'On Time', 'late': 'Late', 'missed': 'Missed'},
    )
```

- [ ] **14.4: Update test class**.

- [ ] **14.5: Run tests**.

- [ ] **14.6: Render preview**.

- [ ] **14.7: Wait for chart 11** (same batch).

---

## Task 15: Chart 11 — Window Start Accuracy (Batch 7, part 2)

**Replacing matplotlib renderer.** Same shape as chart 10, different prefix.

**Files:** charts.py (replace `render_window_start_accuracy` to use the shared helper).

- [ ] **15.1: Skip inspection** — same chart shape as chart 10. Confirm the palette is identical (it should be — SmartPM uses the same green/yellow/red across the trio).

- [ ] **15.2: Reuse existing fixture** `11-window-start-accuracy.json`.

- [ ] **15.3: Replace `render_window_start_accuracy` body**

```python
def render_window_start_accuracy(data, output_path):
    """Chart 11 — Window Start Accuracy (HTML+SVG → PNG)."""
    _render_hit_rate_bars(
        data, output_path,
        prefix='started',
        title='Window Start Accuracy (Last 12 Months)',
        labels={'on_time': 'Started On Time', 'late': 'Started Late',
                'missed': 'Did Not Start'},
    )
```

- [ ] **15.4: Update test class**.

- [ ] **15.5: Run tests**.

- [ ] **15.6: Render preview**.

- [ ] **15.7: Wait for chart 12** (same batch).

---

## Task 16: Chart 12 — Window Finish Accuracy (Batch 7, part 3)

**Replacing matplotlib renderer.** Same shape as charts 10/11.

**Files:** charts.py (thin wrapper around `_render_hit_rate_bars`).

- [ ] **16.1: Reuse existing fixture** `12-window-finish-accuracy.json`.

- [ ] **16.2: Replace `render_window_finish_accuracy` body**

```python
def render_window_finish_accuracy(data, output_path):
    """Chart 12 — Window Finish Accuracy (HTML+SVG → PNG)."""
    _render_hit_rate_bars(
        data, output_path,
        prefix='finished',
        title='Window Finish Accuracy (Last 12 Months)',
        labels={'on_time': 'Finished On Time', 'late': 'Finished Late',
                'missed': 'Did Not Finish'},
    )
```

- [ ] **16.3: Update test class**.

- [ ] **16.4: Run tests**.

- [ ] **16.5: Render preview** (all three hit-rate charts side-by-side).

- [ ] **16.6: Bump versions for Batch 7** — `5.5.6` → `5.5.7`.

- [ ] **16.7: Commit Batch 7** — slugs `10` + `11` + `12`.

- [ ] **16.8: Render Batch 7 preview gallery**, pause for human review.

---

## Task 17: Summary report — single HTML with three sections (Batch 8)

The biggest task. Three matplotlib renderers (`render_summary_cards`, `render_summary_plan_vs_actual`, `render_summary_milestones`) plus the PIL-stitching `_composite_summary_report` collapse into **one** HTML+SVG renderer: `render_summary_report`.

**Files:**
- Modify: `scheduling/skills/schedule-update/references/charts/charts.py` (add `render_summary_report`, leave existing 3 matplotlib functions for now — Task 18 deletes them)
- Modify: `scheduling/skills/schedule-update/references/charts/render.py` (REGISTRY update)
- Modify: `scheduling/skills/schedule-update/references/charts/tests/test_render.py` (replace `TestSummaryReportComposite`)
- Create: `scheduling/skills/schedule-update/references/charts/tests/fixtures/smartpm-summary-report.json`
- Modify: `scheduling/skills/schedule-update/phases/screenshots.md`

- [ ] **17.1: Inspect SmartPM's actual summary report**

SmartPM's summary report is a separate route (not the trends page). Per the existing pipeline, it opens via the "Run Summary Report" button on the project card. Open in Chrome MCP, inspect each region:
- Top: 3 metric cards (Health Index, Schedule Performance, Schedule Feasibility)
- Middle: Planned vs Actual curve
- Bottom: Project name/milestone/location/data date header + milestones table + critical path delays/recoveries + schedule changes triplet

For each region capture: title text, font sizes, colors, layout proportions. Save inspection notes to `chart-previews/inspection-summary-report.json`.

- [ ] **17.2: Build the combined payload shape**

The single `smartpm-summary-report` slug consumes one payload that bundles all three sub-shapes:

```json
{
  "cards": {
    "health":                  {"value": 65},
    "spi":                     0.65,
    "planned_pct":             61,
    "actual_pct":              43,
    "critical_path_delay_days": 21,
    "planned_impact_days":     14,
    "quality_grade":           "B+",
    "compression_pct":         12,
    "predicted_completion":    "2027-03-15",
    "last_predicted_completion": "2027-03-08"
  },
  "curve": {
    "percentCompleteTypes": {...},
    "data": [...]
  },
  "milestones": {
    "project_name":     "...",
    "milestone_name":   "...",
    "project_location": "...",
    "data_date":        "...",
    "milestones":               [...],
    "critical_path_delays":     {"count": ..., "items": [...]},
    "critical_path_recoveries": {"count": ..., "items": [...]},
    "last_period_changes":      {"total": ..., "critical_path": ..., "acceleration_days": ...}
  }
}
```

Each sub-shape is the same as the existing per-slug payloads from the legacy matplotlib path. Build the fixture by combining the existing summary-cards / summary-curve / summary-milestones fixture contents into one JSON file at `charts/tests/fixtures/smartpm-summary-report.json`.

- [ ] **17.3: Add `render_summary_report` to charts.py**

```python
# ---- Summary Report: cards + curve + milestones in one HTML (HTML+SVG) ----

# Card layout: each section sized in pixels at SVG-equivalent dimensions.
_SR_CARDS_H      = 250
_SR_CURVE_H      = 360
_SR_MILESTONES_H = 'auto'   # sized by row count

# Palette inherits from chart-01 for curve consistency + summary-specific
# colors for cards.
_SR_BG           = '#ffffff'
_SR_CARD_BG      = '#f5f5f5'
_SR_HEALTH_GREEN = '<inspected>'
_SR_HEALTH_YELLOW = '<inspected>'
_SR_HEALTH_RED   = '<inspected>'
# ...


def render_summary_report(data, output_path):
    """Summary report — three sections (cards + curve + milestones) in one
    HTML document, rasterised to one PNG (matches the legacy
    smartpm-summary-report.png filename so the email pipeline doesn't
    change).

    Consumes a combined payload:
      {"cards": {<cards data>},
       "curve": {<curve data, MCP percent_complete_curve_v2 shape>},
       "milestones": {<milestones data>}}
    """
    cards = data.get('cards') or {}
    curve = data.get('curve') or {}
    milestones = data.get('milestones') or {}
    output_path = Path(output_path)
    html_path = output_path.with_suffix('.html')

    # Section 1: 3 metric cards
    cards_html = _summary_cards_section(cards)

    # Section 2: Planned vs Actual curve (re-uses chart-01-like rendering at
    # a slightly different size for the embedded context).
    curve_html = _summary_curve_section(curve)

    # Section 3: Project header + milestones table + bullets + last-period triplet
    milestones_html = _summary_milestones_section(milestones)

    title = 'Schedule Summary Report'
    sections_html = (
        f'<section class="sr-cards">{cards_html}</section>\n'
        f'<section class="sr-curve">{curve_html}</section>\n'
        f'<section class="sr-milestones">{milestones_html}</section>'
    )
    html_content = _summary_html_envelope(title, sections_html)
    html_path.write_text(html_content, encoding='utf-8')

    # The combined card is tall — use a larger rasterisation height.
    svg_lib.html_to_png(html_path, output_path,
                        width=svg_lib.CARD_W, height=1200, scale=svg_lib.SCALE)


def _summary_cards_section(cards):
    """Build the 3-card row HTML+SVG.

    Card 1: Project Health Index thermometer.
    Card 2: Schedule Performance (SPI + Planned/Actual bars + Critical Path Delay + Planned Impact).
    Card 3: Schedule Feasibility (Quality Grade / Compression Index / Predicted Completion).
    """
    # ... full HTML+SVG composition matching the matplotlib render_summary_cards layout
    # but rendered in HTML for typography flexibility


def _summary_curve_section(curve):
    """Build the Planned vs Actual curve HTML+SVG.

    Same series as chart 01 but with simplified markers (no Progress Target
    band needed in the summary context — the chart is showing the
    trajectory at a glance, not the planning envelope).
    """
    # ... HTML+SVG composition similar to chart 01 but at summary scale


def _summary_milestones_section(m):
    """Build the milestones header + table + bullets + triplet.

    HTML uses real <table> for the milestones grid (HTML wins for tables),
    not SVG. Header lines use bold-label + value pattern. Bullets are
    rendered as <ul>.
    """
    # ... HTML composition (no SVG needed for this section)


def _summary_html_envelope(title, sections_html):
    """Wraps the three sections in a styled HTML page, ready for Chromium
    screenshot. Different from svg_lib.html_envelope because the summary
    has its own card geometry (taller) and section-specific styling."""
    # ... full HTML envelope
```

- [ ] **17.4: Update `render.py` REGISTRY**

```python
REGISTRY = {
    '01-planned-vs-actual-percent-complete':   charts.render_planned_vs_actual_percent_complete,
    '02-schedule-quality-grade-over-time':     charts.render_schedule_quality_grade_over_time,
    '03-project-health-index-over-time':       charts.render_project_health_index_over_time,
    '04-schedule-changes-over-time':           charts.render_schedule_changes_over_time,
    '05-schedule-delay-over-time':             charts.render_schedule_delay_over_time,
    '06-end-date-variance':                    charts.render_end_date_variance,
    '07-schedule-compression-index-over-time': charts.render_schedule_compression_index,
    '08-velocity':                             charts.render_velocity,
    '09-spi-over-time':                        charts.render_spi_over_time,
    '10-activity-hit-rate':                    charts.render_activity_hit_rate,
    '11-window-start-accuracy':                charts.render_window_start_accuracy,
    '12-window-finish-accuracy':               charts.render_window_finish_accuracy,
    '13-missing-logic':                        charts.render_missing_logic,
    '14-average-total-float':                  charts.render_average_total_float,
    '15-high-total-float':                     charts.render_high_total_float,
    '16-critical-path-percentage':             charts.render_critical_path_percentage,
    'smartpm-summary-report':                  charts.render_summary_report,
}
```

Delete the entries for `smartpm-summary-cards`, `smartpm-summary-curve`, `smartpm-summary-milestones`.

- [ ] **17.5: Delete `_composite_summary_report` from render.py**

The PIL-stitching function is dead — the single HTML renders to one PNG directly. Delete the function plus the call site (look for `composite = _composite_summary_report(...)` and `if composite is not None: ...` in `render_payload`).

- [ ] **17.6: Update test_render.py**

Replace `TestSummaryReportComposite` with `TestSummaryReport`:

```python
@unittest.skipIf(shutil.which('node') is None,
                 'node executable not on PATH — HTML→PNG rasterisation needs it')
class TestSummaryReport(unittest.TestCase):
    """Summary report — one HTML, three sections, one PNG. Replaces the
    PIL-stitched 3-PNG composite."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / 'smartpm-summary-report.png'
        self.html = self.output.with_suffix('.html')
        self.data = json.loads(
            (FIXTURE_DIR / 'smartpm-summary-report.json').read_text()
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_html_with_three_sections(self):
        original = charts._html_to_png
        try:
            charts._html_to_png = lambda *a, **kw: None
            charts.render_summary_report(self.data, str(self.output))
        finally:
            charts._html_to_png = original

        self.assertTrue(self.html.exists())
        body = self.html.read_text(encoding='utf-8')
        for section in ('sr-cards', 'sr-curve', 'sr-milestones'):
            self.assertIn(section, body, f'missing section: {section}')
        # Curve palette colors (carried from chart 01).
        self.assertIn('#388543', body)  # Scheduled Completion green

    def test_full_pipeline_writes_png_via_chromium(self):
        try:
            charts.render_summary_report(self.data, str(self.output))
        except RuntimeError as e:
            msg = str(e)
            if 'Playwright is not installed' in msg or 'Executable doesn' in msg:
                self.skipTest(msg.splitlines()[0])
            raise

        self.assertTrue(self.output.exists())
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')
        # Summary report is TALL, not wide (matches the matplotlib composite).
        # Height should exceed width.
        self.assertGreater(img.height, img.width * 0.5)
        img.close()
```

- [ ] **17.7: Run tests** — full suite. Confirm:
  - `TestSummaryReport` (new) passes.
  - All chart tests still pass.
  - svg_lib tests still pass.

- [ ] **17.8: Render preview** — open the summary PNG, compare against current matplotlib composite.

- [ ] **17.9: Update phases/screenshots.md**

In Step 3 (Fetch + write payload JSONs), remove the three sub-recipes (`smartpm-summary-cards`, `smartpm-summary-curve`, `smartpm-summary-milestones`) and add one combined recipe:

```markdown
##### `smartpm-summary-report`

Three MCP calls combined into one payload:

\`\`\`
# Section 1: metric cards
cards_resp = smartpm_post_project_summary(
    projectId=project_id,
    scenarioId=default_scenario_id,
    columns=[...])

# Section 2: planned-vs-actual curve
curve_resp = smartpm_get_scenario_percent_complete_curve_v2(
    projectId=project_id, scenarioId=default_scenario_id)

# Section 3: milestones + change log
milestones_resp = ... (see legacy summary-milestones recipe — unchanged)

payload = {
    "cards":      map_cards(cards_resp),
    "curve":      curve_resp,
    "milestones": milestones_resp,
}
\`\`\`
```

Remove the "Summary-report composite" note from Step 4 (no PIL stitching anymore).

- [ ] **17.10: Test the orchestrator end-to-end**

```bash
mkdir -p /tmp/test-summary/payload
cp scheduling/skills/schedule-update/references/charts/tests/fixtures/smartpm-summary-report.json /tmp/test-summary/payload/

cd scheduling/skills/schedule-update/references
python -m charts.render /tmp/test-summary/payload /tmp/test-summary/out

ls /tmp/test-summary/out/
```

Expected: only `smartpm-summary-report.html` + `smartpm-summary-report.png` in `/tmp/test-summary/out/` (no separate cards/curve/milestones PNGs).

- [ ] **17.11: Render against a second project**

To confirm the renderer handles variance, build a `smartpm-summary-report.json` payload for a different Westland project (any project from `smartpm_list_projects`). Render and eyeball. If it breaks (e.g., a project with a very long milestone name, or one with no critical-path delays), fix the renderer.

- [ ] **17.12: Bump versions for Batch 8** — `5.5.7` → `5.5.8`.

- [ ] **17.13: Commit Batch 8**

```bash
git commit -m "$(cat <<'EOF'
refactor(scheduling): HTML+SVG summary report — one HTML, three sections

Collapses three matplotlib renderers (cards, curve, milestones) plus
PIL stitching into a single HTML+SVG renderer (render_summary_report)
that emits one PNG at the legacy smartpm-summary-report.png filename.
Email pipeline unchanged.

REGISTRY in render.py updated; _composite_summary_report deleted;
phases/screenshots.md collapses the three sub-recipes into one.
The matplotlib renderers (render_summary_cards, render_summary_plan_vs_actual,
render_summary_milestones) stay in place for one more batch — final
cleanup deletes them along with matplotlib + numpy.

Batch 8 of 8. See [the migration spec](docs/superpowers/specs/2026-05-21-html-svg-chart-migration-design.md).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **17.14: Render summary preview against 3 production projects**

Per the spec's Risk 7 mitigation: "delete the --legacy branch only in the FINAL cleanup commit, after all 16 charts plus the summary report have rendered against real production data from at least 3 different Westland projects."

Pick 3 projects from `smartpm_list_projects`. For each:
1. Build the combined payload (per 17.2)
2. Render via `render_summary_report`
3. Confirm visual quality (no overflow, all sections render, palette correct)

Save the previews to `chart-previews/<PROJECT>-summary-report.png`. If any project breaks the renderer, fix and re-test before proceeding to Task 18.

- [ ] **17.15: Pause for human review**

Show the user the 3 production previews + all 16 trend chart previews. Get explicit "ship it" before Task 18 (cleanup) — the cleanup deletes the matplotlib + legacy Playwright safety nets.

---

## Task 18: Cleanup — delete matplotlib + legacy Playwright capture

All chart renderers now emit HTML+SVG. The matplotlib code is dead weight; the legacy `--legacy` Playwright path is no longer needed (no chart slugs are stubs). Final commit removes both.

**Files:**
- Modify: `scheduling/skills/schedule-update/references/charts/charts.py` (delete dead code)
- Modify: `scheduling/skills/schedule-update/references/charts/requirements.txt` (drop deps)
- Modify: `scheduling/skills/schedule-update/references/charts/tests/test_render.py` (delete `TestNonDefaultStubs`)
- Modify: `scheduling/skills/schedule-update/phases/screenshots.md` (delete `--legacy` section)
- Delete: `scheduling/skills/schedule-update/references/smartpm/capture-smartpm.js`
- Modify: `scheduling/skills/schedule-update/references/smartpm/smartpm-client.js` (delete chart-capture functions)
- Modify: `scheduling/skills/schedule-update/references/tests/smartpm.spec.js` (delete chart-capture tests)

- [ ] **18.1: Delete matplotlib imports from charts.py**

Top of `charts.py`:

```python
# DELETE these lines:
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.dates import DateFormatter
from matplotlib.patches import FancyBboxPatch, Rectangle

from . import style    # DELETE if `style` is no longer used anywhere

# KEEP these:
import html as _html_lib
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path

from . import svg_lib
```

- [ ] **18.2: Delete dead matplotlib helpers from charts.py**

Search for and delete:
- The `_VEL_*` velocity palette constants block (matplotlib palette)
- The `_SMARTPM_RED`, `_SMARTPM_PINK_FILL`, `_SMARTPM_GREEN_FILL`, `_SMARTPM_LABEL_BG` constants (matplotlib palette)
- The `_SCI_*` compression-index palette constants (matplotlib palette)
- The `_SPI_*` SPI threshold constants (matplotlib palette)
- The `_render_hit_rate_chart` matplotlib helper (replaced by `_render_hit_rate_bars` in HTML+SVG)
- The `_render_window_accuracy_chart` matplotlib helper (ditto)
- The `_PVA_*` summary palette constants (matplotlib)

Keep all the `_PVA0X_*` palette constants for the HTML+SVG charts.

- [ ] **18.3: Delete matplotlib summary renderers**

Delete the functions `render_summary_plan_vs_actual`, `render_summary_cards`, `render_summary_milestones` from charts.py. They were only used by the old composite path; `render_summary_report` replaces all three.

- [ ] **18.4: Delete `_stub` factory + remaining stub bindings**

All 8 chart-NN stub bindings should already be gone (replaced by real renderers in Tasks 1-8). The `_stub` factory function itself is now unused — delete it.

- [ ] **18.5: Drop matplotlib + Pillow from requirements.txt**

Edit `scheduling/skills/schedule-update/references/charts/requirements.txt`:

```
# Before:
matplotlib>=3.8
Pillow>=10.0

# After:
# (empty file, or just a comment explaining the chart renderer has no Python deps)
```

Check whether Pillow is still imported anywhere in the charts/ tree:

```bash
cd scheduling/skills/schedule-update
grep -r 'from PIL' references/charts/ || echo "no PIL imports remain"
grep -r 'import PIL' references/charts/ || echo "no PIL imports remain"
```

If imports remain (most likely the chart-test PNG validation uses `Image.open`), keep `Pillow>=10.0`. Otherwise drop it.

- [ ] **18.6: Delete `TestNonDefaultStubs` from test_render.py**

No more stubs exist; the test class is dead. Delete the entire `class TestNonDefaultStubs(...)` block.

- [ ] **18.7: Delete chart-capture from smartpm-client.js**

In `references/smartpm/smartpm-client.js`, delete:
- `captureSummaryReport` function
- `captureTrendGraphs` function
- `captureAll` function (orchestrator)
- `CHART_NAMES` and `WIDE_CHART_INDICES` constants
- Module exports for the above

Keep:
- `launchContext`, `loginIfNeeded`, `gotoProjectsCards`, `findProjectCard`, `isLoginPage`, `normalizePath`, `PROFILE_DIR`, `NAVIGATION_TIMEOUT` — these are general SmartPM-page-navigation helpers; they may be useful elsewhere.

If after the deletion nothing else uses `smartpm-client.js`, delete the whole file (and `capture-smartpm.js`). Otherwise just trim.

- [ ] **18.8: Delete `capture-smartpm.js`**

The CLI entry point for the legacy chart capture. No callers anymore.

```bash
git rm scheduling/skills/schedule-update/references/smartpm/capture-smartpm.js
```

- [ ] **18.9: Delete chart-capture tests from smartpm.spec.js**

Edit `references/tests/smartpm.spec.js`. Delete:
- `test('@smoke captures the Summary Report screenshot', ...)`
- `test('@smoke captures all 16 trend graphs', ...)`

Keep the login + project-card lookup tests (these still serve the smartpm-client helpers that remain).

If after deletion the spec file has no tests, delete it entirely along with the chart-capture-only Playwright config.

- [ ] **18.10: Update phases/screenshots.md — remove `--legacy` section**

Remove the entire "two paths" framing — there's only one path now. Specifically:
- Delete the table at the top showing the legacy/MCP path comparison.
- Delete the `--legacy` invocation documentation.
- Delete the "Non-default slugs" subsection (no stubs remain).
- Update the default `graph_screenshots` list to include all 16 trend slugs + `smartpm-summary-report`.
- Confirm every slug in the default list has a recipe in the "Recipe per slug" section.

- [ ] **18.11: Run the full test suite, confirm green**

```bash
cd scheduling/skills/schedule-update/references
python -m unittest discover -s charts/tests -v 2>&1 | tail -10
```

Expected: every test class for every chart passes (17 chart classes + svg_lib + orchestrator = ~20 test classes, ~40 tests).

- [ ] **18.12: Smoke-test the full pipeline end-to-end**

Run the orchestrator against a real payload directory:

```bash
mkdir -p /tmp/test-full/payload
# Populate /tmp/test-full/payload/ with one JSON per slug from charts/tests/fixtures/
for slug in 01-planned-vs-actual-percent-complete 02-schedule-quality-grade-over-time \
            03-project-health-index-over-time 04-schedule-changes-over-time \
            05-schedule-delay-over-time 06-end-date-variance \
            07-schedule-compression-index-over-time 08-velocity 09-spi-over-time \
            10-activity-hit-rate 11-window-start-accuracy 12-window-finish-accuracy \
            13-missing-logic 14-average-total-float 15-high-total-float \
            16-critical-path-percentage smartpm-summary-report; do
  cp scheduling/skills/schedule-update/references/charts/tests/fixtures/$slug.json /tmp/test-full/payload/
done

cd scheduling/skills/schedule-update/references
python -m charts.render /tmp/test-full/payload /tmp/test-full/out

ls /tmp/test-full/out/ | wc -l
```

Expected: 34 files (17 .html + 17 .png), no errors, JSON output shows all 17 slugs in `rendered` and an empty `failed` list.

- [ ] **18.13: Bump versions for cleanup** — `5.5.8` → `5.6.0` (minor bump — major migration completes; removes the entire matplotlib path).

- [ ] **18.14: Commit cleanup**

```bash
git add scheduling/skills/schedule-update/references/charts/charts.py \
        scheduling/skills/schedule-update/references/charts/requirements.txt \
        scheduling/skills/schedule-update/references/charts/render.py \
        scheduling/skills/schedule-update/references/charts/tests/test_render.py \
        scheduling/skills/schedule-update/references/smartpm/smartpm-client.js \
        scheduling/skills/schedule-update/references/tests/smartpm.spec.js \
        scheduling/skills/schedule-update/phases/screenshots.md \
        scheduling/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json

git rm scheduling/skills/schedule-update/references/smartpm/capture-smartpm.js

git commit -m "$(cat <<'EOF'
chore(scheduling): delete matplotlib + legacy Playwright capture path

Final cleanup of the HTML+SVG chart migration. Removes:

- matplotlib + numpy imports and all matplotlib render functions in
  charts.py (chart renderers, summary parts, helpers).
- Pillow if no longer imported by tests.
- _composite_summary_report and _stub helpers (no longer used).
- Legacy chart-capture code: capture-smartpm.js (deleted),
  capture-related functions in smartpm-client.js (trimmed),
  chart-capture tests in smartpm.spec.js (trimmed).
- The --legacy invocation in phases/screenshots.md and the
  non-default-stubs section (no stubs remain).

The schedule-update pipeline now has one chart-rendering path:
MCP fetch → Python HTML+SVG → Chromium PNG. Visually consistent
with SmartPM's web rendering across all 17 artifacts. No more
dashed-line drop, no more clipped-screenshot subpixel bugs.

Closes the HTML+SVG chart migration. See [the migration spec](docs/superpowers/specs/2026-05-21-html-svg-chart-migration-design.md).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **18.15: Final smoke test**

Open a fresh terminal, navigate to a real Westland project's Schedules folder, run the weekly schedule update for that project, confirm:
- The `screenshots` phase produces 17 PNGs in `{dated_folder}/screenshots/`.
- All PNGs render correctly (no broken images, no missing dashes, no empty regions).
- The email-preview HTML embeds the new screenshots and looks right.
- The Outlook draft `.eml` shows the right images.

If any of these fail, the migration isn't done — fix and re-commit before declaring victory.

- [ ] **18.16: Merge to main**

Per the repo CLAUDE.md release convention: push the feature branch, open a PR, get review, merge to main. After merge, in the main checkout:

```bash
cd "<main checkout, not worktree>"
git switch main
git pull --ff-only
python build.py scheduling
```

The `python build.py scheduling` rebuilds `src/scheduling.zip` for the enterprise distribution.

---

## Self-Review Notes

Before handing off this plan for execution, run this check:

**Spec coverage:**
- ✅ Goal 1 (17 HTML+SVG artifacts): Tasks 1-8 (charts 02-05, 13-16) + 10-16 (charts 06-12) + 17 (summary) = 16 trends + 1 summary
- ✅ Goal 2 (no email pipeline changes): Task 17 keeps filename; Task 18 doesn't touch email pipeline
- ✅ Goal 3 (matplotlib gone): Task 18.1, 18.2, 18.3, 18.5
- ✅ Goal 4 (`--legacy` gone): Task 18.7-18.10
- ✅ Goal 5 (svg_lib factored): Task 9
- ✅ Risk 7 (3-project validation before --legacy delete): Task 17.14

**Type consistency:**
- `svg_lib.html_to_png` (snake_case in Task 9.1) — used by all post-refactor renderers and the summary report. Matches.
- `_html_to_png` (existing _PVA01 path, Task 0): renamed to `svg_lib.html_to_png` in Task 9.4. After 9.4, all references should be the new name.
- `svg_lib.series_pts` signature: `(rows, field, dmin, dmax, x0, x1, y0, y1, p_min=0.0, p_max=100.0)` — extended with p_min/p_max vs chart-01 original. Chart-01 callers pass only the first 8 args; new charts use p_min/p_max for non-percent Y-axes (SPI 0-1.3, total float days, etc.).

**Placeholder scan:**
- All chart-NN palette constants are intentional placeholders filled by the inspection step that precedes them. Each chart task's step 1 (Chrome MCP inspection) explicitly captures these values. Not "TBD" in the bad sense — they're "captured-by-prior-step values".
- Step 5.2 mentions "the trend may be in get_scenario_schedule_quality_trend" — the exact tool name to be confirmed via `ToolSearch` in step 5.2. Acceptable: the step instructs an explicit lookup.

Plan checked. Ready to execute.
