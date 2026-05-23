# HTML+SVG chart migration — phase out matplotlib

> **Status: SUPERSEDED 2026-05-21** by [2026-05-21 HTML+SVG chart migration (TypeScript)](2026-05-21-html-svg-chart-migration-typescript-design.md).
>
> The four Python renderers committed under this spec (chart 01 in `b6a58ee`, chart 02 fix in `d26fe78`, chart 03 in `b707b79`, chart 04 in `1ea9b22`) stay on the branch as a visual-contract reference during the TS port. They're removed wholesale in the TS-spec's 12th cleanup commit, along with all matplotlib code and the legacy `--legacy` Playwright SmartPM-capture path. The decision to pivot to TypeScript was driven by a separate branch that wraps these renderers in a Deno-based Supabase Edge Function — keeping Python would have forced a second hosting service. The visual contract per chart does not change; the runtime/language does.

**Date:** 2026-05-21
**Branch:** `blissful-tharp-ad03c2` → `feat/html-svg-chart-migration`
**Plugin scope:** `scheduling` (chart renderer rewrite + phase doc updates + matplotlib removal)
**Builds on:** [2026-05-19 MCP-driven schedule charts](2026-05-19-mcp-driven-schedule-charts-design.md). That spec replaced Playwright capture with MCP fetch + matplotlib render; this one replaces matplotlib with HTML+SVG cloned from SmartPM's Highcharts CSS.

## Motivation

Two problems with the current matplotlib path drove this.

1. **Visual inconsistency with SmartPM.** The matplotlib charts are "SmartPM-feeling" — same intent, different rendering. Side-by-side they look like siblings, not twins. Westland's boss wants the emailed report to render the same way it looks on SmartPM's site so colleagues see one consistent visual language.

2. **The dashed-line bug.** Charts that fell back to the legacy Playwright capture path (`screenshots --legacy`) were losing `stroke-dasharray` on element-clipped screenshots. The dashed green Scheduled Completion line on chart 01 disappeared on the SGRWRF capture (2026-05-21). This is a Playwright/Chromium subpixel-clip issue that can't be reliably fixed at the capture layer.

Chart 01 (`01-planned-vs-actual-percent-complete`) was migrated in this branch as a proof-of-concept: HTML+SVG document with palette and dash patterns copied directly off SmartPM's Highcharts SVG (Chrome MCP inspection on 2026-05-21), rasterised to PNG via a fresh headless Chromium pass (no element clip). Output is pixel-faithful to SmartPM. This spec generalises that approach to every remaining chart.

## Goals

1. **17 HTML+SVG artifacts** replace every existing matplotlib renderer:
   - 16 trend chart slugs (`01-planned-vs-actual-percent-complete` … `16-critical-path-percentage`), each emitting a sibling `.html` + `.png` pair.
   - 1 summary report slug (`smartpm-summary-report`), a single HTML document with three vertically-stacked sections (cards + curve + milestones) rasterised to one PNG.
2. **No changes to the email pipeline.** Output filenames stay the same so `generate_email_preview_html.py`, `generate_email_eml.py`, the Procore upload step, and the carry-forward archive don't change.
3. **matplotlib is gone at the end.** `matplotlib` and `numpy` removed from `charts/requirements.txt`. All matplotlib imports removed from `charts/charts.py`. No dual-render path; one way to render.
4. **Legacy Playwright capture (`--legacy`) is also removed at the end.** With HTML+SVG covering every chart, the escape hatch is no longer needed; keeping it would mean maintaining the dashed-line bug in perpetuity.
5. **Shared SVG plumbing factored out** into `charts/svg_lib.py` so per-chart renderers stay focused on visual decisions (palette, axis ranges, series ordering) and reuse the boring infrastructure (HTML envelope, marker glyphs, scale helpers, Catmull-Rom smoother, `html_to_png` shell-out).

## Non-goals (out of scope)

- Reshaping the email body, carry-forward, Procore steps, or archive markdown.
- Re-resolving `smartpm_project_name` / `scenario_id` from the project name (out of scope here, tracked separately).
- Building anything Cowork-specific. Works equally in Claude Code CLI and Cowork.
- Replacing the "SmartPM might still be processing" 30-minute wait — same upstream, same wait.
- Adding hover tooltips, zoom, or other interactive features to the HTML artifacts. They're rendered for screenshot purposes; interactivity adds maintenance burden without payback.

## Architecture

### Per-chart trend renderers (16 charts)

Same pattern chart 01 already uses:

