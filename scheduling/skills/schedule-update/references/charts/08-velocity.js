// 08-velocity.js — Monthly Activity Start & Finish Distribution.
//
// Six grouped column series + one stepped average line + a dark-blue data-date
// marker. The MCP (`smartpm_get_scenario_velocity`) returns one number per
// month for currentStarts and currentFinishes; SmartPM splits each into an
// Actual portion (months ≤ scenario data_date) and a Planned portion (months
// after data_date) so the chart visually separates "what happened" from
// "what's left to do". Palette / typography captured live from SmartPM DOM
// (project 113385, scenario 1644) on 2026-05-28.
//
// Series (legend order):
//   0  Current Starts (Actual)     #B4C7E7   light blue
//   1  Current Finishes (Actual)   #4472C4   dark  blue
//   2  Baseline Starts             #cccccc   light gray
//   3  Baseline Finishes           #808080   dark  gray
//   4  Current Starts (Planned)    #C5E0B4   light green
//   5  Current Finishes (Planned)  #70AD47   dark  green
//   6  Average                     #F2A623   orange line (stepped at data_date)
//
// Plus:
//   • Dark-blue vertical line (#4472C4, stroke-width 3) at the boundary
//     between the data-date month's slot and the next month's slot, with a
//     "DD MMM-YY" label rotated 90° at the top of the line.
//   • Stepped average: horizontal segment at the mean of actual months,
//     vertical step at the data-date boundary, horizontal segment at the
//     mean of planned months.
//   • X-axis labels rotated -45° so every month can fit without collision.
//   • "Values" rotated Y-axis title.

import {
  HTML_CARD_W, HTML_CARD_H,
  parseDate, legendItem, htmlEnvelope, emptyHtml,
} from './svg-lib.js';

// --- Palette --------------------------------------------------------------
const ACTUAL_STARTS     = '#B4C7E7';
const ACTUAL_FINISHES   = '#4472C4';
const BASELINE_STARTS   = '#cccccc';
const BASELINE_FINISHES = '#808080';
const PLANNED_STARTS    = '#C5E0B4';
const PLANNED_FINISHES  = '#70AD47';
const AVERAGE_LINE      = '#F2A623';
const DATA_DATE_LINE    = '#4472C4';
const BAR_STROKE        = '#ffffff';
const GRID              = '#e6e6e6';
const AXIS_LABEL_TXT    = '#333333';
const AXIS_TITLE_TXT    = '#666666';

const MONTHS_ABBR = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
/** @param {Date} d @returns {string} */
const fmtMMMYY = (d) => `${MONTHS_ABBR[d.getUTCMonth()]}-${String(d.getUTCFullYear()).slice(-2)}`;

/**
 * @typedef {Object} VelocityRow
 * @property {string} date
 * @property {number} baselineStarts
 * @property {number} baselineFinishes
 * @property {number} currentStarts
 * @property {number} currentFinishes
 */

