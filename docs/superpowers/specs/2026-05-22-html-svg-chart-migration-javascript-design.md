# HTML+SVG chart migration — JavaScript port (JSDoc types)

**Date:** 2026-05-22
**Branch:** `claude/blissful-tharp-ad03c2` → `feat/html-svg-chart-migration`
**Plugin scope:** `scheduling` (chart renderer rewrite + phase doc updates + matplotlib + Playwright-capture removal)
**Supersedes:** [2026-05-21 HTML+SVG chart migration — TypeScript port](2026-05-21-html-svg-chart-migration-typescript-design.md), which in turn superseded [2026-05-21 HTML+SVG chart migration — Python](2026-05-21-html-svg-chart-migration-design.md). The TypeScript spec was 90% architecturally right; this spec pivots the implementation language one more step because the actual consumer of these renderers is now [westland-mcps](https://github.com/CamronWalker/westland-mcps) — a Cloudflare Worker, "JavaScript, no TypeScript build step" per its `CLAUDE.md`. Keeping the renderers in TypeScript would either force a build step on the consumer or fragment the codebase. The visual contract per chart does not change; the runtime/language does.

## Motivation

A separate branch (`claude/interesting-noyce-d0f3e2`, design doc in flight) wraps a browser-based draft editor around these chart renderers, backed by a new service inside westland-mcps. westland-mcps deploys as a single Cloudflare Worker with no TypeScript build step — `npx wrangler deploy` ships raw `.js` files. For westland-mcps to consume these renderers, they must be runnable in the CF Workers JS runtime *as published source*: plain JS, ESM, no compile pass, no Node-only globals in the renderer code paths.

JSDoc gives us the same authoring ergonomics TypeScript does — IntelliSense, jump-to-def, autocomplete on payload fields, `tsc --noEmit` type-checking in CI — *because* the editor's TS language service reads JSDoc natively. Consumers receive pure `.js` files; no `.d.ts` shipping, no compile-time hooks.

Three consumers will exist when this branch lands:

1. **Local Node CLI** — invoked from `phases/screenshots.md` to write `{slug}.html` + `{slug}.png` next to each other for the weekly email pipeline. Same observable contract as the Python `render.py` it replaces.
2. **westland-mcps Cloudflare Worker** — imports the registry, calls `RENDERERS[slug](payload)` to get `{ html, svgInner }`, ships the HTML to the browser draft editor. Will also call `renderPlaceholder(slug)` when SmartPM data is still processing.
3. **The browser draft editor itself** — receives rendered HTML over the wire; doesn't import this package directly.

The visual contract — SmartPM Highcharts CSS pixel-for-pixel, palette + dasharray pulled off the live DOM via Chrome MCP — does not change. This is a runtime/language pivot, not a redesign.

## What's already on this branch

Four Python renderers shipped, plus the rasteriser. Read these as the visual-contract reference before porting:

| Commit  | Slug                                            | Status after pivot                                                                                                          |
|---------|-------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------|
| `b6a58ee` | `01-planned-vs-actual-percent-complete`         | Port to JS. `_pva01_*` helpers become `svg-lib.js`.                                                                          |
| `d26fe78` | `02-schedule-quality-grade-over-time`           | Port to JS. Single `#2caffe` line, categorical letter-grade Y, no bands, no legend, ™ in title.                              |
| `b707b79` | `03-project-health-index-over-time`             | Port to JS. Single `#2caffe` line + `#1AA462` GOOD circle markers, auto-fit numeric % Y.                                     |
| `1ea9b22` | `04-schedule-changes-over-time`                 | Port to JS. 7 spline series with verified palette; "Total Activities" column dropped (MCP does not expose it).               |

The intermediate broken-palette commit (`12f78fb`) for chart 02 was fixed in `d26fe78`; only port the fix.

`charts/html_to_png.js` (Node + Playwright, CommonJS) gets **renamed to `charts/html_to_png.cjs`** in commit 1. No code changes — the rename is forced by the new `"type": "module"` in `charts/package.json`, which would otherwise make Node try to run the existing `require('playwright')` calls as ESM. The `.cjs` extension overrides the package's `type` field for that one file. The CF Workers path ships HTML to the browser directly and doesn't need this file at all; the Node CLI continues to shell out to it for local PNG rasterisation via `child_process.spawnSync('node', ['html_to_png.cjs', ...])`. The CJS/ESM boundary is fine because `cli.js` (ESM) `spawn`s a separate Node process — no in-process import. (A future cleanup could rewrite `html_to_png.cjs` to ESM and drop the extension, but that's not in scope here.)

`chart-previews/SGRWRF-0{1,2,3,4}-*.png` are gitignored throwaway artifacts from the Python port. Re-render with JS and visually diff against them as each port lands.

## Goals

1. **17 JavaScript chart renderers** under `scheduling/skills/schedule-update/references/charts/`, one file per slug, each exporting a JSDoc-typed `renderXyz(payload): RenderResult` function. 16 trend charts + 1 summary report.
2. **A single registry** (`registry.js`) mapping slug → `RenderFn` so the Node CLI and the CF Worker dispatch identically.
3. **A placeholder renderer** (`renderPlaceholder(slug, opts?): RenderResult`) for the "SmartPM still processing" case in the cloud editor. Same card dimensions as the real chart for that slug — no layout shift when the placeholder gets swapped for live data.
4. **A per-chart metadata export** (`CHART_META` in `meta.js`) keyed by slug, providing the SVG width / height / human-readable title used by `renderPlaceholder` and by any external consumer that needs chart dimensions without invoking the full renderer.
5. **Importable from both Node and Cloudflare Workers** with no bundle step and zero runtime npm dependencies in the rendering path. Source `.js` is the deliverable.
6. **Node CLI** (`cli.js`) that mirrors today's `render.py` contract: read `{slug}.json` payloads from one directory, write `{slug}.html` + `{slug}.png` to another, print a `{rendered, failed}` JSON summary, return non-zero exit on any failure.
7. **Visual contract preserved.** Every chart's palette, dasharray, smoothing curve, axis behavior, and legend matches the Python reference (and through it, the SmartPM Highcharts source) byte-similar.
8. **Cleanup commit removes all Python rendering code** plus the legacy Playwright SmartPM-capture path. End state: one rendering path, one language for chart logic, no `--legacy` escape hatch.

## Non-goals (out of scope)

- Changes to the email pipeline, Procore upload, archive markdown, or any consumer of `{slug}.png`. Filenames stay identical.
- Building the westland-mcps cloud-editor service or the browser draft editor. That's the consumer branch; this branch ships the library it consumes.
- Re-resolving `smartpm_project_name` / `scenario_id` (out of scope here, tracked separately).
- Adding hover tooltips, zoom, or interactivity to the rendered HTML. The HTML serves three consumers (PNG rasterisation, email-inline embed, browser editor) and stays static for all of them.
- Re-deriving any visual contract from the live SmartPM DOM. The DOM inspections done during the Python port (commits `b6a58ee` through `1ea9b22`) are the source of truth for charts 01–04. New charts inspect the DOM as they come up — same workflow.
- Publishing the chart package to public npm. The package may end up on a private GitHub Packages registry (see §"CF Workers consumption mechanism" below), but choosing and configuring that is the consumer branch's job; the chart package itself just needs a valid `package.json`.

## Architecture

### Required API shape (mandated by the consumer branch)

```js
// svg-lib.js — shared types via JSDoc

/**
 * @typedef {Object} RenderResult
 * @property {string} html       Self-contained HTML document for standalone use / PNG rasterisation.
 * @property {string} svgInner   Just the <g>… contents — for inline-embedding in another HTML doc.
 *                               Empty string for composite renderers (summary report).
 */

/**
 * @template [T=any]
 * @typedef {(payload: T) => RenderResult} RenderFn
 */
```

```js
// 01-planned-vs-actual.js

/**
 * @typedef {Object} PlannedVsActualPayload
 * @property {Record<string,string>} percentCompleteTypes
 * @property {Array<{
 *   DATE: string,
 *   LATE_DATE_PLANNED: number|null,
 *   BASELINE_PLANNED:  number|null,
 *   ACTUAL:            number|null,
 *   SCHEDULED:         number|null,
 *   PLANNED:           number|null,
 * }>} data
 */

/**
 * @param {PlannedVsActualPayload} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderPlannedVsActual(payload) { /* ... */ }

/**
 * Per-chart dimensions / title — aggregated in meta.js as CHART_META[slug].
 * Co-located with the renderer so it can't drift.
 * @type {{ svgWidth: number, svgHeight: number, title: string }}
 */
export const META = {
  svgWidth:  1728,
  svgHeight: 432,
  title:     'Planned VS Actual Percent Complete',
};
```

```js
// registry.js

import { renderPlannedVsActual } from './01-planned-vs-actual.js';
// ... 16 more imports

/** @type {Record<string, import('./svg-lib.js').RenderFn<any>>} */
export const RENDERERS = {
  '01-planned-vs-actual-percent-complete': renderPlannedVsActual,
  '02-schedule-quality-grade-over-time':   renderScheduleQuality,
  // ...
  'smartpm-summary-report':                renderSummaryReport,
};
```

```js
// meta.js

import { META as META01 } from './01-planned-vs-actual.js';
import { META as META02 } from './02-schedule-quality.js';
// ... 15 more imports

/** @type {Record<string, { svgWidth: number, svgHeight: number, title: string }>} */
export const CHART_META = {
  '01-planned-vs-actual-percent-complete': META01,
  '02-schedule-quality-grade-over-time':   META02,
  // ...
  'smartpm-summary-report':                METASummary,
};
```

Each per-chart file exports its own JSDoc-typed `RenderXyzPayload` typedef, its `renderXyz` function, and a `META` const. Consumers that know the slug they're calling get full IntelliSense on the typedef; consumers dispatching by string-keyed slug (the CLI, the cloud-editor service) erase to `RenderFn<any>` and pass through whatever the JSON parsed to. Same payload-passthrough rule as the Python design: MCP response shapes hit the renderer unchanged, no orchestrator normalization.

### `svgInner` for the summary report

The `RenderResult.svgInner` field exists so the cloud editor can inline-embed a single chart's SVG into an HTML email body (better email-client rendering than full standalone HTML documents). The summary report is one HTML document with three vertically-stacked sub-visualizations (cards + plan-vs-actual curve + milestones table) — it has no single canonical SVG.

`renderSummaryReport` returns `{ html, svgInner: '' }`. The cloud consumer treats empty-string `svgInner` as "use `html` directly." Documented at the type level via JSDoc on `RenderFn` and called out explicitly in the summary-report file's header comment.

### Placeholder rendering (cloud-editor requirement)

The cloud editor needs to render per-slug placeholder cards when SmartPM is still processing (typical wait: up to 30 minutes after an XER upload). Two requirements:

- **Same card dimensions as the real chart for that slug** — no layout shift when the placeholder gets swapped for live data on a re-render.
- **Reusable from both consumers** — the CLI can also emit placeholders for charts where the MCP payload is empty / errored, instead of failing the whole batch.

API in `svg-lib.js`:

```js
/**
 * Render a placeholder card matching the dimensions of the real chart for `slug`.
 * Throws if `slug` is not present in CHART_META.
 *
 * @param {string} slug                                      Registry key.
 * @param {Object}  [opts]
 * @param {string}  [opts.message='Data not yet available']  Centered message text.
 * @param {('clock'|'warn'|'none')} [opts.icon='clock']      Icon glyph above the message.
 * @returns {import('./svg-lib.js').RenderResult}
 * @throws {Error}                                           Unknown slug.
 */
export function renderPlaceholder(slug, opts = {}) { /* ... */ }
```

Implementation: reads `CHART_META[slug]` for dimensions + title, emits the standard `htmlEnvelope` shell with a single centered `<g>` containing the icon glyph (inline SVG) and the message text. No data series, no axes, no legend. `svgInner` returns the centered `<g>`; `html` is the full envelope.

### Error handling contract

Renderers signal *programming-bug-class* failures by throwing. They handle *data-shape-class* edge cases (empty arrays, null entries) by rendering an empty-state card.

| Condition | Renderer behavior |
|---|---|
| `payload.data` is `undefined`, `null`, or not an array | **Throw** `TypeError('expected payload.data to be an array')` |
| Required nested field missing (e.g. `data[i].DATE`) | **Throw** `TypeError` with the offending row index |
| Numeric field is `NaN` after parse | **Throw** `RangeError` with field name + row index |
| `payload.data` is an empty array | **Return** `emptyHtml(title)` — single-card "no data" message, no exception |
| Individual rows have `null` for a series value | **Skip the row for that series** (matches `_pva01_series_pts` Python rule) |
| Date range collapses to one day (`dmin === dmax`) | **Render** with `span = 1` (matches Python `or 1` fallback) |

Consumers (CLI, cloud function) catch the thrown errors at the orchestration layer:

- **CLI:** records `{slug, reason: 'ErrorName: message'}` in the `failed` array, continues to the next slug, exits non-zero at the end if `failed.length > 0`.
- **Cloud function:** substitutes `renderPlaceholder(slug, { message: 'Render failed', icon: 'warn' })` so the editor still gets a card of the right dimensions, and logs the error server-side for debugging.

The chart package itself never returns error sentinels (`null`, `undefined`, `{ error: ... }`) — exceptions propagate. This keeps the per-chart contract narrow ("input shape valid → RenderResult; input shape invalid → throw") and pushes the policy decision (fail vs degrade) to the caller.

### Package layout

```
scheduling/skills/schedule-update/references/charts/
├── package.json                    # "type":"module", "exports":{...}, devDeps: vitest typescript @types/node
├── jsconfig.json                   # allowJs/checkJs/noEmit:true — purely for editor + dev typecheck
├── index.js                        # re-exports RENDERERS, CHART_META, renderPlaceholder, every renderXyz, svg-lib helpers
├── svg-lib.js                      # ported _pva01_* helpers + renderPlaceholder + emptyHtml + htmlEnvelope
├── svg-lib.test.js
├── meta.js                         # aggregates per-chart META exports into CHART_META
├── meta.test.js                    # asserts every registry slug has a META entry and vice versa
├── 01-planned-vs-actual.js
├── 01-planned-vs-actual.test.js
├── 02-schedule-quality.js
├── 02-schedule-quality.test.js
├── 03-project-health.js
├── 03-project-health.test.js
├── 04-schedule-changes.js
├── 04-schedule-changes.test.js
├── 05-schedule-delay.js            # ... through 16
├── 16-critical-path-percentage.js
├── 16-critical-path-percentage.test.js
├── summary-report.js
├── summary-report.test.js
├── registry.js                     # slug → RenderFn map
├── cli.js                          # Node CLI driver — fs + child_process; shells out to html_to_png.cjs
├── html_to_png.cjs                 # RENAMED from html_to_png.js in commit 1 (forced by "type":"module"); code unchanged; cli.js shells out via child_process
├── tests/
│   ├── workers-import.test.js      # Wrangler-bundles registry.js + meta.js — fails if a renderer imports node:fs / node:path / etc.
│   └── fixtures/                   # existing JSON fixtures stay, language-agnostic
└── (Python charts.py / render.py / style.py stay until cleanup commit, then removed)
```

Filename `NN-slug.js` mirrors the slug exactly so the registry mapping is trivial and grep-friendly.

`package.json` shape:

```json
{
  "name": "@westland/charts",
  "version": "0.1.0",
  "type": "module",
  "main": "./index.js",
  "exports": {
    ".":            "./index.js",
    "./registry":   "./registry.js",
    "./meta":       "./meta.js",
    "./svg-lib":    "./svg-lib.js"
  },
  "scripts": {
    "test":      "vitest run",
    "typecheck": "tsc -p jsconfig.json"
  },
  "devDependencies": {
    "vitest":      "^2.0.0",
    "typescript":  "^5.5.0",
    "@types/node": "^20.0.0"
  }
}
```

`cli.js` and `html_to_png.cjs` are deliberately **not** in `exports`. They're Node-only entry points invoked via `node references/charts/cli.js`, not via `import`. Keeping them out of `exports` documents that they're not part of the public API and prevents accidental import from the cloud-editor side.

`jsconfig.json` shape:

```json
{
  "compilerOptions": {
    "target":       "ES2022",
    "module":       "ESNext",
    "moduleResolution": "Bundler",
    "allowJs":      true,
    "checkJs":      true,
    "noEmit":       true,
    "strict":       true,
    "lib":          ["ES2022"]
  },
  "include": ["*.js", "tests/**/*.js"]
}
```

`tsc -p jsconfig.json` produces no output files; its only purpose is to fail with type errors when JSDoc annotations don't match reality. Consumers never invoke it.

### `svg-lib.js` — ported geometry helpers (and why we don't pull in d3)

Direct line-for-line port of the `_pva01_*` helpers in `charts.py` (lines 1311–1531). The full surface:

```js
// Geometry

/** @param {Date} d @param {Date} dmin @param {Date} dmax @param {number} x0 @param {number} x1 @returns {number} */
export function dateToX(d, dmin, dmax, x0, x1) { /* ... */ }

/** @param {number} p @param {number} y0 @param {number} y1 @returns {number} */
export function pctToY(p, y0, y1) { /* ... */ }

/** @param {Array<[number, number]>} pts @returns {string} */
export function smoothPath(pts) { /* Catmull-Rom → cubic Bezier */ }

/** @param {Date} dmin @param {Date} dmax @param {number} [maxTicks=10] @returns {Date[]} */
export function xTicks(dmin, dmax, maxTicks = 10) { /* ... */ }

/** @param {Array<Record<string, unknown>>} rows @param {string} field @param {Date} dmin @param {Date} dmax
 *  @param {number} x0 @param {number} x1 @param {number} y0 @param {number} y1
 *  @returns {Array<[number, number]>} */
export function seriesPts(rows, field, dmin, dmax, x0, x1, y0, y1) { /* ... */ }

// Glyphs + envelope

/** @typedef {'circle'|'square'|'diamond'|'triangle'|'invtri'} MarkerKind */

/** @param {MarkerKind} kind @param {number} x @param {number} y @param {string} color @param {number} [size=4] @returns {string} */
export function markerSvg(kind, x, y, color, size = 4) { /* ... */ }

/** @param {MarkerKind|'area'} kind @param {string} color @param {string} dash @param {string} label @returns {string} */
export function legendItem(kind, color, dash, label) { /* ... */ }

/** @param {{title: string, svgW: number, svgH: number, svgInner: string,
 *           legendHtml: string, cardW?: number, cardH?: number}} opts @returns {string} */
export function htmlEnvelope(opts) { /* ... */ }

/** @param {string} title @returns {string} */
export function emptyHtml(title) { /* ... */ }

// Placeholder rendering (see "Placeholder rendering" section above)

/** @param {string} slug @param {{message?: string, icon?: 'clock'|'warn'|'none'}} [opts]
 *  @returns {RenderResult} */
export function renderPlaceholder(slug, opts = {}) { /* ... */ }
```

**No d3.** d3-shape, d3-scale, and d3-time look more tempting for CF Workers than for Deno (Workers can bundle npm deps cleanly), but the cost/benefit still favors reimplementation:

| Helper | Lines if reimplemented | d3 equivalent | d3 cost (bundled into Worker) |
|---|---|---|---|
| `dateToX` / `pctToY` | 8 lines | `d3.scaleTime()`, `d3.scaleLinear()` | d3-scale: ~12 KB after tree-shake |
| `smoothPath` (Catmull-Rom → cubic Bezier) | ~25 lines | `d3.line().curve(d3.curveCatmullRom)` | d3-shape: ~25 KB |
| `xTicks` (calendar-aware step selection) | ~12 lines | `d3.scaleTime().ticks(n)` | (already in d3-scale above) |

Total reimplementation: ~200 lines, byte-faithful to the Python reference. Total d3 dependency: ~40 KB minified across two sub-packages, plus the API surface to learn, plus **`d3.curveCatmullRom` defaults to centripetal Catmull-Rom (alpha=0.5)**; the Python `_pva01_smooth_path` uses uniform Catmull-Rom with a `/6.0` control-point offset. The curves drift visibly along sharp data inflections. d3 supports uniform Catmull-Rom via `d3.curveCatmullRom.alpha(0)`, but at that point we're configuring d3 to match our existing math instead of writing 25 lines of our existing math. The per-chart contract tests assert byte-similar output against the Python reference; reimplementing keeps that guarantee intact.

The reimplementation argument is also durability: 200 lines of `svg-lib.js` will outlive any specific d3 version's deprecation cycle.

### Node CLI (`cli.js`) — replaces `render.py`

```bash
node references/charts/cli.js <payload_dir> <output_dir>
```

No Node experimental flags. No `tsx`. No build step.

For each `{payload_dir}/{slug}.json` (sorted):

1. Read JSON.
2. Look up `RENDERERS[slug]`. If missing, record `{slug, reason: 'no renderer in registry'}` in `failed`.
3. Call renderer → `{ html, svgInner }`.
4. Write `{output_dir}/{slug}.html` from the renderer's `html`.
5. Shell out to `html_to_png.cjs` (`child_process.spawnSync('node', ['html_to_png.cjs', htmlPath, pngPath, ...])`) to produce `{output_dir}/{slug}.png`.
6. On any error (thrown by renderer, non-zero exit from `html_to_png.cjs`, fs failure): record `{slug, reason: 'ErrorName: message'}` in `failed`. Continue.
7. Print `{rendered: [{slug, path}], failed: [{slug, reason}]}` to stdout.
8. Exit `0` if no failures, `1` otherwise.

Same observable behavior as the Python `render.py`. No PIL-stitching path (the summary report is one renderer call now). No summary-composite logic.

`cli.js` is the **only** file in the package allowed to import `node:fs`, `node:path`, `node:child_process`, or `node:url`. The workers-import smoke test (below) enforces this rule.

### CF Workers consumption mechanism

The chart package itself is shaped identically regardless of how the consumer installs it. westland-mcps' branch picks one of:

| Option | What it looks like in westland-mcps' `package.json` | Trade-off |
|---|---|---|
| **A. Public-repo gitpkg shim** | `"@westland/charts": "https://gitpkg.vercel.app/CamronWalker/construction-skills/scheduling/skills/schedule-update/references/charts?main"` | **Ruled out while construction-skills is private.** gitpkg.vercel.app fetches via the public GitHub raw API; it cannot authenticate to private repos. Only viable if construction-skills is made public, which conflicts with the enterprise plugin distribution model. |
| **B. Publish to GitHub Packages (private npm)** | `"@westland/charts": "^0.1.0"` plus an `.npmrc` on the consumer side pointing at `https://npm.pkg.github.com/CamronWalker` with a `GITHUB_TOKEN` | **Preferred long-term.** GitHub Packages supports private packages free under modest usage. One-time setup: `npm publish` step in construction-skills' release flow (likely automated via the existing build hook), `.npmrc` + `GITHUB_TOKEN` secret in westland-mcps. ~30 min of one-time work, then frictionless — each chart commit auto-bumps the package version, westland-mcps `npm update`s when it wants. |
| **C. Git submodule** | westland-mcps adds construction-skills as a submodule at `vendor/construction-skills`, then `"@westland/charts": "file:vendor/construction-skills/scheduling/skills/schedule-update/references/charts"` | **Acceptable fallback.** Zero npm infra needed. Friction: every chart commit means `git submodule update --remote` + a commit in westland-mcps to bump the submodule pointer. Acceptable while the chart cadence is high (during this migration); annoying when it stabilises. |

This spec doesn't pick — the consumer branch does. The chart package's `package.json` is shaped to work with B (`"name": "@westland/charts"` ready to publish, valid `exports` field) and with C (`file:` deps don't need anything special). Switching between B and C later is a one-line change in westland-mcps' `package.json`.

### Visual contract — how byte-similarity is maintained

Each JS renderer ports its Python counterpart line-for-line:

- Same palette constants (hex codes from Chrome MCP DOM inspection).
- Same SVG card geometry (`1728 × 432`, padding `14 / 32 / 30 / 56`, plot rect derived from those).
- Same float-formatting precision (Python `f'{x:.2f}'` → JS `x.toFixed(2)`; Python `f'{y:.1f}'` → JS `y.toFixed(1)` for gridline y).
- Same date-tick algorithm (calendar-aware step selection: 7, 14, 30, 60, 90, 180, 365 days).
- Same Catmull-Rom smoother math (uniform Catmull-Rom, control points at `(p2 - p0) / 6.0` offset).
- Same HTML envelope CSS (Inter font, `.chart-card` 12px padding, `.legend-item` `6px 18px` gap).

The HTML contract tests (below) assert the *content* of the emitted HTML — palette colors, dasharray patterns, legend labels, title — and the visual diff against `chart-previews/` confirms the *layout* matches.

JS-specific watchouts during the port:

- **Date parsing.** Python `date.fromisoformat('2026-05-21')` returns a naive date. JS `new Date('2026-05-21')` returns a UTC-midnight Date that displays in the local timezone — the `.getDate()` may be off by one in negative-UTC zones. Use `new Date(`${iso}T00:00:00Z`)` and then `getUTCDate()` / `getUTCMonth()` consistently. Alternatively, parse to `{year, month, day}` and never use `Date` for date math.
- **Floor division.** Python `(d - dmin).days` is integer. JS `(d - dmin) / 86400000` is float; `Math.floor` it before using as a day count.
- **String `toFixed`.** JS's `Number.prototype.toFixed(2)` returns a string and uses banker's-rounding-ish behavior that differs from Python's `f'{x:.2f}'` on `.005` cases. Coordinates this fine-grained shouldn't show in PNG output, but the per-chart spec assertions look for literal substring matches — pin one or the other.
- **JSON.parse on the payload.** Make sure `cli.js` reads with `{ encoding: 'utf-8' }` and `JSON.parse` doesn't see a BOM — Python's `json.load` handles that automatically, Node's doesn't.

## Migration sequence — 12 commits

Each commit:
- Bumps `scheduling/.claude-plugin/plugin.json` + matching `marketplace.json` entry (pre-commit hook enforces this).
- Stays on the branch (no push to main, no `python build.py`, no deploy — per pivot tasks).

| # | Commit                                              | Scope                                                                                                                                                                                                                |
|---|-----------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| 1 | `feat(scheduling): JS chart package bootstrap`      | `package.json`, `jsconfig.json`, `svg-lib.js` (incl. `renderPlaceholder`) + spec, empty `meta.js` + spec, empty `registry.js`, `cli.js` skeleton, `tests/workers-import.test.js`, `index.js` re-exports. **Rename `html_to_png.js` → `html_to_png.cjs`** (no code change; forced by the new `"type":"module"`). **Types ship here — westland-mcps branch can start coding against `RenderResult` / `RenderFn` / `CHART_META` / `renderPlaceholder` immediately.** |
| 2 | `feat(scheduling): JS chart 01 (planned-vs-actual)` | Port `renderPlannedVsActual` + spec. Add `META` export. Register in `registry.js` + `meta.js`. Update `phases/screenshots.md` chart 01 recipe to point at JS CLI.                                                  |
| 3 | `feat(scheduling): JS chart 02 (schedule quality)`  | Port `renderScheduleQuality` + spec + META. Fix stale `grade.score` → `grade.mark` recipe in screenshots.md.                                                                                                       |
| 4 | `feat(scheduling): JS chart 03 (project health)`    | Port `renderProjectHealth` + spec + META. Fix stale `indicator` → `risk` recipe in screenshots.md.                                                                                                                  |
| 5 | `feat(scheduling): JS chart 04 (schedule changes)`  | Port `renderScheduleChanges` + spec + META. Document the dropped "Total Activities" column.                                                                                                                         |
| 6 | `feat(scheduling): JS charts 05, 13, 14`            | New trend renderers. Parent agent does Chrome MCP DOM inspection (subagents cannot auth to SmartPM); subagents receive captured palette/axis/series JSON in-prompt. Use Wellington (113385) or Anchorage (111751) projects when SGRWRF is data-sparse. |
| 7 | `feat(scheduling): JS charts 15, 16`                | Two more trend renderers. Same subagent-with-JSON-in-prompt workflow.                                                                                                                                              |
| 8 | `feat(scheduling): JS charts 06, 07`                | Visual upgrade from matplotlib — re-inspect DOM since matplotlib was an approximation.                                                                                                                              |
| 9 | `feat(scheduling): JS charts 08, 09`                | Velocity (the heavy one — 6 bar series + average line + data-date marker) + SPI.                                                                                                                                   |
| 10| `feat(scheduling): JS charts 10, 11, 12 (hit-rate trio)` | Three charts share the stacked-bar shape (Total / Started / Finished × On-Time / Late / Missed). Implement once via a shared `_renderHitRate` helper in the chart file, three thin entry-point wrappers.       |
| 11| `feat(scheduling): JS summary report`               | The big one — 3 sections (cards + curve + milestones table) in 1 HTML, single PNG. `svgInner: ''`.                                                                                                                  |
| 12| **Cleanup commit — see "Cleanup commit" section below**                                                                                                                                                              |

## Per-chart testing contract

Each `NN-slug.test.js` uses Vitest (`describe / it / expect`), runs against the existing fixture in `tests/fixtures/{slug}.json`, and asserts the HTML contract:

```js
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { renderPlannedVsActual, META } from './01-planned-vs-actual.js';

const fixture = JSON.parse(readFileSync(
  new URL('./tests/fixtures/01-planned-vs-actual-percent-complete.json', import.meta.url),
  'utf-8'
));

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
    expect(html).toContain(META.title);
  });

  it('emits each legend label', () => {
    for (const label of ['Progress Target', 'Late Date Planned', 'Planned (All Schedules)',
                          'Actual', 'Scheduled Completion', 'Early Date Planned']) {
      expect(html).toContain(label);
    }
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });

  it('throws on malformed payload', () => {
    expect(() => renderPlannedVsActual({ data: null })).toThrow(TypeError);
  });

  it('renders empty-state card for empty data array', () => {
    const { html: empty } = renderPlannedVsActual({ ...fixture, data: [] });
    expect(empty).toContain('no data');
  });
});
```

Per-chart specs assert the same seven things:
1. Every palette hex appears in `html`.
2. Every `stroke-dasharray` pattern appears in `html` (regression against the chart-02 disaster shape: invented colors / missing dashes).
3. Chart title appears verbatim (sourced from `META.title` — single source of truth).
4. Every legend label appears (when applicable — chart 02 / chart 03 have no legend, so this is skipped).
5. `svgInner` is non-empty for single-SVG charts. Summary report asserts `svgInner === ''` instead.
6. Malformed payload throws (error-handling contract regression).
7. Empty `data` array returns an empty-state card without throwing.

`svg-lib.test.js` adds geometry/scale/tick/placeholder boundary tests:
- `dateToX` / `pctToY` boundary conditions (dmin == dmax, p < 0, p > 100).
- `smoothPath` with 0, 1, 2, 3, n points.
- `xTicks` with various date spans (7 days, 90 days, 5 years).
- `markerSvg` for each kind.
- `htmlEnvelope` produces valid HTML5 with no `<script>` tag.
- `renderPlaceholder('01-planned-vs-actual-percent-complete')` produces an HTML doc whose SVG width matches `CHART_META['01-...'].svgWidth`.
- `renderPlaceholder('not-a-real-slug')` throws.
- `renderPlaceholder(slug, { message: 'Custom' })` includes the custom message text in `html`.

`meta.test.js`:
- Every key in `RENDERERS` has a matching key in `CHART_META`.
- Every key in `CHART_META` has a matching key in `RENDERERS`.
- Every `META` export has all three required fields (`svgWidth`, `svgHeight`, `title`).

`tests/workers-import.test.js` confirms CF-Workers portability — invokes `npx wrangler` against a 4-line shim Worker that imports `registry.js`, `meta.js`, and `renderPlaceholder`, and exports a `fetch` handler returning the placeholder HTML for one known slug. Asserts the bundle build succeeds and produces no Node-builtin warnings. Catches the "package suddenly depends on a Node-only import" regression at PR time. The test class-skips if `wrangler` is not installed locally, with a clear message ("install wrangler to run the workers-import smoke test").

**No Chromium-smoke equivalent at the unit level.** Visual regression is human eyeballing of `chart-previews/` PNGs after re-rendering with the JS CLI. The Python-spec's `--legacy` Playwright smoke is gone with the cleanup; the new approach is "look at the PNGs, compare to SmartPM web view."

## Cleanup commit (final, 12th commit)

After all 17 JS renderers are landed and visually verified against `chart-previews/`, **one** commit removes the Python rendering path and the legacy Playwright SmartPM-capture path.

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
scheduling/skills/schedule-update/references/charts/html_to_png.cjs              # Renamed from .js in commit 1; Node CLI still shells out to this
scheduling/skills/schedule-update/references/charts/tests/fixtures/*.json        # MCP response samples — language-agnostic
scheduling/skills/schedule-update/references/package.json                        # Playwright stays (html_to_png.cjs still uses chromium)
```

### Files edited

**`scheduling/skills/schedule-update/phases/screenshots.md`** — major revision:
- Single rendering path: MCP-fetch payload → `Write` `{slug}.json` → `node charts/cli.js <payload_dir> <output_dir>` → produces `{slug}.html` + `{slug}.png` pairs.
- All 17 per-slug MCP recipes inline, with the corrections discovered during the Python port:
  - **Chart 02:** raw `smartpm_get` against `/projects/{id}/scenarios/{id}/schedule-quality-trend`; reader uses `grade.mark` (letter, categorical), not `grade.score` (numeric); response is a flat list with no `{"trend": [...]}` envelope.
  - **Chart 03:** response is a flat list (no `{"trend": [...]}` envelope); indicator field is `risk`, not `indicator`.
  - **Chart 04:** response is a flat list (no `{"summary": [...]}` envelope); metrics nested under `metrics: {}` with PascalCase keys; no `totalActivities` field — "Total Activities" column is intentionally absent.
- The "non-default slugs / `--legacy` fallback" subsection: deleted entirely.
- The default `graph_screenshots` list: includes all 16 trend slugs + `smartpm-summary-report`.

**`scheduling/commands/write-weekly-schedule-email.md`** — Step 6 currently (lines 2 and 83) describes capture via `references/smartpm/capture-smartpm.js`. Stale post-Python-migration; doubly stale after this pivot. Update Step 6 to: "MCP-fetch each chart payload → run JS CLI to render all 17 PNGs."

**`scheduling/skills/schedule-update/SKILL.md`** — grep for any surviving references to `capture-smartpm.js` or `--legacy` and update or delete.

**`scheduling/skills/schedule-update/references/package.json`** (the outer `references/` package, NOT `charts/package.json`):
- Playwright dep stays — `html_to_png.cjs` still uses it.
- Remove any scripts that referenced deleted files (e.g. anything wired to `smartpm/capture-smartpm.js`).
- **Do NOT add vitest / typescript / @types/node here.** Those devDeps live in `charts/package.json`, were added in commit 1, and stay there. Running chart tests is `cd references/charts && npm test`; running the email-pipeline tests stays on whatever pytest invocation already exists.

The new chart package's `package.json` (at `references/charts/package.json`) was already complete from commit 1 (`"name": "@westland/charts"`, `"type": "module"`, `exports`, devDeps, scripts). The cleanup commit doesn't touch it.

**`scheduling/.claude-plugin/plugin.json` + `.claude-plugin/marketplace.json`** scheduling entry — version bump (matched pair, enforced by the pre-commit hook).

### Smoke test before merging the cleanup commit

```bash
# 1. Nothing in the skill references the deleted files
git grep -E "capture-smartpm|smartpm-client|matplotlib|_composite_summary_report|--legacy|charts\.py|render\.py" -- 'scheduling/'
# Expected: zero matches.

# 2. JS CLI handles every slug end-to-end from a real project payload
node scheduling/skills/schedule-update/references/charts/cli.js \
  scheduling/skills/schedule-update/references/charts/tests/fixtures \
  /tmp/chart-cleanup-smoke
# Expected: 17 .html + 17 .png in /tmp/chart-cleanup-smoke, exit 0.

# 3. Tests pass (run from inside the chart package, not the outer references/ dir)
cd scheduling/skills/schedule-update/references/charts && npm test
# Expected: every per-chart spec green, svg-lib spec green, meta spec green, workers-import test passes (or class-skipped with a clear message).

# 4. JSDoc type-checking passes
cd scheduling/skills/schedule-update/references/charts && npm run typecheck
# Expected: no errors.
```

If any check fails, fix inside the cleanup commit before merge.

## Risks & mitigations

**1. The cloud-editor consumer spec does not exist yet.** Neither on this branch nor on `claude/interesting-noyce-d0f3e2` (which is currently at `main` lineage). The API surface is designed against the prompt's stated `{ html, svgInner }` shape plus `renderPlaceholder` and `CHART_META`. *Mitigation:* the API ships in commit 1 (bootstrap); if the cloud-editor spec, once written, needs adjustments, those can land before lots of charts are built against the wrong shape. Commits 2–11 only touch per-chart files plus the registry — easy to refactor the return type later if needed.

**2. Subagent Chrome MCP cannot authenticate to SmartPM** — cookies don't carry between subagent contexts. This caused the chart-02 disaster on the Python port (invented palette `#54a854 / #f5a623 / #c0223a`). *Mitigation:* parent agent does ALL Chrome MCP DOM inspections, captures palette + axis + series structure as JSON, then passes that JSON inside the implementer subagent's prompt. Subagents stop needing Chrome MCP. This workflow is documented in the implementation plan, not the spec.

**3. SGRWRF (project 141462) is data-sparse for some charts.** Chart 05 has no rendered series; chart 04's "Total Activities" column has no bars. *Mitigation:* use Wellington NZ Temple (113385, `defaultScenarioId=1644`) or Anchorage Alaska Temple (111751, `defaultScenarioId=1618`) for inspection when SGRWRF is empty.

**4. MCP response shapes differ from documentation.** Discovered during the Python port: chart 02 has no dedicated tool (use raw `smartpm_get`); chart 03 response is flat list with `risk` not `indicator`; chart 04 metrics nest under `metrics{}` with PascalCase. *Mitigation:* always fetch the fixture first and read the JSON before writing the renderer. Each chart's payload shape is documented in its `*.js` file's `RenderXyzPayload` JSDoc typedef — `tsc --noEmit` catches drift the second the orchestrator passes the wrong field.

**5. `svgInner` shape mismatch for the summary report.** Single-SVG-per-chart assumption breaks for a 3-section composite. *Mitigation:* `renderSummaryReport` returns `{ html, svgInner: '' }`. Documented at the call site and in the `RenderFn` JSDoc. The summary-report spec asserts `svgInner === ''` so the contract is enforced.

**6. Visual drift from Python.** Float-formatting differences (Python `%.2f` vs JS `.toFixed(2)`), date parsing nuance, or floating-point rounding could shift pixels. *Mitigation:* per-chart spec asserts the contract content (palette, dasharray, labels); `chart-previews/` PNG diff against the Python reference is the layout regression check. If the PNGs differ noticeably, the float math is off — fix and re-render. Specific watchouts called out in "Visual contract" §.

**7. Cross-runtime portability regression.** A future renderer accidentally imports `node:fs` or `node:path` and breaks CF Workers consumption. *Mitigation:* `tests/workers-import.test.js` invokes `wrangler` against a shim Worker that imports the package. Runs in CI / as part of `npm test`. The CLI (`cli.js`) is the *only* file allowed to import Node-only modules; per-chart files, `svg-lib.js`, `meta.js`, and `registry.js` must be pure-string-output / pure-data.

**8. Cleanup commit reverts working code prematurely.** If commits 6–11 produce a chart whose visual doesn't match SmartPM and we can't fix it before merge, deleting matplotlib means no fallback. *Mitigation:* the cleanup commit is the **12th** commit, after every JS renderer is verified visually against `chart-previews/`. If commit 11 (summary report) isn't ready, the cleanup commit isn't either — Python stays until both are green.

**9. JSDoc types silently diverge from runtime payloads.** `tsc --noEmit` only checks code that has annotations. If a renderer accidentally drops the JSDoc on a payload field, the check passes vacuously. *Mitigation:* `meta.test.js` plus the per-chart "throws on malformed payload" test together catch the case where the renderer is parsing fields the typedef doesn't document, or vice versa. Less rigid than TypeScript's compile-time guarantee but sufficient for this surface area.

**10. CF Workers consumption mechanism is undecided.** westland-mcps' branch picks between B (GitHub Packages) and C (git submodule). *Mitigation:* the chart package's `package.json` is shaped to work with either; switching from C to B later is a one-line change in the consumer's `package.json`. This branch ships the library in a form that doesn't lock in either choice.

## Open questions

The four open questions from the pivot prompt are settled in **Architecture** above:

1. **d3 vs reimplement** → reimplement (~200 lines, no runtime deps, byte-similar output guarantee preserved, durability over d3 deprecation cycles, avoids the centripetal-vs-uniform Catmull-Rom drift).
2. **CF Workers consumption mechanism** → noted but not picked here. westland-mcps' branch settles between **B (GitHub Packages, preferred long-term)** and **C (git submodule, acceptable fallback)**. **A (gitpkg)** is ruled out while construction-skills is private.
3. **Python renderer cleanup timing** → leave during migration (commits 2–11) for side-by-side eyeball reference, revert wholesale in the 12th cleanup commit.
4. **Test runner** → Vitest primary (per-chart `*.test.js` colocated next to `*.js`); one `tests/workers-import.test.js` for cross-runtime smoke; `meta.test.js` for registry/META coverage.

## What "done" looks like

- All 17 JS renderers in `scheduling/skills/schedule-update/references/charts/*.js`, each one file, exporting `renderXyz(payload): RenderResult` and a `META` const.
- `registry.js` maps 17 slugs → 17 renderer functions. No stubs.
- `meta.js` maps 17 slugs → 17 `META` records. No stubs. `meta.test.js` confirms 1:1 coverage with `registry.js`.
- `svg-lib.js` holds all shared plumbing — including `renderPlaceholder` — and per-chart files never mention Chromium or `html_to_png.cjs` (that's `cli.js`'s job).
- `cli.js` reads payloads, writes `.html` + `.png` pairs, matches the observable contract of the deleted `render.py`.
- `renderPlaceholder('<any-known-slug>')` returns a `RenderResult` with HTML matching the chart's declared dimensions and a placeholder card visible in the browser.
- Vitest specs green: 17 per-chart contract specs + svg-lib spec + meta spec + workers-import smoke test.
- `chart-previews/` re-rendered with JS, eyeball-compared against SmartPM web rendering and the Python reference PNGs, judged faithful for at least 2 projects (SGRWRF + 1 data-rich project like Wellington or Anchorage).
- `charts.py`, `render.py`, `style.py`, `requirements.txt` deleted. No `matplotlib`, `numpy`, `Pillow`, `mdates`, `mticker`, `LineCollection`, `DateFormatter`, `FancyBboxPatch`, `Rectangle` strings anywhere in `scheduling/`.
- `references/smartpm/` directory removed. `--legacy` Playwright capture path removed from `phases/screenshots.md`. Two smoke-test files (`smartpm.spec.js`, `full-page-debug.spec.js`) removed.
- `phases/screenshots.md` documents one path, all 17 MCP recipes inline with the corrected chart-02 / chart-03 / chart-04 details.
- `commands/write-weekly-schedule-email.md` Step 6 description updated.
- `scheduling/.claude-plugin/plugin.json` + `marketplace.json` bumped through 12 versions, all matched pairs.
- Branch state at the end: the westland-mcps consumer branch can `import { RENDERERS, CHART_META, renderPlaceholder } from '@westland/charts'` (regardless of whether B or C is the install mechanism) and dispatch every slug. Local weekly schedule update produces identical-filename PNGs via the JS CLI.

When the dust settles, a future engineer touching one chart's visuals edits one `NN-slug.js` file, runs `vitest run -- NN-slug`, eyeballs the regenerated PNG against SmartPM, and ships. They never see matplotlib, never reach for `--legacy`, never re-encounter the dashed-line bug, never need a TypeScript build step, never need to think about Python/Node bridging.
