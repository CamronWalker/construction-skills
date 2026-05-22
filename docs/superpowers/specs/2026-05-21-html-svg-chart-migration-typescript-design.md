# HTML+SVG chart migration — TypeScript port

**Date:** 2026-05-21
**Branch:** `claude/blissful-tharp-ad03c2` → `feat/html-svg-chart-migration`
**Plugin scope:** `scheduling` (chart renderer rewrite + phase doc updates + matplotlib + Playwright-capture removal)
**Supersedes:** [2026-05-21 HTML+SVG chart migration (Python)](2026-05-21-html-svg-chart-migration-design.md). That spec migrated the matplotlib charts to a Python `charts.py` → HTML+SVG → Chromium pipeline. This spec pivots the renderers to TypeScript so a Deno-based Supabase Edge Function (separate branch) can consume them server-side without standing up a second hosting service for Python.

## Motivation

A separate branch wraps a browser-based draft editor around these chart renderers, backed by a Supabase Edge Function. Supabase Edge runs Deno-only. Keeping the renderers in Python would force the cloud editor to either (a) stand up a Python hosting service (Vercel, Render, Cloud Run) just to call them or (b) reimplement the renderers itself, drifting from the local CLI.

TypeScript lets one codebase serve both consumers:

- **Local Node CLI** — invoked from `phases/screenshots.md` to write `{slug}.html` + `{slug}.png` next to each other for the email pipeline. Same observable contract as the Python `render.py` it replaces.
- **Deno-side cloud function** — imports the same registry, calls `renderXyz(payload)` to get back `{ html, svgInner }`, ships the HTML chunks to the browser editor.

The visual contract — SmartPM Highcharts CSS pixel-for-pixel, palette + dasharray pulled off the live DOM via Chrome MCP — does not change. This is a runtime/language pivot, not a redesign.

## What's already on this branch

Four Python renderers already shipped, plus the rasteriser. Read these as the visual-contract reference before porting:

| Commit  | Slug                                            | Status after pivot                                                                                                          |
|---------|-------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|
| `b6a58ee` | `01-planned-vs-actual-percent-complete`         | Port to TS. `_pva01_*` helpers become `svg-lib.ts`.                                                                          |
| `d26fe78` | `02-schedule-quality-grade-over-time`           | Port to TS. Single `#2caffe` line, categorical letter-grade Y, no bands, no legend, ™ in title.                              |
| `b707b79` | `03-project-health-index-over-time`             | Port to TS. Single `#2caffe` line + `#1AA462` GOOD circle markers, auto-fit numeric % Y.                                     |
| `1ea9b22` | `04-schedule-changes-over-time`                 | Port to TS. 7 spline series with verified palette; "Total Activities" column dropped (MCP does not expose it).               |

The intermediate broken-palette commit (`12f78fb`) for chart 02 was fixed in `d26fe78`; only port the fix.

`charts/html_to_png.js` (Node + Playwright) stays as-is — the cloud Deno path ships HTML to the browser directly and doesn't need it; the Node CLI continues to use it for local PNG rasterisation.

`chart-previews/SGRWRF-0{1,2,3,4}-*.png` are gitignored throwaway artifacts from the Python port. Re-render with TS and visually diff against them as each port lands.

## Goals

1. **17 TypeScript chart renderers** under `scheduling/skills/schedule-update/references/charts/`, one file per slug, each exporting a typed `renderXyz(payload): RenderResult` function. 16 trend charts + 1 summary report.
2. **A single registry** (`registry.ts`) mapping slug → `RenderFn` so the Node CLI and the cloud function dispatch identically.
3. **Importable from both Node and Deno** with no bundle step and no runtime npm dependencies. Source `.ts` is the deliverable.
4. **Node CLI** (`cli.ts`) that mirrors today's `render.py` contract: read `{slug}.json` payloads from one directory, write `{slug}.html` + `{slug}.png` to another, print a `{rendered, failed}` JSON summary, return non-zero exit on any failure.
5. **Visual contract preserved.** Every chart's palette, dasharray, smoothing curve, axis behavior, and legend matches the Python reference (and through it, the SmartPM Highcharts source) byte-similar.
6. **Cleanup commit removes all Python rendering code** plus the legacy Playwright SmartPM-capture path. End state: one rendering path, one language for chart logic, no `--legacy` escape hatch.

