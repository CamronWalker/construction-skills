// 03-project-health.js — port of charts.py:render_project_health_index_over_time.

import {
  HTML_CARD_W, HTML_CARD_H,
  dateToX, xTicks, parseDate, markerSvg, htmlEnvelope, emptyHtml,
} from './svg-lib.js';

const LINE_COLOR  = '#2caffe';
const MARKER_GOOD = '#1AA462';
const MARKER_FINE = '#FFC000';
const MARKER_BAD  = '#D01010';
const GRID        = '#e6e6e6';

/**
 * @typedef {Array<{ dataDate: string, health: number, risk?: 'GOOD'|'FINE'|'BAD' }>} ProjectHealthPayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Project Health Index™ Over Time',
};

/** @param {string|undefined} risk @returns {string} */
function markerColor(risk) {
  if (risk === 'BAD')  return MARKER_BAD;
  if (risk === 'FINE') return MARKER_FINE;
  return MARKER_GOOD;
}

/**
 * @param {ProjectHealthPayload | { trend?: ProjectHealthPayload }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderProjectHealth(payload) {
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
      throw new TypeError('expected ProjectHealthPayload (array) or { trend: array }');
    }
  } else {
    throw new TypeError('expected ProjectHealthPayload (array) or { trend: array }');
  }

  const parsed = rows
    .filter(r => r && typeof r.health === 'number' && !Number.isNaN(r.health))
    .map(r => ({
      d:      parseDate(String(r.dataDate)),
      health: Number(r.health),
      risk:   r.risk,
    }));

  if (!parsed.length) {
    return { html: emptyHtml(META.title), svgInner: '' };
  }

  const svgW = 1692, svgH = 312;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const dmin = new Date(Math.min(...parsed.map(p => p.d.getTime())));
  const dmax = new Date(Math.max(...parsed.map(p => p.d.getTime())));

  // Auto-fit Y range with ~2% padding (matches Python charts.py).
  let healthMin = Math.min(...parsed.map(p => p.health));
  let healthMax = Math.max(...parsed.map(p => p.health));
  if (healthMin === healthMax) {
    healthMin = Math.max(0,   healthMin - 1);
    healthMax = Math.min(100, healthMax + 1);
  }
  const yPad = (healthMax - healthMin) * 0.02 || 1;
  const yMin = Math.max(0,   healthMin - yPad);
  const yMax = Math.min(100, healthMax + yPad);
  const ySpan = Math.max(1, yMax - yMin);
  /** @param {number} h @returns {number} */
  const healthToY = (h) => y1 - ((h - yMin) / ySpan) * (y1 - y0);

  /** @type {Array<[number, number]>} */
  const pts = parsed.map(p => [dateToX(p.d, dmin, dmax, x0, x1), healthToY(p.health)]);
  // Straight segments per Python reference.
  const linePath = 'M ' + pts.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(' L ');

  // ~5 horizontal gridlines covering the auto-fit range.
  const gridlines = [];
  const yLabels = [];
  for (let i = 0; i <= 4; i++) {
    const pct = yMin + (i / 4) * ySpan;
    const y = healthToY(pct);
    gridlines.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" class="grid-line" />`);
    yLabels.push(`<text x="${x0 - 8}" y="${(y + 4).toFixed(1)}" class="axis-text axis-text-y">${pct.toFixed(0)}</text>`);
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

  // Series: straight line first, then per-point circle markers color-coded by risk.
  const series = [
    `<path d="${linePath}" fill="none" stroke="${LINE_COLOR}" stroke-width="2" />`,
    ...pts.map(([x, y], i) => markerSvg('circle', x, y, markerColor(parsed[i].risk), 4)),
  ];

  const svgInner = [...gridlines, frame, ...yLabels, ...xLabels, ...series].join('\n');
  const html = htmlEnvelope({ title: META.title, svgW, svgH, svgInner, legendHtml: '' });
  return { html, svgInner };
}