```
def render_<slug>(data: dict, output_path: str | Path) -> None:
    # 1. validate / extract series from MCP-response-shaped dict
    # 2. build SVG inner markup (lines, markers, axes, plotlines, band)
    # 3. wrap in HTML envelope via svg_lib.html_envelope(...)
    # 4. write sibling .html
    # 5. svg_lib.html_to_png(html_path, png_path, ...)
```

The MCP-response shape is the canonical input — no pre-processing in the orchestrator (`render.py`), no shape translation. Whatever the SmartPM MCP endpoint returns is what the renderer reads. (This is the same payload-passthrough rule as the existing matplotlib path.)

Each renderer owns its own palette constants, axis ranges, and series ordering. Duplication where it matters (per-chart tweakability is the whole point); shared infrastructure for the boring SVG plumbing.

### Summary report (one HTML, three sections)

The current implementation renders three separate matplotlib PNGs (`smartpm-summary-cards`, `smartpm-summary-curve`, `smartpm-summary-milestones`) and PIL-stitches them into `smartpm-summary-report.png`. The replacement:

```
def render_summary_report(data: dict, output_path: str | Path) -> None:
    # data shape: {
    #     "project_name": str, "milestone_name": str, ...,
    #     "cards":      {<smartpm-summary-cards payload>},
    #     "curve":      {<smartpm-summary-curve payload>},
    #     "milestones": {<smartpm-summary-milestones payload>},
    # }
    # Single HTML with three <section>s, single SVG per section (or HTML/SVG mix
    # for the milestones table), one Chromium screenshot of the whole card.
```

The three separate slugs collapse into one: `smartpm-summary-report`. The PIL-stitching helper `_composite_summary_report` in `render.py` is deleted. `phases/screenshots.md` updates to fetch all three sub-payloads under the single `smartpm-summary-report` slug.

The output PNG filename stays `smartpm-summary-report.png` so the email pipeline's `summary_screenshot_path` consumer doesn't change.

### Shared SVG plumbing (`charts/svg_lib.py`)

Factored out of the existing `_pva01_*` helpers in `charts.py`:

```
svg_lib.html_envelope(title, svg_w, svg_h, svg_inner, legend_html, *,
                      card_w, card_h)  -> str
svg_lib.html_to_png(html_path, png_path, *, width, height, scale)  -> None

# Geometry
svg_lib.date_to_x(d, dmin, dmax, x0, x1)  -> float
svg_lib.pct_to_y(p, y0, y1)               -> float
svg_lib.smooth_path(pts)                  -> str  # Catmull-Rom → cubic Bezier
svg_lib.x_ticks(dmin, dmax, max_ticks=10) -> list[date]
svg_lib.series_pts(rows, field, dmin, dmax, x0, x1, y0, y1) -> list[tuple]

# Glyphs
svg_lib.marker(kind, x, y, color, size=4) -> str
svg_lib.legend_item(kind, color, dash, label) -> str
```

Each per-chart renderer imports svg_lib and supplies its own palette and SVG composition. `charts.py` becomes a tighter file: per-chart render functions + per-chart palette constants only.

`svg_lib.py` is the only place we touch HTML and Chromium plumbing. Per-chart code stops mentioning `html_to_png.js` or font loading or Chromium scale factors — that's all svg_lib's responsibility.

### Renderer registry (`charts/render.py`)

The `REGISTRY` dict in `render.py` shrinks. Today (post-chart-01):

```
REGISTRY = {
    '01-planned-vs-actual-percent-complete': charts.render_planned_vs_actual_percent_complete,
    '02-schedule-quality-grade-over-time':    charts.render_schedule_quality_grade_over_time,  # stub
    ...
    'smartpm-summary-cards':       charts.render_summary_cards,        # matplotlib
    'smartpm-summary-curve':       charts.render_summary_plan_vs_actual,  # matplotlib
    'smartpm-summary-milestones':  charts.render_summary_milestones,    # matplotlib
}
```

After this migration:

```
REGISTRY = {
    '01-planned-vs-actual-percent-complete':   charts.render_planned_vs_actual_percent_complete,
    '02-schedule-quality-grade-over-time':     charts.render_schedule_quality_grade_over_time,
    ...
    '16-critical-path-percentage':             charts.render_critical_path_percentage,
    'smartpm-summary-report':                  charts.render_summary_report,
}
```

17 entries. No stubs. No matplotlib references. `_composite_summary_report` deleted from `render.py`.

## Migration plan (8 batches + refactor + cleanup)

Each batch is its own commit + plugin version bump (semver patch). Per-batch flow: inspect SmartPM DOM via Chrome MCP → confirm MCP endpoint → write fixture (real project data, ideally SGRWRF for trend continuity) → write renderer + tests → render preview to `chart-previews/` → human review → commit.