## Non-goals (out of scope)

- Changes to the email pipeline, Procore upload, archive markdown, or any consumer of `{slug}.png`. Filenames stay identical.
- Building the Supabase Edge Function or the browser draft editor. That's the consumer branch; this branch ships the library it consumes.
- Re-resolving `smartpm_project_name` / `scenario_id` (out of scope here, tracked separately).
- Adding hover tooltips, zoom, or interactivity to the rendered HTML. The HTML serves three consumers (PNG rasterisation, email-inline embed, browser editor) and stays static for all of them.
- Re-deriving any visual contract from the live SmartPM DOM. The DOM inspections done during the Python port (commits `b6a58ee` through `1ea9b22`) are the source of truth for charts 01–04. New charts inspect the DOM as they come up — same workflow.

## Architecture

### Required API shape (mandated by the consumer branch)

```typescript
// svg-lib.ts (shared types)
export type RenderResult = { html: string; svgInner: string };
export type RenderFn<T = unknown> = (payload: T) => RenderResult;

// 01-planned-vs-actual.ts
export interface PlannedVsActualPayload {
  percentCompleteTypes: Record<string, string>;
  data: Array<{
    DATE: string;
    LATE_DATE_PLANNED: number | null;
    BASELINE_PLANNED:  number | null;
    ACTUAL:            number | null;
    SCHEDULED:         number | null;
    PLANNED:           number | null;
  }>;
}
export function renderPlannedVsActual(payload: PlannedVsActualPayload): RenderResult { ... }

// registry.ts
import { renderPlannedVsActual }   from './01-planned-vs-actual.ts';
import { renderScheduleQuality }   from './02-schedule-quality.ts';
// ... 14 more imports
export const RENDERERS: Record<string, RenderFn> = {
  '01-planned-vs-actual-percent-complete': renderPlannedVsActual as RenderFn,
  '02-schedule-quality-grade-over-time':   renderScheduleQuality as RenderFn,
  // ...
  'smartpm-summary-report':                renderSummaryReport as RenderFn,
};
```

Each per-chart file exports its own typed `RenderXyzPayload` interface plus the strongly-typed `renderXyz` function. Consumers that know the slug they're calling get full type safety; consumers dispatching by string-keyed slug (the CLI) erase to `RenderFn` and pass through whatever the JSON parsed to. Same payload-passthrough rule as the Python design: MCP response shapes hit the renderer unchanged, no orchestrator normalization.

### `svgInner` for the summary report

The `RenderResult.svgInner` field exists so the cloud editor can inline-embed a single chart's SVG into an HTML email body (better email-client rendering than full standalone HTML documents). The summary report is one HTML document with three vertically-stacked sub-visualizations (cards + plan-vs-actual curve + milestones table) — it has no single canonical SVG.

`renderSummaryReport` returns `{ html, svgInner: '' }`. The cloud consumer treats empty-string `svgInner` as "use `html` directly." Documented at the type level via a JSDoc note on `RenderFn` and called out explicitly in the summary-report file's docstring.

### Package layout

```
scheduling/skills/schedule-update/references/charts/
├── package.json                    # "type":"module", devDeps only: vitest typescript @types/node tsx
├── tsconfig.json                   # target ES2022, strict, moduleResolution bundler
├── svg-lib.ts                      # ports of _pva01_* helpers
├── svg-lib.spec.ts                 # unit tests for geometry/scale/tick helpers
├── 01-planned-vs-actual.ts
├── 01-planned-vs-actual.spec.ts
├── 02-schedule-quality.ts
├── 02-schedule-quality.spec.ts
├── 03-project-health.ts
├── 03-project-health.spec.ts
├── 04-schedule-changes.ts
├── 04-schedule-changes.spec.ts
├── 05-schedule-delay.ts            # ... through 16
├── 16-critical-path-percentage.ts
├── 16-critical-path-percentage.spec.ts
├── summary-report.ts
├── summary-report.spec.ts
├── registry.ts                     # slug → RenderFn map
├── cli.ts                          # Node CLI driver
├── html_to_png.js                  # UNCHANGED — Node CLI shells out to this
├── tests/
│   ├── deno-import.test.ts         # Deno-runtime cross-runtime smoke test
│   └── fixtures/                   # existing JSON fixtures stay, language-agnostic
└── (Python charts.py / render.py / style.py stay until cleanup commit, then removed)
```

