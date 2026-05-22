// 01-planned-vs-actual.js — port of charts.py:render_planned_vs_actual_percent_complete.

import {
  HTML_CARD_W, HTML_CARD_H,
  dateToX, pctToY, smoothPath, xTicks, seriesPts,
  markerSvg, legendItem, htmlEnvelope, emptyHtml,
} from './svg-lib.js';

// Palette — copied verbatim from charts.py:1316-1325. Each value came from a
// <path stroke="..."> attribute in SmartPM's Highcharts SVG via Chrome MCP
// DOM inspection on 2026-05-21 (SGRWRF trends page).
const PROGRESS_TARGET_FILL = '#808080';
const LATE_DATE_PLANNED    = '#b00020';
const BASELINE_PLANNED     = '#2caffe';
const ACTUAL               = '#1476b7';
const SCHEDULED_COMPLETION = '#388543';
const EARLY_DATE_PLANNED   = '#388543';
const DATA_DATE_LINE       = '#cccccc';
const GRID                 = '#e6e6e6';

/**
 * @typedef {Object} PlannedVsActualPayload
 * @property {Record<string, string>} [percentCompleteTypes]
 * @property {Array<{
 *   DATE: string,
 *   LATE_DATE_PLANNED: number|null,
 *   BASELINE_PLANNED:  number|null,
 *   ACTUAL:            number|null,
 *   SCHEDULED:         number|null,
 *   PLANNED:           number|null,
 * }>} data
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Planned VS Actual Percent Complete',
};

/**
 * @param {PlannedVsActualPayload} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderPlannedVsActual(payload) {
  if (!payload || typeof payload !== 'object') {
    throw new TypeError('expected payload object');
  }
  if (payload.data !== null && payload.data !== undefined && !Array.isArray(payload.data)) {
    throw new TypeError('expected payload.data to be an array');
  }
  const rows = Array.isArray(payload.data) ? payload.data : [];
  const types = payload.percentCompleteTypes ?? {};

  if (!rows.length) {
    return { html: emptyHtml(META.title), svgInner: '' };
  }

  const svgW = 1692, svgH = 312;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  /** @type {Date[]} */
  const dates = rows.map(r => new Date(`${r.DATE}T00:00:00Z`));
  const dmin = new Date(Math.min(...dates.map(d => d.getTime())));
  const dmax = new Date(Math.max(...dates.map(d => d.getTime())));

  /** @type {Date|null} */
  let dataDate = null;
  for (const r of rows) {
    if (r.ACTUAL !== null && r.ACTUAL !== undefined) {
      dataDate = new Date(`${r.DATE}T00:00:00Z`);
    }
  }

  const ptsLate  = seriesPts(rows, 'LATE_DATE_PLANNED', dmin, dmax, x0, x1, y0, y1);
  const ptsBase  = seriesPts(rows, 'BASELINE_PLANNED',  dmin, dmax, x0, x1, y0, y1);
  const ptsAct   = seriesPts(rows, 'ACTUAL',            dmin, dmax, x0, x1, y0, y1);
  const ptsSched = seriesPts(rows, 'SCHEDULED',         dmin, dmax, x0, x1, y0, y1);
  const ptsEarly = seriesPts(rows, 'PLANNED',           dmin, dmax, x0, x1, y0, y1);

  /** @type {Array<[number, number]>} */
  const bandTop = [];
  /** @type {Array<[number, number]>} */
  const bandBot = [];
  for (const r of rows) {
    if (r.BASELINE_PLANNED === null || r.LATE_DATE_PLANNED === null) continue;
    const d = new Date(`${r.DATE}T00:00:00Z`);
    const x = dateToX(d, dmin, dmax, x0, x1);
    bandTop.push([x, pctToY(Number(r.BASELINE_PLANNED), y0, y1)]);
    bandBot.push([x, pctToY(Number(r.LATE_DATE_PLANNED), y0, y1)]);
  }
  let bandPath = '';
  if (bandTop.length) {
    const topStr = bandTop.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L ');
    const botStr = [...bandBot].reverse().map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L ');
    bandPath = `M ${topStr} L ${botStr} Z`;
  }

  const gridlines = [];
  const yLabels = [];
  for (const pct of [0, 25, 50, 75, 100]) {
    const y = pctToY(pct, y0, y1);
    gridlines.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" class="grid-line" />`);
    yLabels.push(`<text x="${x0 - 8}" y="${(y + 4).toFixed(1)}" class="axis-text axis-text-y">${pct} %</text>`);
  }

  const xLabels = [];
  for (const d of xTicks(dmin, dmax)) {
    const x = dateToX(d, dmin, dmax, x0, x1);
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(d.getUTCDate()).padStart(2, '0');
    const yy = String(d.getUTCFullYear()).slice(-2);
    xLabels.push(`<text x="${x.toFixed(1)}" y="${y1 + 18}" class="axis-text axis-text-x">${mm}/${dd}/${yy}</text>`);
  }

  let plotLine = '';
  if (dataDate) {
    const dx = dateToX(dataDate, dmin, dmax, x0, x1);
    plotLine = `<line x1="${dx.toFixed(1)}" y1="${y0}" x2="${dx.toFixed(1)}" y2="${y1}" stroke="${DATA_DATE_LINE}" stroke-width="2" stroke-dasharray="8,6" />`;
  }

  /** @param {Array<[number, number]>} pts @param {string} color @param {import('./svg-lib.js').MarkerKind} kind */
  const markers = (pts, color, kind) => pts.map(([x, y]) => markerSvg(kind, x, y, color, 4)).join('\n');

  const seriesSvg = [];
  if (bandPath) {
    seriesSvg.push(`<path d="${bandPath}" fill="${PROGRESS_TARGET_FILL}" fill-opacity="0.2" stroke="none" />`);
  }
  if (plotLine) seriesSvg.push(plotLine);
  if (ptsLate.length) {
    seriesSvg.push(`<path d="${smoothPath(ptsLate)}" fill="none" stroke="${LATE_DATE_PLANNED}" stroke-width="2" />`);
    seriesSvg.push(markers(ptsLate, LATE_DATE_PLANNED, 'diamond'));
  }
  if (ptsBase.length) {
    seriesSvg.push(`<path d="${smoothPath(ptsBase)}" fill="none" stroke="${BASELINE_PLANNED}" stroke-width="2" />`);
    seriesSvg.push(markers(ptsBase, BASELINE_PLANNED, 'square'));
  }
  if (ptsAct.length) {
    seriesSvg.push(`<path d="${smoothPath(ptsAct)}" fill="none" stroke="${ACTUAL}" stroke-width="2" />`);
    seriesSvg.push(markers(ptsAct, ACTUAL, 'triangle'));
  }
  if (ptsEarly.length) {
    seriesSvg.push(`<path d="${smoothPath(ptsEarly)}" fill="none" stroke="${EARLY_DATE_PLANNED}" stroke-width="2" />`);
    seriesSvg.push(markers(ptsEarly, EARLY_DATE_PLANNED, 'circle'));
  }
  if (ptsSched.length) {
    seriesSvg.push(`<path d="${smoothPath(ptsSched)}" fill="none" stroke="${SCHEDULED_COMPLETION}" stroke-width="2" stroke-dasharray="8,6" />`);
    seriesSvg.push(markers(ptsSched, SCHEDULED_COMPLETION, 'invtri'));
  }

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;
  const yAxisTitle = `<text x="${x0 - 40}" y="${((y0 + y1) / 2).toFixed(1)}" transform="rotate(-90 ${x0 - 40} ${((y0 + y1) / 2).toFixed(1)})" class="axis-title-text">Values</text>`;

  const svgInner = [
    ...gridlines, frame, ...yLabels, ...xLabels, yAxisTitle, ...seriesSvg,
  ].join('\n');

  /** @type {Array<[import('./svg-lib.js').MarkerKind | 'area', string, string, string]>} */
  const legendItems = [
    ['area',     PROGRESS_TARGET_FILL, '',    'Progress Target'],
    ['diamond',  LATE_DATE_PLANNED,    '',    types.LATE_DATE_PLANNED ?? 'Late Date Planned'],
    ['square',   BASELINE_PLANNED,     '',    types.BASELINE_PLANNED  ?? 'Planned (All Schedules)'],
    ['triangle', ACTUAL,               '',    types.ACTUAL            ?? 'Actual'],
    ['invtri',   SCHEDULED_COMPLETION, '8,6', types.SCHEDULED         ?? 'Scheduled Completion'],
    ['circle',   EARLY_DATE_PLANNED,   '',    types.PLANNED           ?? 'Early Date Planned'],
  ];
  const legendHtml = legendItems.map(([kind, color, dash, label]) =>
    legendItem(kind, color, dash, label)
  ).join('\n');

  const html = htmlEnvelope({ title: META.title, svgW, svgH, svgInner, legendHtml });
  return { html, svgInner };
}
