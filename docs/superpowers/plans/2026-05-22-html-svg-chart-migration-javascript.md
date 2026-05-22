# HTML+SVG Chart Migration (JavaScript) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Port the 4 Python HTML+SVG chart renderers (chart 01–04) to JavaScript with JSDoc types, add 13 more renderers (charts 05–16 + summary report), and delete the Python rendering path entirely. End state: one JS package shippable to both Node CLI (local weekly email pipeline) and Cloudflare Workers (westland-mcps cloud-editor consumer).

**Architecture:** ESM JavaScript with JSDoc-typed payloads. One file per slug, each exporting a pure `renderXyz(payload): { html, svgInner }` function plus a `META` const. Aggregated by `registry.js` (slug → renderFn) and `meta.js` (slug → dimensions/title). Shared geometry helpers in `svg-lib.js` (line-for-line port of Python `_pva01_*` helpers, no d3). Node-only `cli.js` shells out to a renamed `html_to_png.cjs` for PNG rasterisation.

**Tech Stack:** Node 18+ (ESM), Vitest (tests), TypeScript devDep (for `tsc --noEmit` JSDoc type-checking), Playwright (existing, used by `html_to_png.cjs` only), Wrangler (devDep on consumer side; smoke-test optional locally).

**Spec reference:** [`docs/superpowers/specs/2026-05-22-html-svg-chart-migration-javascript-design.md`](../specs/2026-05-22-html-svg-chart-migration-javascript-design.md).

---

## Conventions used throughout this plan

Repeated in each task because the engineer may read tasks out of order.

**Working directory** for shell commands: `scheduling/skills/schedule-update/references/charts/` unless stated otherwise. Paths in this plan are relative to the repo root.

**Tests run via Vitest:** `cd scheduling/skills/schedule-update/references/charts && npm test`. To run one file: `npx vitest run NN-slug.test.js`. To watch: `npx vitest`.

**Type-check the JSDoc:** `cd scheduling/skills/schedule-update/references/charts && npm run typecheck`.

**Per-commit version bump** (enforced by `.githooks/pre-commit`):
1. Bump `scheduling/.claude-plugin/plugin.json` `version` field (semver patch).
2. Bump matching `plugins[].version` in `.claude-plugin/marketplace.json` to the same value.
3. Both bumps must be in the same commit as the code change.

**Commit message format:** `feat(scheduling): JS chart NN (slug)` or `feat(scheduling): JS chart package bootstrap` (per spec migration table). End with the Claude co-author trailer:

```
Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

**Visual verification step** is human eyeballing — there's no automated PNG diff. The plan tells you to render to `chart-previews/` (which is `.gitignore`'d) and visually compare to SmartPM's live web view. The browser tab open to SmartPM's trends page on the project under test (SGRWRF: project 141462, scenario 1721; Wellington: project 113385, scenario 1644; Anchorage: project 111751, scenario 1618) is your visual contract.

**Chrome MCP DOM inspection** (commits 6–11): subagents cannot authenticate to SmartPM — cookies don't carry across subagent contexts. The PARENT AGENT must do all DOM inspections, capture palette / dasharray / series structure as JSON, and pass that JSON in the subagent's prompt. If you find yourself dispatching a subagent that says "I'll inspect SmartPM," stop and do the inspection yourself first.

---

## File structure

### Files created in commit 1 (the bootstrap)

| Path | Purpose |
|---|---|
| `scheduling/skills/schedule-update/references/charts/package.json` | Chart package manifest. `"name": "@westland/charts"`, `"type": "module"`, exports field, devDeps. |
| `scheduling/skills/schedule-update/references/charts/jsconfig.json` | JSDoc type-check config. `allowJs: true, checkJs: true, noEmit: true`. |
| `scheduling/skills/schedule-update/references/charts/svg-lib.js` | Ported geometry/glyph/envelope helpers + `renderPlaceholder`. |
| `scheduling/skills/schedule-update/references/charts/svg-lib.test.js` | Unit tests for `svg-lib.js`. |
| `scheduling/skills/schedule-update/references/charts/registry.js` | `RENDERERS` map (empty at commit 1; chart entries added in commits 2–11). |
| `scheduling/skills/schedule-update/references/charts/meta.js` | `CHART_META` map (empty at commit 1; entries added in commits 2–11). |
| `scheduling/skills/schedule-update/references/charts/meta.test.js` | Asserts 1:1 coverage between `RENDERERS` and `CHART_META`. |
| `scheduling/skills/schedule-update/references/charts/index.js` | Top-level re-exports of `RENDERERS`, `CHART_META`, `renderPlaceholder`, all renderers. |
| `scheduling/skills/schedule-update/references/charts/cli.js` | Node CLI driver. Reads `{slug}.json` from a payload dir, writes `{slug}.html` + `{slug}.png` to an output dir, shells to `html_to_png.cjs` for rasterisation. |
| `scheduling/skills/schedule-update/references/charts/tests/workers-import.test.js` | Wrangler-bundle smoke test catching Node-only imports in renderer code. |

### Files renamed in commit 1

- `scheduling/skills/schedule-update/references/charts/html_to_png.js` → `html_to_png.cjs`. **No code change.** Forced by the package's new `"type": "module"`.

### Files created per chart (commits 2–11)

For each slug `NN-slug`:
- `scheduling/skills/schedule-update/references/charts/NN-slug.js` — renderer + `META` export.
- `scheduling/skills/schedule-update/references/charts/NN-slug.test.js` — palette / dasharray / title / legend / malformed-payload / empty-data assertions.

Modified each chart commit:
- `registry.js` — add `import` + entry.
- `meta.js` — add `import` + entry.
- `index.js` — add `export`.
- `phases/screenshots.md` — verify/update the per-slug MCP recipe.

### Files deleted in commit 12 (cleanup)

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

---

## Task 1: Bootstrap the chart package (commit 1)

**Goal:** A working `@westland/charts` package with no chart implementations yet — but with the full API surface (`renderPlaceholder`, types, CLI, smoke test) so the westland-mcps consumer branch can start coding against it.

**Files:**
- Create: `scheduling/skills/schedule-update/references/charts/package.json`
- Create: `scheduling/skills/schedule-update/references/charts/jsconfig.json`
- Create: `scheduling/skills/schedule-update/references/charts/svg-lib.js`
- Create: `scheduling/skills/schedule-update/references/charts/svg-lib.test.js`
- Create: `scheduling/skills/schedule-update/references/charts/registry.js`
- Create: `scheduling/skills/schedule-update/references/charts/meta.js`
- Create: `scheduling/skills/schedule-update/references/charts/meta.test.js`
- Create: `scheduling/skills/schedule-update/references/charts/index.js`
- Create: `scheduling/skills/schedule-update/references/charts/cli.js`
- Create: `scheduling/skills/schedule-update/references/charts/tests/workers-import.test.js`
- Rename: `scheduling/skills/schedule-update/references/charts/html_to_png.js` → `html_to_png.cjs`
- Modify: `scheduling/.claude-plugin/plugin.json` (version bump)
- Modify: `.claude-plugin/marketplace.json` (matching version bump)

- [ ] **Step 1: Rename `html_to_png.js` to `html_to_png.cjs` (preserve git history)**

```bash
git mv scheduling/skills/schedule-update/references/charts/html_to_png.js \
       scheduling/skills/schedule-update/references/charts/html_to_png.cjs