Filename `NN-slug.ts` mirrors the slug exactly so the registry mapping is trivial and grep-friendly.

### `svg-lib.ts` — ported geometry helpers

Direct line-for-line port of the `_pva01_*` helpers in `charts.py` (lines 1311–1531):

```typescript
// Geometry
export function dateToX(d: Date, dmin: Date, dmax: Date, x0: number, x1: number): number;
export function pctToY(p: number, y0: number, y1: number): number;
export function smoothPath(pts: Array<[number, number]>): string;     // Catmull-Rom → cubic Bezier
export function xTicks(dmin: Date, dmax: Date, maxTicks?: number): Date[];
export function seriesPts(
  rows: Array<Record<string, unknown>>, field: string,
  dmin: Date, dmax: Date, x0: number, x1: number, y0: number, y1: number,
): Array<[number, number]>;

// Glyphs + envelope
export type MarkerKind = 'circle' | 'square' | 'diamond' | 'triangle' | 'invtri';
export function markerSvg(kind: MarkerKind, x: number, y: number, color: string, size?: number): string;
export function legendItem(kind: MarkerKind | 'area', color: string, dash: string, label: string): string;
export function htmlEnvelope(opts: {
  title: string; svgW: number; svgH: number;
  svgInner: string; legendHtml: string;
  cardW?: number; cardH?: number;
}): string;
export function emptyHtml(title: string): string;

// Shared types
export type RenderResult = { html: string; svgInner: string };
export type RenderFn<T = unknown> = (payload: T) => RenderResult;
```

**No d3.** The Python helpers total ~150 lines; d3-shape + d3-scale + d3-time-format would add ~60 KB on the wire and a wider API surface to learn. Reimplementing keeps the byte-similar visual output guarantee against the Python reference and means zero runtime npm dependencies — which in turn means trivial Deno consumption (no transitive npm resolution needed).

### Node CLI (`cli.ts`) — replaces `render.py`

```bash
node --experimental-strip-types charts/cli.ts <payload_dir> <output_dir>
# or, on Node <22:
npx tsx charts/cli.ts <payload_dir> <output_dir>
```

For each `{payload_dir}/{slug}.json` (sorted):

1. Read JSON.
2. Look up `RENDERERS[slug]`. If missing, record `{slug, reason: 'no renderer in registry'}` in `failed`.
3. Call renderer → `{ html, svgInner }`.
4. Write `{output_dir}/{slug}.html` from the renderer's `html`.
5. Shell out to `html_to_png.js` to produce `{output_dir}/{slug}.png`.
6. On any error: record `{slug, reason: 'ErrorName: message'}` in `failed`. Continue.
7. Print `{rendered: [{slug, path}], failed: [{slug, reason}]}` to stdout.
8. Exit `0` if no failures, `1` otherwise.

Same observable behavior as the Python `render.py`. No PIL-stitching path (the summary report is one renderer call now). No summary-composite logic.

### Deno consumption

The cloud editor branch imports the package via a path or pinned-commit HTTPS URL:

```typescript
// Supabase Edge Function (Deno runtime)
import { RENDERERS } from 'https://.../charts/registry.ts';
const result = RENDERERS[slug](payload);
// result.html → ship to browser
```

No `import_map.json`. No bundle step. Deno reads `.ts` natively; because there are no runtime npm dependencies (decision: no d3), there is no `npm:` resolution to configure.

### Visual contract — how byte-similarity is maintained

Each TS renderer ports its Python counterpart line-for-line:

- Same palette constants (hex codes from Chrome MCP DOM inspection).
- Same SVG card geometry (`1728 × 432`, padding `14 / 32 / 30 / 56`, plot rect derived from those).
- Same float-formatting precision (`.toFixed(2)` for coordinates, `.toFixed(1)` for gridline y).
- Same date-tick algorithm (calendar-aware step selection: 7, 14, 30, 60, 90, 180, 365 days).
- Same Catmull-Rom smoother math (control points at `(p2 - p0) / 6.0` offset).
- Same HTML envelope CSS (Inter font, `.chart-card` 12px padding, `.legend-item` 6 18px gap).

The HTML contract tests (below) assert the *content* of the emitted HTML — palette colors, dasharray patterns, legend labels, title — and the visual diff against `chart-previews/` confirms the *layout* matches.