/**
 * @typedef {{ velocityList: VelocityRow[], dataDate?: string } | VelocityRow[]} VelocityPayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Monthly Activity Start & Finish Distribution',
};

/**
 * @param {VelocityPayload} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderVelocity(payload) {
  /** @type {VelocityRow[]} */
  let rows;
  /** @type {string | undefined} */
  let dataDateISO;
  if (Array.isArray(payload)) {
    rows = payload;
    dataDateISO = undefined;
  } else if (payload && typeof payload === 'object') {
    const envelope = /** @type {any} */ (payload).velocityList;
    if (envelope === undefined || envelope === null) {
      rows = [];
    } else if (Array.isArray(envelope)) {
      rows = envelope;
    } else {
      throw new TypeError('expected VelocityPayload ({ velocityList: array }) or array');
    }
    dataDateISO = /** @type {any} */ (payload).dataDate;
  } else {
    throw new TypeError('expected VelocityPayload ({ velocityList: array }) or array');
  }

  if (!rows.length) return { html: emptyHtml(META.title), svgInner: '' };

  /** @param {any} v */
  const num = (v) => (typeof v === 'number' ? v : Number(v) || 0);

  // The data-date month is the boundary between Actual and Planned. If the
  // payload omits dataDate (e.g. array form), fall back to the latest month
  // with any currentStarts/currentFinishes — that's the last "actual" month.
  /** @type {Date | null} */
  let dataDate = dataDateISO ? parseDate(dataDateISO) : null;

  /** @type {Array<{ d: Date, csTotal: number, cfTotal: number, bs: number, bf: number }>} */
  const parsed = rows
    .filter(r => r && r.date != null)
    .map(r => ({
      d: parseDate(String(r.date)),
      csTotal: num(r.currentStarts),
      cfTotal: num(r.currentFinishes),
      bs: num(r.baselineStarts),
      bf: num(r.baselineFinishes),
    }))
    .filter(p => !isNaN(p.d.getTime()))
    .sort((a, b) => a.d.getTime() - b.d.getTime());

  if (!parsed.length) return { html: emptyHtml(META.title), svgInner: '' };

  if (!dataDate) {
    for (let i = parsed.length - 1; i >= 0; i--) {
      if (parsed[i].csTotal || parsed[i].cfTotal) {
        dataDate = parsed[i].d;
        break;
      }
    }
  }
  if (!dataDate) dataDate = parsed[parsed.length - 1].d;

  const dataDateMonthMs = Date.UTC(dataDate.getUTCFullYear(), dataDate.getUTCMonth(), 1);

  // Split current* into Actual (≤ data-date month) vs Planned (> data-date month).
  const split = parsed.map(p => {
    const monthMs = Date.UTC(p.d.getUTCFullYear(), p.d.getUTCMonth(), 1);
    const isPlanned = monthMs > dataDateMonthMs;
    return {
      d: p.d,
      bs: p.bs,
      bf: p.bf,
      csa: isPlanned ? 0 : p.csTotal,
      cfa: isPlanned ? 0 : p.cfTotal,
      csp: isPlanned ? p.csTotal : 0,
      cfp: isPlanned ? p.cfTotal : 0,
    };
  });

  // Trim leading/trailing all-zero months; keep interior zeros for spacing.
  let firstIdx = 0;
  while (firstIdx < split.length) {
    const r = split[firstIdx];
    if (r.bs || r.bf || r.csa || r.cfa || r.csp || r.cfp) break;
    firstIdx++;
  }
  let lastIdx = split.length - 1;
  while (lastIdx > firstIdx) {
    const r = split[lastIdx];
    if (r.bs || r.bf || r.csa || r.cfa || r.csp || r.cfp) break;
    lastIdx--;
  }
  const months = split.slice(firstIdx, lastIdx + 1);
  if (!months.length) return { html: emptyHtml(META.title), svgInner: '' };
  const N = months.length;

  // --- Layout ------------------------------------------------------------
  const svgW = 1692, svgH = 400;
  const padT = 14, padR = 32, padB = 64, padL = 64;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  // One slot per month, 6-bar group fills ~70% of the slot leaving ~30% gap
  // between months (matches SmartPM spacing at this density).
  const N_SERIES = 6;
  const slotW = N >= 2 ? (x1 - x0) / N : (x1 - x0);
  const GROUP_W = Math.max(12, Math.min(40, slotW * 0.70));
  const BAR_W = GROUP_W / N_SERIES;
  const offsets = [-2.5, -1.5, -0.5, 0.5, 1.5, 2.5].map(k => k * BAR_W);

  /** @param {number} i */
  const monthX = (i) => (N === 1 ? (x0 + x1) / 2 : x0 + slotW * (i + 0.5));

  // Y range — fit 0 to max of all 6 bar series + the per-month combined avg.
  let vMax = 0;
  for (const m of months) vMax = Math.max(vMax, m.bs, m.bf, m.csa, m.cfa, m.csp, m.cfp);
  const perMonthAvg = months.map(m => ((m.csa + m.csp) + (m.cfa + m.cfp)) / 2);
  vMax = Math.max(vMax, ...perMonthAvg);
  vMax = Math.max(1, vMax) * 1.10;
  const span = vMax;
  /** @param {number} v */
  const valueToY = (v) => y1 - (v / span) * (y1 - y0);

  // --- Y ticks -----------------------------------------------------------
  const tickStep = pickTickStep(vMax);
  const yTicks = [];
  for (let v = 0; v <= vMax + 0.5; v += tickStep) yTicks.push(v);

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

  // --- X tick labels (rotated -45°) --------------------------------------
  const xLabels = [];
  for (let i = 0; i < N; i++) {
    const x = monthX(i);
    const ly = y1 + 12;
    xLabels.push(`<text x="${x.toFixed(1)}" y="${ly}" font-family="Inter, sans-serif" font-size="12.8" fill="${AXIS_LABEL_TXT}" text-anchor="end" transform="rotate(-45 ${x.toFixed(1)} ${ly})">${fmtMMMYY(months[i].d)}</text>`);
  }

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;

  // --- 6 column series ---------------------------------------------------
  const yBot = valueToY(0);
  /** @type {string[]} */
  const bars = [];
  /** @param {number} cx @param {number} off @param {number} v @param {string} fill */
  const drawRect = (cx, off, v, fill) => {
    if (v <= 0) return;
    const yTop = valueToY(v);
    const h = Math.max(0, yBot - yTop);
    if (h === 0) return;
    const x = cx + off - BAR_W / 2;
    bars.push(`<rect x="${x.toFixed(2)}" y="${yTop.toFixed(2)}" width="${BAR_W.toFixed(2)}" height="${h.toFixed(2)}" fill="${fill}" stroke="${BAR_STROKE}" stroke-width="1" />`);
  };
  months.forEach((m, i) => {
    const cx = monthX(i);
    drawRect(cx, offsets[0], m.csa, ACTUAL_STARTS);
    drawRect(cx, offsets[1], m.cfa, ACTUAL_FINISHES);
    drawRect(cx, offsets[2], m.bs,  BASELINE_STARTS);
    drawRect(cx, offsets[3], m.bf,  BASELINE_FINISHES);
    drawRect(cx, offsets[4], m.csp, PLANNED_STARTS);
    drawRect(cx, offsets[5], m.cfp, PLANNED_FINISHES);
  });

  // --- Data-date marker (boundary between actual and planned months) ----
  let dataDateIdx = -1;
  for (let i = 0; i < N; i++) {
    if (
      months[i].d.getUTCFullYear() === dataDate.getUTCFullYear() &&
      months[i].d.getUTCMonth() === dataDate.getUTCMonth()
    ) { dataDateIdx = i; break; }
  }
  let dataDateLineSvg = '';
  let dataDateLabelSvg = '';
  /** @type {number | null} */
  let dataDateX = null;
  if (dataDateIdx >= 0) {
    dataDateX = monthX(dataDateIdx) + slotW / 2;
    dataDateLineSvg = `<line x1="${dataDateX.toFixed(1)}" y1="${y0}" x2="${dataDateX.toFixed(1)}" y2="${y1}" stroke="${DATA_DATE_LINE}" stroke-width="3" />`;
    const day = dataDate.getUTCDate();
    const labelTxt = `${day} ${fmtMMMYY(dataDate)}`;
    const lx = dataDateX + 4;
    const ly = y0 + 6;
    dataDateLabelSvg = `<text x="${lx.toFixed(1)}" y="${ly.toFixed(1)}" font-family="Inter, sans-serif" font-size="12.8" fill="${AXIS_LABEL_TXT}" text-anchor="start" transform="rotate(90 ${lx.toFixed(1)} ${ly.toFixed(1)})">${labelTxt}</text>`;
  }

  // --- Stepped Average line ---------------------------------------------
  const actualMonths  = months.filter(m => m.csa || m.cfa);
  const plannedMonths = months.filter(m => m.csp || m.cfp);
  /** @param {number[]} arr */
  const mean = (arr) => arr.length ? arr.reduce((a, b) => a + b, 0) / arr.length : 0;
  const actualAvg  = mean(actualMonths.map(m => (m.csa + m.cfa) / 2));
  const plannedAvg = mean(plannedMonths.map(m => (m.csp + m.cfp) / 2));

  const avgSegs = [];
  if (actualMonths.length && dataDateX != null) {
    const xLeft = monthX(0);
    const yA = valueToY(actualAvg);
    avgSegs.push(`<line x1="${xLeft.toFixed(1)}" y1="${yA.toFixed(2)}" x2="${dataDateX.toFixed(1)}" y2="${yA.toFixed(2)}" stroke="${AVERAGE_LINE}" stroke-width="2" />`);
  }
  if (plannedMonths.length && dataDateX != null) {
    const xRight = monthX(N - 1);
    const yP = valueToY(plannedAvg);
    if (actualMonths.length) {
      const yA = valueToY(actualAvg);
      avgSegs.push(`<line x1="${dataDateX.toFixed(1)}" y1="${yA.toFixed(2)}" x2="${dataDateX.toFixed(1)}" y2="${yP.toFixed(2)}" stroke="${AVERAGE_LINE}" stroke-width="2" />`);
    }
    avgSegs.push(`<line x1="${dataDateX.toFixed(1)}" y1="${yP.toFixed(2)}" x2="${xRight.toFixed(1)}" y2="${yP.toFixed(2)}" stroke="${AVERAGE_LINE}" stroke-width="2" />`);
  }
  const avgLineSvg = avgSegs.join('\n');

  const svgInner = [
    ...gridlines,
    frame,
    ...yLabels,
    ...xLabels,
    yTitle,
    ...bars,
    avgLineSvg,
    dataDateLineSvg,
    dataDateLabelSvg,
  ].join('\n');

  const legendHtml = [
    legendItem('square', ACTUAL_STARTS,    '', 'Current Starts (Actual)'),
    legendItem('square', ACTUAL_FINISHES,  '', 'Current Finishes (Actual)'),
    legendItem('square', BASELINE_STARTS,  '', 'Baseline Starts'),
    legendItem('square', BASELINE_FINISHES,'', 'Baseline Finishes'),
    legendItem('square', PLANNED_STARTS,   '', 'Current Starts (Planned)'),
    legendItem('square', PLANNED_FINISHES, '', 'Current Finishes (Planned)'),
    legendItem('circle', AVERAGE_LINE,     '', 'Average'),
  ].join('\n');

  const html = htmlEnvelope({
    title: META.title,
    svgW, svgH,
    svgInner,
    legendHtml,
  });
  return { html, svgInner };
}

/** @param {number} vMax @returns {number} */
function pickTickStep(vMax) {
  const candidates = [5, 10, 20, 25, 50, 100, 200, 500];
  for (const c of candidates) {
    if (vMax / c <= 6) return c;
  }
  return 1000;
}