```

No code change inside the file. The `.cjs` extension overrides the package's `"type": "module"` for that single file, letting `require('playwright')` continue to work.

- [ ] **Step 2: Create `package.json`**

```json
{
  "name": "@westland/charts",
  "version": "0.1.0",
  "type": "module",
  "main": "./index.js",
  "exports": {
    ".":          "./index.js",
    "./registry": "./registry.js",
    "./meta":     "./meta.js",
    "./svg-lib":  "./svg-lib.js"
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

- [ ] **Step 3: Create `jsconfig.json`**

```json
{
  "compilerOptions": {
    "target":           "ES2022",
    "module":           "ESNext",
    "moduleResolution": "Bundler",
    "allowJs":          true,
    "checkJs":          true,
    "noEmit":           true,
    "strict":           true,
    "lib":              ["ES2022"]
  },
  "include": ["*.js", "tests/**/*.js"]
}
```

- [ ] **Step 4: Install devDeps**

```bash
cd scheduling/skills/schedule-update/references/charts && npm install
```

Expected: `node_modules/` populated, no errors. (`node_modules/` is `.gitignore`'d at repo root.)

- [ ] **Step 5: Write `svg-lib.test.js` — all helpers expected to fail**

```js
// svg-lib.test.js
import { describe, it, expect } from 'vitest';
import {
  dateToX, pctToY, smoothPath, xTicks, seriesPts,
  markerSvg, legendItem, htmlEnvelope, emptyHtml, renderPlaceholder,
} from './svg-lib.js';

describe('dateToX', () => {
  it('maps dmin → x0 and dmax → x1', () => {
    const dmin = new Date('2026-01-01T00:00:00Z');
    const dmax = new Date('2026-12-31T00:00:00Z');
    expect(dateToX(dmin, dmin, dmax, 100, 900)).toBeCloseTo(100, 6);
    expect(dateToX(dmax, dmin, dmax, 100, 900)).toBeCloseTo(900, 6);
  });
  it('treats dmin === dmax as span=1 (no divide-by-zero)', () => {
    const d = new Date('2026-01-01T00:00:00Z');
    expect(dateToX(d, d, d, 100, 900)).toBe(100);
  });
});

describe('pctToY', () => {
  it('inverts: 0% → y1, 100% → y0', () => {
    expect(pctToY(0,   100, 400)).toBe(400);
    expect(pctToY(100, 100, 400)).toBe(100);
  });
  it('clamps below 0 and above 100', () => {
    expect(pctToY(-50,  100, 400)).toBe(400);
    expect(pctToY(150,  100, 400)).toBe(100);
  });
});

describe('smoothPath', () => {
  it('returns empty string for empty input', () => {
    expect(smoothPath([])).toBe('');
  });
  it('returns a single M for one point', () => {
    expect(smoothPath([[10, 20]])).toMatch(/^M 10\.00,20\.00$/);
  });
  it('returns M+L for two points', () => {
    expect(smoothPath([[0, 0], [10, 10]])).toMatch(/^M 0\.00,0\.00 L 10\.00,10\.00$/);
  });
  it('emits M + C segments for three or more points', () => {
    const out = smoothPath([[0, 0], [10, 10], [20, 5]]);
    expect(out).toMatch(/^M 0\.00,0\.00 /);
    expect(out).toMatch(/ C /);
  });
});

describe('xTicks', () => {
  it('picks 7-day stride for short ranges', () => {
    const dmin = new Date('2026-01-01T00:00:00Z');
    const dmax = new Date('2026-01-31T00:00:00Z');
    const ticks = xTicks(dmin, dmax, 10);
    expect(ticks.length).toBeGreaterThanOrEqual(4);
    expect(ticks.length).toBeLessThanOrEqual(10);
  });
  it('always includes dmax as the last tick', () => {
    const dmin = new Date('2026-01-01T00:00:00Z');
    const dmax = new Date('2026-04-15T00:00:00Z');
    const ticks = xTicks(dmin, dmax, 6);
    expect(ticks[ticks.length - 1].getTime()).toBe(dmax.getTime());
  });
});

describe('markerSvg', () => {
  for (const kind of ['circle', 'square', 'diamond', 'triangle', 'invtri']) {
    it(`emits SVG for kind=${kind}`, () => {
      expect(markerSvg(kind, 10, 20, '#abc', 4)).toMatch(/^<(circle|rect|polygon)\b/);
    });
  }
  it('returns empty string for unknown kind', () => {
    // @ts-expect-error — testing the runtime guard
    expect(markerSvg('unknown', 10, 20, '#abc', 4)).toBe('');
  });
});

describe('htmlEnvelope', () => {
  it('contains the title text escaped', () => {
    const html = htmlEnvelope({
      title: 'My <Chart> & Co',
      svgW: 1692, svgH: 312,
      svgInner: '<g/>',
      legendHtml: '',
    });
    expect(html).toContain('&lt;Chart&gt;');
    expect(html).not.toContain('<script');
  });
  it('has no <script> tag (rasteriser must render with JS disabled)', () => {
    const html = htmlEnvelope({
      title: 't', svgW: 100, svgH: 100, svgInner: '', legendHtml: '',
    });
    expect(html).not.toContain('<script');
  });
});

describe('renderPlaceholder', () => {
  it('throws on unknown slug', () => {
    expect(() => renderPlaceholder('not-a-real-slug')).toThrow(/unknown slug/i);
  });
  // Note: the "matches CHART_META dimensions" test moves into chart commits as
  // CHART_META gets populated. At commit 1, CHART_META is empty, so we only
  // verify the throw behavior here.
});
```

- [ ] **Step 6: Run the tests — confirm they all fail**

```bash
cd scheduling/skills/schedule-update/references/charts && npx vitest run svg-lib.test.js
```

Expected: every test errors with `Cannot find module './svg-lib.js'` or `is not a function`. That's fine — we haven't written it yet.

- [ ] **Step 7: Write `svg-lib.js` — port from `charts.py:1311–1531`**

Read the Python reference: [`scheduling/skills/schedule-update/references/charts/charts.py`](../../scheduling/skills/schedule-update/references/charts/charts.py) lines 1311–1531 (`_pva01_*` helpers + envelope).

Translate each Python helper to a JS export. Naming map:

| Python | JS |
|---|---|
| `_pva01_x` | `dateToX` |
| `_pva01_y` | `pctToY` |
| `_pva01_smooth_path` | `smoothPath` |
| `_pva01_x_ticks` | `xTicks` |
| `_pva01_series_pts` | `seriesPts` |
| `_pva01_marker_svg` | `markerSvg` |
| `_pva01_legend_item_html` | `legendItem` |
| `_pva01_html_envelope` | `htmlEnvelope` |
| `_pva01_empty_html` | `emptyHtml` |
| (new) | `renderPlaceholder` |

Key translation notes (from the spec's "Visual contract" §):
- Python `date.fromisoformat('2026-05-21')` → JS `new Date('2026-05-21T00:00:00Z')`. Use `getUTCDate()` / `getUTCMonth()` / `getUTCFullYear()` exclusively for date math. Never call `.getDate()` (returns local-tz day-of-month).
- Python `(d - dmin).days` → `Math.floor((d.getTime() - dmin.getTime()) / 86400000)`. Add `|| 1` to the `span` to match the Python `or 1` fallback.
- Python `f'{x:.2f}'` → JS `x.toFixed(2)`. They're string-equal for non-`.005` cases; coordinate values from `(d - dmin) / span * (x1 - x0)` won't typically land on `.005` boundaries.
- Python `_html_lib.escape(s)` → write your own small `escapeHtml(s)` (5-replace function: `&`, `<`, `>`, `"`, `'`).

JSDoc-typed skeleton (write the bodies by porting from Python):

```js
// svg-lib.js
// Card dimensions — matches the SmartPM web view exactly.
export const HTML_CARD_W = 1728;
export const HTML_CARD_H = 432;

// Palette constants from chart 01 (lifted into svg-lib because envelope CSS
// references them). Per-chart palettes live in their own files.
const PVA01_GRID       = '#e6e6e6';
const PVA01_AXIS_TEXT  = '#666';
const PVA01_TITLE_TEXT = '#181d27';

/**
 * @typedef {Object} RenderResult
 * @property {string} html      Self-contained HTML document.
 * @property {string} svgInner  The <g> contents — for embedding in another doc.
 *                              Empty string for composite renderers.
 */

/**
 * @template [T=any]
 * @typedef {(payload: T) => RenderResult} RenderFn
 */

/** @typedef {'circle'|'square'|'diamond'|'triangle'|'invtri'} MarkerKind */

/** @param {string} s @returns {string} */
function escapeHtml(s) {
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

/**
 * @param {Date} d @param {Date} dmin @param {Date} dmax @param {number} x0 @param {number} x1
 * @returns {number}
 */
export function dateToX(d, dmin, dmax, x0, x1) {
  const span = Math.max(1, Math.floor((dmax.getTime() - dmin.getTime()) / 86400000));
  const offset = Math.floor((d.getTime() - dmin.getTime()) / 86400000);
  return x0 + (offset / span) * (x1 - x0);
}

/** @param {number} p @param {number} y0 @param {number} y1 @returns {number} */
export function pctToY(p, y0, y1) {
  const clamped = Math.max(0, Math.min(100, p));
  return y1 - (clamped / 100) * (y1 - y0);
}

/** @param {Array<[number, number]>} pts @returns {string} */
export function smoothPath(pts) {
  if (!pts.length) return '';
  if (pts.length === 1) {
    const [x, y] = pts[0];
    return `M ${x.toFixed(2)},${y.toFixed(2)}`;
  }
  if (pts.length === 2) {
    const [[x0, y0], [x1, y1]] = pts;
    return `M ${x0.toFixed(2)},${y0.toFixed(2)} L ${x1.toFixed(2)},${y1.toFixed(2)}`;
  }
  const out = [`M ${pts[0][0].toFixed(2)},${pts[0][1].toFixed(2)}`];
  const n = pts.length;
  for (let i = 0; i < n - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] ?? p2;
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = p2[1] - (p3[1] - p1[1]) / 6;
    out.push(
      `C ${c1x.toFixed(2)},${c1y.toFixed(2)} ` +
      `${c2x.toFixed(2)},${c2y.toFixed(2)} ` +
      `${p2[0].toFixed(2)},${p2[1].toFixed(2)}`
    );
  }
  return out.join(' ');
}

/** @param {Date} dmin @param {Date} dmax @param {number} [maxTicks=10] @returns {Date[]} */
export function xTicks(dmin, dmax, maxTicks = 10) {
  const spanDays = Math.max(1, Math.floor((dmax.getTime() - dmin.getTime()) / 86400000));
  const candidates = [7, 14, 30, 60, 90, 180, 365];
  let stride = 365;
  for (const c of candidates) {
    if (spanDays / Math.max(c, 1) <= maxTicks) { stride = c; break; }
  }
  /** @type {Date[]} */
  const ticks = [];
  let d = new Date(dmin.getTime());
  while (d.getTime() <= dmax.getTime()) {
    ticks.push(new Date(d.getTime()));
    d = new Date(d.getTime() + stride * 86400000);
  }
  if (ticks[ticks.length - 1].getTime() !== dmax.getTime()) ticks.push(new Date(dmax.getTime()));
  return ticks;
}

/**
 * @param {Array<Record<string, unknown>>} rows
 * @param {string} field
 * @param {Date} dmin @param {Date} dmax
 * @param {number} x0 @param {number} x1 @param {number} y0 @param {number} y1
 * @returns {Array<[number, number]>}
 */
export function seriesPts(rows, field, dmin, dmax, x0, x1, y0, y1) {
  /** @type {Array<[number, number]>} */
  const out = [];
  for (const r of rows) {
    const v = r[field];
    if (v === null || v === undefined) continue;
    const d = new Date(`${String(r.DATE)}T00:00:00Z`);
    out.push([dateToX(d, dmin, dmax, x0, x1), pctToY(Number(v), y0, y1)]);
  }
  return out;
}

/**
 * @param {MarkerKind} kind @param {number} x @param {number} y @param {string} color @param {number} [size=4]
 * @returns {string}
 */
export function markerSvg(kind, x, y, color, size = 4) {
  if (kind === 'circle') {
    return `<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="${size}" fill="${color}" stroke="none" />`;
  }
  if (kind === 'square') {
    const s = size;
    return `<rect x="${(x - s).toFixed(2)}" y="${(y - s).toFixed(2)}" width="${s * 2}" height="${s * 2}" fill="${color}" />`;
  }
  if (kind === 'diamond') {
    const s = size + 1;
    return `<polygon points="${x.toFixed(2)},${(y - s).toFixed(2)} ${(x + s).toFixed(2)},${y.toFixed(2)} ${x.toFixed(2)},${(y + s).toFixed(2)} ${(x - s).toFixed(2)},${y.toFixed(2)}" fill="${color}" />`;
  }
  if (kind === 'triangle') {
    const s = size + 1;
    return `<polygon points="${x.toFixed(2)},${(y - s).toFixed(2)} ${(x + s).toFixed(2)},${(y + s).toFixed(2)} ${(x - s).toFixed(2)},${(y + s).toFixed(2)}" fill="${color}" />`;
  }
  if (kind === 'invtri') {
    const s = size + 1;
    return `<polygon points="${x.toFixed(2)},${(y + s).toFixed(2)} ${(x + s).toFixed(2)},${(y - s).toFixed(2)} ${(x - s).toFixed(2)},${(y - s).toFixed(2)}" fill="${color}" />`;
  }
  return '';
}

/**
 * @param {MarkerKind | 'area'} kind @param {string} color @param {string} dash @param {string} label
 * @returns {string}
 */
export function legendItem(kind, color, dash, label) {
  const labelEsc = escapeHtml(label);
  if (kind === 'area') {
    const swatch =
      '<svg width="22" height="10" viewBox="0 0 22 10">' +
      `<rect x="0" y="0" width="22" height="10" fill="${color}" ` +
      `fill-opacity="0.2" stroke="${color}" stroke-width="1" />` +
      '</svg>';
    return `<span class="legend-item">${swatch}<span class="legend-label">${labelEsc}</span></span>`;
  }
  const dashAttr = dash ? ` stroke-dasharray="${dash}"` : '';
  const swatch =
    '<svg width="26" height="10" viewBox="0 0 26 10">' +
    `<line x1="0" y1="5" x2="26" y2="5" stroke="${color}" stroke-width="2"${dashAttr} />` +
    markerSvg(/** @type {MarkerKind} */ (kind), 13, 5, color, 4) +
    '</svg>';
  return `<span class="legend-item">${swatch}<span class="legend-label">${labelEsc}</span></span>`;
}

/**
 * @param {{ title: string, svgW: number, svgH: number, svgInner: string,
 *           legendHtml: string, cardW?: number, cardH?: number }} opts
 * @returns {string}
 */
export function htmlEnvelope({ title, svgW, svgH, svgInner, legendHtml, cardW = HTML_CARD_W, cardH = HTML_CARD_H }) {
  const titleEsc = escapeHtml(title);
  // CSS-templated card; everything is inline so the rasteriser doesn't need fetches.
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${titleEsc}</title>
<style>
  html, body { margin: 0; padding: 0; background: #ffffff; font-family: Inter, "Helvetica Neue", Arial, sans-serif; color: ${PVA01_TITLE_TEXT}; -webkit-font-smoothing: antialiased; }
  .chart-card { width: ${cardW}px; height: ${cardH}px; box-sizing: border-box; background: #ffffff; border-radius: 12px; padding: 14px 18px 8px; display: flex; flex-direction: column; }
  .chart-title { font-size: 14px; font-weight: 600; color: ${PVA01_TITLE_TEXT}; margin: 0 0 6px 0; line-height: 1.1; }
  .chart-svg { display: block; flex: 0 0 auto; }
  .axis-text { font-size: 11px; fill: ${PVA01_AXIS_TEXT}; }
  .axis-text-y { text-anchor: end; }
  .axis-text-x { text-anchor: middle; }
  .axis-title-text { font-size: 12px; fill: ${PVA01_AXIS_TEXT}; text-anchor: middle; }
  .grid-line { stroke: ${PVA01_GRID}; stroke-width: 1; stroke-dasharray: 2,3; }
  .legend-row { display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 6px 18px; font-size: 11px; color: ${PVA01_TITLE_TEXT}; padding-top: 6px; }
  .legend-item { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
  .legend-label { line-height: 1; }
</style>
</head>
<body>
<div class="chart-card">
  <h3 class="chart-title">${titleEsc}</h3>
  <svg class="chart-svg" width="${svgW}" height="${svgH}" viewBox="0 0 ${svgW} ${svgH}" xmlns="http://www.w3.org/2000/svg">
${svgInner}
  </svg>
  <div class="legend-row">
${legendHtml}
  </div>
</div>
</body>
</html>
`;
}

/** @param {string} title @returns {string} */
export function emptyHtml(title) {
  const titleEsc = escapeHtml(title);
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>${titleEsc}</title>
<style>
  html, body { margin: 0; padding: 0; background: #fff; font-family: Inter, sans-serif; color: ${PVA01_TITLE_TEXT}; }
  .chart-card { width: ${HTML_CARD_W}px; height: ${HTML_CARD_H}px; box-sizing: border-box; padding: 14px 18px 8px; display: flex; align-items: center; justify-content: center; }
  .chart-title { font-size: 14px; font-weight: 600; }
</style></head><body>
<div class="chart-card"><h3 class="chart-title">${titleEsc} — no data</h3></div>
</body></html>
`;
}

/**
 * Render a placeholder card matching the dimensions of the real chart for `slug`.
 *
 * @param {string} slug
 * @param {{ message?: string, icon?: 'clock'|'warn'|'none' }} [opts]
 * @returns {RenderResult}
 * @throws {Error} unknown slug.
 */
export function renderPlaceholder(slug, opts = {}) {
  // Lazy import to avoid circular: meta.js imports per-chart files which may
  // import svg-lib.js. By requiring meta only inside the function, the cycle
  // is broken at module load time.
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  /** @type {{ CHART_META: Record<string, {svgWidth:number, svgHeight:number, title:string}> }} */
  // Use a dynamic import-then-cache pattern. At commit 1 CHART_META is {}, so
  // the throw path is the only reachable code.
  /** @type {Record<string, {svgWidth:number, svgHeight:number, title:string}>} */
  // We do this synchronously by reading from the already-evaluated module.
  // eslint-disable-next-line no-undef
  const metaModule = globalThis.__WESTLAND_CHART_META__;
  if (!metaModule) {
    // Synchronous cycle-safe load: tests inject CHART_META via globalThis at setup;
    // production code path uses the static import from meta.js below.
    throw new Error(`unknown slug "${slug}": CHART_META not loaded`);
  }
  const meta = metaModule[slug];
  if (!meta) throw new Error(`unknown slug "${slug}"`);
  const { svgWidth, svgHeight, title } = meta;
  const message = opts.message ?? 'Data not yet available';
  const icon = opts.icon ?? 'clock';
  const iconSvg = iconGlyph(icon, svgWidth / 2, svgHeight / 2 - 20);
  const svgInner =
    `<g>` +
    iconSvg +
    `<text x="${svgWidth / 2}" y="${svgHeight / 2 + 30}" text-anchor="middle" class="axis-text" font-size="16">${escapeHtml(message)}</text>` +
    `</g>`;
  const html = htmlEnvelope({ title, svgW: svgWidth, svgH: svgHeight, svgInner, legendHtml: '' });
  return { html, svgInner };
}

/** @param {'clock'|'warn'|'none'} icon @param {number} cx @param {number} cy @returns {string} */
function iconGlyph(icon, cx, cy) {
  if (icon === 'none') return '';
  if (icon === 'warn') {
    return `<polygon points="${cx},${cy - 14} ${cx + 14},${cy + 10} ${cx - 14},${cy + 10}" fill="#FFC000" stroke="#181d27" stroke-width="1" />` +
           `<text x="${cx}" y="${cy + 6}" text-anchor="middle" font-size="18" font-weight="700" fill="#181d27">!</text>`;
  }
  // 'clock' (default)
  return `<circle cx="${cx}" cy="${cy}" r="14" fill="none" stroke="#666" stroke-width="2" />` +
         `<line x1="${cx}" y1="${cy}" x2="${cx}" y2="${cy - 9}" stroke="#666" stroke-width="2" />` +
         `<line x1="${cx}" y1="${cy}" x2="${cx + 7}" y2="${cy}" stroke="#666" stroke-width="2" />`;
}
```

> **Note on `renderPlaceholder`'s `globalThis` hack:** It's a workaround for a circular dependency. `svg-lib.js` doesn't `import { CHART_META } from './meta.js'` because `meta.js` imports per-chart files which (in commits 2+) import `svg-lib.js`. The cycle is broken by injection: `meta.js` writes `globalThis.__WESTLAND_CHART_META__ = CHART_META` at module load time. Document this clearly in `meta.js`'s top comment.

- [ ] **Step 8: Run svg-lib tests — confirm they pass**

```bash
cd scheduling/skills/schedule-update/references/charts && npx vitest run svg-lib.test.js
```

Expected: all tests pass (the `renderPlaceholder` test only asserts the throw path at commit 1).

- [ ] **Step 9: Create `meta.js` — empty registry + globalThis injection**

```js
// meta.js — slug → { svgWidth, svgHeight, title } map.
//
// Aggregates per-chart META exports for use by renderPlaceholder and by external
// consumers that need chart dimensions without invoking a renderer.
//
// IMPORTANT: We assign to globalThis so svg-lib.js's renderPlaceholder can read
// CHART_META without importing this file (avoids a circular dep — svg-lib.js
// → meta.js → NN-slug.js → svg-lib.js).

// At commit 1 the registry is empty; per-chart META imports get added as
// charts land.

/** @type {Record<string, { svgWidth: number, svgHeight: number, title: string }>} */
export const CHART_META = {};

globalThis.__WESTLAND_CHART_META__ = CHART_META;
```

- [ ] **Step 10: Create `meta.test.js` — registry coverage assertion**

```js
// meta.test.js
import { describe, it, expect } from 'vitest';
import { CHART_META } from './meta.js';
import { RENDERERS } from './registry.js';

describe('CHART_META', () => {
  it('has every required field per entry', () => {
    for (const [slug, meta] of Object.entries(CHART_META)) {
      expect(meta, slug).toHaveProperty('svgWidth');
      expect(meta, slug).toHaveProperty('svgHeight');
      expect(meta, slug).toHaveProperty('title');
      expect(typeof meta.svgWidth).toBe('number');
      expect(typeof meta.svgHeight).toBe('number');
      expect(typeof meta.title).toBe('string');
    }
  });
  it('matches the RENDERERS registry 1:1', () => {
    const metaSlugs = new Set(Object.keys(CHART_META));
    const rendererSlugs = new Set(Object.keys(RENDERERS));
    expect([...metaSlugs].sort()).toEqual([...rendererSlugs].sort());
  });
});
```

- [ ] **Step 11: Create `registry.js` — empty map**

```js
// registry.js — slug → renderer function map.

/** @typedef {import('./svg-lib.js').RenderFn<any>} RenderFn */

/** @type {Record<string, RenderFn>} */
export const RENDERERS = {};
```

- [ ] **Step 12: Create `index.js` — top-level re-exports**

```js
// index.js — public entry point.
// Re-exports the registry, metadata, placeholder renderer, and shared types
// so consumers can `import { RENDERERS } from '@westland/charts'` without
// thinking about file layout.
//
// Per-chart renderers are also re-exported by name as charts land so the
// westland-mcps consumer can type-narrow when it knows which renderer it's
// calling (`renderPlannedVsActual(typedPayload)` vs `RENDERERS[slug](anyPayload)`).

export { RENDERERS } from './registry.js';
export { CHART_META } from './meta.js';
export { renderPlaceholder } from './svg-lib.js';
// Per-chart re-exports get added as charts land:
//   export { renderPlannedVsActual } from './01-planned-vs-actual.js';  // (commit 2)
//   ...
```

- [ ] **Step 13: Create `cli.js` — Node CLI driver**

```js
#!/usr/bin/env node
// cli.js — read {slug}.json payloads from a dir, dispatch via RENDERERS,
// write {slug}.html + {slug}.png to an output dir. Mirrors render.py's
// observable contract exactly.

import { readdirSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { resolve, join, dirname } from 'node:path';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { RENDERERS } from './registry.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const HTML_TO_PNG = resolve(__dirname, 'html_to_png.cjs');
// Card dimensions match svg-lib's HTML_CARD_W/H (default rasteriser size).
const CARD_W = 1728;
const CARD_H = 432;
const SCALE  = 2;

function main() {
  const [payloadDir, outputDir] = process.argv.slice(2);
  if (!payloadDir || !outputDir) {
    console.error('Usage: node cli.js <payload_dir> <output_dir>');
    process.exit(2);
  }
  mkdirSync(outputDir, { recursive: true });

  /** @type {Array<{slug: string, path: string}>} */
  const rendered = [];
  /** @type {Array<{slug: string, reason: string}>} */
  const failed = [];

  const files = readdirSync(payloadDir).filter(f => f.endsWith('.json')).sort();
  for (const file of files) {
    const slug = file.replace(/\.json$/, '');
    const fn = RENDERERS[slug];
    if (!fn) {
      failed.push({ slug, reason: 'no renderer in registry' });
      continue;
    }
    try {
      const payload = JSON.parse(readFileSync(join(payloadDir, file), 'utf-8'));
      const { html } = fn(payload);
      const htmlPath = join(outputDir, `${slug}.html`);
      const pngPath  = join(outputDir, `${slug}.png`);
      writeFileSync(htmlPath, html, 'utf-8');
      const result = spawnSync('node',
        [HTML_TO_PNG, htmlPath, pngPath, String(CARD_W), String(CARD_H), String(SCALE)],
        { encoding: 'utf-8', timeout: 60_000 });
      if (result.status !== 0) {
        const stderr = (result.stderr || '').trim();
        throw new Error(`html_to_png.cjs exited ${result.status}: ${stderr.slice(0, 500)}`);
      }
      rendered.push({ slug, path: pngPath });
    } catch (err) {
      const e = /** @type {Error} */ (err);
      failed.push({ slug, reason: `${e.name}: ${e.message}` });
    }
  }

  console.log(JSON.stringify({ rendered, failed }, null, 2));
  process.exit(failed.length ? 1 : 0);
}

main();
```

- [ ] **Step 14: Create `tests/workers-import.test.js` — wrangler-bundle smoke test**

```js
// tests/workers-import.test.js — confirms the package bundles cleanly for
// Cloudflare Workers (no node:fs / node:path / etc. sneaking into renderer
// code via a future commit).

import { describe, it, expect } from 'vitest';
import { execSync, spawnSync } from 'node:child_process';
import { writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve, join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const CHARTS_DIR = resolve(__dirname, '..');

function wranglerInstalled() {
  try { execSync('npx --no-install wrangler --version', { stdio: 'ignore' }); return true; }
  catch { return false; }
}

describe('Cloudflare Workers compatibility', () => {
  it.skipIf(!wranglerInstalled())('wrangler can bundle the package without Node-only imports', () => {
    const shim = join(tmpdir(), `westland-charts-smoke-${Date.now()}`);
    mkdirSync(shim, { recursive: true });
    try {
      const chartsAbs = CHARTS_DIR.replace(/\\/g, '/');
      writeFileSync(join(shim, 'wrangler.toml'),
        `name = "smoke"\nmain = "worker.js"\ncompatibility_date = "2024-11-01"\n`);
      writeFileSync(join(shim, 'worker.js'),
        `import { RENDERERS, CHART_META, renderPlaceholder } from '${chartsAbs}/index.js';\n` +
        `export default { async fetch() {\n` +
        `  return new Response(JSON.stringify({ renderers: Object.keys(RENDERERS), metas: Object.keys(CHART_META) }), { headers: { 'content-type': 'application/json' } });\n` +
        `}};\n`);
      const result = spawnSync('npx',
        ['wrangler', 'deploy', '--dry-run', '--outdir', join(shim, 'out')],
        { cwd: shim, encoding: 'utf-8', timeout: 90_000 });
      if (result.status !== 0) {
        throw new Error(`wrangler bundle failed (${result.status}):\n${result.stdout}\n${result.stderr}`);
      }
      const combined = (result.stdout + result.stderr).toLowerCase();
      // wrangler logs warnings when Node built-ins are referenced without the
      // `nodejs_compat` flag. Catch them here — `renderer code paths must be
      // pure-string-output` per the spec.
      expect(combined).not.toMatch(/used by your worker.*?node:(fs|path|child_process|os|crypto)/);
    } finally {
      try { rmSync(shim, { recursive: true, force: true }); } catch {}
    }
  });
});
```

- [ ] **Step 15: Run the full test suite**

```bash
cd scheduling/skills/schedule-update/references/charts && npm test
```

Expected:
- All `svg-lib.test.js` assertions pass.
- `meta.test.js` passes (vacuously — both sides empty).
- `tests/workers-import.test.js` runs if wrangler is on PATH; skipped with a clear message otherwise.

If wrangler isn't installed locally, install it with `npm install --no-save wrangler@4` once to verify the test path, then `git status` to confirm package.json wasn't accidentally modified.

- [ ] **Step 16: Run the JSDoc typecheck**

```bash
cd scheduling/skills/schedule-update/references/charts && npm run typecheck
```

Expected: zero errors. If the `tsc` complains about an `@template` parameter, double-check the JSDoc syntax against the snippets in step 7.

- [ ] **Step 17: Bump plugin + marketplace versions**

Look up the current scheduling plugin version:

```bash
grep '"version"' scheduling/.claude-plugin/plugin.json
```

Increment by patch (e.g., `1.4.7` → `1.4.8`). Update BOTH files:

```bash
# 1. scheduling/.claude-plugin/plugin.json — bump the "version" field.
# 2. .claude-plugin/marketplace.json — find the "scheduling" entry under
#    "plugins" and bump its "version" field to match.
```

Use the Edit tool to make exact replacements; do not template these by hand. The pre-commit hook compares the two files and aborts the commit if they don't match.

- [ ] **Step 18: Commit**

```bash
git add scheduling/skills/schedule-update/references/charts/ \
        scheduling/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json