## Migration sequence — 12 commits

Each commit:
- Bumps `scheduling/.claude-plugin/plugin.json` + matching `marketplace.json` entry (pre-commit hook enforces this).
- Stays on the branch (no push to main, no `python build.py`, no deploy — per pivot tasks).

| # | Commit                                            | Scope                                                                                                                                                                                                                |
|---|---------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1 | `feat(scheduling): TS chart package bootstrap`     | `package.json`, `tsconfig.json`, `svg-lib.ts` + spec, empty `registry.ts`, `cli.ts` skeleton, `tests/deno-import.test.ts`. **Types ship here — other branches can start coding against `RenderResult` / `RenderFn`.** |
| 2 | `feat(scheduling): TS chart 01 (planned-vs-actual)` | Port `renderPlannedVsActual` + spec. Register. Update `phases/screenshots.md` chart 01 recipe to point at TS CLI.                                                                                                  |
| 3 | `feat(scheduling): TS chart 02 (schedule quality)`  | Port `renderScheduleQuality` + spec. Fix stale `grade.score` → `grade.mark` recipe in screenshots.md.                                                                                                              |
| 4 | `feat(scheduling): TS chart 03 (project health)`    | Port `renderProjectHealth` + spec. Fix stale `indicator` → `risk` recipe in screenshots.md.                                                                                                                        |
| 5 | `feat(scheduling): TS chart 04 (schedule changes)`  | Port `renderScheduleChanges` + spec. Document the dropped "Total Activities" column.                                                                                                                                |
| 6 | `feat(scheduling): TS charts 05, 13, 14`            | New trend renderers. Parent agent does Chrome MCP DOM inspection (subagents cannot auth to SmartPM); subagents receive captured palette/axis/series JSON in-prompt. Use Wellington (113385) or Anchorage (111751) projects when SGRWRF is data-sparse. |
| 7 | `feat(scheduling): TS charts 15, 16`                | Two more trend renderers. Same subagent-with-JSON-in-prompt workflow.                                                                                                                                              |
| 8 | `feat(scheduling): TS charts 06, 07`                | Visual upgrade from matplotlib — re-inspect DOM since matplotlib was an approximation.                                                                                                                              |
| 9 | `feat(scheduling): TS charts 08, 09`                | Velocity (the heavy one — 6 bar series + average line + data-date marker) + SPI.                                                                                                                                   |
| 10| `feat(scheduling): TS charts 10, 11, 12 (hit-rate trio)` | Three charts share the stacked-bar shape (Total / Started / Finished × On-Time / Late / Missed). Implement once via a shared `_renderHitRate` helper in the chart file, three thin entry-point wrappers.       |
| 11| `feat(scheduling): TS summary report`               | The big one — 3 sections (cards + curve + milestones table) in 1 HTML, single PNG. `svgInner: ''`.                                                                                                                  |
| 12| **Cleanup commit — see "Cleanup commit" section below**                                                                                                                                                            |

## Per-chart testing contract

Each `NN-slug.spec.ts` uses Vitest (`describe / it / expect`), runs against the existing fixture in `tests/fixtures/{slug}.json`, and asserts the HTML contract:

```typescript
import { describe, it, expect } from 'vitest';
import { renderPlannedVsActual } from './01-planned-vs-actual.ts';
import fixture from './tests/fixtures/01-planned-vs-actual-percent-complete.json' with { type: 'json' };

describe('renderPlannedVsActual', () => {
  const { html, svgInner } = renderPlannedVsActual(fixture);

  it('uses all 6 series palette colors', () => {
    for (const hex of ['#b00020', '#2caffe', '#1476b7', '#388543', '#808080', '#cccccc']) {
      expect(html).toContain(hex);
    }
  });

  it('preserves the dashed Scheduled Completion line', () => {
    expect(html).toContain('stroke-dasharray="8,6"');
  });

  it('emits the canonical title', () => {
    expect(html).toContain('Planned VS Actual Percent Complete');
  });

  it('emits each legend label', () => {
    for (const label of ['Progress Target', 'Late Date Planned', 'Planned (All Schedules)', 'Actual', 'Scheduled Completion', 'Early Date Planned']) {
      expect(html).toContain(label);
    }
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });
});
```

