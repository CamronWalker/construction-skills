// 06-end-date-variance.js — End Date Variance.
//
// Variance = sourceEndDate - contractual_completion (in days), plotted per
// scenario data-date. Categorical X axis (each data date gets equal spacing,
// regardless of wall-clock gap), with a zero-line splitting the plot into a
// pink "behind" region above and a light-green "ahead" region below. The
// trend line and markers switch color at the boundary (red above, green at
// or below — Highcharts-zone semantics). Each point carries a colored pill
// label showing the projected end date.
//
// Palette / typography / layout captured live from SmartPM's DOM
// (project 113385, scenario 1644, milestone 1644) on 2026-05-28. SmartPM
// uses Highcharts under the hood; the wide-SVG categorical layout, exact
// zone colors, pill styling (Inter 700 11.2 px, 3 px padding, 3 px radius,
// 20 % alpha background) are all lifted directly from `getComputedStyle()`
// readings of the live elements rather than approximated.

import {
  HTML_CARD_W, HTML_CARD_H,
  parseDate, htmlEnvelope, emptyHtml, legendItem,
} from './svg-lib.js';

// --- Palette (captured live from SmartPM DOM 2026-05-28) -------------------
const ZERO_LINE      = '#1476b7';                       // plot line stroke
const TREND_RED      = '#b00020';                       // line above zero
const TREND_GREEN    = '#388543';                       // line at/below zero
const SHADE_RED      = 'rgba(176, 0, 32, 0.0375)';      // plot band above
const SHADE_GREEN    = 'rgba(20, 118, 75, 0.0375)';     // plot band below
const PILL_RED_BG    = 'rgba(176, 0, 32, 0.2)';
const PILL_RED_TXT   = '#b00020';
const PILL_GREEN_BG  = 'rgba(56, 133, 67, 0.2)';
const PILL_GREEN_TXT = '#388543';
const GRID           = '#e6e6e6';
const AXIS_LABEL_TXT = '#333333';
const LEGEND_SWATCH  = '#2caffe';                       // SmartPM brand blue

const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

// SmartPM's live chart shows roughly the most recent ~3 months of weekly
// data dates by default (wider history is reachable via the horizontal
// scrollbar in their web UI). For the static PNG embedded in the weekly
// email, mirror that: show the most recent N data dates.
const WINDOW = 13;

