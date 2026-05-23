// 02-schedule-quality.js — port of charts.py:render_schedule_quality_grade_over_time
// (lines 1739-1878).

import {
  HTML_CARD_W, HTML_CARD_H,
  dateToX, xTicks, parseDate, htmlEnvelope, emptyHtml,
} from './svg-lib.js';

const LINE_COLOR = '#2caffe';
const GRID       = '#e6e6e6';

// Canonical SmartPM grade scale, top (A+ = rank 0) to bottom (F = rank 10).
const GRADE_RANKS = [
  'A+', 'A', 'A-',
  'B+', 'B', 'B-',
  'C+', 'C', 'C-',
  'D',  'F',
];

/**
 * @typedef {Array<{ dataDate: string, grade?: { mark?: string, indicator?: string, score?: number } }>} ScheduleQualityPayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Schedule Quality Grade™ Over Time',
};

/**
 * @param {ScheduleQualityPayload | { trend?: ScheduleQualityPayload }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderScheduleQuality(payload) {
  // Accept flat list (raw MCP shape) OR { trend: [...] } envelope.
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
      throw new TypeError('expected ScheduleQualityPayload (array) or { trend: array }');
    }
  } else {
    throw new TypeError('expected ScheduleQualityPayload (array) or { trend: array }');
  }

  const gradeToRank = /** @type {Record<string, number>} */ (
    Object.fromEntries(GRADE_RANKS.map((g, i) => [g, i]))
  );
  /** @type {Array<{ d: Date, rank: number, grade: string }>} */
  const parsed = [];
  for (const r of rows) {
    const grade = r?.grade?.mark;
    if (!grade || !(grade in gradeToRank)) continue;
    parsed.push({
      d: parseDate(String(r.dataDate)),
      rank: gradeToRank[grade],
      grade,
    });
  }

  if (!parsed.length) {
    return { html: emptyHtml(META.title), svgInner: '' };
  }

  const svgW = 1692, svgH = 312;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const dmin = new Date(Math.min(...parsed.map(p => p.d.getTime())));
  const dmax = new Date(Math.max(...parsed.map(p => p.d.getTime())));

  // Auto-fit Y to observed rank range; if all same grade, pad by 1 above/below.
  let yRankTop = Math.min(...parsed.map(p => p.rank));
  let yRankBot = Math.max(...parsed.map(p => p.rank));
  if (yRankTop === yRankBot) {
    yRankTop = Math.max(0, yRankTop - 1);
    yRankBot = Math.min(GRADE_RANKS.length - 1, yRankBot + 1);
  }
  const rankSpan = Math.max(1, yRankBot - yRankTop);
  /** @param {number} rank @returns {number} */
  const rankToY = (rank) => y0 + ((rank - yRankTop) / rankSpan) * (y1 - y0);

  /** @type {Array<[number, number]>} */
  const pts = parsed.map(p => [dateToX(p.d, dmin, dmax, x0, x1), rankToY(p.rank)]);
  // Straight segments (not smoothed) — per Python reference (charts.py:1835).
  const linePath = 'M ' + pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L ');

  const gridlines = [];
  const yLabels = [];
  for (let rank = yRankTop; rank <= yRankBot; rank++) {
    const y = rankToY(rank);
    gridlines.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" class="grid-line" />`);
    yLabels.push(`<text x="${x0 - 8}" y="${(y + 4).toFixed(1)}" class="axis-text axis-text-y">${GRADE_RANKS[rank]}</text>`);
  }

  const xLabels = [];
  for (const d of xTicks(dmin, dmax)) {
    const x = dateToX(d, dmin, dmax, x0, x1);
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(d.getUTCDate()).padStart(2, '0');
    const yy = String(d.getUTCFullYear()).slice(-2);
    xLabels.push(`<text x="${x.toFixed(1)}" y="${y1 + 18}" class="axis-text axis-text-x">${mm}/${dd}/${yy}</text>`);
  }

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;
  const series = `<path d="${linePath}" fill="none" stroke="${LINE_COLOR}" stroke-width="2" />`;

  const svgInner = [...gridlines, frame, ...yLabels, ...xLabels, series].join('\n');
  // legendHtml empty — single-series chart.
  const html = htmlEnvelope({ title: META.title, svgW, svgH, svgInner, legendHtml: '' });
  return { html, svgInner };
}