| Batch | Slugs | Shape notes | MCP endpoint |
|---|---|---|---|
| 1 | `02-schedule-quality-grade-over-time`, `03-project-health-index-over-time` | Line + threshold bands. Similar to existing SPI chart. | `smartpm_get_scenario_schedule_quality` trend, `smartpm_get_scenario_project_health_trend` |
| 2 | `04-schedule-changes-over-time`, `05-schedule-delay-over-time` | Likely bars (per-period change counts) + line (delay days). | `smartpm_list_scenario_change_log_by_type`, `smartpm_get_scenario_delay` (trend) |
| 3 | `13-missing-logic`, `14-average-total-float` | Bar count + line. Confirm shapes via DOM inspection. | TBD via inspection |
| 4 | `15-high-total-float`, `16-critical-path-percentage` | Line / percent area. | TBD via inspection |
| **Refactor** | Extract `svg_lib.py`, migrate chart 01 + the 8 new charts onto it | No visual change; renderers shrink. Add unit tests for svg_lib geometry helpers. | — |
| 5 | `06-end-date-variance`, `07-schedule-compression-index-over-time` | Visual upgrade from matplotlib → HTML+SVG. Re-inspect SmartPM DOM since matplotlib was an approximation. | `smartpm_list_scenario_schedules_v2` (06 already wired), `smartpm_get_scenario_schedule_compression_trend` |
| 6 | `08-velocity`, `09-spi-over-time` | Velocity is the complex 6-bar + average-line chart; budget extra inspection. SPI is simple. | `smartpm_get_scenario_velocity`, `smartpm_get_scenario_spi_trend` |
| 7 | `10-activity-hit-rate`, `11-window-start-accuracy`, `12-window-finish-accuracy` | The hit-rate trio shares a stacked-bar shape. Migrate together to share work. | `smartpm_get_scenario_should_start_finish_trend` for all three |
| 8 | `smartpm-summary-report` (3 sections in 1 HTML) | The big one. Section layout: cards (top, ~250px), curve (middle, ~360px), milestones table (bottom, sized by row count). Single Chromium screenshot. | Three calls: `smartpm_post_project_summary` (cards), `smartpm_get_scenario_percent_complete_curve_v2` (curve), `smartpm_post_project_summary` per milestone + `smartpm_list_scenario_change_log_by_type` (milestones) — bundled into one payload. |
| **Cleanup** | Delete matplotlib code, drop deps, update phase docs, remove `--legacy` | See below | — |

### Cleanup commit (final)