git commit -m "$(cat <<'EOF'
feat(scheduling): JS chart package bootstrap

Adds the @westland/charts package skeleton — svg-lib helpers, registry +
meta maps (empty), index.js re-exports, Node CLI, wrangler-bundle smoke
test, JSDoc typecheck config. Renames html_to_png.js to .cjs (forced by
the new "type": "module"; no code change inside the file).

Per-chart renderers and CHART_META entries land in commits 2-11. westland-mcps
can start coding against RenderResult / RenderFn / renderPlaceholder /
CHART_META immediately.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

Pre-commit hook should pass. If it fails citing version mismatch, recheck step 17.

---

## Task 2: Port chart 01 — Planned VS Actual Percent Complete (commit 2)

**Goal:** First chart renderer lands. Visual contract clones SmartPM's Highcharts (palette pulled from Chrome MCP DOM inspection done during the Python port). PNG byte-similar to the existing chart-01 Python output.

**Files:**
- Create: `scheduling/skills/schedule-update/references/charts/01-planned-vs-actual.js`
- Create: `scheduling/skills/schedule-update/references/charts/01-planned-vs-actual.test.js`
- Modify: `scheduling/skills/schedule-update/references/charts/registry.js`
- Modify: `scheduling/skills/schedule-update/references/charts/meta.js`
- Modify: `scheduling/skills/schedule-update/references/charts/index.js`
- Modify: `scheduling/skills/schedule-update/references/charts/svg-lib.test.js` (one new test for `renderPlaceholder` against the now-populated CHART_META)
- Modify: `scheduling/skills/schedule-update/phases/screenshots.md` (chart 01 recipe → JS CLI)
- Modify: `scheduling/.claude-plugin/plugin.json` (version bump)
- Modify: `.claude-plugin/marketplace.json` (matching version bump)

**Reference Python implementation:** [`charts.py`](../../scheduling/skills/schedule-update/references/charts/charts.py) lines 1311–1736 (`_pva01_*` helpers already ported to `svg-lib.js`; the renderer itself is at lines 1535–1736).

- [ ] **Step 1: Write the failing test `01-planned-vs-actual.test.js`**

```js
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { renderPlannedVsActual, META } from './01-planned-vs-actual.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/01-planned-vs-actual-percent-complete.json'),
  'utf-8',
));

describe('renderPlannedVsActual', () => {
  const { html, svgInner } = renderPlannedVsActual(fixture);

  it('uses all 6 series palette colors', () => {
    for (const hex of ['#b00020', '#2caffe', '#1476b7', '#388543', '#808080', '#cccccc']) {
      expect(html).toContain(hex);
    }
  });

  it('preserves the dashed Scheduled Completion line (stroke-dasharray="8,6")', () => {
    expect(html).toContain('stroke-dasharray="8,6"');
  });

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Planned VS Actual Percent Complete');
    expect(html).toContain(META.title);
  });

  it('emits each legend label', () => {
    for (const label of ['Progress Target', 'Late Date Planned', 'Planned (All Schedules)',
                          'Actual', 'Scheduled Completion', 'Early Date Planned']) {
      // legend labels may have project-specific suffixes (e.g. "Late Date Planned (...)"),
      // so substring-contain rather than exact-match.
      expect(html).toContain(label);
    }
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });

  it('throws TypeError on malformed payload (data is null)', () => {
    expect(() => renderPlannedVsActual(/** @type {any} */ ({ data: null }))).toThrow(TypeError);
  });

  it('renders empty-state card when data array is empty', () => {
    const { html: empty } = renderPlannedVsActual({ ...fixture, data: [] });
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });
});
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
cd scheduling/skills/schedule-update/references/charts && npx vitest run 01-planned-vs-actual.test.js
```

Expected: `Cannot find module './01-planned-vs-actual.js'`.

- [ ] **Step 3: Read the Python reference**

Open [`charts.py`](../../scheduling/skills/schedule-update/references/charts/charts.py) lines 1535–1736 (the `render_planned_vs_actual_percent_complete` function). Note:
- Six series: Progress Target (gray band), Late Date Planned (red diamond), Planned (blue square), Actual (dark-blue triangle), Scheduled Completion (green DASHED inverted-triangle), Early Date Planned (green circle).
- Data-date plotline: gray dashed vertical at the last row where `ACTUAL` is non-null.
- Z-order: band first, plotline, then series back-to-front, with Scheduled Completion LAST (so its dashed green sits above the solid green Early Date Planned at coincident points).
- Gridlines at 0/25/50/75/100%.
- X-ticks via `xTicks` (already in `svg-lib.js`).
- Legend uses the `percentCompleteTypes` map for the two long labels.

- [ ] **Step 4: Write `01-planned-vs-actual.js`**

```js
// 01-planned-vs-actual.js — port of charts.py:render_planned_vs_actual_percent_complete.

import {
  HTML_CARD_W, HTML_CARD_H,
  dateToX, pctToY, smoothPath, xTicks, seriesPts,
  markerSvg, legendItem, htmlEnvelope, emptyHtml,
} from './svg-lib.js';

// Palette — copied verbatim from charts.py:1316-1325. Each value came from a
// <path stroke="..."> attribute in SmartPM's Highcharts SVG via Chrome MCP
// DOM inspection on 2026-05-21 (SGRWRF trends page).
const PROGRESS_TARGET_FILL = '#808080';
const LATE_DATE_PLANNED    = '#b00020';
const BASELINE_PLANNED     = '#2caffe';
const ACTUAL               = '#1476b7';
const SCHEDULED_COMPLETION = '#388543';
const EARLY_DATE_PLANNED   = '#388543';
const DATA_DATE_LINE       = '#cccccc';
const GRID                 = '#e6e6e6';

/**
 * @typedef {Object} PlannedVsActualPayload
 * @property {Record<string, string>} [percentCompleteTypes]
 * @property {Array<{
 *   DATE: string,
 *   LATE_DATE_PLANNED: number|null,
 *   BASELINE_PLANNED:  number|null,
 *   ACTUAL:            number|null,
 *   SCHEDULED:         number|null,
 *   PLANNED:           number|null,
 * }>} data
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Planned VS Actual Percent Complete',
};

/**
 * @param {PlannedVsActualPayload} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderPlannedVsActual(payload) {
  if (!payload || typeof payload !== 'object') {
    throw new TypeError('expected payload object');
  }
  if (payload.data !== null && payload.data !== undefined && !Array.isArray(payload.data)) {
    throw new TypeError('expected payload.data to be an array');
  }
  const rows = Array.isArray(payload.data) ? payload.data : [];
  const types = payload.percentCompleteTypes ?? {};

  if (!rows.length) {
    return { html: emptyHtml(META.title), svgInner: '' };
  }

  // SVG geometry — same proportions as the Python reference (svg.w 1692,
  // svg.h 312 leaves ~80px below for the HTML legend row inside the
  // 1728x432 chart card).
  const svgW = 1692, svgH = 312;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  /** @type {Date[]} */
  const dates = rows.map(r => new Date(`${r.DATE}T00:00:00Z`));
  const dmin = new Date(Math.min(...dates.map(d => d.getTime())));
  const dmax = new Date(Math.max(...dates.map(d => d.getTime())));

  // Data date = last row where ACTUAL is non-null.
  /** @type {Date|null} */
  let dataDate = null;
  for (const r of rows) {
    if (r.ACTUAL !== null && r.ACTUAL !== undefined) {
      dataDate = new Date(`${r.DATE}T00:00:00Z`);
    }
  }

  const ptsLate  = seriesPts(rows, 'LATE_DATE_PLANNED', dmin, dmax, x0, x1, y0, y1);
  const ptsBase  = seriesPts(rows, 'BASELINE_PLANNED',  dmin, dmax, x0, x1, y0, y1);
  const ptsAct   = seriesPts(rows, 'ACTUAL',            dmin, dmax, x0, x1, y0, y1);
  const ptsSched = seriesPts(rows, 'SCHEDULED',         dmin, dmax, x0, x1, y0, y1);
  const ptsEarly = seriesPts(rows, 'PLANNED',           dmin, dmax, x0, x1, y0, y1);

  // Progress Target band — closed area between BASELINE_PLANNED (upper) and
  // LATE_DATE_PLANNED (lower).
  /** @type {Array<[number, number]>} */
  const bandTop = [];
  /** @type {Array<[number, number]>} */
  const bandBot = [];
  for (const r of rows) {
    if (r.BASELINE_PLANNED === null || r.LATE_DATE_PLANNED === null) continue;
    const d = new Date(`${r.DATE}T00:00:00Z`);
    const x = dateToX(d, dmin, dmax, x0, x1);
    bandTop.push([x, pctToY(Number(r.BASELINE_PLANNED), y0, y1)]);
    bandBot.push([x, pctToY(Number(r.LATE_DATE_PLANNED), y0, y1)]);
  }
  let bandPath = '';
  if (bandTop.length) {
    const topStr = bandTop.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L ');
    const botStr = [...bandBot].reverse().map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L ');
    bandPath = `M ${topStr} L ${botStr} Z`;
  }

  // Gridlines + Y-axis labels at 0/25/50/75/100%.
  const gridlines = [];
  const yLabels = [];
  for (const pct of [0, 25, 50, 75, 100]) {
    const y = pctToY(pct, y0, y1);
    gridlines.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" class="grid-line" />`);
    yLabels.push(`<text x="${x0 - 8}" y="${(y + 4).toFixed(1)}" class="axis-text axis-text-y">${pct} %</text>`);
  }

  // X-axis tick labels.
  const xLabels = [];
  for (const d of xTicks(dmin, dmax)) {
    const x = dateToX(d, dmin, dmax, x0, x1);
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(d.getUTCDate()).padStart(2, '0');
    const yy = String(d.getUTCFullYear()).slice(-2);
    xLabels.push(`<text x="${x.toFixed(1)}" y="${y1 + 18}" class="axis-text axis-text-x">${mm}/${dd}/${yy}</text>`);
  }

  // Data-date plotline.
  let plotLine = '';
  if (dataDate) {
    const dx = dateToX(dataDate, dmin, dmax, x0, x1);
    plotLine = `<line x1="${dx.toFixed(1)}" y1="${y0}" x2="${dx.toFixed(1)}" y2="${y1}" stroke="${DATA_DATE_LINE}" stroke-width="2" stroke-dasharray="8,6" />`;
  }

  const markers = (pts, color, kind) => pts.map(([x, y]) => markerSvg(kind, x, y, color, 4)).join('\n');

  // Series, back-to-front. Scheduled Completion last so its dashed green
  // sits above the solid green Early Date Planned at coincident points.
  const seriesSvg = [];
  if (bandPath) {
    seriesSvg.push(`<path d="${bandPath}" fill="${PROGRESS_TARGET_FILL}" fill-opacity="0.2" stroke="none" />`);
  }
  if (plotLine) seriesSvg.push(plotLine);
  if (ptsLate.length) {
    seriesSvg.push(`<path d="${smoothPath(ptsLate)}" fill="none" stroke="${LATE_DATE_PLANNED}" stroke-width="2" />`);
    seriesSvg.push(markers(ptsLate, LATE_DATE_PLANNED, 'diamond'));
  }
  if (ptsBase.length) {
    seriesSvg.push(`<path d="${smoothPath(ptsBase)}" fill="none" stroke="${BASELINE_PLANNED}" stroke-width="2" />`);
    seriesSvg.push(markers(ptsBase, BASELINE_PLANNED, 'square'));
  }
  if (ptsAct.length) {
    seriesSvg.push(`<path d="${smoothPath(ptsAct)}" fill="none" stroke="${ACTUAL}" stroke-width="2" />`);
    seriesSvg.push(markers(ptsAct, ACTUAL, 'triangle'));
  }
  if (ptsEarly.length) {
    seriesSvg.push(`<path d="${smoothPath(ptsEarly)}" fill="none" stroke="${EARLY_DATE_PLANNED}" stroke-width="2" />`);
    seriesSvg.push(markers(ptsEarly, EARLY_DATE_PLANNED, 'circle'));
  }
  if (ptsSched.length) {
    seriesSvg.push(`<path d="${smoothPath(ptsSched)}" fill="none" stroke="${SCHEDULED_COMPLETION}" stroke-width="2" stroke-dasharray="8,6" />`);
    seriesSvg.push(markers(ptsSched, SCHEDULED_COMPLETION, 'invtri'));
  }

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;
  const yAxisTitle = `<text x="${x0 - 40}" y="${((y0 + y1) / 2).toFixed(1)}" transform="rotate(-90 ${x0 - 40} ${((y0 + y1) / 2).toFixed(1)})" class="axis-title-text">Values</text>`;

  const svgInner = [
    ...gridlines, frame, ...yLabels, ...xLabels, yAxisTitle, ...seriesSvg,
  ].join('\n');

  // Legend.
  const legendItems = [
    ['area',     PROGRESS_TARGET_FILL, '',    'Progress Target'],
    ['diamond',  LATE_DATE_PLANNED,    '',    types.LATE_DATE_PLANNED ?? 'Late Date Planned'],
    ['square',   BASELINE_PLANNED,     '',    types.BASELINE_PLANNED  ?? 'Planned (All Schedules)'],
    ['triangle', ACTUAL,               '',    types.ACTUAL            ?? 'Actual'],
    ['invtri',   SCHEDULED_COMPLETION, '8,6', types.SCHEDULED         ?? 'Scheduled Completion'],
    ['circle',   EARLY_DATE_PLANNED,   '',    types.PLANNED           ?? 'Early Date Planned'],
  ];
  const legendHtml = legendItems.map(([kind, color, dash, label]) =>
    legendItem(/** @type {any} */ (kind), color, dash, label)
  ).join('\n');

  const html = htmlEnvelope({ title: META.title, svgW, svgH, svgInner, legendHtml });
  return { html, svgInner };
}
```

- [ ] **Step 5: Register the renderer + META — update `registry.js`, `meta.js`, `index.js`**

`registry.js`:

```js
// registry.js
import { renderPlannedVsActual } from './01-planned-vs-actual.js';

