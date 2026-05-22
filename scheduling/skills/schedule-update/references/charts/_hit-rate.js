// _hit-rate.js — shared stacked-column renderer for charts 11 + 12.
// Three series stacked vertically per data date: on-time (green), late (yellow),
// did-not (red). Palette captured from SmartPM's live DOM via Chrome MCP on
// Wellington NZ Temple (project 113385, scenario 1644) on 2026-05-22.
//
// Chart 10 (Activity Hit Rate %) is a single-line chart, not a stack, so it
// does NOT use this helper — it lives inline in 10-activity-hit-rate.js.

import {
  HTML_CARD_W, HTML_CARD_H,
  dateToX, xTicks, parseDate,
  htmlEnvelope, emptyHtml, legendItem,
} from './svg-lib.js';

export const HIT_GREEN  = '#388543';
export const HIT_YELLOW = '#f2c031';
export const HIT_RED    = '#b00020';
const COLUMN_STROKE     = '#ffffff';
const GRID              = '#e6e6e6';

const BAR_WIDTH = 11; // px — visible without crowding even when data dates are dense

/**
 * @typedef {Object} HitRateStackedConfig
 * @property {string} title
 * @property {[string, string, string]} legendLabels  [onTime, late, didNot]
 * @property {{ onTime: string, late: string, didNot: string }} fields
 */

/**
 * Render a hit-rate stacked-column chart. Renderer for charts 11 + 12.
 *
 * @param {Array<Record<string, unknown>> | { hitRates?: Array<Record<string, unknown>> }} payload
 * @param {HitRateStackedConfig} config
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderHitRateStacked(payload, config) {
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

  /** @type {Array<{ d: Date, onTime: number, late: number, didNot: number, total: number }>} */
  const parsed = [];
  for (const r of rows) {
    if (!r || typeof r !== 'object') continue;
    const dataDate = /** @type {any} */ (r).dataDate;
    if (!dataDate) continue;
    const onTime = numberOrZero(/** @type {any} */ (r)[config.fields.onTime]);
    const late   = numberOrZero(/** @type {any} */ (r)[config.fields.late]);
    const didNot = numberOrZero(/** @type {any} */ (r)[config.fields.didNot]);
    parsed.push({
      d: parseDate(String(dataDate)),
      onTime, late, didNot,
      total: onTime + late + didNot,
    });
  }

  if (!parsed.length) return { html: emptyHtml(config.title), svgInner: '' };

  const svgW = 1692, svgH = 312;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const dmin = new Date(Math.min(...parsed.map(p => p.d.getTime())));
  const dmax = new Date(Math.max(...parsed.map(p => p.d.getTime())));

  // Y range: 0 to max stack height (with small headroom). Minimum of 1 so a
  // pathological "all zeros" payload still draws a coherent axis.
  const vMaxObs = Math.max(1, ...parsed.map(p => p.total));
  const vMax = Math.ceil(vMaxObs * 1.05);
  const vMin = 0;
  const ySpan = vMax - vMin;
  /** @param {number} v @returns {number} */
  const valueToY = (v) => y1 - ((v - vMin) / ySpan) * (y1 - y0);

  // ~5 horizontal gridlines + integer Y-axis labels.
  const gridlines = [];
  const yLabels = [];
  for (let i = 0; i <= 4; i++) {
    const v = vMin + (i / 4) * ySpan;
    const y = valueToY(v);
    gridlines.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" class="grid-line" />`);
    yLabels.push(`<text x="${x0 - 8}" y="${(y + 4).toFixed(1)}" class="axis-text axis-text-y">${Math.round(v)}</text>`);
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

  // Stacked columns — on-time at the bottom (green), then late (yellow), then
  // did-not (red) on top. Bar centered on the data date's x.
  const yBaseline = valueToY(0);
  /** @type {string[]} */
  const columns = [];
  for (const p of parsed) {
    const xCenter = dateToX(p.d, dmin, dmax, x0, x1);
    const xLeft = xCenter - BAR_WIDTH / 2;
    let runningBottom = yBaseline; // y of the top of the previous segment (or baseline)
    const segments = [
      { value: p.onTime, color: HIT_GREEN },
      { value: p.late,   color: HIT_YELLOW },
      { value: p.didNot, color: HIT_RED },
    ];
    for (const seg of segments) {
      if (seg.value <= 0) continue;
      const segTopY = valueToY(stackTopValue(p, seg));
      const h = runningBottom - segTopY;
      if (h <= 0) continue;
      columns.push(
        `<rect x="${xLeft.toFixed(2)}" y="${segTopY.toFixed(2)}" width="${BAR_WIDTH}" height="${h.toFixed(2)}" ` +
        `fill="${seg.color}" stroke="${COLUMN_STROKE}" stroke-width="1" />`
      );
      runningBottom = segTopY;
    }
  }

  const svgInner = [
    ...gridlines, frame,
    ...yLabels, ...xLabels,
    ...columns,
  ].join('\n');

  const [labelOnTime, labelLate, labelDidNot] = config.legendLabels;
  const legendHtml = [
    legendItem('square', HIT_GREEN,  '', labelOnTime),
    legendItem('square', HIT_YELLOW, '', labelLate),
    legendItem('square', HIT_RED,    '', labelDidNot),
  ].join('\n');

  const html = htmlEnvelope({ title: config.title, svgW, svgH, svgInner, legendHtml });
  return { html, svgInner };
}

/**
 * Cumulative stack value through the current segment, used to find the y of
 * the segment's top edge. The bottom edge is the previous segment's top (or
 * the baseline if this is the on-time segment).
 *
 * @param {{ onTime: number, late: number, didNot: number }} p
 * @param {{ value: number, color: string }} seg
 * @returns {number}
 */
function stackTopValue(p, seg) {
  if (seg.color === HIT_GREEN)  return p.onTime;
  if (seg.color === HIT_YELLOW) return p.onTime + p.late;
  return p.onTime + p.late + p.didNot;
}

/** @param {unknown} v @returns {number} */
function numberOrZero(v) {
  if (typeof v !== 'number' || Number.isNaN(v)) return 0;
  return v;
}
