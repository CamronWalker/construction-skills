// 10-activity-hit-rate.js — Activity Hit Rate (%) Over Time.
//
// Single-series trend with 3-zone coloring:
//   value < 0.80          → red    #b00020 (BAD)
//   0.80 ≤ value < 0.90   → yellow #f2c031 (FINE)
//   value ≥ 0.90          → green  #388543 (GOOD)
//
// Plus dashed horizontal threshold lines at 0.80 (yellow) and 0.90 (green).
// Palette / typography captured live from SmartPM DOM (project 113385,
// scenario 1644) on 2026-05-28. Same visual treatment as chart 09 (SPI).

import {
  HTML_CARD_W, HTML_CARD_H,
  parseDate, htmlEnvelope, emptyHtml, legendItem,
} from './svg-lib.js';

const ZONE_RED       = '#b00020';
const ZONE_YELLOW    = '#f2c031';
const ZONE_GREEN     = '#388543';
const DASH_YELLOW    = '#f2c031';
const DASH_GREEN     = '#388543';
const GRID           = '#e6e6e6';
const AXIS_LABEL_TXT = '#333333';
const AXIS_TITLE_TXT = '#666666';
const LEGEND_SWATCH  = '#2caffe';

const THRESH_RED_YELLOW   = 0.80;
const THRESH_YELLOW_GREEN = 0.90;

const WINDOW = 26;

/**
 * @typedef {Array<{ dataDate: string, totalOnTimeHitRate: number }>} HitRatePayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Activity Hit Rate (%)',
};

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

  const all = (rows ?? [])
    .filter(r => r && r.dataDate != null && typeof r.totalOnTimeHitRate === 'number' && !Number.isNaN(r.totalOnTimeHitRate))
    .map(r => ({ d: parseDate(String(r.dataDate)), v: /** @type {number} */ (r.totalOnTimeHitRate) }))
    .sort((a, b) => a.d.getTime() - b.d.getTime());

  if (!all.length) return { html: emptyHtml(META.title), svgInner: '' };
  const visible = all.slice(-WINDOW);

  const svgW = 1692, svgH = 400;
  const padT = 14, padR = 32, padB = 36, padL = 80;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const indexToX = (i) =>
    visible.length <= 1 ? (x0 + x1) / 2 : x0 + (i / (visible.length - 1)) * (x1 - x0);

  const vMin = 0;
  const vMax = 1;
  const span = vMax - vMin;
  /** @param {number} v */
  const valueToY = (v) => y1 - ((v - vMin) / span) * (y1 - y0);

  // Y ticks at 20% increments.
  const yTicks = [];
  for (let v = 0; v <= 1.0001; v += 0.20) yTicks.push(Math.round(v * 100) / 100);

  const gridlines = yTicks.map(v => {
    const y = valueToY(v);
    return `<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" stroke="${GRID}" stroke-width="1" />`;
  });
  const yLabels = yTicks.map(v => {
    const y = valueToY(v);
    return `<text x="${x0 - 10}" y="${(y + 4).toFixed(1)}" font-family="Inter, sans-serif" font-size="12.8" fill="${AXIS_LABEL_TXT}" text-anchor="end">${(v * 100).toFixed(0)} %</text>`;
  });

  const yTitleCX = 22;
  const yTitleCY = (y0 + y1) / 2;
  const yTitle = `<text x="${yTitleCX}" y="${yTitleCY}" font-family="Inter, sans-serif" font-size="12.8" fill="${AXIS_TITLE_TXT}" text-anchor="middle" transform="rotate(-90 ${yTitleCX} ${yTitleCY})">Values</text>`;

  const xLabels = visible.map((r, i) => {
    const x = indexToX(i);
    const mm = String(r.d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(r.d.getUTCDate()).padStart(2, '0');
    const yy = String(r.d.getUTCFullYear()).slice(-2);
    return `<text x="${x.toFixed(1)}" y="${y1 + 20}" font-family="Inter, sans-serif" font-size="12.8" fill="${AXIS_LABEL_TXT}" text-anchor="middle">${mm}/${dd}/${yy}</text>`;
  });

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;

  const yYellow = valueToY(THRESH_RED_YELLOW);
  const yGreen  = valueToY(THRESH_YELLOW_GREEN);
  const dashYellowLine = `<line x1="${x0}" y1="${yYellow.toFixed(1)}" x2="${x1}" y2="${yYellow.toFixed(1)}" stroke="${DASH_YELLOW}" stroke-width="2" stroke-dasharray="8,6" />`;
  const dashGreenLine  = `<line x1="${x0}" y1="${yGreen.toFixed(1)}"  x2="${x1}" y2="${yGreen.toFixed(1)}"  stroke="${DASH_GREEN}"  stroke-width="2" stroke-dasharray="8,6" />`;

  const pts = visible.map((r, i) => ({ x: indexToX(i), y: valueToY(r.v), v: r.v }));

  const segs = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i];
    const b = pts[i + 1];
    if (zoneOf(a.v) === zoneOf(b.v)) {
      segs.push({ pts: [a, b], color: colorFor(a.v) });
      continue;
    }
    const thresholds = [THRESH_RED_YELLOW, THRESH_YELLOW_GREEN]
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
    dashYellowLine,
    dashGreenLine,
    ...lineSegs,
    ...markers,
  ].join('\n');

  const legendHtml = legendItem('circle', LEGEND_SWATCH, '', 'Total On-Time Hit Rate');

  const html = htmlEnvelope({
    title: META.title,
    svgW, svgH,
    svgInner,
    legendHtml,
  });
  return { html, svgInner };
}

/** @param {number} v */
function colorFor(v) {
  if (v < THRESH_RED_YELLOW) return ZONE_RED;
  if (v < THRESH_YELLOW_GREEN) return ZONE_YELLOW;
  return ZONE_GREEN;
}

/** @param {number} v @returns {0|1|2} */
function zoneOf(v) {
  if (v < THRESH_RED_YELLOW) return 0;
  if (v < THRESH_YELLOW_GREEN) return 1;
  return 2;
}