/** @typedef {import('./svg-lib.js').RenderFn<any>} RenderFn */

/** @type {Record<string, RenderFn>} */
export const RENDERERS = {
  '01-planned-vs-actual-percent-complete': renderPlannedVsActual,
};
```

`meta.js`:

```js
// meta.js
import { META as META01 } from './01-planned-vs-actual.js';

/** @type {Record<string, { svgWidth: number, svgHeight: number, title: string }>} */
export const CHART_META = {
  '01-planned-vs-actual-percent-complete': META01,
};

globalThis.__WESTLAND_CHART_META__ = CHART_META;
```

`index.js`:

```js
// index.js
export { RENDERERS } from './registry.js';
export { CHART_META } from './meta.js';
export { renderPlaceholder } from './svg-lib.js';
export { renderPlannedVsActual } from './01-planned-vs-actual.js';
```

- [ ] **Step 6: Update svg-lib.test.js — add the now-passable placeholder test**

Add to `svg-lib.test.js`:

```js
import { CHART_META } from './meta.js';

describe('renderPlaceholder (with populated CHART_META)', () => {
  it('emits HTML matching the chart dimensions for chart 01', () => {
    const { html, svgInner } = renderPlaceholder('01-planned-vs-actual-percent-complete');
    expect(html).toContain(`width="${CHART_META['01-planned-vs-actual-percent-complete'].svgWidth}"`);
    expect(html).toContain('Data not yet available');
    expect(svgInner).toContain('<text');
  });
  it('honors custom message + warn icon', () => {
    const { html } = renderPlaceholder('01-planned-vs-actual-percent-complete',
      { message: 'Render failed', icon: 'warn' });
    expect(html).toContain('Render failed');
    expect(html).toContain('#FFC000');
  });
});
```

- [ ] **Step 7: Run the full test suite**

```bash
cd scheduling/skills/schedule-update/references/charts && npm test
```

Expected: 01-planned-vs-actual tests pass, svg-lib tests pass, meta.test.js confirms 1:1 coverage.

- [ ] **Step 8: Render to chart-previews and eyeball against SmartPM**

```bash
# From repo root:
mkdir -p chart-previews
node scheduling/skills/schedule-update/references/charts/cli.js \
     scheduling/skills/schedule-update/references/charts/tests/fixtures \
     chart-previews
```

Open `chart-previews/01-planned-vs-actual-percent-complete.png` AND the same chart on SmartPM's web view (project 141462 SGRWRF, scenario 1721, Trends tab → "Planned vs Actual Percent Complete").

Visual checklist:
- All 6 series colors match.
- Scheduled Completion line is DASHED green (not solid).
- Progress Target gray band fills the area between BASELINE and LATE.
- Data-date vertical line is dashed gray.
- Y-axis: 0/25/50/75/100% labels.
- X-axis: month/day/year ticks.
- Legend at bottom with all 6 entries.

If anything looks off, debug at the JS source — never at the rasteriser. Open `chart-previews/01-planned-vs-actual-percent-complete.html` directly in a browser (no Chromium screenshot in the way) to localize layout vs raster issues.

- [ ] **Step 9: Update `phases/screenshots.md` — point chart 01 recipe at the JS CLI**

Find the chart 01 section in [`phases/screenshots.md`](../../scheduling/skills/schedule-update/phases/screenshots.md). The current text mentions `python -m charts.render` or similar. Replace the rendering invocation with:

```
node scheduling/skills/schedule-update/references/charts/cli.js \
     {dated_folder}/.chart-payload \
     {dated_folder}/screenshots
```

The MCP payload recipe (which SmartPM endpoint, what to write to `{slug}.json`) is unchanged.

- [ ] **Step 10: Bump versions + commit**

Edit `scheduling/.claude-plugin/plugin.json` and `.claude-plugin/marketplace.json` to the next patch version.

```bash
git add scheduling/skills/schedule-update/references/charts/01-planned-vs-actual.js \
        scheduling/skills/schedule-update/references/charts/01-planned-vs-actual.test.js \
        scheduling/skills/schedule-update/references/charts/registry.js \
        scheduling/skills/schedule-update/references/charts/meta.js \
        scheduling/skills/schedule-update/references/charts/index.js \
        scheduling/skills/schedule-update/references/charts/svg-lib.test.js \
        scheduling/skills/schedule-update/phases/screenshots.md \
        scheduling/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json

git commit -m "$(cat <<'EOF'
feat(scheduling): JS chart 01 (planned-vs-actual percent complete)

Port of charts.py:render_planned_vs_actual_percent_complete. Six series
(Progress Target band, Late Date Planned diamonds, Planned squares, Actual
triangles, Scheduled Completion dashed-green inverted-triangles, Early
Date Planned circles) + data-date plotline. Palette and dasharray copied
verbatim from the Python reference (which lifted them from Chrome MCP DOM
inspection on 2026-05-21).

Registers '01-planned-vs-actual-percent-complete' in RENDERERS and
CHART_META. Updates phases/screenshots.md to invoke the JS CLI for this
slug.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Port chart 02 — Schedule Quality Grade™ Over Time (commit 3)

**Goal:** Single-series categorical-Y line chart. No band, no legend, no markers. Title includes the ™ glyph. Auto-fits Y range to observed grades.

**Files:**
- Create: `scheduling/skills/schedule-update/references/charts/02-schedule-quality.js`
- Create: `scheduling/skills/schedule-update/references/charts/02-schedule-quality.test.js`
- Modify: `registry.js`, `meta.js`, `index.js`, `phases/screenshots.md` (chart 02 recipe: correct stale `grade.score` → `grade.mark`), `plugin.json`, `marketplace.json`

**Reference Python implementation:** [`charts.py`](../../scheduling/skills/schedule-update/references/charts/charts.py) lines 1739–1878.

**Payload shape** (from the spec's "Risks & mitigations" §4):

```js
// Raw smartpm_get against /projects/{id}/scenarios/{id}/schedule-quality-trend
// returns a flat list — NO {"trend": [...]} envelope. Each row:
//   { dataDate: "2026-05-21T00:00:00", grade: { mark: "B+", indicator: "GOOD", score: 89.0 } }
// Renderer uses grade.mark (categorical letter), NOT grade.score (numeric).
```

- [ ] **Step 1: Write `02-schedule-quality.test.js`**

```js
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderScheduleQuality, META } from './02-schedule-quality.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/02-schedule-quality-grade-over-time.json'),
  'utf-8'
));

describe('renderScheduleQuality', () => {
  const { html, svgInner } = renderScheduleQuality(fixture);

  it('uses the single #2caffe line color', () => {
    expect(html).toContain('#2caffe');
  });

  it('has NO Progress Target band fill (#808080 fill-opacity)', () => {
    expect(html).not.toMatch(/fill="#808080" fill-opacity/);
  });

  it('has NO stroke-dasharray="8,6" (single straight line, no plotline)', () => {
    expect(html).not.toContain('stroke-dasharray="8,6"');
  });

  it('has NO legend row content (empty legend)', () => {
    // The legend-row div exists but contains only whitespace
    expect(html).toMatch(/<div class="legend-row">\s*<\/div>/);
  });

  it('emits the title with the ™ glyph from META', () => {
    expect(META.title).toBe('Schedule Quality Grade™ Over Time');
    expect(html).toContain('Schedule Quality Grade');
    expect(html).toContain('™');
  });

  it('Y-axis includes at least one canonical letter-grade label', () => {
    expect(html).toMatch(/>(A\+|A-?|B\+|B-?|C\+|C-?|D|F)<\/text>/);
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });

  it('throws TypeError when payload is not a list and lacks trend', () => {
    expect(() => renderScheduleQuality(/** @type {any} */ ({ trend: 'nope' }))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderScheduleQuality([]);
    expect(empty).toContain('no data');
  });
});
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
cd scheduling/skills/schedule-update/references/charts && npx vitest run 02-schedule-quality.test.js
```

- [ ] **Step 3: Read the Python reference**

[`charts.py`](../../scheduling/skills/schedule-update/references/charts/charts.py) lines 1739–1878. Key notes:
- `_PVA02_LINE_COLOR = '#2caffe'`.
- `_PVA02_GRADE_RANKS` is the canonical 11-grade ladder (A+ at index 0, F at index 10). Y position = rank index normalized to the observed-rank window.
- STRAIGHT line segments (`M ... L ...`), NOT smoothed.
- No markers, no legend, no data-date plotline, no Progress Target band.
- Auto-fit Y to observed range; if all rows are the same grade, pad by 1 above and below.
- Skip rows where `grade.mark` is missing or unrecognised.

- [ ] **Step 4: Write `02-schedule-quality.js`**

```js
// 02-schedule-quality.js — port of charts.py:render_schedule_quality_grade_over_time.

import { HTML_CARD_W, HTML_CARD_H, dateToX, xTicks, htmlEnvelope, emptyHtml } from './svg-lib.js';

const LINE_COLOR = '#2caffe';
const GRID       = '#e6e6e6';

// Canonical SmartPM grade scale, top (A+ = rank 0) to bottom (F = rank 10).
const GRADE_RANKS = [
  'A+', 'A', 'A-',
  'B+', 'B', 'B-',
  'C+', 'C', 'C-',
  'D',  'F',
];

/**
 * @typedef {Array<{ dataDate: string, grade?: { mark?: string, indicator?: string, score?: number } }>} ScheduleQualityPayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Schedule Quality Grade™ Over Time',
};

/**
 * @param {ScheduleQualityPayload | { trend?: ScheduleQualityPayload }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderScheduleQuality(payload) {
  // Accept flat list (raw MCP shape) OR { trend: [...] } envelope.
  let rows;
  if (Array.isArray(payload)) rows = payload;
  else if (payload && Array.isArray(/** @type {any} */ (payload).trend)) rows = /** @type {any} */ (payload).trend;
  else if (payload && (payload.trend === undefined || payload.trend === null)) rows = [];
  else throw new TypeError('expected ScheduleQualityPayload (array) or { trend: array }');

  const gradeToRank = Object.fromEntries(GRADE_RANKS.map((g, i) => [g, i]));
  /** @type {Array<{ d: Date, rank: number, grade: string }>} */
  const parsed = [];
  for (const r of rows) {
    const grade = r?.grade?.mark;
    if (!grade || !(grade in gradeToRank)) continue;
    parsed.push({
      d: new Date(`${String(r.dataDate).slice(0, 10)}T00:00:00Z`),
      rank: gradeToRank[grade],
      grade,
    });
  }

  if (!parsed.length) {
    return { html: emptyHtml(META.title), svgInner: '' };
  }

  const svgW = 1692, svgH = 312;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const dmin = new Date(Math.min(...parsed.map(p => p.d.getTime())));
  const dmax = new Date(Math.max(...parsed.map(p => p.d.getTime())));

  let yRankTop = Math.min(...parsed.map(p => p.rank));
  let yRankBot = Math.max(...parsed.map(p => p.rank));
  if (yRankTop === yRankBot) {
    yRankTop = Math.max(0, yRankTop - 1);
    yRankBot = Math.min(GRADE_RANKS.length - 1, yRankBot + 1);
  }
  const rankSpan = Math.max(1, yRankBot - yRankTop);
  const rankToY = (rank) => y0 + ((rank - yRankTop) / rankSpan) * (y1 - y0);

  const pts = parsed.map(p => [dateToX(p.d, dmin, dmax, x0, x1), rankToY(p.rank)]);
  // Straight segments (not smoothed) — per Python reference.
  const linePath = 'M ' + pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L ');

  const gridlines = [];
  const yLabels = [];
  for (let rank = yRankTop; rank <= yRankBot; rank++) {
    const y = rankToY(rank);
    gridlines.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" class="grid-line" />`);
    yLabels.push(`<text x="${x0 - 8}" y="${(y + 4).toFixed(1)}" class="axis-text axis-text-y">${GRADE_RANKS[rank]}</text>`);
  }

  const xLabels = [];
  for (const d of xTicks(dmin, dmax)) {
    const x = dateToX(d, dmin, dmax, x0, x1);
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(d.getUTCDate()).padStart(2, '0');
    const yy = String(d.getUTCFullYear()).slice(-2);
    xLabels.push(`<text x="${x.toFixed(1)}" y="${y1 + 18}" class="axis-text axis-text-x">${mm}/${dd}/${yy}</text>`);
  }

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;
  const series = `<path d="${linePath}" fill="none" stroke="${LINE_COLOR}" stroke-width="2" />`;

  const svgInner = [...gridlines, frame, ...yLabels, ...xLabels, series].join('\n');
  // legendHtml empty — single-series chart.
  const html = htmlEnvelope({ title: META.title, svgW, svgH, svgInner, legendHtml: '' });
  return { html, svgInner };
}
```

- [ ] **Step 5: Register the renderer + META**

`registry.js`:

```js
import { renderPlannedVsActual } from './01-planned-vs-actual.js';
import { renderScheduleQuality } from './02-schedule-quality.js';

/** @typedef {import('./svg-lib.js').RenderFn<any>} RenderFn */

/** @type {Record<string, RenderFn>} */
export const RENDERERS = {
  '01-planned-vs-actual-percent-complete': renderPlannedVsActual,
  '02-schedule-quality-grade-over-time':   renderScheduleQuality,
};
```

`meta.js`:

```js
import { META as META01 } from './01-planned-vs-actual.js';
import { META as META02 } from './02-schedule-quality.js';

/** @type {Record<string, { svgWidth: number, svgHeight: number, title: string }>} */
export const CHART_META = {
  '01-planned-vs-actual-percent-complete': META01,
  '02-schedule-quality-grade-over-time':   META02,
};

globalThis.__WESTLAND_CHART_META__ = CHART_META;
```

`index.js`:

```js
export { RENDERERS } from './registry.js';
export { CHART_META } from './meta.js';
export { renderPlaceholder } from './svg-lib.js';
export { renderPlannedVsActual } from './01-planned-vs-actual.js';
export { renderScheduleQuality } from './02-schedule-quality.js';
```

- [ ] **Step 6: Run tests**

```bash
cd scheduling/skills/schedule-update/references/charts && npm test
```

Expected: chart 02 tests pass, chart 01 still green, meta + svg-lib still green.

- [ ] **Step 7: Render + eyeball**

```bash
node scheduling/skills/schedule-update/references/charts/cli.js \
     scheduling/skills/schedule-update/references/charts/tests/fixtures \
     chart-previews
```

Open `chart-previews/02-schedule-quality-grade-over-time.png` and compare to SmartPM's "Schedule Quality Grade™ Over Time" trend. Visual checklist:
- Single light-blue (#2caffe) line, STRAIGHT segments.
- No markers, no legend.
- Y-axis: letter grades (A+/A/A-/...), only the observed range.
- X-axis: MM/DD/YY.
- Title includes the ™ glyph.

- [ ] **Step 8: Update `phases/screenshots.md` — chart 02 recipe**

The current chart 02 recipe may reference the wrong field (`grade.score` instead of `grade.mark`). Fix to read `grade.mark` for the Y position. Confirm the raw-`smartpm_get` endpoint (no dedicated MCP tool exists for this trend): `/projects/{id}/scenarios/{id}/schedule-quality-trend`.

- [ ] **Step 9: Bump versions + commit**

```bash
git add scheduling/skills/schedule-update/references/charts/02-schedule-quality.js \
        scheduling/skills/schedule-update/references/charts/02-schedule-quality.test.js \
        scheduling/skills/schedule-update/references/charts/registry.js \
        scheduling/skills/schedule-update/references/charts/meta.js \
        scheduling/skills/schedule-update/references/charts/index.js \
        scheduling/skills/schedule-update/phases/screenshots.md \
        scheduling/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json

git commit -m "$(cat <<'EOF'
feat(scheduling): JS chart 02 (schedule quality grade over time)

Port of charts.py:render_schedule_quality_grade_over_time. Single #2caffe
line, straight segments (not smoothed), categorical letter-grade Y-axis
auto-fit to observed range, no bands, no legend, no plotline. Title
preserves the ™ glyph.

Updates phases/screenshots.md to correct the chart 02 recipe — uses
grade.mark (letter, categorical) not grade.score (numeric); raw smartpm_get
against /projects/{id}/scenarios/{id}/schedule-quality-trend (no dedicated
MCP tool); response is a flat list with no {"trend": [...]} envelope.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Port chart 03 — Project Health Index™ Over Time (commit 4)

