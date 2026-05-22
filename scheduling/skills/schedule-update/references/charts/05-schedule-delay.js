// 05-schedule-delay.js — Schedule Delay Over Time, 3-series columnrange.
// No Python reference (charts.py stub). Palette + series structure captured
// from SmartPM's live DOM via Chrome MCP on Wellington NZ Temple
// (project 113385, scenario 1644) on 2026-05-22.

import {
  HTML_CARD_W, HTML_CARD_H,
  dateToX, xTicks, parseDate,
  legendItem, htmlEnvelope, emptyHtml,
} from './svg-lib.js';

const DELAY_COLOR     = '#b00020';                  // In-Period Delay
const GAIN_COLOR      = '#388543';                  // In-Period Gains
const PLANNED_STROKE  = '#1476b7';                  // Planned Impacts outline
const PLANNED_FILL    = 'rgba(16, 91, 141, 0.3)';   // Planned Impacts semi-transparent fill
const GRID            = '#e6e6e6';
const ZERO_GRID       = '#999';

const MONTH_ABBR = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

/**
 * @typedef {Object} DelayRow
 * @property {number} period
 * @property {string} scheduleName
 * @property {string} dataDate
 * @property {string} endDate
 * @property {{ period: number|null, cumulative: number }} endDateVariance
 * @property {{ period: number|null, cumulative: number }} criticalPathDelay
 * @property {{ period: number|null, cumulative: number }} criticalPathRecovery
 * @property {{ period: number|null, cumulative: number }} delayRecovery
 */

/** @typedef {DelayRow[]} ScheduleDelayPayload */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Schedule Delay Over Time',
};

