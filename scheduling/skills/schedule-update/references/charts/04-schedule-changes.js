// 04-schedule-changes.js — port of charts.py:render_schedule_changes_over_time
// (lines 2092-2246).

import {
  HTML_CARD_W, HTML_CARD_H,
  dateToX, smoothPath, xTicks, parseDate,
  legendItem, htmlEnvelope, emptyHtml,
} from './svg-lib.js';

// Palette from charts.py:2071-2077 (Chrome MCP DOM inspection 2026-05-21).
const CRITICAL_CHANGES      = '#D01010';
const NEAR_CRITICAL_CHANGES = '#FFC000';
const ACTIVITY_CHANGES      = '#1AA462';
const LOGIC_CHANGES         = '#0000FF';
const CALENDAR_CHANGES      = '#2196F3';
const DURATION_CHANGES      = '#1476B7';
const DELAYED_ACTIVITY      = '#DB495B';
const GRID                  = '#e6e6e6';

// MCP field name (inside metrics{}) → label + color. PascalCase as returned
// by smartpm_get_scenario_change_log_summary. Order matches SmartPM's legend.
const SPLINE_SERIES = [
  { field: 'CriticalChanges',         label: 'Critical Changes',          color: CRITICAL_CHANGES      },
  { field: 'NearCriticalChanges',     label: 'Near Critical Changes',     color: NEAR_CRITICAL_CHANGES },
  { field: 'ActivityChanges',         label: 'Activity Changes',          color: ACTIVITY_CHANGES      },
  { field: 'LogicChanges',            label: 'Logic Changes',             color: LOGIC_CHANGES         },
  { field: 'CalendarChanges',         label: 'Calendar Changes',          color: CALENDAR_CHANGES      },
  { field: 'DurationChanges',         label: 'Duration Changes',          color: DURATION_CHANGES      },
  { field: 'DelayedActivityChanges',  label: 'Delayed Activity Changes',  color: DELAYED_ACTIVITY      },
];

/**
 * @typedef {Array<{ dataDate: string, metrics: Record<string, number> }>} ScheduleChangesPayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Schedule Changes Over Time',
};

/**
 * @param {ScheduleChangesPayload | { summary?: ScheduleChangesPayload, trend?: ScheduleChangesPayload }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderScheduleChanges(payload) {
  let rows;
  if (Array.isArray(payload)) {
    rows = payload;
  } else if (payload && typeof payload === 'object') {
    const summary = /** @type {any} */ (payload).summary;
    const trend = /** @type {any} */ (payload).trend;
    if (Array.isArray(summary)) {
      rows = summary;
    } else if (Array.isArray(trend)) {
      rows = trend;
    } else if (summary === undefined && trend === undefined) {
      rows = [];
    } else {
      throw new TypeError('expected ScheduleChangesPayload (array) or { summary: array, trend: array }');
    }
  } else {
    throw new TypeError('expected ScheduleChangesPayload (array) or { summary: array, trend: array }');
  }

  if (!rows.length) return { html: emptyHtml(META.title), svgInner: '' };

  const svgW = 1692, svgH = 312;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const dates = rows.map(r => parseDate(String(r.dataDate)));
  const dmin = new Date(Math.min(...dates.map(d => d.getTime())));
  const dmax = new Date(Math.max(...dates.map(d => d.getTime())));

  // Y range: 0 to nice-tick ceiling of max observed value across all 7 series.
  const allValues = [];
  for (const r of rows) {
    const m = r.metrics ?? {};
    for (const { field } of SPLINE_SERIES) {
      const v = m[field];
      if (v !== null && v !== undefined) allValues.push(Number(v));
    }
  }
  let yMax, tickStep;
  if (!allValues.length || Math.max(...allValues) === 0) {
    yMax = 10; tickStep = 2;
  } else {
    const rawMax = Math.max(...allValues) * 1.1;
    if      (rawMax > 100) tickStep = 25;
    else if (rawMax > 40)  tickStep = 10;
    else if (rawMax > 15)  tickStep = 5;
    else if (rawMax > 6)   tickStep = 2;
    else                   tickStep = 1;
    yMax = Math.ceil(rawMax / tickStep) * tickStep;
  }
  /** @param {number} v @returns {number} */
  const valueToY = (v) => y1 - (Number(v) / yMax) * (y1 - y0);

  const gridlines = [];
  const yLabels = [];
  for (let tick = 0; tick <= yMax; tick += tickStep) {
    const y = valueToY(tick);
    gridlines.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" class="grid-line" />`);
    yLabels.push(`<text x="${x0 - 8}" y="${(y + 4).toFixed(1)}" class="axis-text axis-text-y">${tick}</text>`);
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

  // 7 smoothed spline lines, one per change category.
  const seriesSvg = [];
  for (const { field, color } of SPLINE_SERIES) {
    /** @type {Array<[number, number]>} */
    const pts = [];
    for (const r of rows) {
      const v = r.metrics?.[field];
      if (v === null || v === undefined) continue;
      const d = parseDate(String(r.dataDate));
      pts.push([dateToX(d, dmin, dmax, x0, x1), valueToY(Number(v))]);
    }
    if (!pts.length) continue;
    seriesSvg.push(`<path d="${smoothPath(pts)}" fill="none" stroke="${color}" stroke-width="2" />`);
  }

  const svgInner = [...gridlines, frame, ...yLabels, ...xLabels, ...seriesSvg].join('\n');
  const legendHtml = SPLINE_SERIES.map(({ label, color }) =>
    legendItem('circle', color, '', label)
  ).join('\n');
  const html = htmlEnvelope({ title: META.title, svgW, svgH, svgInner, legendHtml });
  return { html, svgInner };
}