**Goal:** Single light-blue line + per-point circle markers color-coded by health indicator (GOOD/FINE/BAD). Auto-fit numeric Y range.

**Files:**
- Create: `scheduling/skills/schedule-update/references/charts/03-project-health.js`
- Create: `scheduling/skills/schedule-update/references/charts/03-project-health.test.js`
- Modify: `registry.js`, `meta.js`, `index.js`, `phases/screenshots.md` (correct `risk` field; flat-list shape; no envelope), `plugin.json`, `marketplace.json`

**Reference Python implementation:** [`charts.py`](../../scheduling/skills/schedule-update/references/charts/charts.py) lines 1881 onwards.

**Payload shape:**

```js
// Flat list (no envelope). Indicator field is "risk", NOT "indicator".
//   [ { dataDate: "2026-05-21T00:00:00", health: 92, risk: "GOOD" }, ... ]
// Accept { trend: [...] } envelope for forward-compat.
```

- [ ] **Step 1: Write `03-project-health.test.js`**

```js
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderProjectHealth, META } from './03-project-health.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/03-project-health-index-over-time.json'),
  'utf-8'
));

describe('renderProjectHealth', () => {
  const { html, svgInner } = renderProjectHealth(fixture);

  it('uses #2caffe for the line', () => {
    expect(html).toContain('#2caffe');
  });

  it('uses the GOOD marker color #1AA462 (at least one point)', () => {
    expect(html).toContain('#1AA462');
  });

  it('emits the title with the ™ glyph from META', () => {
    expect(META.title).toBe('Project Health Index™ Over Time');
    expect(html).toContain('Project Health Index');
    expect(html).toContain('™');
  });

  it('has NO legend row content', () => {
    expect(html).toMatch(/<div class="legend-row">\s*<\/div>/);
  });

  it('has at least one circle marker', () => {
    expect(svgInner).toMatch(/<circle\b/);
  });

  it('throws TypeError on malformed payload', () => {
    expect(() => renderProjectHealth(/** @type {any} */ ({ trend: 'nope' }))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderProjectHealth([]);
    expect(empty).toContain('no data');
  });
});
```

- [ ] **Step 2: Run the test — confirm it fails**

```bash
cd scheduling/skills/schedule-update/references/charts && npx vitest run 03-project-health.test.js
```

- [ ] **Step 3: Read the Python reference**

[`charts.py`](../../scheduling/skills/schedule-update/references/charts/charts.py) — find `render_project_health_index_over_time` (around line 1901). Key notes:
- `_PVA03_LINE_COLOR = '#2caffe'`, line stroke-width 2, STRAIGHT segments.
- Per-point circle markers radius 4, fill color-coded:
  - `GOOD` → `#1AA462`
  - `FINE` → `#FFC000`
  - `BAD`  → `#D01010`
- Y-axis numeric percent 0–100, auto-fits visible range with ~2% padding.
- X-axis dates MM/DD/YY.
- No bands, no legend, no data-date plotline.

- [ ] **Step 4: Write `03-project-health.js`**

```js
// 03-project-health.js — port of charts.py:render_project_health_index_over_time.

import { HTML_CARD_W, HTML_CARD_H, dateToX, xTicks, markerSvg, htmlEnvelope, emptyHtml } from './svg-lib.js';

const LINE_COLOR  = '#2caffe';
const MARKER_GOOD = '#1AA462';
const MARKER_FINE = '#FFC000';
const MARKER_BAD  = '#D01010';
const GRID        = '#e6e6e6';

/**
 * @typedef {Array<{ dataDate: string, health: number, risk?: 'GOOD'|'FINE'|'BAD' }>} ProjectHealthPayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Project Health Index™ Over Time',
};

function markerColor(risk) {
  if (risk === 'BAD')  return MARKER_BAD;
  if (risk === 'FINE') return MARKER_FINE;
  return MARKER_GOOD;
}

/**
 * @param {ProjectHealthPayload | { trend?: ProjectHealthPayload }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderProjectHealth(payload) {
  let rows;
  if (Array.isArray(payload)) rows = payload;
  else if (payload && Array.isArray(/** @type {any} */ (payload).trend)) rows = /** @type {any} */ (payload).trend;
  else if (payload && (payload.trend === undefined || payload.trend === null)) rows = [];
  else throw new TypeError('expected ProjectHealthPayload (array) or { trend: array }');

  const parsed = rows
    .filter(r => r && typeof r.health === 'number' && !Number.isNaN(r.health))
    .map(r => ({
      d:      new Date(`${String(r.dataDate).slice(0, 10)}T00:00:00Z`),
      health: Number(r.health),
      risk:   r.risk ?? 'GOOD',
    }));

  if (!parsed.length) {
    return { html: emptyHtml(META.title), svgInner: '' };
  }

  const svgW = 1692, svgH = 312;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const dmin = new Date(Math.min(...parsed.map(p => p.d.getTime())));
  const dmax = new Date(Math.max(...parsed.map(p => p.d.getTime())));

  // Auto-fit Y range with ~2% padding.
  let healthMin = Math.min(...parsed.map(p => p.health));
  let healthMax = Math.max(...parsed.map(p => p.health));
  if (healthMin === healthMax) {
    healthMin = Math.max(0,   healthMin - 1);
    healthMax = Math.min(100, healthMax + 1);
  }
  const yPad = (healthMax - healthMin) * 0.02 || 1;
  const yMin = Math.max(0,   healthMin - yPad);
  const yMax = Math.min(100, healthMax + yPad);
  const ySpan = Math.max(1, yMax - yMin);
  const healthToY = (h) => y1 - ((h - yMin) / ySpan) * (y1 - y0);

  const pts = parsed.map(p => /** @type {[number, number]} */ ([dateToX(p.d, dmin, dmax, x0, x1), healthToY(p.health)]));
  const linePath = 'M ' + pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L ');

  // ~5 horizontal gridlines.
  const gridlines = [];
  const yLabels = [];
  for (let i = 0; i <= 4; i++) {
    const pct = yMin + (i / 4) * ySpan;
    const y = healthToY(pct);
    gridlines.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" class="grid-line" />`);
    yLabels.push(`<text x="${x0 - 8}" y="${(y + 4).toFixed(1)}" class="axis-text axis-text-y">${pct.toFixed(0)}</text>`);
  }

  const xLabels = [];
  for (const d of xTicks(dmin, dmax)) {
    const x = dateToX(d, dmin, dmax, x0, x1);
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(d.getUTCDate()).padStart(2, '0');
    const yy = String(d.getUTCFullYear()).slice(-2);
    xLabels.push(`<text x="${x.toFixed(1)}" y="${y1 + 18}" class="axis-text axis-text-x">${mm}/${dd}/${yy}</text>`);
  }

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;

  const series = [
    `<path d="${linePath}" fill="none" stroke="${LINE_COLOR}" stroke-width="2" />`,
    ...pts.map(([x, y], i) => markerSvg('circle', x, y, markerColor(parsed[i].risk), 4)),
  ];

  const svgInner = [...gridlines, frame, ...yLabels, ...xLabels, ...series].join('\n');
  const html = htmlEnvelope({ title: META.title, svgW, svgH, svgInner, legendHtml: '' });
  return { html, svgInner };
}
```

- [ ] **Step 5: Register in `registry.js`, `meta.js`, `index.js`**

`registry.js`:

```js
import { renderPlannedVsActual } from './01-planned-vs-actual.js';
import { renderScheduleQuality } from './02-schedule-quality.js';
import { renderProjectHealth }   from './03-project-health.js';

/** @typedef {import('./svg-lib.js').RenderFn<any>} RenderFn */

/** @type {Record<string, RenderFn>} */
export const RENDERERS = {
  '01-planned-vs-actual-percent-complete': renderPlannedVsActual,
  '02-schedule-quality-grade-over-time':   renderScheduleQuality,
  '03-project-health-index-over-time':     renderProjectHealth,
};
```

`meta.js`:

```js
import { META as META01 } from './01-planned-vs-actual.js';
import { META as META02 } from './02-schedule-quality.js';
import { META as META03 } from './03-project-health.js';

/** @type {Record<string, { svgWidth: number, svgHeight: number, title: string }>} */
export const CHART_META = {
  '01-planned-vs-actual-percent-complete': META01,
  '02-schedule-quality-grade-over-time':   META02,
  '03-project-health-index-over-time':     META03,
};

globalThis.__WESTLAND_CHART_META__ = CHART_META;
```

`index.js`:

```js
export { RENDERERS } from './registry.js';
export { CHART_META } from './meta.js';
export { renderPlaceholder } from './svg-lib.js';
export { renderPlannedVsActual } from './01-planned-vs-actual.js';
export { renderScheduleQuality } from './02-schedule-quality.js';
export { renderProjectHealth }   from './03-project-health.js';
```

- [ ] **Step 6: Run tests**

```bash
cd scheduling/skills/schedule-update/references/charts && npm test
```

Expected: chart 03 green, charts 01/02 still green, meta + svg-lib still green.

- [ ] **Step 7: Render + eyeball**

```bash
node scheduling/skills/schedule-update/references/charts/cli.js \
     scheduling/skills/schedule-update/references/charts/tests/fixtures \
     chart-previews
```

Open `chart-previews/03-project-health-index-over-time.png` and compare to SmartPM. Checklist: blue line + green circles (or amber/red where data has FINE/BAD); ™ in title; numeric Y; MM/DD/YY X; no legend.

- [ ] **Step 8: Update `phases/screenshots.md` — chart 03 recipe**

Fix the recipe to: response is a flat list (NO `{trend: [...]}` envelope); indicator field is `risk`, not `indicator`. Endpoint: `smartpm_get_scenario_project_health_trend`.

- [ ] **Step 9: Bump versions + commit**

```bash
git add scheduling/skills/schedule-update/references/charts/03-project-health.js \
        scheduling/skills/schedule-update/references/charts/03-project-health.test.js \
        scheduling/skills/schedule-update/references/charts/registry.js \
        scheduling/skills/schedule-update/references/charts/meta.js \
        scheduling/skills/schedule-update/references/charts/index.js \
        scheduling/skills/schedule-update/phases/screenshots.md \
        scheduling/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json

git commit -m "$(cat <<'EOF'
feat(scheduling): JS chart 03 (project health index over time)

Port of charts.py:render_project_health_index_over_time. Single #2caffe
line + per-point circle markers color-coded by health risk (GOOD=#1AA462,
FINE=#FFC000, BAD=#D01010). Numeric percent Y-axis auto-fits to observed
range with ~2% padding.

Updates phases/screenshots.md to correct the chart 03 recipe — response
is a flat list (no {"trend": [...]} envelope); indicator field is "risk",
not "indicator".

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Port chart 04 — Schedule Changes Over Time (commit 5)

**Goal:** 7-spline trend chart. Documented "Total Activities" column dropped because the MCP doesn't expose it.

**Files:**
- Create: `scheduling/skills/schedule-update/references/charts/04-schedule-changes.js`
- Create: `scheduling/skills/schedule-update/references/charts/04-schedule-changes.test.js`
- Modify: `registry.js`, `meta.js`, `index.js`, `phases/screenshots.md` (chart 04 recipe: nested `metrics{}` PascalCase fields, flat list), `plugin.json`, `marketplace.json`

**Reference Python implementation:** [`charts.py`](../../scheduling/skills/schedule-update/references/charts/charts.py) — find `render_schedule_changes_over_time`. 7 series spline chart.

- [ ] **Step 1: Read the Python reference, capture palette + series ordering**

Open `charts.py` and locate `render_schedule_changes_over_time`. Extract:
- The 7 palette hex codes (one per series).
- The 7 series field names (PascalCase under `metrics: {}`).
- The legend label for each series.
- Marker kinds (likely all the same — probably circle or square).

Write these as constants at the top of `04-schedule-changes.js`.

- [ ] **Step 2: Write `04-schedule-changes.test.js`**

```js
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderScheduleChanges, META } from './04-schedule-changes.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/04-schedule-changes-over-time.json'),
  'utf-8'
));

describe('renderScheduleChanges', () => {
  const { html, svgInner } = renderScheduleChanges(fixture);

  it('uses all 7 palette hex codes', () => {
    // Palette from charts.py:2071-2077 (Chrome MCP DOM inspection 2026-05-21).
    for (const hex of ['#D01010', '#FFC000', '#1AA462', '#0000FF', '#2196F3', '#1476B7', '#DB495B']) {
      expect(html).toContain(hex);
    }
  });

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Schedule Changes Over Time');
    expect(html).toContain(META.title);
  });

  it('emits each of the 7 legend labels', () => {
    // Labels from charts.py:_PVA04_SPLINE_SERIES (lines 2081-2089).
    for (const label of [
      'Critical Changes', 'Near Critical Changes', 'Activity Changes',
      'Logic Changes', 'Calendar Changes', 'Duration Changes',
      'Delayed Activity Changes',
    ]) {
      expect(html).toContain(label);
    }
  });

  it('does NOT include "Total Activities" (column intentionally dropped)', () => {
    expect(html).not.toContain('Total Activities');
  });

  it('throws TypeError on malformed payload', () => {
    expect(() => renderScheduleChanges(/** @type {any} */ ('nope'))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderScheduleChanges([]);
    expect(empty).toContain('no data');
  });
});
```

- [ ] **Step 3: Run the test — confirm it fails**

```bash
cd scheduling/skills/schedule-update/references/charts && npx vitest run 04-schedule-changes.test.js
```

- [ ] **Step 4: Write `04-schedule-changes.js`** — port the Python `render_schedule_changes_over_time` function line-for-line from [`charts.py:2092-2246`](../../scheduling/skills/schedule-update/references/charts/charts.py).

```js
// 04-schedule-changes.js — port of charts.py:render_schedule_changes_over_time.

import {
  HTML_CARD_W, HTML_CARD_H,
  dateToX, smoothPath, xTicks, legendItem, htmlEnvelope, emptyHtml,
} from './svg-lib.js';

// Palette from charts.py:2071-2077 (Chrome MCP DOM inspection 2026-05-21).
const CRITICAL_CHANGES      = '#D01010';
const NEAR_CRITICAL_CHANGES = '#FFC000';
const ACTIVITY_CHANGES      = '#1AA462';
const LOGIC_CHANGES         = '#0000FF';
const CALENDAR_CHANGES      = '#2196F3';
const DURATION_CHANGES      = '#1476B7';
const DELAYED_ACTIVITY      = '#DB495B';
const GRID                  = '#e6e6e6';

// MCP field name (inside metrics{}) → label + color. PascalCase as returned
// by smartpm_get_scenario_change_log_summary. Order matches SmartPM's legend.
const SPLINE_SERIES = [
  { field: 'CriticalChanges',         label: 'Critical Changes',          color: CRITICAL_CHANGES      },
  { field: 'NearCriticalChanges',     label: 'Near Critical Changes',     color: NEAR_CRITICAL_CHANGES },
  { field: 'ActivityChanges',         label: 'Activity Changes',          color: ACTIVITY_CHANGES      },
  { field: 'LogicChanges',            label: 'Logic Changes',             color: LOGIC_CHANGES         },
  { field: 'CalendarChanges',         label: 'Calendar Changes',          color: CALENDAR_CHANGES      },
  { field: 'DurationChanges',         label: 'Duration Changes',          color: DURATION_CHANGES      },
  { field: 'DelayedActivityChanges',  label: 'Delayed Activity Changes',  color: DELAYED_ACTIVITY      },
];

/**
 * @typedef {Array<{ dataDate: string, metrics: Record<string, number> }>} ScheduleChangesPayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Schedule Changes Over Time',
};

/**
 * @param {ScheduleChangesPayload | { summary?: ScheduleChangesPayload, trend?: ScheduleChangesPayload }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderScheduleChanges(payload) {
  let rows;
  if (Array.isArray(payload)) rows = payload;
  else if (payload && typeof payload === 'object') {
    rows = /** @type {any} */ (payload).summary ?? /** @type {any} */ (payload).trend ?? [];
    if (!Array.isArray(rows)) throw new TypeError('expected ScheduleChangesPayload (array) or { summary: array, trend: array }');
  }
  else throw new TypeError('expected ScheduleChangesPayload (array) or { summary: array, trend: array }');

  if (!rows.length) return { html: emptyHtml(META.title), svgInner: '' };

  const svgW = 1692, svgH = 312;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const dates = rows.map(r => new Date(`${String(r.dataDate).slice(0, 10)}T00:00:00Z`));
  const dmin = new Date(Math.min(...dates.map(d => d.getTime())));
  const dmax = new Date(Math.max(...dates.map(d => d.getTime())));

  // Y range: 0 to nice-tick ceiling of max observed value across all 7 series.
  const allValues = [];
  for (const r of rows) {
    const m = r.metrics ?? {};
    for (const { field } of SPLINE_SERIES) {
      const v = m[field];
      if (v !== null && v !== undefined) allValues.push(Number(v));
    }
  }
  let yMax, tickStep;
  if (!allValues.length || Math.max(...allValues) === 0) {
    yMax = 10; tickStep = 2;
  } else {
    const rawMax = Math.max(...allValues) * 1.1;
    if      (rawMax > 100) tickStep = 25;
    else if (rawMax > 40)  tickStep = 10;
    else if (rawMax > 15)  tickStep = 5;
    else if (rawMax > 6)   tickStep = 2;
    else                   tickStep = 1;
    yMax = Math.ceil(rawMax / tickStep) * tickStep;
  }
  const valueToY = (v) => y1 - (Number(v) / yMax) * (y1 - y0);

  const gridlines = [];
  const yLabels = [];
  for (let tick = 0; tick <= yMax; tick += tickStep) {
    const y = valueToY(tick);
    gridlines.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" class="grid-line" />`);
    yLabels.push(`<text x="${x0 - 8}" y="${(y + 4).toFixed(1)}" class="axis-text axis-text-y">${tick}</text>`);
  }

  const xLabels = [];
  for (const d of xTicks(dmin, dmax)) {
    const x = dateToX(d, dmin, dmax, x0, x1);
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(d.getUTCDate()).padStart(2, '0');
    const yy = String(d.getUTCFullYear()).slice(-2);
    xLabels.push(`<text x="${x.toFixed(1)}" y="${y1 + 18}" class="axis-text axis-text-x">${mm}/${dd}/${yy}</text>`);
  }

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;

  const seriesSvg = [];
  for (const { field, color } of SPLINE_SERIES) {
    /** @type {Array<[number, number]>} */
    const pts = [];
    for (const r of rows) {
      const v = r.metrics?.[field];
      if (v === null || v === undefined) continue;
      const d = new Date(`${String(r.dataDate).slice(0, 10)}T00:00:00Z`);
      pts.push([dateToX(d, dmin, dmax, x0, x1), valueToY(Number(v))]);
    }
    if (!pts.length) continue;
    seriesSvg.push(`<path d="${smoothPath(pts)}" fill="none" stroke="${color}" stroke-width="2" />`);
  }

  const svgInner = [...gridlines, frame, ...yLabels, ...xLabels, ...seriesSvg].join('\n');
  const legendHtml = SPLINE_SERIES.map(({ label, color }) => legendItem('circle', color, '', label)).join('\n');
  const html = htmlEnvelope({ title: META.title, svgW, svgH, svgInner, legendHtml });
  return { html, svgInner };
}
```

- [ ] **Step 5: Register in `registry.js`, `meta.js`, `index.js`**

`registry.js`:

```js
import { renderPlannedVsActual } from './01-planned-vs-actual.js';
import { renderScheduleQuality } from './02-schedule-quality.js';
import { renderProjectHealth }   from './03-project-health.js';
import { renderScheduleChanges } from './04-schedule-changes.js';