/**
 * @typedef {{ dataDate: string, sourceEndDate: string }} EndDateUpdate
 * @typedef {{ updates: Array<EndDateUpdate>, contractual_completion?: string }} EndDateVariancePayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'End Date Variance',
};

/**
 * @param {EndDateVariancePayload | Array<EndDateUpdate>} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderEndDateVariance(payload) {
  /** @type {Array<EndDateUpdate>} */
  let updates;
  /** @type {string | undefined} */
  let contractualISO;
  if (Array.isArray(payload)) {
    updates = payload;
    contractualISO = undefined;
  } else if (payload && typeof payload === 'object') {
    const envelope = /** @type {any} */ (payload).updates;
    if (envelope === undefined || envelope === null) {
      updates = [];
    } else if (Array.isArray(envelope)) {
      updates = envelope;
    } else {
      throw new TypeError('expected EndDateVariancePayload ({ updates: array }) or array');
    }
    contractualISO = /** @type {any} */ (payload).contractual_completion;
  } else {
    throw new TypeError('expected EndDateVariancePayload ({ updates: array }) or array');
  }

  if (!updates.length) return { html: emptyHtml(META.title), svgInner: '' };

  // Sort by data date ascending so the window slice and X-axis order are
  // deterministic regardless of input order.
  const sorted = [...updates]
    .filter(r => r && r.dataDate && r.sourceEndDate)
    .sort((a, b) => parseDate(a.dataDate).getTime() - parseDate(b.dataDate).getTime());

  if (!sorted.length) return { html: emptyHtml(META.title), svgInner: '' };

  // Baseline = contractual_completion if provided (the field SmartPM exposes
  // for this chart). Fall back to the earliest sourceEndDate when the
  // envelope lacks it, so historic / synthetic payloads still render with a
  // valid zero line (variance will read as 0 at the first data point).
  const baselineMs = contractualISO
    ? parseDate(contractualISO).getTime()
    : parseDate(sorted[0].sourceEndDate).getTime();

  const all = sorted.map(r => ({
    d:   parseDate(r.dataDate),
    end: parseDate(r.sourceEndDate),
    v:   Math.round((parseDate(r.sourceEndDate).getTime() - baselineMs) / 86400000),
  }));
  const rows = all.slice(-WINDOW);

  // --- Layout --------------------------------------------------------------
  // SmartPM's live SVG is 4900×400 (huge horizontal scroll). For the email
  // PNG we use the narrower card width while matching their plot height.
  const svgW = 1692, svgH = 400;
  const padT = 14, padR = 32, padB = 36, padL = 64;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  // Categorical X: each data date occupies one slot of width
  // (x1 - x0) / (rows.length - 1). Confirmed against SmartPM's live SVG
  // path data — consecutive points were 172.14 px apart regardless of
  // wall-clock gap between their dataDates.
  const indexToX = (i) =>
    rows.length <= 1 ? (x0 + x1) / 2 : x0 + (i / (rows.length - 1)) * (x1 - x0);

  // Y range — include zero plus 18 % padding around observed extrema. Floor
  // the span at 50 days so a tight window doesn't compress the plot.
  const vRaw = rows.map(r => r.v);
  let vMin = Math.min(0, ...vRaw);
  let vMax = Math.max(0, ...vRaw);
  let span = Math.max(50, vMax - vMin);
  const padV = span * 0.18;
  vMin -= padV;
  vMax += padV;
  span = vMax - vMin;
  /** @param {number} v @returns {number} */
  const valueToY = (v) => y1 - ((v - vMin) / span) * (y1 - y0);
  const yZero = valueToY(0);

  // --- Gridlines / Y-axis ticks -------------------------------------------
  const tickStep = pickTickStep(span);
  const yTicks = [];
  let t = Math.ceil(vMin / tickStep) * tickStep;
  while (t <= vMax + 0.5) { yTicks.push(t); t += tickStep; }

  const gridlines = yTicks.map(v => {
    const y = valueToY(v);
    return `<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" stroke="${GRID}" stroke-width="1" />`;
  });
  const yLabels = yTicks.map(v => {
    const y = valueToY(v);
    return `<text x="${x0 - 10}" y="${(y + 4).toFixed(1)}" font-family="Inter, sans-serif" font-size="12.8" fill="${AXIS_LABEL_TXT}" text-anchor="end">${v}</text>`;
  });

  // --- X-axis tick labels (one per data point) ----------------------------
  const xLabels = rows.map((r, i) => {
    const x = indexToX(i);
    const mon = MONTHS[r.d.getUTCMonth()];
    const dd  = String(r.d.getUTCDate()).padStart(2, '0');
    const yyyy = r.d.getUTCFullYear();
    return `<text x="${x.toFixed(1)}" y="${y1 + 20}" font-family="Inter, sans-serif" font-size="12.8" fill="${AXIS_LABEL_TXT}" text-anchor="middle">${mon} ${dd}, ${yyyy}</text>`;
  });

  // --- Pink-above / green-below plot bands + zero line --------------------
  const shadeAbove = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${(yZero - y0).toFixed(1)}" fill="${SHADE_RED}" />`;
  const shadeBelow = `<rect x="${x0}" y="${yZero.toFixed(1)}" width="${x1 - x0}" height="${(y1 - yZero).toFixed(1)}" fill="${SHADE_GREEN}" />`;
  const zeroLine   = `<line x1="${x0}" y1="${yZero.toFixed(1)}" x2="${x1}" y2="${yZero.toFixed(1)}" stroke="${ZERO_LINE}" stroke-width="2" />`;
  const frame      = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${GRID}" stroke-width="1" />`;

  // --- Trend line, segment-split at zero crossings ------------------------
  const pts = rows.map((r, i) => ({
    x: indexToX(i),
    y: valueToY(r.v),
    v: r.v,
  }));

  const segs = [];
  for (let i = 0; i < pts.length - 1; i++) {
    const a = pts[i];
    const b = pts[i + 1];
    const sameSide = (a.v > 0) === (b.v > 0);
    if (sameSide) {
      segs.push({ pts: [a, b], color: a.v > 0 ? TREND_RED : TREND_GREEN });
    } else {
      const tFrac = a.v / (a.v - b.v);
      const xc = a.x + (b.x - a.x) * tFrac;
      const mid = { x: xc, y: yZero, v: 0 };
      segs.push({ pts: [a, mid], color: a.v > 0 ? TREND_RED : TREND_GREEN });
      segs.push({ pts: [mid, b], color: b.v > 0 ? TREND_RED : TREND_GREEN });
    }
  }
  const lineSegs = segs.map(({ pts: [p, q], color }) =>
    `<line x1="${p.x.toFixed(2)}" y1="${p.y.toFixed(2)}" x2="${q.x.toFixed(2)}" y2="${q.y.toFixed(2)}" stroke="${color}" stroke-width="2" />`
  );

  const markers = pts.map(({ x, y, v }) => {
    const color = v > 0 ? TREND_RED : TREND_GREEN;
    return `<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="4" fill="${color}" />`;
  });

  // --- Pill labels (projected end date at each point) ---------------------
  const pills = rows.map((r, i) => {
    const { x, y } = pts[i];
    const isBehind = r.v > 0;
    const bg = isBehind ? PILL_RED_BG  : PILL_GREEN_BG;
    const fg = isBehind ? PILL_RED_TXT : PILL_GREEN_TXT;
    const mon = MONTHS[r.end.getUTCMonth()];
    const dd  = String(r.end.getUTCDate()).padStart(2, '0');
    const yyyy = r.end.getUTCFullYear();
    const label = `${mon} ${dd}, ${yyyy}`;
    // Bold Inter 11.2 px averages ~7 px/char. 6 px horizontal padding (3 each side).
    const textW = label.length * 7.0 + 6;
    const textH = 18;
    // Behind points sit in the red zone → pill above; ahead points → below.
    const dy = isBehind ? -18 : 16;
    const px = x - textW / 2;
    const py = y + dy - textH / 2;
    return `<g>` +
      `<rect x="${px.toFixed(1)}" y="${py.toFixed(1)}" width="${textW.toFixed(1)}" height="${textH}" rx="3" ry="3" fill="${bg}" />` +
      `<text x="${x.toFixed(1)}" y="${(py + 13).toFixed(1)}" text-anchor="middle" font-family="Inter, sans-serif" font-size="11.2" font-weight="700" fill="${fg}">${label}</text>` +
      `</g>`;
  });

  const svgInner = [
    shadeAbove,
    shadeBelow,
    ...gridlines,
    zeroLine,
    frame,
    ...yLabels,
    ...xLabels,
    ...lineSegs,
    ...markers,
    ...pills,
  ].join('\n');

  // Legend swatch is SmartPM's neutral brand blue (their hidden Highcharts
  // base series path uses #2caffe before the zone overlays).
  const legendHtml = legendItem('circle', LEGEND_SWATCH, '', 'End Date Variance');

  const html = htmlEnvelope({
    title: META.title,
    svgW, svgH,
    svgInner,
    legendHtml,
  });
  return { html, svgInner };
}

/** @param {number} span @returns {number} */
function pickTickStep(span) {
  const candidates = [10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000];
  for (const c of candidates) {
    if (span / c <= 6) return c;
  }
  return 5000;
}
