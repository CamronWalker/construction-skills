// 09-spi-over-time.js — SPI Over Time.
// Single-series straight line with per-point threshold-colored circle markers,
// plus two horizontal reference plotlines (yellow at 0.7, green at 1.0).
// Palette/style captured from SmartPM's live DOM via Chrome MCP on Wellington
// NZ Temple (project 113385, scenario 1644) on 2026-05-22. No Python reference.
//
// Written inline (not via renderTrendLine helper) because chart 09 needs:
//   - per-point marker fill (3 SPI thresholds)
//   - two horizontal reference plotlines (target + caution)
//   - line gaps where SPI is 0 (treat as missing data, not zero)
//   - a custom Y-axis (floor=0, ceiling=max(1.2, observed+0.1), percent fmt)
// Wrapping the helper to support all four would be a bigger change than this
// inline implementation. Task 10's _trend-line.js extraction is the right
// place to design the shared API once we have 4+ similar consumers.

import {
  HTML_CARD_W, HTML_CARD_H,
  dateToX, xTicks, parseDate, htmlEnvelope, emptyHtml,
} from './svg-lib.js';

const LINE_COLOR    = '#1476b7';
const MARKER_STROKE = '#ffffff';
const MARKER_RED    = '#b00020';
const MARKER_YELLOW = '#f2c031';
const MARKER_GREEN  = '#1AA462';
const PLOT_YELLOW   = '#f2c031'; // caution plotline at SPI = 0.7
const PLOT_GREEN    = '#388543'; // target plotline at SPI = 1.0
const GRID          = '#e6e6e6';

const SPI_TARGET  = 1.0;
const SPI_CAUTION = 0.7;
const SPI_GREEN   = 0.9;

/**
 * @typedef {Array<{ dataDate: string, spi: number }>} SpiTrendPayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'SPI Over Time',
};

/** @param {number} spi @returns {string} */
function markerFillForSpi(spi) {
  if (spi < SPI_CAUTION) return MARKER_RED;
  if (spi < SPI_GREEN)   return MARKER_YELLOW;
  return MARKER_GREEN;
}

/**
 * @param {SpiTrendPayload | { trend?: SpiTrendPayload }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderSpiOverTime(payload) {
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
      throw new TypeError('expected SpiTrendPayload (array) or { trend: array }');
    }
  } else {
    throw new TypeError('expected SpiTrendPayload (array) or { trend: array }');
  }

  /** @type {Array<{ d: Date, v: number | null }>} */
  // Walk every row to preserve chronological order; null = gap (spi 0 or missing).
  const parsed = [];
  for (const r of rows) {
    if (!r || typeof r !== 'object') continue;
    const dataDate = /** @type {any} */ (r).dataDate;
    if (!dataDate) continue;
    const d = parseDate(String(dataDate));
    const spi = /** @type {any} */ (r).spi;
    if (typeof spi !== 'number' || Number.isNaN(spi) || spi === 0) {
      parsed.push({ d, v: null });
    } else {
      parsed.push({ d, v: spi });
    }
  }

  const realPoints = parsed.filter(p => p.v !== null);
  if (!realPoints.length) return { html: emptyHtml(META.title), svgInner: '' };

  const svgW = 1692, svgH = 312;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const dmin = new Date(Math.min(...parsed.map(p => p.d.getTime())));
  const dmax = new Date(Math.max(...parsed.map(p => p.d.getTime())));

  // Y range: floor at 0, ceiling at max(1.2, observed max + 0.1).
  const vMaxObs = Math.max(...realPoints.map(p => /** @type {number} */ (p.v)));
  const vMin = 0;
  const vMax = Math.max(1.2, vMaxObs + 0.1);
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

  // Reference plotlines — drawn BEFORE the data line so the data marks stay on top.
  const yCaution = valueToY(SPI_CAUTION);
  const yTarget  = valueToY(SPI_TARGET);
  const plotCaution = `<line x1="${x0}" y1="${yCaution.toFixed(1)}" x2="${x1}" y2="${yCaution.toFixed(1)}" stroke="${PLOT_YELLOW}" stroke-width="2" stroke-dasharray="8,6" />`;
  const plotTarget  = `<line x1="${x0}" y1="${yTarget.toFixed(1)}" x2="${x1}" y2="${yTarget.toFixed(1)}" stroke="${PLOT_GREEN}" stroke-width="2" stroke-dasharray="8,6" />`;

  // Data line — broken into subpaths at gaps (spi 0 or null). Straight
  // segments only (M-L-L-...), NO cubic-Bezier curves.
  /** @type {Array<Array<[number, number, number]>>} */
  const subpaths = [];
  /** @type {Array<[number, number, number]>} */
  let cur = [];
  for (const p of parsed) {
    if (p.v === null) {
      if (cur.length) { subpaths.push(cur); cur = []; }
      continue;
    }
    const x = dateToX(p.d, dmin, dmax, x0, x1);
    const y = valueToY(p.v);
    cur.push([x, y, p.v]);
  }
  if (cur.length) subpaths.push(cur);

  /** @type {string[]} */
  const lineSegs = [];
  /** @type {string[]} */
  const markerSegs = [];
  for (const sub of subpaths) {
    if (sub.length === 1) {
      const [x, y] = sub[0];
      // Single isolated point — no line, just the marker.
      lineSegs.push(`<path d="M ${x.toFixed(2)},${y.toFixed(2)}" fill="none" stroke="${LINE_COLOR}" stroke-width="2" />`);
    } else {
      const d = 'M ' + sub.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L ');
      lineSegs.push(`<path d="${d}" fill="none" stroke="${LINE_COLOR}" stroke-width="2" />`);
    }
    for (const [x, y, v] of sub) {
      const fill = markerFillForSpi(v);
      markerSegs.push(
        `<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="4" fill="${fill}" stroke="${MARKER_STROKE}" stroke-width="1" />`
      );
    }
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