/** @typedef {import('./svg-lib.js').RenderFn<any>} RenderFn */

/** @type {Record<string, RenderFn>} */
export const RENDERERS = {
  '01-planned-vs-actual-percent-complete': renderPlannedVsActual,
  '02-schedule-quality-grade-over-time':   renderScheduleQuality,
  '03-project-health-index-over-time':     renderProjectHealth,
  '04-schedule-changes-over-time':         renderScheduleChanges,
};
```

`meta.js`:

```js
import { META as META01 } from './01-planned-vs-actual.js';
import { META as META02 } from './02-schedule-quality.js';
import { META as META03 } from './03-project-health.js';
import { META as META04 } from './04-schedule-changes.js';

/** @type {Record<string, { svgWidth: number, svgHeight: number, title: string }>} */
export const CHART_META = {
  '01-planned-vs-actual-percent-complete': META01,
  '02-schedule-quality-grade-over-time':   META02,
  '03-project-health-index-over-time':     META03,
  '04-schedule-changes-over-time':         META04,
};

globalThis.__WESTLAND_CHART_META__ = CHART_META;
```

`index.js`:

```js
export { RENDERERS } from './registry.js';
export { CHART_META } from './meta.js';
export { renderPlaceholder } from './svg-lib.js';
export { renderPlannedVsActual } from './01-planned-vs-actual.js';
export { renderScheduleQuality } from './02-schedule-quality.js';
export { renderProjectHealth }   from './03-project-health.js';
export { renderScheduleChanges } from './04-schedule-changes.js';
```

- [ ] **Step 6: Run tests**

```bash
cd scheduling/skills/schedule-update/references/charts && npm test
```

- [ ] **Step 7: Render + eyeball**

```bash
node scheduling/skills/schedule-update/references/charts/cli.js \
     scheduling/skills/schedule-update/references/charts/tests/fixtures \
     chart-previews
```

Open `chart-previews/04-schedule-changes-over-time.png`. Compare to SmartPM's "Schedule Changes Over Time" trend. Checklist: 7 spline series matching SmartPM palette; legend with 7 entries; NO "Total Activities" line (MCP doesn't expose it).

- [ ] **Step 8: Update `phases/screenshots.md` — chart 04 recipe**

Document: response is a flat list (no `{summary: [...]}` envelope); metrics nest under `metrics: {}` with PascalCase keys; no `totalActivities` field — "Total Activities" column is intentionally absent. Endpoint: `smartpm_list_scenario_change_log_by_type` (confirm in Python source).

- [ ] **Step 9: Bump versions + commit**

```bash
git add scheduling/skills/schedule-update/references/charts/04-schedule-changes.js \
        scheduling/skills/schedule-update/references/charts/04-schedule-changes.test.js \
        scheduling/skills/schedule-update/references/charts/registry.js \
        scheduling/skills/schedule-update/references/charts/meta.js \
        scheduling/skills/schedule-update/references/charts/index.js \
        scheduling/skills/schedule-update/phases/screenshots.md \
        scheduling/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json

git commit -m "$(cat <<'EOF'
feat(scheduling): JS chart 04 (schedule changes over time)

Port of charts.py:render_schedule_changes_over_time. 7 spline series with
verified palette (Chrome MCP DOM inspection 2026-05-21). "Total Activities"
column intentionally absent — the MCP does not expose it.

Updates phases/screenshots.md to correct the chart 04 recipe — response
is a flat list (no {"summary": [...]} envelope); metrics nest under
metrics: {} with PascalCase keys; documents the missing totalActivities.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: New charts 05, 13, 14 via Chrome MCP DOM inspection (commit 6)

**Goal:** Three new trend renderers. No Python implementations exist — palette + series structure must be captured from SmartPM's live DOM via Chrome MCP.

**Files (each chart):**
- Create: `scheduling/skills/schedule-update/references/charts/05-schedule-delay.js`
- Create: `scheduling/skills/schedule-update/references/charts/05-schedule-delay.test.js`
- Create: `scheduling/skills/schedule-update/references/charts/13-missing-logic.js`
- Create: `scheduling/skills/schedule-update/references/charts/13-missing-logic.test.js`
- Create: `scheduling/skills/schedule-update/references/charts/14-average-total-float.js`
- Create: `scheduling/skills/schedule-update/references/charts/14-average-total-float.test.js`
- Modify: `registry.js`, `meta.js`, `index.js`, `phases/screenshots.md` (3 new recipes), `plugin.json`, `marketplace.json`

**Inspection workflow (PARENT AGENT only — subagents cannot auth to SmartPM):**

- [ ] **Step 1: Sign in to SmartPM in Chrome via Chrome MCP**

Open https://smartpm.com in the Chrome MCP-controlled browser. Sign in with your Westland credentials.

- [ ] **Step 2: Navigate to a data-rich project**

SGRWRF is data-sparse for some of these charts. Prefer Wellington NZ Temple (project 113385, scenario 1644) or Anchorage Alaska Temple (project 111751, scenario 1618). Open the Trends tab.

- [ ] **Step 3: Inspect chart 05 — Schedule Delay Over Time**

```
Chrome MCP > navigate to /projects/113385/scenarios/1644/trends
Chrome MCP > scroll to "Schedule Delay Over Time"
Chrome MCP > use the JS console / get_page_text to extract:
   - All <path stroke="..."> values inside the chart's SVG (palette).
   - Any stroke-dasharray attributes.
   - Series count and naming (from the legend).
   - Y-axis label format (days? percent?).
   - X-axis date format.
   - Marker kinds per series.
```

Capture the result as JSON in your local notes; you'll pass it to a subagent.

- [ ] **Step 4: Inspect chart 13 — Missing Logic + chart 14 — Average Total Float**

Repeat Step 3 for each. Charts 13 and 14 may be single-series bar/line charts; the inspection tells you which.

- [ ] **Step 5: Fetch the MCP payloads for each slug**

Use the SmartPM MCP from this Claude Code session:

```
smartpm_get_scenario_delay({ projectId, scenarioId, since, until })
# Save response to scheduling/skills/schedule-update/references/charts/tests/fixtures/05-schedule-delay-over-time.json

smartpm_get against an endpoint for missing-logic trend  # confirm via the DOM inspection's network tab
# Save response to .../tests/fixtures/13-missing-logic.json

# Same for 14-average-total-float.
```

If a fixture already exists from prior work, confirm it has the expected shape against the live DOM before overwriting.

- [ ] **Step 6: For each of charts 05, 13, 14 — write the failing test, write the renderer, register, render, eyeball, repeat**

The pattern is identical to Tasks 3 and 4. For each chart:

1. Write `NN-slug.test.js` that asserts the palette hexes (from Step 3), the title (from the DOM), the legend labels if any, the title's special characters (™), the malformed-payload throw, and the empty-data empty-state path.
2. Write `NN-slug.js` from scratch — there's no Python reference. Use Tasks 2/3/4 as templates for the SVG geometry math, but the series structure / glyph types / palette comes from your Chrome MCP capture in Step 3.
3. Register in `registry.js`, `meta.js`, `index.js`.
4. Run `npm test` — confirm green.
5. Render via the CLI, eyeball against SmartPM.

If you're delegating to a subagent for the implementation: pass the captured palette + series + axis JSON in the prompt. The subagent NEVER calls Chrome MCP itself.

- [ ] **Step 7: Update `phases/screenshots.md` — add chart 05, 13, 14 recipes**

For each chart, document:
- MCP endpoint + parameters (from Step 5).
- Response shape (snippet of the actual JSON from the fixture).
- Output filename slug.

- [ ] **Step 8: Bump versions + commit**

```bash
git add scheduling/skills/schedule-update/references/charts/05-schedule-delay.js \
        scheduling/skills/schedule-update/references/charts/05-schedule-delay.test.js \
        scheduling/skills/schedule-update/references/charts/13-missing-logic.js \
        scheduling/skills/schedule-update/references/charts/13-missing-logic.test.js \
        scheduling/skills/schedule-update/references/charts/14-average-total-float.js \
        scheduling/skills/schedule-update/references/charts/14-average-total-float.test.js \
        scheduling/skills/schedule-update/references/charts/tests/fixtures/05-schedule-delay-over-time.json \
        scheduling/skills/schedule-update/references/charts/tests/fixtures/13-missing-logic.json \
        scheduling/skills/schedule-update/references/charts/tests/fixtures/14-average-total-float.json \
        scheduling/skills/schedule-update/references/charts/registry.js \
        scheduling/skills/schedule-update/references/charts/meta.js \
        scheduling/skills/schedule-update/references/charts/index.js \
        scheduling/skills/schedule-update/phases/screenshots.md \
        scheduling/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json

git commit -m "$(cat <<'EOF'
feat(scheduling): JS charts 05, 13, 14 (schedule delay + missing logic + avg total float)

Three new trend renderers. No Python reference — palette, series structure,
and axis behavior captured from SmartPM's live DOM via Chrome MCP on
Wellington NZ Temple (project 113385, scenario 1644).

Adds MCP fixtures for each slug under tests/fixtures/. Updates phases/
screenshots.md with the three new per-slug recipes.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: New charts 15, 16 (commit 7)

**Goal:** Two more trend renderers via the same Chrome MCP DOM inspection workflow as Task 6.

**Files (each chart):**
- Create: `scheduling/skills/schedule-update/references/charts/15-high-total-float.js`
- Create: `scheduling/skills/schedule-update/references/charts/15-high-total-float.test.js`
- Create: `scheduling/skills/schedule-update/references/charts/16-critical-path-percentage.js`
- Create: `scheduling/skills/schedule-update/references/charts/16-critical-path-percentage.test.js`
- Modify: `registry.js`, `meta.js`, `index.js`, `phases/screenshots.md`, `plugin.json`, `marketplace.json`

- [ ] **Step 1: Inspect chart 15 — High Total Float**

Chrome MCP DOM inspection on Wellington or Anchorage. Capture: palette, series count, axis behavior. Save JSON notes.

- [ ] **Step 2: Inspect chart 16 — Critical Path Percentage**

Same workflow. Chart 16 may be a percent area chart per the spec table — confirm via DOM.

- [ ] **Step 3: Fetch MCP payloads**

```
# Confirm endpoint per chart via the SmartPM MCP documentation or DOM network inspection.
# Save responses to tests/fixtures/{slug}.json.
```

- [ ] **Step 4: For each chart (15, then 16), write failing test → renderer → register → render → eyeball**

For each slug:

1. **Write the failing test** `NN-slug.test.js`. The test must `import { renderXyz, META }` from the new chart file and assert: every palette hex (from the DOM-inspection JSON) appears in `html`; every `stroke-dasharray` pattern (if any) appears; `META.title` appears in `html`; every legend label (if the chart has a legend) appears; `svgInner.length > 100`; malformed payload throws `TypeError`; empty input returns an empty-state card containing "no data".
2. **Run it**: `npx vitest run NN-slug.test.js`. Confirm it fails.
3. **Write `NN-slug.js`**. Import `HTML_CARD_W`, `HTML_CARD_H`, and the relevant geometry helpers (`dateToX`, `pctToY`, `smoothPath`, `xTicks`, `markerSvg`, `legendItem`, `htmlEnvelope`, `emptyHtml`) from `./svg-lib.js`. Declare palette constants at the top from your DOM-inspection capture. Export a `META` const and the `renderXyz` function. Geometry math: copy the `svgW = 1692, svgH = 312, padT = 14, padR = 32, padB = 30, padL = 56` pattern that all single-card trends in this plan use.
4. **Register** in `registry.js`, `meta.js`, and `index.js` — add an import + entry for the new slug + the previous N-1 slugs already landed.
5. **Run all tests**: `npm test`. Confirm green.
6. **Render + eyeball**: `node scheduling/skills/schedule-update/references/charts/cli.js scheduling/skills/schedule-update/references/charts/tests/fixtures chart-previews`. Open `chart-previews/NN-slug.png` against the live SmartPM view on Wellington (113385) or Anchorage (111751). If anything looks off, open the `.html` sibling in a browser to localize layout vs raster issues.

- [ ] **Step 5: Update `phases/screenshots.md`**

Add chart 15 + 16 recipes.

- [ ] **Step 6: Bump versions + commit**

```bash
git add # ... 15-* + 16-* files + fixtures + registry/meta/index/screenshots + version files

git commit -m "$(cat <<'EOF'
feat(scheduling): JS charts 15, 16 (high total float + critical path percentage)

Two more trend renderers, same Chrome-MCP-DOM-inspection workflow as
commit 6. No Python reference.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Visual upgrade — charts 06, 07 (commit 8)

**Goal:** Charts 06 (End Date Variance) and 07 (Schedule Compression Index Over Time) already exist as matplotlib renderers but those are approximations. Re-inspect SmartPM's DOM and rewrite as HTML+SVG matching the live web view.

**Files (each chart):**
- Create: `scheduling/skills/schedule-update/references/charts/06-end-date-variance.js`
- Create: `scheduling/skills/schedule-update/references/charts/06-end-date-variance.test.js`
- Create: `scheduling/skills/schedule-update/references/charts/07-schedule-compression.js`
- Create: `scheduling/skills/schedule-update/references/charts/07-schedule-compression.test.js`
- Modify: `registry.js`, `meta.js`, `index.js`, `phases/screenshots.md`, `plugin.json`, `marketplace.json`

- [ ] **Step 1: Inspect chart 06 + chart 07 on SmartPM**

Use Wellington (113385) or Anchorage (111751). For each chart: palette, series count, axis types, marker kinds. Capture JSON notes.

Note: the matplotlib rendering you'll see in `chart-previews/` (if you render them via the OLD Python path) is an approximation. Compare to the LIVE SmartPM web view, not the matplotlib reference.

- [ ] **Step 2: Confirm/refresh MCP fixtures**

```
smartpm_list_scenario_schedules_v2(...)  # endpoint for 06 — verify from Python source / DOM
smartpm_get_scenario_schedule_compression_trend(...)  # endpoint for 07

# Save to tests/fixtures/06-end-date-variance.json and 07-schedule-compression-index-over-time.json
```

- [ ] **Step 3: For each of charts 06, 07 — failing test → renderer → register → render → eyeball**

For each slug:

