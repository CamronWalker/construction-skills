// 07-schedule-compression.js — Schedule Compression Index™ Over Time.
//
// Plots the raw `scheduleCompressionIndex` (percent units; lower = healthier)
// over a categorical X axis (one slot per data date, equal spacing).
//
// Palette / typography / layout captured live from SmartPM's DOM
// (project 113385, scenario 1644) on 2026-05-28.
//
// Visual treatment:
//   • Trend line + markers colored by 3 zones —
//       value < 15  → green   #1AA462 (GOOD)
//       15 ≤ v < 25 → orange  #F5A623 (FINE)
//       value ≥ 25  → red     #DB495B (BAD)
//   • Dashed horizontal threshold lines at y=15 (mustard) and y=25 (dark red).
//   • Categorical X with MM/DD/YY tick labels (Inter 12.8 px).
//   • Rotated "Values" Y-axis title (SmartPM convention).
//   • Y range pinned to 0 floor + ≥28 top so the red dashed line stays
//     visible even when the project is fully green.
//   • Window: most recent 26 data dates (≈6 months of weekly cadence).
//   • No pills, no plot bands, no zero line.

import {
  HTML_CARD_W, HTML_CARD_H,
  parseDate, htmlEnvelope, emptyHtml, legendItem,
} from './svg-lib.js';

// --- Palette --------------------------------------------------------------
const ZONE_GREEN     = '#1AA462';
const ZONE_ORANGE    = '#F5A623';
const ZONE_RED       = '#DB495B';
const DASH_ORANGE    = '#E0B020';      // dashed threshold @ 15 (mustard)
const DASH_RED       = '#B41E2F';      // dashed threshold @ 25 (darker red)
const GRID           = '#e6e6e6';
const AXIS_LABEL_TXT = '#333333';
const AXIS_TITLE_TXT = '#666666';
const LEGEND_SWATCH  = '#2caffe';

const THRESH_GREEN_ORANGE = 15;
const THRESH_ORANGE_RED   = 25;

const WINDOW = 26;

/**
 * @typedef {Object} CompressionTrendRow
 * @property {string}      dataDate
 * @property {number|null} [scheduleCompressionIndex]
 * @property {number|null} [scheduleCompression]
 * @property {string|null} [indicator]
 */

