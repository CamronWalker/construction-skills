// 10-activity-hit-rate.js — Activity Hit Rate (%).
// Single-series straight line with per-point threshold-colored circle markers,
// plus two horizontal reference plotlines (yellow at 0.7, green at 1.0).
// Same visualization shape as chart 09 (SPI Over Time) — palette/style captured
// from SmartPM's live DOM via Chrome MCP on Wellington NZ Temple (project
// 113385, scenario 1644) on 2026-05-22. No Python reference.
//
// Written inline (not via a shared helper) for the same reasons as chart 09:
// per-point marker fill across 3 thresholds, two horizontal reference plotlines,
// and a custom Y-axis (floor=0, ceiling=max(1.05, observed+0.05), percent fmt).
// _hit-rate.js handles only the stacked-column shape used by charts 11 and 12.

import {
  HTML_CARD_W, HTML_CARD_H,
  dateToX, xTicks, parseDate, htmlEnvelope, emptyHtml,
} from './svg-lib.js';

const LINE_COLOR    = '#1476b7';
const MARKER_STROKE = '#ffffff';
const MARKER_RED    = '#b00020';
const MARKER_YELLOW = '#f2c031';
const MARKER_GREEN  = '#1AA462';
const PLOT_YELLOW   = '#f2c031'; // caution plotline at hit rate = 0.7
const PLOT_GREEN    = '#388543'; // target  plotline at hit rate = 1.0
const GRID          = '#e6e6e6';

const HIT_TARGET  = 1.0;
const HIT_CAUTION = 0.7;
const HIT_GREEN   = 0.9;

/**
 * @typedef {Array<{ dataDate: string, totalOnTimeHitRate: number }>} HitRatePayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Activity Hit Rate (%)',
};

/** @param {number} v @returns {string} */
function markerFillForHitRate(v) {
  if (v < HIT_CAUTION) return MARKER_RED;
  if (v < HIT_GREEN)   return MARKER_YELLOW;
  return MARKER_GREEN;
}

/**
 * @param {HitRatePayload | { hitRates?: HitRatePayload }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderActivityHitRate(payload) {
  let rows;
  if (Array.isArray(payload)) {
    rows = payload;
  } else if (payload && typeof payload === 'object') {
    const envelope = /** @type {any} */ (payload).hitRates;
    if (envelope === undefined || envelope === null) {
      rows = [];
    } else if (Array.isArray(envelope)) {
      rows = envelope;
    } else {
      throw new TypeError('expected HitRatePayload (array) or { hitRates: array }');
    }
  } else {
    throw new TypeError('expected HitRatePayload (array) or { hitRates: array }');
  }

  /** @type {Array<{ d: Date, v: number }>} */
  const parsed = [];
  for (const r of rows) {
    if (!r || typeof r !== 'object') continue;
    const dataDate = /** @type {any} */ (r).dataDate;
    if (!dataDate) continue;
    const v = /** @type {any} */ (r).totalOnTimeHitRate;
    if (typeof v !== 'number' || Number.isNaN(v)) continue;
    parsed.push({ d: parseDate(String(dataDate)), v });
  }

  if (!parsed.length) return { html: emptyHtml(META.title), svgInner: '' };

  const svgW = 1692, svgH = 312;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const dmin = new Date(Math.min(...parsed.map(p => p.d.getTime())));
  const dmax = new Date(Math.max(...parsed.map(p => p.d.getTime())));

  // Y range: floor at 0, ceiling at max(1.05, observed max + 0.05).
  const vMaxObs = Math.max(...parsed.map(p => p.v));
  const vMin = 0;
  const vMax = Math.max(1.05, vMaxObs + 0.05);
  const ySpan = vMax - vMin;
  /** @param {number} v @returns {number} */
  const valueToY = (v) => y1 - ((v - vMin) / ySpan) * (y1 - y0);

  // ~5 horizontal gridlines + percent-formatted Y-axis labels.
  /** @param {number} v @returns {string} */
  const fmtY = (v) => `${(v * 100).toFixed(0)} %`;
  const gridlines = [];
  const yLabels = [];
  for (let i = 0; i <= 4; i++) {
    const v = vMin + (i / 4) * ySpan;
    const y = valueToY(v);
    gridlines.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" class="grid-line" />`);
    yLabels.push(`<text x="${x0 - 8}" y="${(y + 4).toFixed(1)}" class="axis-text axis-text-y">${fmtY(v)}</text>`);
  }

  // X-axis labels: MM/DD/YY via xTicks.
  const xLabels = [];
  for (const d of xTicks(dmin, dmax)) {
    const x = dateToX(d, dmin, dmax, x0, x1);
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(d.getUTCDate()).padStart(2, '0');
    const yy = String(d.getUTCFullYear()).slice(-2);
    xLabels.push(`<text x="${x.toFixed(1)}" y="${y1 + 18}" class="axis-text axis-text-x">${mm}/${dd}/${yy}</text>`);
  }

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;

  // Reference plotlines — drawn BEFORE the data line so data marks stay on top.
  const yCaution = valueToY(HIT_CAUTION);
  const yTarget  = valueToY(HIT_TARGET);
  const plotCaution = `<line x1="${x0}" y1="${yCaution.toFixed(1)}" x2="${x1}" y2="${yCaution.toFixed(1)}" stroke="${PLOT_YELLOW}" stroke-width="2" stroke-dasharray="8,6" />`;
  const plotTarget  = `<line x1="${x0}" y1="${yTarget.toFixed(1)}" x2="${x1}" y2="${yTarget.toFixed(1)}" stroke="${PLOT_GREEN}" stroke-width="2" stroke-dasharray="8,6" />`;

  // Data line — straight segments only (M-L-L-...), NO cubic-Bezier curves.
  /** @type {Array<[number, number, number]>} */
  const pts = parsed.map(p => [
    dateToX(p.d, dmin, dmax, x0, x1),
    valueToY(p.v),
    p.v,
  ]);
  /** @type {string[]} */
  const lineSegs = [];
  /** @type {string[]} */
  const markerSegs = [];
  if (pts.length === 1) {
    const [x, y] = pts[0];
    lineSegs.push(`<path d="M ${x.toFixed(2)},${y.toFixed(2)}" fill="none" stroke="${LINE_COLOR}" stroke-width="2" />`);
  } else {
    const d = 'M ' + pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L ');
    lineSegs.push(`<path d="${d}" fill="none" stroke="${LINE_COLOR}" stroke-width="2" />`);
  }
  for (const [x, y, v] of pts) {
    const fill = markerFillForHitRate(v);
    markerSegs.push(
      `<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="4" fill="${fill}" stroke="${MARKER_STROKE}" stroke-width="1" />`
    );
  }

  const svgInner = [
    ...gridlines, frame,
    ...yLabels, ...xLabels,
    plotCaution, plotTarget,
    ...lineSegs, ...markerSegs,
  ].join('\n');

  // No legend — single series, colors are self-explanatory by threshold.
  const html = htmlEnvelope({ title: META.title, svgW, svgH, svgInner, legendHtml: '' });
  return { html, svgInner };
}