1. **Write `NN-slug.test.js`** asserting: every palette hex from the DOM-inspection JSON appears in `html`; the `META.title` appears; legend labels appear (if any); `svgInner.length > 100`; malformed payload throws `TypeError`; empty input returns an empty-state card.
2. **Run it** (`npx vitest run NN-slug.test.js`); confirm it fails.
3. **Write `NN-slug.js`**. Import the geometry helpers from `./svg-lib.js`. Palette constants at the top from your DOM inspection. Declare `META` and export `renderXyz`. Use the same `svgW = 1692, svgH = 312, padT = 14, padR = 32, padB = 30, padL = 56` geometry as the other single-card trends. **Eyeball against the LIVE SmartPM web view, not the old matplotlib PNG** — matplotlib was an approximation.
4. **Register** in `registry.js`, `meta.js`, and `index.js`.
5. **Run all tests** (`npm test`); confirm green.
6. **Render + eyeball**: invoke the JS CLI; open `chart-previews/NN-slug.png` against SmartPM.

- [ ] **Step 4: Update `phases/screenshots.md`**

Replace/refresh the chart 06 + 07 recipes.

- [ ] **Step 5: Bump versions + commit**

```bash
git add # ... 06-* + 07-* files + fixtures + registry/meta/index/screenshots + version files

git commit -m "$(cat <<'EOF'
feat(scheduling): JS charts 06, 07 (end date variance + schedule compression)

Visual upgrade from matplotlib — chart 06 (End Date Variance) and chart 07
(Schedule Compression Index Over Time) re-inspected from SmartPM's live
DOM (Wellington 113385). Matplotlib was an approximation; HTML+SVG now
matches the SmartPM web view.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Velocity + SPI — charts 08, 09 (commit 9)

**Goal:** Chart 08 is the heavy one — 6 grouped bar series + average line + vertical data-date marker. Chart 09 is a simple single-series SPI line.

**Files (each chart):**
- Create: `scheduling/skills/schedule-update/references/charts/08-velocity.js`
- Create: `scheduling/skills/schedule-update/references/charts/08-velocity.test.js`
- Create: `scheduling/skills/schedule-update/references/charts/09-spi-over-time.js`
- Create: `scheduling/skills/schedule-update/references/charts/09-spi-over-time.test.js`
- Modify: `registry.js`, `meta.js`, `index.js`, `phases/screenshots.md`, `plugin.json`, `marketplace.json`

- [ ] **Step 1: Inspect chart 08 — Velocity**

Most complex chart in the migration. Chrome MCP DOM inspection on Wellington (113385). Capture:
- 6 bar palette hexes.
- Bar grouping pattern (per-period stacked bars or side-by-side).
- Average-line color + stroke style.
- Data-date marker color + dasharray.
- Y-axis units (activities/period?).

If the SVG layout grows past ~400 lines, **factor a `groupedBars` helper into `svg-lib.js` as part of THIS commit**. The helper signature should look like:

```js
/** @param {{ groups: number[][], colors: string[], x0: number, x1: number, y0: number, y1: number, groupWidth: number }} opts @returns {string} */
export function groupedBars(opts) { ... }
```

- [ ] **Step 2: Inspect chart 09 — SPI Over Time**

Simple line chart. Capture palette + axis.

- [ ] **Step 3: Confirm/refresh MCP fixtures**

```
smartpm_get_scenario_velocity(...)
smartpm_get_scenario_spi_trend(...)

# Save to tests/fixtures/08-velocity.json and 09-spi-over-time.json
```

- [ ] **Step 4: For each of 08, 09 — failing test → renderer → register → render → eyeball**

Velocity test asserts: 6 palette hexes, average-line color, data-date dasharray, Y-axis units in the labels. SPI test asserts: single palette hex, line stroke, malformed-payload throw, empty-data empty-state.

- [ ] **Step 5: Update `phases/screenshots.md`**

Add chart 08 + 09 recipes.

- [ ] **Step 6: Bump versions + commit**

```bash
git add # ... 08-* + 09-* files + (svg-lib.js if groupedBars added) + fixtures + registry/meta/index/screenshots + version files

git commit -m "$(cat <<'EOF'
feat(scheduling): JS charts 08, 09 (velocity + SPI over time)

Chart 08 — 6 grouped bar series + average line + vertical data-date
marker. Most complex layout in the migration. [If a groupedBars helper was
factored: add it to svg-lib.js + svg-lib.test.js to keep per-chart code
focused on palette/axis decisions.]

Chart 09 — single-series SPI line, palette and axis from Chrome MCP DOM
inspection on Wellington (113385).

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 10: Hit-rate trio — charts 10, 11, 12 (commit 10)

**Goal:** Three charts share the stacked-bar shape (Total / Started / Finished × On-Time / Late / Missed). Implement once via a shared helper, three thin entry wrappers.

**Files:**
- Create: `scheduling/skills/schedule-update/references/charts/10-activity-hit-rate.js`
- Create: `scheduling/skills/schedule-update/references/charts/10-activity-hit-rate.test.js`
- Create: `scheduling/skills/schedule-update/references/charts/11-window-start-accuracy.js`
- Create: `scheduling/skills/schedule-update/references/charts/11-window-start-accuracy.test.js`
- Create: `scheduling/skills/schedule-update/references/charts/12-window-finish-accuracy.js`
- Create: `scheduling/skills/schedule-update/references/charts/12-window-finish-accuracy.test.js`
- Create (or modify): `scheduling/skills/schedule-update/references/charts/_hit-rate.js` (shared helper, exported only internally)
- Modify: `registry.js`, `meta.js`, `index.js`, `phases/screenshots.md`, `plugin.json`, `marketplace.json`

- [ ] **Step 1: Inspect one of the trio on SmartPM**

Chrome MCP DOM inspection on Wellington (113385). Pick chart 10 (Activity Hit Rate) — the other two share the visual shape. Capture: 3 palette hexes (On-Time / Late / Missed), bar grouping (Total / Started / Finished × time period), Y-axis units (count? percent?), data-date marker.

- [ ] **Step 2: Confirm MCP fixtures**

```
smartpm_get_scenario_should_start_finish_trend(...)
# This returns all three slugs' data — split by reading the right sub-field per slug.
# Save to tests/fixtures/10-activity-hit-rate.json (existing), 11-window-start-accuracy.json, 12-window-finish-accuracy.json
```

- [ ] **Step 3: Write `_hit-rate.js` — shared rendering helper**

```js
// _hit-rate.js — shared rendering logic for charts 10/11/12.
//
// The three charts have identical visual shape (stacked Total/Started/Finished
// bars × On-Time/Late/Missed segments). Only the title, the data sub-field,
// and the chart-card prefix vary.

import { HTML_CARD_W, HTML_CARD_H, dateToX, xTicks, htmlEnvelope, emptyHtml, legendItem } from './svg-lib.js';

// Palette: replace with the 3 hex codes from Chrome MCP DOM inspection.
const ON_TIME = '#1AA462';
const LATE    = '#FFC000';
const MISSED  = '#D01010';
const GRID    = '#e6e6e6';

/**
 * @typedef {Object} HitRateConfig
 * @property {string} title             Chart title.
 * @property {string} dataField         The sub-field name in each row (e.g. 'started' or 'finished').
 * @property {string[]} legendLabels    [onTimeLabel, lateLabel, missedLabel] for the legend.
 */

/**
 * @param {Array<{ dataDate: string, [k: string]: any }>} rows
 * @param {HitRateConfig} config
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderHitRate(rows, config) {
  // Validate, extract series, render stacked bars + legend.
  // ... (port from Python or write fresh from DOM inspection capture) ...
}
```

- [ ] **Step 4: Write the three entry files**

`10-activity-hit-rate.js`:

```js
import { HTML_CARD_W, HTML_CARD_H } from './svg-lib.js';
import { renderHitRate } from './_hit-rate.js';

export const META = {
  svgWidth: HTML_CARD_W, svgHeight: HTML_CARD_H,
  title: 'Activity Hit Rate',  // confirm vs Python / SmartPM
};

/** @param {Array<{ dataDate: string, [k: string]: any }>} payload @returns {import('./svg-lib.js').RenderResult} */
export function renderActivityHitRate(payload) {
  if (!Array.isArray(payload)) throw new TypeError('expected array payload');
  return renderHitRate(payload, {
    title: META.title,
    dataField: 'total',
    legendLabels: ['On Time', 'Late', 'Missed'],
  });
}
```

`11-window-start-accuracy.js` and `12-window-finish-accuracy.js`: same shape with `dataField: 'started'` and `'finished'`, and titles "Window Start Accuracy" / "Window Finish Accuracy" (confirm from SmartPM).

- [ ] **Step 5: Write the three test files**

Each test imports its own `META` + render function and asserts:

```js
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderActivityHitRate, META } from './10-activity-hit-rate.js';  // adapt name + slug per chart

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/10-activity-hit-rate.json'),
  'utf-8'
));

describe('renderActivityHitRate', () => {
  const { html, svgInner } = renderActivityHitRate(fixture);

  it('uses the 3 hit-rate palette hexes', () => {
    for (const hex of ['#1AA462', '#FFC000', '#D01010']) expect(html).toContain(hex);
  });

  it('emits the canonical title from META', () => {
    expect(html).toContain(META.title);
  });

  it('emits the 3 legend labels', () => {
    for (const label of ['On Time', 'Late', 'Missed']) expect(html).toContain(label);
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });

  it('throws TypeError on malformed payload', () => {
    expect(() => renderActivityHitRate(/** @type {any} */ ('nope'))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderActivityHitRate([]);
    expect(empty).toContain('no data');
  });
});
```

- [ ] **Step 6: Register all three in `registry.js`, `meta.js`, `index.js`**

- [ ] **Step 7: Run tests**

```bash
cd scheduling/skills/schedule-update/references/charts && npm test
```

- [ ] **Step 8: Render + eyeball each of the three**

```bash
node scheduling/skills/schedule-update/references/charts/cli.js \
     scheduling/skills/schedule-update/references/charts/tests/fixtures \
     chart-previews
```

Open all three `chart-previews/{10,11,12}-*.png` against the live SmartPM web views.

- [ ] **Step 9: Update `phases/screenshots.md`**

Add chart 10/11/12 recipes. All three use `smartpm_get_scenario_should_start_finish_trend` with different sub-field reads.

- [ ] **Step 10: Bump versions + commit**

```bash
git add scheduling/skills/schedule-update/references/charts/_hit-rate.js \
        scheduling/skills/schedule-update/references/charts/10-activity-hit-rate.js \
        scheduling/skills/schedule-update/references/charts/10-activity-hit-rate.test.js \
        scheduling/skills/schedule-update/references/charts/11-window-start-accuracy.js \
        scheduling/skills/schedule-update/references/charts/11-window-start-accuracy.test.js \
        scheduling/skills/schedule-update/references/charts/12-window-finish-accuracy.js \
        scheduling/skills/schedule-update/references/charts/12-window-finish-accuracy.test.js \
        scheduling/skills/schedule-update/references/charts/tests/fixtures/11-window-start-accuracy.json \
        scheduling/skills/schedule-update/references/charts/tests/fixtures/12-window-finish-accuracy.json \
        scheduling/skills/schedule-update/references/charts/registry.js \
        scheduling/skills/schedule-update/references/charts/meta.js \
        scheduling/skills/schedule-update/references/charts/index.js \
        scheduling/skills/schedule-update/phases/screenshots.md \
        scheduling/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json

git commit -m "$(cat <<'EOF'
feat(scheduling): JS charts 10, 11, 12 (hit-rate trio)

Three charts share the stacked-bar shape (Total/Started/Finished ×
On-Time/Late/Missed). Implemented once in _hit-rate.js, three thin entry
wrappers — same pattern as the Python _render_hit_rate_chart helper.

All three slugs back onto smartpm_get_scenario_should_start_finish_trend
with different sub-field reads.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 11: Summary report (commit 11)

**Goal:** Three sections (cards + plan-vs-actual curve + milestones table) in one HTML document, single PNG. `svgInner: ''` (composite — no canonical SVG). This is the threshold where the cloud editor matches the local CLI's coverage.

**Files:**
- Create: `scheduling/skills/schedule-update/references/charts/summary-report.js`
- Create: `scheduling/skills/schedule-update/references/charts/summary-report.test.js`
- Modify: `registry.js`, `meta.js`, `index.js`, `phases/screenshots.md` (replace 3 sub-slugs with 1 composite), `plugin.json`, `marketplace.json`

**Reference Python implementation:** Three separate matplotlib renderers in `charts.py` (`render_summary_cards`, `render_summary_plan_vs_actual`, `render_summary_milestones`) + the PIL-stitching in `render.py:_composite_summary_report`. Read all three to know the visual contract; the JS implementation collapses them into one HTML doc.

**Payload shape** (bundled by the orchestrator):

```js
{
  project_name: string,
  milestone_name: string,
  cards:      {/* smartpm_post_project_summary response */},
  curve:      {/* smartpm_get_scenario_percent_complete_curve_v2 response */},
  milestones: {/* smartpm_post_project_summary + smartpm_list_scenario_change_log_by_type, merged */},
}
```

- [ ] **Step 1: Inspect SmartPM's summary export view**

The summary view isn't a single SmartPM URL — it's a report builder. The three sections each correspond to a SmartPM widget. Open SmartPM's summary report for a Wellington release (project 113385) and screenshot it. The visual contract is your screenshot.

- [ ] **Step 2: Write `summary-report.test.js`**

```js
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderSummaryReport, META } from './summary-report.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/smartpm-summary-report.json'),
  'utf-8'
));

describe('renderSummaryReport', () => {
  const { html, svgInner } = renderSummaryReport(fixture);

  it('returns empty svgInner (composite has no canonical SVG)', () => {
    expect(svgInner).toBe('');
  });

  it('html contains all three section markers', () => {
    expect(html).toContain('class="summary-cards"');
    expect(html).toContain('class="summary-curve"');
    expect(html).toContain('class="summary-milestones"');
  });

  it('html contains the project name', () => {
    expect(html).toContain(fixture.project_name);
  });

  it('html contains at least one milestone row', () => {
    expect(html).toMatch(/<tr class="milestone-row"/);
  });

  it('throws when required sub-payload is missing', () => {
    expect(() => renderSummaryReport(/** @type {any} */ ({ cards: {} }))).toThrow();
  });
});
```

- [ ] **Step 3: Run the test — confirm it fails**

```bash
cd scheduling/skills/schedule-update/references/charts && npx vitest run summary-report.test.js
```

- [ ] **Step 4: Write `summary-report.js`**

Three sections in one HTML document, single chart-card envelope. Cards = top (~250px), curve = middle (~360px), milestones = bottom (sized by row count).

```js
// summary-report.js — composite renderer for cards + curve + milestones.

import { HTML_CARD_W, dateToX, pctToY, smoothPath, xTicks } from './svg-lib.js';

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: 1100,  // approximate; actual height varies with milestone-row count
  title:     'Schedule Summary Report',
};

/**
 * @typedef {Object} SummaryReportPayload
 * @property {string} project_name
 * @property {string} milestone_name
 * @property {Object} cards         smartpm_post_project_summary response
 * @property {Object} curve         smartpm_get_scenario_percent_complete_curve_v2 response
 * @property {Object} milestones    Merged milestone + change-log payload
 */

/**
 * @param {SummaryReportPayload} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderSummaryReport(payload) {
  if (!payload || !payload.cards || !payload.curve || !payload.milestones) {
    throw new TypeError('expected SummaryReportPayload with cards, curve, milestones');
  }

  const cardsHtml = renderCardsSection(payload.cards, payload.project_name);
  const curveHtml = renderCurveSection(payload.curve);
  const milestonesHtml = renderMilestonesSection(payload.milestones, payload.milestone_name);

  // Single-document HTML with the three sub-sections stacked vertically.
  // Width 1728px matches HTML_CARD_W so the rasteriser captures it at the
  // same scale as the trend charts.
  const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${escapeText(META.title)}</title>
<style>
  html, body { margin: 0; padding: 0; background: #fff; font-family: Inter, "Helvetica Neue", Arial, sans-serif; color: #181d27; }
  .chart-card { width: ${HTML_CARD_W}px; box-sizing: border-box; background: #fff; padding: 24px 32px; }
  .summary-cards { display: flex; gap: 16px; margin-bottom: 24px; }
  .summary-curve { margin-bottom: 24px; }
  .summary-milestones table { width: 100%; border-collapse: collapse; }
  .summary-milestones th, .summary-milestones td { padding: 6px 12px; text-align: left; border-bottom: 1px solid #e6e6e6; }
  .milestone-row.late td { color: #b00020; }
  /* ... more CSS as needed ... */
</style>
</head>
<body>
<div class="chart-card">
  ${cardsHtml}
  ${curveHtml}
  ${milestonesHtml}