Per-chart specs assert the same five things:
1. Every palette hex appears in `html`.
2. Every `stroke-dasharray` pattern appears in `html` (regression against the chart-02 disaster shape: invented colors / missing dashes).
3. Chart title appears verbatim.
4. Every legend label appears (when applicable — chart 02 / chart 03 have no legend, so this is skipped).
5. `svgInner` is non-empty for single-SVG charts. Summary report asserts `svgInner === ''` instead.

`svg-lib.spec.ts` adds geometry/scale/tick boundary tests:
- `dateToX` / `pctToY` boundary conditions (dmin == dmax, p < 0, p > 100).
- `smoothPath` with 0, 1, 2, 3, n points.
- `xTicks` with various date spans (7 days, 90 days, 5 years).
- `markerSvg` for each kind.
- `htmlEnvelope` produces valid HTML5 with no `<script>` tag.

`tests/deno-import.test.ts` confirms cross-runtime portability — runs under Deno via `deno test`, imports `registry.ts`, asserts every slug resolves to a function and that one call (against a stub payload) returns the right `RenderResult` shape. Doesn't visually validate; that's Vitest's job. This catches the "package suddenly depends on a Node-only import" regression.

**No Chromium-smoke equivalent at the unit level.** Visual regression is human eyeballing of `chart-previews/` PNGs after re-rendering with the TS CLI. The Python-spec's `--legacy` Playwright smoke is gone with the cleanup; the new approach is "look at the PNGs, compare to SmartPM web view."

## Cleanup commit (final, 12th commit)

After all 17 TS renderers are landed and visually verified against `chart-previews/`, **one** commit removes the Python rendering path and the legacy Playwright SmartPM-capture path.

### Files deleted entirely

```
scheduling/skills/schedule-update/references/charts/charts.py
scheduling/skills/schedule-update/references/charts/render.py
scheduling/skills/schedule-update/references/charts/style.py
scheduling/skills/schedule-update/references/charts/__init__.py
scheduling/skills/schedule-update/references/charts/requirements.txt
scheduling/skills/schedule-update/references/charts/tests/__init__.py
scheduling/skills/schedule-update/references/charts/tests/conftest.py
scheduling/skills/schedule-update/references/charts/tests/test_render.py

scheduling/skills/schedule-update/references/smartpm/capture-smartpm.js
scheduling/skills/schedule-update/references/smartpm/smartpm-client.js
scheduling/skills/schedule-update/references/smartpm/env-loader.js
scheduling/skills/schedule-update/references/tests/smartpm.spec.js
scheduling/skills/schedule-update/references/tests/full-page-debug.spec.js
```

The `references/smartpm/` directory is empty after these deletions and goes with it. The `references/tests/` directory keeps any other tests that survive (e.g. `html-to-pdf.js`-related tests).

Pre-deletion verification step in the cleanup commit (run before staging the deletes):

```bash
git grep -E "capture-smartpm|smartpm-client|env-loader" -- 'scheduling/' \
  ':!scheduling/.claude-plugin/' ':!scheduling/skills/schedule-update/references/smartpm/' \
  ':!scheduling/skills/schedule-update/references/tests/smartpm.spec.js' \
  ':!scheduling/skills/schedule-update/references/tests/full-page-debug.spec.js'
# Expected: zero matches — if anything appears, surgically remove from those callers first.
```

### Files retained

```
scheduling/skills/schedule-update/references/charts/html_to_png.js               # Node CLI still shells out to this
scheduling/skills/schedule-update/references/charts/tests/fixtures/*.json        # MCP response samples — language-agnostic
scheduling/skills/schedule-update/references/package.json                        # Playwright stays (html_to_png.js still uses chromium)
```

### Files edited

**`scheduling/skills/schedule-update/phases/screenshots.md`** — major revision:
- Single rendering path: MCP-fetch payload → `Write` `{slug}.json` → `node --experimental-strip-types charts/cli.ts <payload_dir> <output_dir>` → produces `{slug}.html` + `{slug}.png` pairs.
- All 17 per-slug MCP recipes inline, with the corrections discovered during the Python port:
  - **Chart 02:** raw `smartpm_get` against `/projects/{id}/scenarios/{id}/schedule-quality-trend`; reader uses `grade.mark` (letter, categorical), not `grade.score` (numeric); response is a flat list with no `{"trend": [...]}` envelope.
  - **Chart 03:** response is a flat list (no `{"trend": [...]}` envelope); indicator field is `risk`, not `indicator`.
  - **Chart 04:** response is a flat list (no `{"summary": [...]}` envelope); metrics nested under `metrics: {}` with PascalCase keys; no `totalActivities` field — "Total Activities" column is intentionally absent.
