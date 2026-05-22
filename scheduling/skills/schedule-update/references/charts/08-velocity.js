// 08-velocity.js — Monthly Activity Start & Finish Distribution (Velocity).
// Grouped column chart: 4 column series (Current Starts/Finishes,
// Baseline Starts/Finishes) per month + an Average line connecting
// per-month averages of Current Starts/Finishes + a dashed data-date
// plotline at the last month with any current* activity.
//
// Palette/series structure captured from SmartPM's live DOM via Chrome MCP
// on Wellington NZ Temple (project 113385, scenario 1644) on 2026-05-22.
// Live SmartPM shows 6 column series (including Planned variants); our
// payload only carries the 4 used here, so we render the 4-series simplification.

import {
  HTML_CARD_W, HTML_CARD_H,
  parseDate, legendItem, htmlEnvelope, emptyHtml,
} from './svg-lib.js';

const CURRENT_STARTS    = '#B4C7E7'; // light blue
const CURRENT_FINISHES  = '#4472C4'; // medium blue
const BASELINE_STARTS   = '#cccccc'; // light gray
const BASELINE_FINISHES = '#808080'; // dark gray
const AVERAGE_LINE      = '#F2A623'; // orange
const BAR_STROKE        = '#ffffff';
const DATA_DATE_LINE    = '#cccccc';
const GRID              = '#e6e6e6';

const MONTH_ABBR = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

/**
 * @typedef {Object} VelocityRow
 * @property {string} date
 * @property {number} baselineStarts
 * @property {number} baselineFinishes
 * @property {number} currentStarts
 * @property {number} currentFinishes
 */

/** @typedef {VelocityRow[]} VelocityPayload */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Monthly Activity Start & Finish Distribution',
};

