// 13-missing-logic.js — Missing Logic Activities Over Time.
// Single-series straight line with circle markers. Palette/style captured
// from SmartPM's live DOM via Chrome MCP on Wellington NZ Temple
// (project 113385, scenario 1644) on 2026-05-22. No Python reference.

import {
  HTML_CARD_W, HTML_CARD_H,
  dateToX, xTicks, parseDate, htmlEnvelope, emptyHtml,
} from './svg-lib.js';

const LINE_COLOR    = '#2caffe';
const MARKER_FILL   = '#388543';
const MARKER_STROKE = '#ffffff';
const GRID          = '#e6e6e6';

/**
 * @typedef {Array<{ dataDate: string, value: number }>} MissingLogicPayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Missing Logic Activities Over Time',
};

/**
 * @param {MissingLogicPayload | { trend?: MissingLogicPayload }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderMissingLogic(payload) {
  let rows;
  if (Array.isArray(payload)) {
    rows = payload;
  } else if (payload && typeof payload === 'object') {
    const envelope = /** @type {any} */ (payload).trend;
    if (envelope === undefined || envelope === null) {
      rows = [];
    } else if (Array.isArray(envelope)) {
      rows = envelope;
    } else {
      throw new TypeError('expected MissingLogicPayload (array) or { trend: array }');
    }
  } else {
    throw new TypeError('expected MissingLogicPayload (array) or { trend: array }');
  }

  // Format the Y tick as a percent (input is a fraction 0..1).
  /** @param {number} v @returns {string} */
  const fmt = (v) => `${(v * 100).toFixed(1)}%`;
  return renderTrendLine(rows, META.title, fmt, 0.01 /* min Y span = 1% */);
}

/**
 * Single-series straight-line trend renderer. Shared by charts 13 (%), 14 (days),
 * 15 (% with red marker), 16 (% with yellow marker), and 07 (compression index %).
 * Kept inline (not factored into svg-lib) because (a) these straight-line
 * single-series consumers are the only ones right now, and (b) Task 10 will
 * introduce a separate `_trend-line.js` shared module for the hit-rate trio.
 *
 * @template R
 * @param {Array<R>} rows
 * @param {string} title
 * @param {(v: number) => string} fmt   Y-axis tick formatter (input is the raw value).
 * @param {number} minSpan              Minimum Y-axis span (in value units).
 * @param {string} [markerFill]         Circle-marker fill color (default `#388543` green).
 * @param {{
 *   xFormat?: 'short' | 'long',
 *   valueGetter?: (row: R) => (number | null | undefined),
 *   includeZero?: boolean,
 * }} [opts]
 *   - xFormat: 'short' = `MM/DD/YY` (default), 'long' = `MMM DD, YYYY`.
 *   - valueGetter: extract a numeric value from each row. Defaults to `r => r.value`.
 *     Returning null/undefined/NaN skips the row.
 *   - includeZero: clamp Y range to include 0 (default true). Set false when the
 *     series is a signed delta and 0 shouldn't dominate the axis (e.g. chart 06).
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderTrendLine(rows, title, fmt, minSpan, markerFill = MARKER_FILL, opts = {}) {
  const xFormat    = opts.xFormat    ?? 'short';
  /** @type {(row: any) => (number | null | undefined)} */
  const defaultGetter = (row) => row?.value;
  const getValue   = opts.valueGetter ?? defaultGetter;
  const includeZero = opts.includeZero ?? true;

  /** @type {Array<{d: Date, v: number}>} */
  const parsed = [];
  for (const r of (rows ?? [])) {
    const raw = getValue(r);
    if (typeof raw !== 'number' || Number.isNaN(raw)) continue;
    // @ts-ignore — row shape is renderer-specific; dataDate is the common contract.
    parsed.push({ d: parseDate(String(r.dataDate)), v: raw });
  }

  if (!parsed.length) return { html: emptyHtml(title), svgInner: '' };

  const svgW = 1692, svgH = 312;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const dmin = new Date(Math.min(...parsed.map(p => p.d.getTime())));
  const dmax = new Date(Math.max(...parsed.map(p => p.d.getTime())));

  // Y range: include observed min/max (and 0 by default), then pad ±10%
  // (clamped to a minimum span).
  const seed = includeZero ? [0] : [];
  let vMin = Math.min(...seed, ...parsed.map(p => p.v));
  let vMax = Math.max(...seed, ...parsed.map(p => p.v));
  let span = Math.max(minSpan, vMax - vMin);
  const pad = span * 0.10;
  vMin -= pad;
  vMax += pad;
  span = Math.max(minSpan, vMax - vMin);
  /** @param {number} v @returns {number} */
  const valueToY = (v) => y1 - ((v - vMin) / span) * (y1 - y0);

  // ~5 horizontal gridlines spanning the auto-fit range.
  const gridlines = [];
  const yLabels = [];
  for (let i = 0; i <= 4; i++) {
    const v = vMin + (i / 4) * span;
    const y = valueToY(v);
    gridlines.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" class="grid-line" />`);
    yLabels.push(`<text x="${x0 - 8}" y="${(y + 4).toFixed(1)}" class="axis-text axis-text-y">${fmt(v)}</text>`);
  }

  const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
  const xLabels = [];
  for (const d of xTicks(dmin, dmax)) {
    const x = dateToX(d, dmin, dmax, x0, x1);
    let label;
    if (xFormat === 'long') {
      const mon = MONTHS[d.getUTCMonth()];
      const dd  = String(d.getUTCDate()).padStart(2, '0');
      const yyyy = d.getUTCFullYear();
      label = `${mon} ${dd}, ${yyyy}`;
    } else {
      const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
      const dd = String(d.getUTCDate()).padStart(2, '0');
      const yy = String(d.getUTCFullYear()).slice(-2);
      label = `${mm}/${dd}/${yy}`;
    }
    xLabels.push(`<text x="${x.toFixed(1)}" y="${y1 + 18}" class="axis-text axis-text-x">${label}</text>`);
  }

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;

  /** @type {Array<[number, number]>} */
  const pts = parsed.map(p => [dateToX(p.d, dmin, dmax, x0, x1), valueToY(p.v)]);
  // Straight segments only (M-L-L-...). NOT smoothed — no cubic-Bezier "C" commands.
  const linePath = 'M ' + pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L ');

  const series = [
    `<path d="${linePath}" fill="none" stroke="${LINE_COLOR}" stroke-width="2" />`,
    ...pts.map(([x, y]) =>
      `<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="4" fill="${markerFill}" stroke="${MARKER_STROKE}" stroke-width="1" />`
    ),
  ];

  const svgInner = [...gridlines, frame, ...yLabels, ...xLabels, ...series].join('\n');
  const html = htmlEnvelope({ title, svgW, svgH, svgInner, legendHtml: '' });
  return { html, svgInner };
}