- The "non-default slugs / `--legacy` fallback" subsection: deleted entirely.
- The default `graph_screenshots` list: includes all 16 trend slugs + `smartpm-summary-report`.

**`scheduling/commands/write-weekly-schedule-email.md`** — Step 6 currently (lines 2 and 83) describes capture via `references/smartpm/capture-smartpm.js`. Stale post-Python-migration; doubly stale after this pivot. Update Step 6 to: "MCP-fetch each chart payload → run TS CLI to render all 17 PNGs."

**`scheduling/skills/schedule-update/SKILL.md`** — grep for any surviving references to `capture-smartpm.js` or `--legacy` and update or delete.

**`scheduling/skills/schedule-update/references/package.json`**:
- Add `"scripts": { "render": "node --experimental-strip-types charts/cli.ts", "test": "vitest run" }`.
- Add devDeps: `vitest`, `typescript`, `@types/node`, `tsx`.
- Playwright dep stays — `html_to_png.js` still uses it.

**`scheduling/.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json`** scheduling entry — version bump (matched pair, enforced by the pre-commit hook).

### Smoke test before merging the cleanup commit

```bash
# 1. Nothing in the skill references the deleted files
git grep -E "capture-smartpm|smartpm-client|matplotlib|_composite_summary_report|--legacy|charts\.py|render\.py" -- 'scheduling/'
# Expected: zero matches.

# 2. TS CLI handles every slug end-to-end from a real project payload
node --experimental-strip-types \
  scheduling/skills/schedule-update/references/charts/cli.ts \
  scheduling/skills/schedule-update/references/charts/tests/fixtures \
  /tmp/chart-cleanup-smoke
# Expected: 17 .html + 17 .png in /tmp/chart-cleanup-smoke, exit 0.

# 3. Tests pass
cd scheduling/skills/schedule-update/references && npm test
# Expected: every per-chart spec green, svg-lib spec green, deno-import test passes.
```

If any check fails, fix inside the cleanup commit before merge.

## Risks & mitigations

**1. The cloud-editor consumer spec does not exist yet.** Neither on this branch nor on `claude/interesting-noyce-d0f3e2` (which is currently `main` lineage with no cloud-editor commits). API surface is designed against the prompt's stated `{ html, svgInner }` shape alone. *Mitigation:* the API ships in commit 1 (bootstrap); if the cloud-editor spec, once written, needs adjustments, those can land before lots of charts are built against the wrong shape. Commits 2–11 only touch per-chart files plus the registry — easy to refactor the return type later if needed.

**2. Subagent Chrome MCP cannot authenticate to SmartPM** — cookies don't carry between subagent contexts. This caused the chart-02 disaster on the Python port (invented palette `#54a854 / #f5a623 / #c0223a`). *Mitigation:* parent agent does ALL Chrome MCP DOM inspections, captures palette + axis + series structure as JSON, then passes that JSON inside the implementer subagent's prompt. Subagents stop needing Chrome MCP. This workflow is documented in the implementation plan, not the spec.

**3. SGRWRF (project 141462) is data-sparse for some charts.** Chart 05 has no rendered series; chart 04's "Total Activities" column has no bars. *Mitigation:* use Wellington NZ Temple (113385, `defaultScenarioId=1644`) or Anchorage Alaska Temple (111751, `defaultScenarioId=1618`) for inspection when SGRWRF is empty.

**4. MCP response shapes differ from documentation.** Discovered during the Python port: chart 02 has no dedicated tool (use raw `smartpm_get`); chart 03 response is flat list with `risk` not `indicator`; chart 04 metrics nest under `metrics{}` with PascalCase. *Mitigation:* always fetch the fixture first and read the JSON before writing the renderer. Each chart's payload shape is documented in its `*.ts` file's `RenderXyzPayload` interface — the type system catches drift the second the orchestrator passes the wrong field.

**5. `svgInner` shape mismatch for the summary report.** Single-SVG-per-chart assumption breaks for a 3-section composite. *Mitigation:* `renderSummaryReport` returns `{ html, svgInner: '' }`. Documented at the call site and in the `RenderFn` JSDoc. The summary-report spec asserts `svgInner === ''` so the contract is enforced.