/**
 * @param {VelocityPayload | { velocityList?: VelocityPayload }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderVelocity(payload) {
  let rows;
  if (Array.isArray(payload)) {
    rows = payload;
  } else if (payload && typeof payload === 'object') {
    const envelope = /** @type {any} */ (payload).velocityList;
    if (envelope === undefined || envelope === null) {
      rows = [];
    } else if (Array.isArray(envelope)) {
      rows = envelope;
    } else {
      throw new TypeError('expected VelocityPayload (array) or { velocityList: array }');
    }
  } else {
    throw new TypeError('expected VelocityPayload (array) or { velocityList: array }');
  }

  if (!rows.length) return { html: emptyHtml(META.title), svgInner: '' };

  /** @param {any} v */
  const num = (v) => (typeof v === 'number' ? v : Number(v) || 0);

  /** @type {Array<{ d: Date, cs: number, cf: number, bs: number, bf: number }>} */
  const parsed = rows.map(r => ({
    d:  parseDate(String(r.date)),
    cs: num(r.currentStarts),
    cf: num(r.currentFinishes),
    bs: num(r.baselineStarts),
    bf: num(r.baselineFinishes),
  }));

  // Trim empty months that fall outside the data-bearing range. We keep
  // interior zero-months as zero-height placeholders so the X-axis stays
  // evenly spaced.
  let firstIdx = 0;
  while (firstIdx < parsed.length) {
    const p = parsed[firstIdx];
    if (p.cs || p.cf || p.bs || p.bf) break;
    firstIdx++;
  }
  let lastIdx = parsed.length - 1;
  while (lastIdx > firstIdx) {
    const p = parsed[lastIdx];
    if (p.cs || p.cf || p.bs || p.bf) break;
    lastIdx--;
  }
  const months = parsed.slice(firstIdx, lastIdx + 1);
  if (!months.length) return { html: emptyHtml(META.title), svgInner: '' };

  const svgW = 1692, svgH = 312;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  // Group geometry: 4 bars per month, ~7px each. Group width ~28px.
  const BAR_W = 7;
  const N_SERIES = 4;
  const GROUP_W = BAR_W * N_SERIES;
  const offsets = [
    -1.5 * BAR_W, // currentStarts
    -0.5 * BAR_W, // currentFinishes
    +0.5 * BAR_W, // baselineStarts
    +1.5 * BAR_W, // baselineFinishes
  ];

  // Per-month X center: linearly space across the plot area so the labels stay
  // evenly distributed even when actual months are unevenly spaced.
  const nMonths = months.length;
  /** @param {number} i @returns {number} */
  const monthX = (i) => {
    if (nMonths === 1) return (x0 + x1) / 2;
    // Leave half a group of padding on each side so end groups don't kiss the frame.
    const usable = (x1 - x0) - GROUP_W;
    return x0 + GROUP_W / 2 + (i / (nMonths - 1)) * usable;
  };

  // Y range: auto-fit from 0 to max column value with 10% top padding.
  let vMax = 0;
  for (const m of months) {
    vMax = Math.max(vMax, m.cs, m.cf, m.bs, m.bf);
  }
  const avgs = months.map(m => (m.cs + m.cf) / 2);
  vMax = Math.max(vMax, ...avgs);
  vMax = Math.max(1, vMax) * 1.10;
  const vMin = 0;
  const ySpan = vMax - vMin;
  /** @param {number} v @returns {number} */
  const valueToY = (v) => y1 - ((v - vMin) / ySpan) * (y1 - y0);

  // ~5 horizontal gridlines spanning 0..vMax at "sensible" round increments.
  // Highcharts default is 5 ticks; we mirror that.
  const gridlines = [];
  const yLabels = [];
  for (let i = 0; i <= 4; i++) {
    const v = vMin + (i / 4) * ySpan;
    const y = valueToY(v);
    gridlines.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" class="grid-line" />`);
    yLabels.push(`<text x="${x0 - 8}" y="${(y + 4).toFixed(1)}" class="axis-text axis-text-y">${v.toFixed(0)}</text>`);
  }

  // X-axis labels: every month gets a label if there are ≤ 24 months;
  // otherwise stride to keep ~12-15 labels.
  const labelStride = Math.max(1, Math.ceil(nMonths / 14));
  const xLabels = [];
  for (let i = 0; i < nMonths; i += labelStride) {
    const m = months[i];
    const mon = MONTH_ABBR[m.d.getUTCMonth()];
    const yyyy = m.d.getUTCFullYear();
    const x = monthX(i);
    xLabels.push(`<text x="${x.toFixed(1)}" y="${y1 + 18}" class="axis-text axis-text-x">${mon} ${yyyy}</text>`);
  }
  // Always include the last month's label, even if the stride skipped it.
  if ((nMonths - 1) % labelStride !== 0 && nMonths > 1) {
    const m = months[nMonths - 1];
    const mon = MONTH_ABBR[m.d.getUTCMonth()];
    const yyyy = m.d.getUTCFullYear();
    const x = monthX(nMonths - 1);
    xLabels.push(`<text x="${x.toFixed(1)}" y="${y1 + 18}" class="axis-text axis-text-x">${mon} ${yyyy}</text>`);
  }

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;

  // Data-date vertical plotline at the last month with any current* activity.
  /** @type {string} */
  let plotLine = '';
  let dataDateIdx = -1;
  for (let i = nMonths - 1; i >= 0; i--) {
    if (months[i].cs || months[i].cf) { dataDateIdx = i; break; }
  }
  if (dataDateIdx >= 0) {
    const dx = monthX(dataDateIdx);
    plotLine = `<line x1="${dx.toFixed(1)}" y1="${y0}" x2="${dx.toFixed(1)}" y2="${y1}" stroke="${DATA_DATE_LINE}" stroke-width="2" stroke-dasharray="8,6" />`;
  }

  // Bars (4 per month, grouped). Order: currentStarts, currentFinishes,
  // baselineStarts, baselineFinishes (left → right).
  /** @type {string[]} */
  const barSvg = [];
  for (let i = 0; i < nMonths; i++) {
    const m = months[i];
    const cx = monthX(i);
    /** @param {number} value @param {number} offset @param {string} fill */
    const rect = (value, offset, fill) => {
      // Render even zero-value bars as zero-height placeholders so the
      // group geometry stays consistent. Skip negative (shouldn't occur).
      if (value < 0) return '';
      const yTop = valueToY(value);
      const yBot = valueToY(0);
      const h = Math.max(0, yBot - yTop);
      const x = cx + offset - BAR_W / 2;
      if (h === 0) return '';
      return `<rect x="${x.toFixed(2)}" y="${yTop.toFixed(2)}" width="${BAR_W}" height="${h.toFixed(2)}" fill="${fill}" stroke="${BAR_STROKE}" stroke-width="1" />`;
    };
    barSvg.push(rect(m.cs, offsets[0], CURRENT_STARTS));
    barSvg.push(rect(m.cf, offsets[1], CURRENT_FINISHES));
    barSvg.push(rect(m.bs, offsets[2], BASELINE_STARTS));
    barSvg.push(rect(m.bf, offsets[3], BASELINE_FINISHES));
  }

  // Average line: connects per-month avgs = (currentStarts + currentFinishes) / 2.
  // SmartPM's live chart uses Highcharts auto-averaging across all visible
  // series; we approximate by averaging the two Current* series, which is
  // what colleagues actually care about (Current pace).
  /** @type {Array<[number, number]>} */
  const avgPts = months.map((m, i) => [monthX(i), valueToY((m.cs + m.cf) / 2)]);
  const avgPath = 'M ' + avgPts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L ');
  const avgLineSvg = `<path d="${avgPath}" fill="none" stroke="${AVERAGE_LINE}" stroke-width="2" />`;

  // Y-axis title — colleague needs to know the unit is activity count, not %.
  const yAxisTitleX = x0 - 38;
  const yAxisTitleY = (y0 + y1) / 2;
  const yAxisTitle = `<text x="${yAxisTitleX}" y="${yAxisTitleY.toFixed(1)}" class="axis-title-text" transform="rotate(-90 ${yAxisTitleX} ${yAxisTitleY.toFixed(1)})">Activities</text>`;

  const svgInner = [
    ...gridlines, frame,
    ...yLabels, ...xLabels, yAxisTitle,
    ...barSvg.filter(s => s !== ''),
    plotLine,
    avgLineSvg,
  ].filter(s => s !== '').join('\n');

  const legendHtml = [
    legendItem('square', CURRENT_STARTS,    '', 'Current Starts'),
    legendItem('square', CURRENT_FINISHES,  '', 'Current Finishes'),
    legendItem('square', BASELINE_STARTS,   '', 'Baseline Starts'),
    legendItem('square', BASELINE_FINISHES, '', 'Baseline Finishes'),
    legendItem('square', AVERAGE_LINE,      '', 'Average'),
  ].join('\n');

  const html = htmlEnvelope({ title: META.title, svgW, svgH, svgInner, legendHtml });
  return { html, svgInner };
}