- Delete `_stub` factory and all `_stub(...)` lines in `charts.py`.
- Delete every `matplotlib`, `numpy`, `mdates`, `mticker`, `LineCollection`, `DateFormatter`, `FancyBboxPatch`, `Rectangle` import from `charts.py`.
- Delete `_composite_summary_report` from `render.py` (the PIL-stitching helper is no longer needed).
- Remove `matplotlib` and `numpy` lines from `charts/requirements.txt`. Confirm `Pillow` (PIL) is still needed elsewhere; if not, drop it too.
- Delete the legacy Playwright capture path. Specifically:
  - `smartpm/capture-smartpm.js` and `smartpm/smartpm-client.js` get evaluated — the parts that handle SmartPM auth + project lookup may still be useful elsewhere; the chart-screenshot code goes.
  - `phases/screenshots.md` loses the `--legacy` branch entirely.
  - `references/tests/smartpm.spec.js` loses the chart-screenshot tests (auth/login tests may stay if there's another consumer).
- Update `phases/screenshots.md`:
  - Remove the "non-default slugs / `--legacy` fallback" subsection.
  - Document the per-chart MCP-endpoint recipes for all 16 trends + the summary report.
  - Update the default `graph_screenshots` list to include all 16 trends.
- Update `scheduling/CLAUDE.md` if needed (the "drive existing scripts, not wrappers" guidance still applies; nothing structural changes).
- Bump `scheduling/.claude-plugin/plugin.json` + matching `marketplace.json` entry for the cleanup commit.

## Testing strategy

### Per-chart tests

Each chart gets two tests in `charts/tests/test_render.py`, matching chart 01's pattern:

1. **HTML contract test (fast, no Chromium).** Stub out `svg_lib.html_to_png` to a no-op, call the renderer, assert the generated HTML contains:
   - All series colors expected for that chart (palette regression).
   - The exact `stroke-dasharray` patterns SmartPM uses (the dashed-line-bug regression).
   - Each legend label text.
   - The chart title verbatim.

2. **Chromium smoke test (slow, end-to-end).** Class-skipped if `node` isn't on PATH; individually skipped if Playwright/Chromium isn't installed. Calls the renderer, asserts PNG written, asserts `>5KB`, asserts wide aspect (`width > height * 1.8`).

### svg_lib unit tests

`charts/tests/test_svg_lib.py` (new file) covers:
- `date_to_x` / `pct_to_y` boundary conditions (dmin == dmax, p < 0, p > 100).
- `smooth_path` with 0, 1, 2, 3, n points.
- `x_ticks` with various date spans (7 days, 90 days, 5 years).
- `marker` for each kind (circle, square, diamond, triangle, invtri).
- `html_envelope` produces valid HTML5 with no `<script>` tag (rasterisation must work with JS disabled).

### Regression tests stay

The existing `TestRenderPayload`, `TestSummaryReportComposite`, and `TestNonDefaultStubs` tests in `test_render.py` either stay or get updated:
- `TestRenderPayload` empty-payload + unknown-slug tests stay.
- `TestSummaryReportComposite` retargets to assert the **single** summary slug produces a single PNG at the right filename (no PIL stitching).
- `TestNonDefaultStubs` gets deleted entirely — no stubs remain.

## Risks & mitigations

**1. Chart shape variety.** The hit-rate trio (10/11/12) is stacked bars; velocity (08) is 6-series bars + average line; missing logic (13) might be a single-series bar + threshold. Each shape needs its own DOM inspection. *Mitigation:* budget 30-45 min per chart for inspection + render + tweak. The batched cadence (2-3 charts per session, human review between batches) naturally surfaces visual misses early.

**2. Summary report HTML layout.** Three sections in one HTML means typography + spacing decisions across sections. *Mitigation:* keep section dimensions matching the current matplotlib output (12in × 144dpi = 1728px wide × proportional heights) so the email layout doesn't shift. Renders preview to `chart-previews/` for direct visual comparison against today's matplotlib summary.

**3. Chromium rasterisation flakiness.** Font loading is the usual culprit. `html_to_png.js` already awaits `document.fonts.ready`. *Mitigation:* keep that. If new failure modes show up per chart, debug at the renderer level (smaller surface than the legacy capture-page-and-clip).

**4. svg_lib refactor breaks chart 01.** The refactor batch migrates chart 01 onto `svg_lib`. *Mitigation:* the chart-01 HTML contract test catches any regression in palette or dasharray; the Chromium smoke test catches any rasterisation failure. The refactor commit must not change the chart-01 PNG visually — if it does, the smoothing or geometry math has drifted.

**5. Velocity chart (batch 6) — the worst case.** Six bar series stacked side-by-side with offset positions plus an orange average line and a vertical data-date marker. Highcharts handles the bar grouping natively; hand-rolling SVG bars + positioning is the most code per chart in the migration. *Mitigation:* if it grows past ~400 lines, factor a `svg_lib.grouped_bars(...)` helper as part of that batch.

**6. Hit-rate trio (batch 7) — shape repetition.** Three charts with the same stacked-bar shape (Total / Started / Finished × On-Time / Late / Missed). *Mitigation:* implement once as a shared `_render_hit_rate(data, output_path, *, prefix, title, labels)`, then three thin wrappers — same pattern as the current matplotlib `_render_hit_rate_chart` + `_render_window_accuracy_chart` helpers.

**7. Premature commitment to deleting Playwright capture.** If the HTML+SVG path has an unanticipated blocker on some specific project (e.g., a project with too many data points to render readably), the legacy path is the escape hatch. *Mitigation:* delete the `--legacy` branch only in the FINAL cleanup commit, after all 16 charts plus the summary report have rendered against real production data from at least 3 different Westland projects (SGRWRF + 2 others, picked during batch 8).

## Open questions

None. All architectural choices were resolved in brainstorming on 2026-05-21.

## What "done" looks like

- All 17 chart renderers in `charts/charts.py` emit HTML+SVG (no matplotlib imports anywhere in the file).
- `charts/svg_lib.py` contains the shared plumbing; no per-chart code mentions Chromium or `html_to_png.js`.
- `charts/requirements.txt` has no `matplotlib` or `numpy` lines.
- `phases/screenshots.md` documents one rendering path; the `--legacy` section is gone.
- `chart-previews/` (gitignored) has fresh PNGs for all 17 artifacts against at least 3 production projects, visually compared against SmartPM's web rendering and judged faithful.
- The weekly schedule update on a Westland project (one full run) ships the new PNGs to colleagues without complaint.

When the dust settles, a future engineer touching one chart's visuals will edit one `render_<slug>` function, see only that chart's palette and series ordering, and re-render to verify. They will never see matplotlib code, will never need to think about Playwright element-clipping, and will never re-encounter the dashed-line bug.