**6. Visual drift from Python.** Float-formatting differences (`%.2f` in Python vs `.toFixed(2)` in JS), date parsing nuance, or floating-point rounding could shift pixels. *Mitigation:* per-chart spec asserts the contract content (palette, dasharray, labels); `chart-previews/` PNG diff against the Python reference is the layout regression check. If the PNGs differ noticeably, the float math is off — fix and re-render.

**7. Cross-runtime portability regression.** A future renderer accidentally imports a Node-only module (`fs`, `path`, `child_process`) and breaks Deno consumption. *Mitigation:* `tests/deno-import.test.ts` imports the registry from Deno and calls every renderer. Runs in CI / as part of `npm test`. The CLI (`cli.ts`) is the *only* file allowed to import Node-only modules; per-chart files and `svg-lib.ts` must be pure-string-output.

**8. Cleanup commit reverts working code prematurely.** If commits 6–11 produce a chart whose visual doesn't match SmartPM and we can't fix it before merge, deleting matplotlib means no fallback. *Mitigation:* the cleanup commit is the **12th** commit, after every TS renderer is verified visually against `chart-previews/`. If commit 11 (summary report) isn't ready, the cleanup commit isn't either — Python stays until both are green.

## Open questions

None. The four open questions from the pivot prompt are settled in **Architecture** above:

1. **d3 vs reimplement** → reimplement (~150 lines, no runtime deps, byte-similar output guarantee, trivial Deno consumption).
2. **Deno/Node import strategy** → single ESM TypeScript package, no import map, no bundle. Deno reads `.ts` natively; Node 22+ does too (`--experimental-strip-types`); Node <22 uses `tsx` (devDep).
3. **Python renderer cleanup timing** → leave during migration (commits 2–11) for side-by-side eyeball reference, revert wholesale in the 12th cleanup commit.
4. **Test runner** → Vitest primary (per-chart `*.spec.ts` colocated next to `*.ts`); one `tests/deno-import.test.ts` for cross-runtime smoke.

## What "done" looks like

- All 17 TS renderers in `scheduling/skills/schedule-update/references/charts/*.ts`, each one file, exporting `renderXyz(payload): RenderResult`.
- `registry.ts` maps 17 slugs → 17 renderer functions. No stubs.
- `cli.ts` reads payloads, writes `.html` + `.png` pairs, matches the observable contract of the deleted `render.py`.
- `svg-lib.ts` holds all shared plumbing; per-chart files never mention Chromium or `html_to_png.js` (that's `cli.ts`'s job).
- Vitest specs green: 17 per-chart contract specs + svg-lib spec + Deno-import smoke test.
- `chart-previews/` re-rendered with TS, eyeball-compared against SmartPM web rendering and the Python reference PNGs, judged faithful for at least 2 projects (SGRWRF + 1 data-rich project like Wellington or Anchorage).
- `charts.py`, `render.py`, `style.py`, `requirements.txt` deleted. No `matplotlib`, `numpy`, `Pillow`, `mdates`, `mticker`, `LineCollection`, `DateFormatter`, `FancyBboxPatch`, `Rectangle` strings anywhere in `scheduling/`.
- `references/smartpm/` directory removed. `--legacy` Playwright capture path removed from `phases/screenshots.md`. Two smoke-test files (`smartpm.spec.js`, `full-page-debug.spec.js`) removed.
- `phases/screenshots.md` documents one path, all 17 MCP recipes inline with the corrected chart-02 / chart-03 / chart-04 details.
- `commands/write-weekly-schedule-email.md` Step 6 description updated.
- `scheduling/.claude-plugin/plugin.json` + `marketplace.json` bumped through 12 versions, all matched pairs.
- Branch state at the end: the cloud-editor consumer branch can `import { RENDERERS } from '.../charts/registry.ts'` and dispatch every slug. Local weekly schedule update produces identical-filename PNGs via the TS CLI.

When the dust settles, a future engineer touching one chart's visuals edits one `NN-slug.ts` file, runs `vitest run -- NN-slug`, eyeballs the regenerated PNG against SmartPM, and ships. They never see matplotlib, never reach for `--legacy`, never re-encounter the dashed-line bug.