/**
 * @typedef {{ trend: Array<CompressionTrendRow> } | Array<CompressionTrendRow>} ScheduleCompressionPayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Schedule Compression Index™ Over Time',
};

/**
 * @param {ScheduleCompressionPayload} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderScheduleCompression(payload) {
  /** @type {Array<CompressionTrendRow>} */
  let trend;
  if (Array.isArray(payload)) {
    trend = payload;
  } else if (payload && typeof payload === 'object') {
    const envelope = /** @type {any} */ (payload).trend;
    if (envelope === undefined || envelope === null) {
      trend = [];
    } else if (Array.isArray(envelope)) {
      trend = envelope;
    } else {
      throw new TypeError('expected ScheduleCompressionPayload ({ trend: array }) or array');
    }
  } else {
    throw new TypeError('expected ScheduleCompressionPayload ({ trend: array }) or array');
  }

  const all = trend
    .filter(r => r && r.dataDate != null && typeof r.scheduleCompressionIndex === 'number' && !Number.isNaN(r.scheduleCompressionIndex))
    .map(r => ({
      d: parseDate(r.dataDate),
      v: /** @type {number} */ (r.scheduleCompressionIndex),
    }))
    .sort((a, b) => a.d.getTime() - b.d.getTime());

  if (!all.length) return { html: emptyHtml(META.title), svgInner: '' };

  const rows = all.slice(-WINDOW);

  // --- Layout ------------------------------------------------------------
  const svgW = 1692, svgH = 400;
  const padT = 14, padR = 32, padB = 36, padL = 80;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const indexToX = (i) =>
    rows.length <= 1 ? (x0 + x1) / 2 : x0 + (i / (rows.length - 1)) * (x1 - x0);

  const vRaw = rows.map(r => r.v);
  let vMin = 0;
  let vMax = Math.max(28, ...vRaw);   // keep red dashed line in frame
  vMax += (vMax - vMin) * 0.10;
  const span = vMax - vMin;
  /** @param {number} v @returns {number} */
  const valueToY = (v) => y1 - ((v - vMin) / span) * (y1 - y0);

  // --- Y ticks -----------------------------------------------------------
  const tickStep = pickTickStep(span);
  const yTicks = [];
  let t = Math.ceil(vMin / tickStep) * tickStep;
  while (t <= vMax + 0.5) { yTicks.push(t); t += tickStep; }

  const gridlines = yTicks.map(v => {
    const y = valueToY(v);
    return `<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" stroke="${GRID}" stroke-width="1" />`;
  });
  const yLabels = yTicks.map(v => {
    const y = valueToY(v);
    return `<text x="${x0 - 10}" y="${(y + 4).toFixed(1)}" font-family="Inter, sans-serif" font-size="12.8" fill="${AXIS_LABEL_TXT}" text-anchor="end">${v} %</text>`;
  });

  const yTitleCX = 22;
  const yTitleCY = (y0 + y1) / 2;
  const yTitle = `<text x="${yTitleCX}" y="${yTitleCY}" font-family="Inter, sans-serif" font-size="12.8" fill="${AXIS_TITLE_TXT}" text-anchor="middle" transform="rotate(-90 ${yTitleCX} ${yTitleCY})">Values</text>`;

  // --- X tick labels (MM/DD/YY at each data point) -----------------------
  const xLabels = rows.map((r, i) => {
    const x = indexToX(i);
    const mm = String(r.d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(r.d.getUTCDate()).padStart(2, '0');
    const yy = String(r.d.getUTCFullYear()).slice(-2);
    return `<text x="${x.toFixed(1)}" y="${y1 + 20}" font-family="Inter, sans-serif" font-size="12.8" fill="${AXIS_LABEL_TXT}" text-anchor="middle">${mm}/${dd}/${yy}</text>`;
  });

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;

  // --- Dashed threshold lines --------------------------------------------
  const yOrange = valueToY(THRESH_GREEN_ORANGE);
  const yRed    = valueToY(THRESH_ORANGE_RED);
  const dashOrangeLine = `<line x1="${x0}" y1="${yOrange.toFixed(1)}" x2="${x1}" y2="${yOrange.toFixed(1)}" stroke="${DASH_ORANGE}" stroke-width="1.5" stroke-dasharray="8,4" />`;
  const dashRedLine    = `<line x1="${x0}" y1="${yRed.toFixed(1)}"    x2="${x1}" y2="${yRed.toFixed(1)}"    stroke="${DASH_RED}"    stroke-width="1.5" stroke-dasharray="8,4" />`;

  // --- 3-zone trend line -------------------------------------------------
  const pts = rows.map((r, i) => ({ x: indexToX(i), y: valueToY(r.v), v: r.v }));

  const segs = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i];
    const b = pts[i + 1];
    const za = zoneOf(a.v);
    const zb = zoneOf(b.v);
    if (za === zb) {
      segs.push({ pts: [a, b], color: colorFor(a.v) });
      continue;
    }
    // Split at each threshold the segment passes through, in segment order.
    const thresholds = [THRESH_GREEN_ORANGE, THRESH_ORANGE_RED]
      .filter(thr => (a.v - thr) * (b.v - thr) < 0)
      .sort((p, q) => Math.sign(b.v - a.v) * (p - q));
    let last = a;
    let lastV = a.v;
    for (const thr of thresholds) {
      const tFrac = (thr - lastV) / (b.v - lastV);
      const x = last.x + (b.x - last.x) * tFrac;
      const y = valueToY(thr);
      const mid = { x, y, v: thr };
      segs.push({ pts: [last, mid], color: colorFor(lastV) });
      last = mid;
      lastV = thr;
    }
    segs.push({ pts: [last, b], color: colorFor(b.v) });
  }
  const lineSegs = segs.map(({ pts: [p, q], color }) =>
    `<line x1="${p.x.toFixed(2)}" y1="${p.y.toFixed(2)}" x2="${q.x.toFixed(2)}" y2="${q.y.toFixed(2)}" stroke="${color}" stroke-width="2" />`
  );

  const markers = pts.map(({ x, y, v }) => {
    const color = colorFor(v);
    return `<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="4" fill="${color}" />`;
  });

  const svgInner = [
    ...gridlines,
    frame,
    ...yLabels,
    ...xLabels,
    yTitle,
    dashOrangeLine,
    dashRedLine,
    ...lineSegs,
    ...markers,
  ].join('\n');

  const legendHtml = legendItem('circle', LEGEND_SWATCH, '', 'Schedule Compression Index');

  const html = htmlEnvelope({
    title: META.title,
    svgW, svgH,
    svgInner,
    legendHtml,
  });
  return { html, svgInner };
}

/** @param {number} v @returns {string} */
function colorFor(v) {
  if (v >= THRESH_ORANGE_RED) return ZONE_RED;
  if (v >= THRESH_GREEN_ORANGE) return ZONE_ORANGE;
  return ZONE_GREEN;
}

/** @param {number} v @returns {0|1|2} */
function zoneOf(v) {
  if (v >= THRESH_ORANGE_RED) return 2;
  if (v >= THRESH_GREEN_ORANGE) return 1;
  return 0;
}

/** @param {number} span @returns {number} */
function pickTickStep(span) {
  const candidates = [2, 5, 10, 20, 25, 50];
  for (const c of candidates) {
    if (span / c <= 6) return c;
  }
  return 100;
}