</div>
</body>
</html>
`;

  return { html, svgInner: '' };
}

function renderCardsSection(cards, projectName) {
  // Port from charts.py:render_summary_cards (lines 849-1027).
  //
  // Three side-by-side cards:
  //   1. Project Health Index — vertical thermometer (red 0-50, yellow 50-75,
  //      green 75-100) with horizontal indicator + % label.
  //      Field: cards.health.value (int 0-100).
  //   2. Schedule Performance — SPI big-number + Planned/Actual % horizontal bars
  //      on the left + Critical Path Delay + Planned Impact big-number columns
  //      on the right.
  //      Fields: cards.spi (float), cards.planned_pct, cards.actual_pct,
  //              cards.critical_path_delay_days, cards.planned_impact_days.
  //   3. Schedule Feasibility — Quality Grade letter (green for A/B, red for
  //      C/D/F), Compression Index % (red if >=25, yellow if >=15, green
  //      otherwise), Predicted Completion (month/day/year stack in green) +
  //      previous-week comparison arrow (▲ red if slipped, ▼ green if recovered).
  //      Fields: cards.quality_grade (str), cards.compression_pct (int),
  //              cards.predicted_completion (YYYY-MM-DD), cards.last_predicted_completion (optional).
  //
  // Translation: matplotlib FancyBboxPatch + Rectangle become <rect rx="..."> SVG
  // or <div> with CSS border-radius; matplotlib ax.text() becomes <text> in
  // SVG or <span> in HTML. Use <div class="card-1|card-2|card-3"> + flexbox.
  // Approximate height: 250px total.
  //
  // SCI color constants (from charts.py style.py): GREEN '#1AA462', YELLOW
  // '#FFC000', RED '#D01010'. SmartPM red '#b00020'.
  return `<section class="summary-cards">...port from charts.py:849-1027...</section>`;
}

function renderCurveSection(curve) {
  // Port from charts.py:render_summary_plan_vs_actual (lines 728-848).
  //
  // The plan-vs-actual curve — same visual shape as chart 01 (Planned VS Actual
  // Percent Complete) but smaller height and simplified (no Progress Target band,
  // no Late Date Planned series — just Planned + Actual + Scheduled, per the
  // Python source).
  //
  // Reuse dateToX / pctToY / smoothPath from svg-lib. Approximate height: 360px.
  // Data shape: same as chart 01's percent_complete_curve_v2 — confirm against
  // the Python source's docstring.
  return `<section class="summary-curve">...port from charts.py:728-848...</section>`;
}

function renderMilestonesSection(milestones, milestoneName) {
  // Port from charts.py:render_summary_milestones (line 1029+).
  //
  // HTML table of milestone rows + change-log summary bullets above/below.
  // Columns (confirm against Python source's docstring):
  //   Milestone Name | Baseline Finish | Current Finish | Variance (days)
  //   | On Critical Path
  // Late rows (Variance > 0) get the .milestone-row.late CSS class — text in red.
  //
  // The change-log summary bullets list per-period change counts above the
  // table — same data the chart 04 trend visualizes, but in text form here.
  return `<section class="summary-milestones">...port from charts.py:1029+...</section>`;
}

function escapeText(s) {
  return String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;');
}
```

> **Reading the Python reference is critical here.** The three sub-section implementations are NOT in this skeleton — they're in `charts.py` as separate matplotlib functions. Open `charts.py` and read `render_summary_cards`, `render_summary_plan_vs_actual`, and `render_summary_milestones` to know:
> - Card layout (which KPIs, what order, what units).
> - Curve series (likely planned + actual, similar to chart 01 minus the band).
> - Milestone table columns (Milestone / Baseline Finish / Current Finish / Variance / etc.).

- [ ] **Step 5: Register in `registry.js`, `meta.js`, `index.js`**

- [ ] **Step 6: Build the fixture**

The summary-report payload doesn't yet exist as a single fixture. Build it from the three existing sub-payloads + a couple of top-level fields:

```bash
# Combine tests/fixtures/smartpm-summary-{cards,curve,milestones}.json
# into a single tests/fixtures/smartpm-summary-report.json:
{
  "project_name": "...",
  "milestone_name": "...",
  "cards":      { /* contents of smartpm-summary-cards.json */ },
  "curve":      { /* contents of smartpm-summary-curve.json */ },
  "milestones": { /* contents of smartpm-summary-milestones.json */ }
}
```

Write the file manually (it's a one-shot JSON merge).

- [ ] **Step 7: Run tests**

```bash
cd scheduling/skills/schedule-update/references/charts && npm test
```

- [ ] **Step 8: Render + eyeball against the SmartPM summary screenshot**

```bash
node scheduling/skills/schedule-update/references/charts/cli.js \
     scheduling/skills/schedule-update/references/charts/tests/fixtures \
     chart-previews
```

Open `chart-previews/smartpm-summary-report.png` AND the SmartPM summary report screenshot from Step 1. Visual checklist:
- Three sections present, in order: cards → curve → milestones.
- KPI cards match SmartPM's KPI palette / spacing.
- Curve matches chart 01's visual contract for shared series (planned + actual).
- Milestone table columns match SmartPM's column order; late rows highlighted.

This is the most complex visual — expect 2-3 inspect/fix/render cycles before it lands.

- [ ] **Step 9: Update `phases/screenshots.md`**

Replace the three separate slugs (`smartpm-summary-cards`, `smartpm-summary-curve`, `smartpm-summary-milestones`) with a single `smartpm-summary-report` recipe. Document the payload-merging step that bundles the three sub-payloads into one JSON.

- [ ] **Step 10: Bump versions + commit**

```bash
git add scheduling/skills/schedule-update/references/charts/summary-report.js \
        scheduling/skills/schedule-update/references/charts/summary-report.test.js \
        scheduling/skills/schedule-update/references/charts/tests/fixtures/smartpm-summary-report.json \
        scheduling/skills/schedule-update/references/charts/registry.js \
        scheduling/skills/schedule-update/references/charts/meta.js \
        scheduling/skills/schedule-update/references/charts/index.js \
        scheduling/skills/schedule-update/phases/screenshots.md \
        scheduling/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json

git commit -m "$(cat <<'EOF'
feat(scheduling): JS summary report (3 sections in 1 HTML)

Cards (top, ~250px), plan-vs-actual curve (middle, ~360px), milestones
table (bottom, sized by row count) — collapsed into a single HTML
document rasterised to one PNG. Three previously-separate Python
matplotlib renderers (render_summary_cards, render_summary_plan_vs_actual,
render_summary_milestones) and their PIL-stitching helper
(_composite_summary_report) are replaced by this single composite.

Returns svgInner: '' — composite has no canonical SVG. Cloud editor reads
the html field directly. Threshold reached: westland-mcps now matches the
local CLI's chart coverage.

Updates phases/screenshots.md to fold three sub-slugs into one
smartpm-summary-report recipe with a payload-merging step.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

## Task 12: Cleanup — delete Python rendering + legacy Playwright capture (commit 12)

**Goal:** Single rendering path, single language. Python and `--legacy` are gone. End state matches the spec's "What 'done' looks like" §.

**Files deleted:**
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

**Files modified:**
- `scheduling/skills/schedule-update/phases/screenshots.md` (major revision)
- `scheduling/commands/write-weekly-schedule-email.md` (Step 6 description)
- `scheduling/skills/schedule-update/SKILL.md` (grep + clean any surviving `--legacy` / `capture-smartpm.js` references)
- `scheduling/skills/schedule-update/references/package.json` (remove scripts referencing deleted files; LEAVE Playwright dep alone — `html_to_png.cjs` still needs it)
- `scheduling/.claude-plugin/plugin.json` (version bump)
- `.claude-plugin/marketplace.json` (matching version bump)

- [ ] **Step 1: Pre-deletion verification — confirm no surviving references**

```bash
git grep -E "capture-smartpm|smartpm-client|env-loader" -- 'scheduling/' \
  ':!scheduling/.claude-plugin/' \
  ':!scheduling/skills/schedule-update/references/smartpm/' \
  ':!scheduling/skills/schedule-update/references/tests/smartpm.spec.js' \
  ':!scheduling/skills/schedule-update/references/tests/full-page-debug.spec.js'
```

Expected: zero matches. If anything appears, surgically remove from those callers FIRST, in this same commit.

- [ ] **Step 2: Delete the Python rendering path**

```bash
git rm scheduling/skills/schedule-update/references/charts/charts.py \
       scheduling/skills/schedule-update/references/charts/render.py \
       scheduling/skills/schedule-update/references/charts/style.py \
       scheduling/skills/schedule-update/references/charts/__init__.py \
       scheduling/skills/schedule-update/references/charts/requirements.txt \
       scheduling/skills/schedule-update/references/charts/tests/__init__.py \
       scheduling/skills/schedule-update/references/charts/tests/conftest.py \
       scheduling/skills/schedule-update/references/charts/tests/test_render.py
```

- [ ] **Step 3: Delete the legacy Playwright capture path**

```bash
git rm scheduling/skills/schedule-update/references/smartpm/capture-smartpm.js \
       scheduling/skills/schedule-update/references/smartpm/smartpm-client.js \
       scheduling/skills/schedule-update/references/smartpm/env-loader.js \
       scheduling/skills/schedule-update/references/tests/smartpm.spec.js \
       scheduling/skills/schedule-update/references/tests/full-page-debug.spec.js
```

After these deletions, the `references/smartpm/` directory is empty. Git will not track it; on next clone the empty dir won't exist.

- [ ] **Step 4: Update `phases/screenshots.md` — major revision**

Open [`phases/screenshots.md`](../../scheduling/skills/schedule-update/phases/screenshots.md). The current file likely has a `--legacy` fallback section + a per-chart recipe list. Rewrite:

- **Remove entirely** the `--legacy` / `capture-smartpm.js` subsection.
- **Single rendering path** documented at the top:
  ```
  For each slug in graph_screenshots:
    1. Call the documented MCP endpoint (per-slug recipes below).
    2. Write the response as-is to {dated_folder}/.chart-payload/{slug}.json.
  Then:
    node scheduling/skills/schedule-update/references/charts/cli.js \
         {dated_folder}/.chart-payload \
         {dated_folder}/screenshots
  ```
- **Per-slug recipes** for all 17 slugs (16 trends + summary report). Each recipe lists: SmartPM MCP tool name, required params, response shape (1-line example), output filename.
- **Default `graph_screenshots`** list: includes all 16 trend slugs + `smartpm-summary-report`.

- [ ] **Step 5: Update `commands/write-weekly-schedule-email.md` — Step 6**

Find the current Step 6 (likely lines 2 + 83 mention `capture-smartpm.js`). Replace with:

```
Step 6 — Render the chart screenshots

For each slug in the project's graph_screenshots list:
  1. MCP-fetch the slug's payload (see phases/screenshots.md for per-slug recipes).
  2. Write the response to {dated_folder}/.chart-payload/{slug}.json.

Then render all 17 PNGs via the JS chart CLI:
  node scheduling/skills/schedule-update/references/charts/cli.js \
       {dated_folder}/.chart-payload \
       {dated_folder}/screenshots
```

- [ ] **Step 6: Grep + clean SKILL.md and any other surviving references**

```bash
git grep -E "--legacy|capture-smartpm|matplotlib|render\.py|charts\.py" -- 'scheduling/'
```

For each match outside of `phases/screenshots.md` and `commands/write-weekly-schedule-email.md` (already updated), Edit to remove/update.

- [ ] **Step 7: Clean up `scheduling/skills/schedule-update/references/package.json`**

Open the file. Remove any `scripts` entries that referenced deleted files (e.g. a `capture-smartpm` or `smartpm-test` script). **Leave Playwright as a dep** — `html_to_png.cjs` still uses it. **Do NOT add vitest/typescript/@types/node here**; those live in `charts/package.json` and have since commit 1.

- [ ] **Step 8: Run the cleanup-commit smoke tests**

```bash
# 1. Nothing in the skill references the deleted files
git grep -E "capture-smartpm|smartpm-client|matplotlib|_composite_summary_report|--legacy|charts\.py|render\.py" -- 'scheduling/'
```

Expected: zero matches. If anything matches, fix it BEFORE committing.

```bash
# 2. JS CLI handles every slug end-to-end from real project payloads
mkdir -p /tmp/chart-cleanup-smoke
node scheduling/skills/schedule-update/references/charts/cli.js \
  scheduling/skills/schedule-update/references/charts/tests/fixtures \
  /tmp/chart-cleanup-smoke
ls /tmp/chart-cleanup-smoke
```

Expected: 17 `.html` + 17 `.png` files in `/tmp/chart-cleanup-smoke`. Process exit 0 (no `failed` slugs).

```bash
# 3. Tests pass
cd scheduling/skills/schedule-update/references/charts && npm test
```

Expected: every per-chart spec green, svg-lib spec green, meta spec green, workers-import test passes (or class-skipped with a clear message).

```bash
# 4. JSDoc type-checking passes
cd scheduling/skills/schedule-update/references/charts && npm run typecheck
```

Expected: no errors.

If any check fails, fix inline before staging the deletes. Do NOT skip and "fix later."

- [ ] **Step 9: Bump versions + commit**

```bash
git add scheduling/skills/schedule-update/phases/screenshots.md \
        scheduling/commands/write-weekly-schedule-email.md \
        scheduling/skills/schedule-update/SKILL.md \
        scheduling/skills/schedule-update/references/package.json \
        scheduling/.claude-plugin/plugin.json \
        .claude-plugin/marketplace.json

# The git rm calls in Steps 2-3 already staged the deletions.

git commit -m "$(cat <<'EOF'
chore(scheduling): remove Python rendering + legacy Playwright capture

Cleanup commit (#12 of 12) for the HTML+SVG chart migration. All 17 JS
renderers landed and visually verified against SmartPM web view in
commits 1-11. Python and the --legacy escape hatch are no longer needed.

Deleted:
- charts.py, render.py, style.py, __init__.py, requirements.txt
- tests/{__init__.py, conftest.py, test_render.py}
- references/smartpm/{capture-smartpm.js, smartpm-client.js, env-loader.js}
- references/tests/{smartpm.spec.js, full-page-debug.spec.js}

Edited:
- phases/screenshots.md — major rewrite; single rendering path; 17 inline
  per-slug recipes; --legacy fallback removed.
- commands/write-weekly-schedule-email.md — Step 6 updated to invoke the
  JS CLI.
- SKILL.md — any surviving --legacy / capture-smartpm references removed.
- references/package.json — capture-* scripts removed; Playwright stays
  for html_to_png.cjs.

Smoke tests passing: git grep returns zero matches for the deleted
identifiers; npm test green; npm run typecheck clean; 17 .html + .png
pairs rendered from tests/fixtures into /tmp.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 10: Verify the cleanup commit didn't break the weekly email pipeline**

```bash
# From repo root — invoke the existing email-preview generator against a real
# project's data to confirm nothing downstream of the chart layer is broken.
# (This is a smoke test, not a release gate; the actual weekly run is the
# truth.)
python -m scheduling.skills.schedule-update.references.generate_email_preview_html --help
```

Expected: prints usage / version. If it errors with an import about `charts.render` or similar, surgically fix the caller.

- [ ] **Step 11: Final sanity grep**

```bash
git grep -E "matplotlib|numpy|Pillow|FancyBboxPatch|charts\.py|render\.py|--legacy" -- 'scheduling/'
```

Expected: zero matches across the entire `scheduling/` plugin directory. If a stray match appears, decide: legitimate historical reference (e.g. in a comment about the migration) or actual dependency that needs removal. Fix as a follow-up commit if not load-bearing for this cleanup.

---

## Self-review (already performed inline)

The plan was checked against the spec for:
1. **Spec coverage** — every spec section maps to a task: §"Architecture" → Tasks 1-2; §"Migration sequence" 12 commits → Tasks 1-12; §"Per-chart testing contract" → Tasks 2-11 step 1; §"Cleanup commit" → Task 12; §"Risks & mitigations" subagent-Chrome-MCP rule → Tasks 6-11 inspection workflow; §"Consumer-branch deploy milestones" → consequential for ordering but no task needed (consumer branch consumes externally).
2. **Placeholders** — no `TBD` / `FIXME` / vague-instruction text. Where the plan defers to the engineer (e.g. summary-report sub-sections in Task 11), it points at exact Python line ranges and enumerates the fields to read; the engineer's work is mechanical translation, not invention. Chart 04's palette + labels are inlined directly from `charts.py:2071-2089`. Tasks 6 and 7 reference Chrome MCP DOM inspection — also not a placeholder, since the inspection workflow itself is itemized step-by-step.
3. **Type consistency** — every renderer signature matches: `renderXyz(payload) -> { html, svgInner }`. Every META export has `svgWidth/svgHeight/title`. Registry keys are the slug strings from `phases/screenshots.md`, byte-identical to the existing Python `REGISTRY` keys.
4. **Ambiguity** — paths are absolute relative to repo root throughout. Commit messages are templated. Version bumps are spelled out with the pre-commit hook's enforcement rule called out in the Conventions §.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-22-html-svg-chart-migration-javascript.md`.

Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Fits this plan well: tasks 2-11 follow a templated pattern that subagents can execute in parallel pairs (e.g., 02 and 03 simultaneously if you want to risk a register-conflict merge — better to run sequentially), and the parent agent does the Chrome MCP inspections that subagents can't (per the spec's risk #2).

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints for your review.

Which approach?