/**
 * @param {ScheduleDelayPayload | { data?: ScheduleDelayPayload }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderScheduleDelay(payload) {
  // Accept flat array OR { data: [...] } envelope. smartpm_get_scenario_delay
  // returns the flat array directly (see phases/screenshots.md recipe).
  let rows;
  if (Array.isArray(payload)) {
    rows = payload;
  } else if (payload && typeof payload === 'object') {
    const envelope = /** @type {any} */ (payload).data;
    if (envelope === undefined || envelope === null) {
      rows = [];
    } else if (Array.isArray(envelope)) {
      rows = envelope;
    } else {
      throw new TypeError('expected ScheduleDelayPayload (array) or { data: array }');
    }
  } else {
    throw new TypeError('expected ScheduleDelayPayload (array) or { data: array }');
  }

  // Skip period 0 — baseline import has all null `period` values.
  const bars = rows.filter(r => r && r.period !== 0);
  if (!bars.length) return { html: emptyHtml(META.title), svgInner: '' };

  const svgW = 1692, svgH = 312;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const dates = bars.map(r => parseDate(String(r.dataDate)));
  const dmin = new Date(Math.min(...dates.map(d => d.getTime())));
  const dmax = new Date(Math.max(...dates.map(d => d.getTime())));

  // Compute y-axis range across the three plotted series (positive + negative).
  // Series semantics:
  //   In-Period Delay    -> +criticalPathDelay.period      (≥0)
  //   In-Period Gains    -> -criticalPathRecovery.period   (≤0)
  //   Planned Impacts    -> +delayRecovery.period          (signed)
  /** @param {any} v */
  const num = (v) => (v === null || v === undefined ? null : Number(v));

  /** @type {number[]} */
  const yValues = [0];
  for (const r of bars) {
    const delay = num(r.criticalPathDelay?.period);
    const gains = num(r.criticalPathRecovery?.period);
    const planned = num(r.delayRecovery?.period);
    if (delay !== null)   yValues.push(delay);
    if (gains !== null)   yValues.push(-gains);
    if (planned !== null) yValues.push(planned);
  }
  let yLo = Math.min(...yValues);
  let yHi = Math.max(...yValues);
  const span0 = Math.max(1, yHi - yLo);
  const pad = span0 * 0.10;
  yLo -= pad;
  yHi += pad;
  const ySpan = Math.max(1, yHi - yLo);
  /** @param {number} v @returns {number} */
  const valueToY = (v) => y1 - ((v - yLo) / ySpan) * (y1 - y0);

  // ~5 horizontal gridlines spanning the auto-fit range.
  const gridlines = [];
  const yLabels = [];
  for (let i = 0; i <= 4; i++) {
    const v = yLo + (i / 4) * ySpan;
    const y = valueToY(v);
    gridlines.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" class="grid-line" />`);
    yLabels.push(`<text x="${x0 - 8}" y="${(y + 4).toFixed(1)}" class="axis-text axis-text-y">${v.toFixed(0)}</text>`);
  }

  // Zero baseline — heavier stroke so positive vs negative bars read clearly.
  const yZero = valueToY(0);
  const zeroLine = `<line x1="${x0}" y1="${yZero.toFixed(1)}" x2="${x1}" y2="${yZero.toFixed(1)}" stroke="${ZERO_GRID}" stroke-width="1" />`;

  // X-axis: ticks via xTicks, format MMM DD, YYYY.
  const xLabels = [];
  for (const d of xTicks(dmin, dmax)) {
    const x = dateToX(d, dmin, dmax, x0, x1);
    const mon = MONTH_ABBR[d.getUTCMonth()];
    const dd  = String(d.getUTCDate()).padStart(2, '0');
    const yyyy = String(d.getUTCFullYear());
    xLabels.push(`<text x="${x.toFixed(1)}" y="${y1 + 18}" class="axis-text axis-text-x">${mon} ${dd}, ${yyyy}</text>`);
  }

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;

  // Bars: per-period group of 3 side-by-side bars (Delay / Gains / Planned).
  // Each individual bar is ~8-12px wide; offset within group so they don't overlap.
  const BAR_W = 9;
  const GROUP_OFFSETS = [-BAR_W - 1, 0, BAR_W + 1]; // left / center / right of period center

  /** @type {string[]} */
  const barSvg = [];
  for (const r of bars) {
    const cx = dateToX(parseDate(String(r.dataDate)), dmin, dmax, x0, x1);
    const delay = num(r.criticalPathDelay?.period);
    const gains = num(r.criticalPathRecovery?.period);
    const planned = num(r.delayRecovery?.period);

    // Draw order back-to-front: Delay, Gains, Planned (Planned on top so its
    // outline reads clearly against the solid-fill peers).
    /** @param {number} value @param {number} offset @param {string} fill @param {string} stroke */
    const rect = (value, offset, fill, stroke) => {
      if (value === null || value === 0) return '';
      const yTop = valueToY(Math.max(0, value));
      const yBot = valueToY(Math.min(0, value));
      const h = Math.max(1, yBot - yTop);
      const x = cx + offset - BAR_W / 2;
      return `<rect x="${x.toFixed(2)}" y="${yTop.toFixed(2)}" width="${BAR_W}" height="${h.toFixed(2)}" fill="${fill}" stroke="${stroke}" stroke-width="2" />`;
    };

    // Delay: positive bar from 0 up to +delay.
    if (delay !== null && delay !== 0) {
      barSvg.push(rect(delay, GROUP_OFFSETS[0], DELAY_COLOR, DELAY_COLOR));
    }
    // Gains: negative bar from 0 down to -gains. (gains is ≥0, render as negative.)
    if (gains !== null && gains !== 0) {
      barSvg.push(rect(-gains, GROUP_OFFSETS[1], GAIN_COLOR, GAIN_COLOR));
    }
    // Planned Impacts: bar from 0 to +planned (signed; can be negative per fixture).
    if (planned !== null && planned !== 0) {
      barSvg.push(rect(planned, GROUP_OFFSETS[2], PLANNED_FILL, PLANNED_STROKE));
    }
  }

  // Y-axis title — rotated text along left edge so colleagues know the unit.
  const yAxisTitleX = x0 - 38;
  const yAxisTitleY = (y0 + y1) / 2;
  const yAxisTitle = `<text x="${yAxisTitleX}" y="${yAxisTitleY.toFixed(1)}" class="axis-title-text" transform="rotate(-90 ${yAxisTitleX} ${yAxisTitleY.toFixed(1)})">Days of Delay</text>`;

  const svgInner = [
    ...gridlines, frame, zeroLine,
    ...yLabels, ...xLabels, yAxisTitle,
    ...barSvg,
  ].join('\n');

  const legendHtml = [
    legendItem('square', DELAY_COLOR,    '', 'In-Period Delay'),
    legendItem('square', GAIN_COLOR,     '', 'In-Period Gains'),
    legendItem('square', PLANNED_STROKE, '', 'Planned Impacts'),
  ].join('\n');

  const html = htmlEnvelope({ title: META.title, svgW, svgH, svgInner, legendHtml });
  return { html, svgInner };
}
