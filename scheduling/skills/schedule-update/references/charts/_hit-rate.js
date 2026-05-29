// _hit-rate.js — shared stacked-column renderer for charts 11 + 12.
//
// Three series stacked per data date — red (Did Not …) at the bottom,
// yellow (… Late) in the middle, green (… On Time) on top — with a per-
// segment count label inside each visible segment and the period total
// labeled above each column. Categorical X axis (one slot per data date).
// Palette / typography / layout captured live from SmartPM DOM (project
// 113385, scenario 1644) on 2026-05-28.
//
// Visual specs:
//   • Columns ≈ 65% of slot width, leaving visible inter-column gaps
//   • Segment labels: Inter 11.2 px bold;
//       black on green/yellow, white on red (SmartPM convention)
//   • Total label above each column: Inter 12.8 px medium, dark gray
//   • Y axis: 0 floor, tick step picked to fit the observed max
//   • "Values" rotated Y-axis title
//   • X-axis labels: MM/DD/YY, horizontal, one per data date
//
// Chart 10 (Activity Hit Rate %) is a single-line chart, not a stack —
// it lives inline in 10-activity-hit-rate.js, not this helper.

import {
  parseDate,
  htmlEnvelope, emptyHtml, legendItem,
} from './svg-lib.js';

export const HIT_GREEN  = '#388543';
export const HIT_YELLOW = '#f2c031';
export const HIT_RED    = '#b00020';
const COLUMN_STROKE     = '#ffffff';
const GRID              = '#e6e6e6';
const AXIS_LABEL_TXT    = '#333333';
const AXIS_TITLE_TXT    = '#666666';
const TOTAL_LABEL_TXT   = '#333333';

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
  parsed.sort((a, b) => a.d.getTime() - b.d.getTime());

  // Show the most recent ~6 months at weekly cadence (matches the email's
  // narrative window). Wider history is still in the fixture if a future
  // version wants to expose a longer view.
  const WINDOW = 26;
  const visible = parsed.slice(-WINDOW);
  const N = visible.length;

  // --- Layout ------------------------------------------------------------
  const svgW = 1692, svgH = 400;
  // padT = 32 to leave room for the total-label above each column.
  const padT = 32, padR = 32, padB = 36, padL = 64;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const slotW = N >= 2 ? (x1 - x0) / N : (x1 - x0);
  const BAR_W = Math.max(8, Math.min(32, slotW * 0.65));
  const colX = (i) => N === 1 ? (x0 + x1) / 2 : x0 + slotW * (i + 0.5);

  // Y range
  const vMax = Math.max(1, ...visible.map(p => p.total));
  const tickStep = pickTickStep(vMax);
  const vCeil = Math.ceil(vMax / tickStep) * tickStep;
  /** @param {number} v */
  const valueToY = (v) => y1 - (v / vCeil) * (y1 - y0);

  const yTicks = [];
  for (let v = 0; v <= vCeil + 0.5; v += tickStep) yTicks.push(v);

  const gridlines = yTicks.map(v => {
    const y = valueToY(v);
    return `<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" stroke="${GRID}" stroke-width="1" />`;
  });
  const yLabels = yTicks.map(v => {
    const y = valueToY(v);
    return `<text x="${x0 - 10}" y="${(y + 4).toFixed(1)}" font-family="Inter, sans-serif" font-size="12.8" fill="${AXIS_LABEL_TXT}" text-anchor="end">${v}</text>`;
  });

  const yTitleCX = 22;
  const yTitleCY = (y0 + y1) / 2;
  const yTitle = `<text x="${yTitleCX}" y="${yTitleCY}" font-family="Inter, sans-serif" font-size="12.8" fill="${AXIS_TITLE_TXT}" text-anchor="middle" transform="rotate(-90 ${yTitleCX} ${yTitleCY})">Values</text>`;

  const xLabels = visible.map((r, i) => {
    const x = colX(i);
    const mm = String(r.d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(r.d.getUTCDate()).padStart(2, '0');
    const yy = String(r.d.getUTCFullYear()).slice(-2);
    return `<text x="${x.toFixed(1)}" y="${y1 + 20}" font-family="Inter, sans-serif" font-size="12.8" fill="${AXIS_LABEL_TXT}" text-anchor="middle">${mm}/${dd}/${yy}</text>`;
  });

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;

  const yBaseline = valueToY(0);
  /** @type {string[]} */
  const columns = [];
  /** @type {string[]} */
  const segmentLabels = [];
  /** @type {string[]} */
  const totalLabels = [];

  for (let i = 0; i < N; i++) {
    const p = visible[i];
    const cx = colX(i);
    const xLeft = cx - BAR_W / 2;
    let runningBottom = yBaseline;
    // Red on bottom, yellow middle, green on top.
    const segments = [
      { v: p.didNot, color: HIT_RED,    cum: p.didNot,                       textFill: '#ffffff' },
      { v: p.late,   color: HIT_YELLOW, cum: p.didNot + p.late,              textFill: '#000000' },
      { v: p.onTime, color: HIT_GREEN,  cum: p.didNot + p.late + p.onTime,   textFill: '#000000' },
    ];
    for (const seg of segments) {
      if (seg.v <= 0) continue;
      const segTop = valueToY(seg.cum);
      const h = runningBottom - segTop;
      if (h <= 0) continue;
      columns.push(
        `<rect x="${xLeft.toFixed(2)}" y="${segTop.toFixed(2)}" width="${BAR_W.toFixed(2)}" height="${h.toFixed(2)}" ` +
        `fill="${seg.color}" stroke="${COLUMN_STROKE}" stroke-width="1" />`
      );
      // In-segment label (only if there's room).
      if (h >= 14) {
        const cy = (segTop + runningBottom) / 2 + 4;
        segmentLabels.push(
          `<text x="${cx.toFixed(1)}" y="${cy.toFixed(1)}" font-family="Inter, sans-serif" font-size="11.2" font-weight="700" fill="${seg.textFill}" text-anchor="middle">${seg.v}</text>`
        );
      }
      runningBottom = segTop;
    }
    if (p.total > 0) {
      const topY = valueToY(p.total);
      totalLabels.push(
        `<text x="${cx.toFixed(1)}" y="${(topY - 4).toFixed(1)}" font-family="Inter, sans-serif" font-size="12.8" font-weight="500" fill="${TOTAL_LABEL_TXT}" text-anchor="middle">${p.total}</text>`
      );
    }
  }

  const svgInner = [
    ...gridlines, frame,
    ...yLabels, ...xLabels,
    yTitle,
    ...columns,
    ...segmentLabels,
    ...totalLabels,
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

/** @param {number} vMax @returns {number} */
function pickTickStep(vMax) {
  const candidates = [5, 10, 15, 20, 25, 50, 100, 200];
  for (const c of candidates) {
    if (vMax / c <= 6) return c;
  }
  return 500;
}

/** @param {unknown} v @returns {number} */
function numberOrZero(v) {
  if (typeof v !== 'number' || Number.isNaN(v)) return 0;
  return v;
}
