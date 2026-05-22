// svg-lib.js
// Card dimensions — matches the SmartPM web view exactly.
export const HTML_CARD_W = 1728;
export const HTML_CARD_H = 432;

// Palette constants from chart 01 (lifted into svg-lib because envelope CSS
// references them). Per-chart palettes live in their own files.
const PVA01_GRID       = '#e6e6e6';
const PVA01_AXIS_TEXT  = '#666';
const PVA01_TITLE_TEXT = '#181d27';

/**
 * @typedef {Object} RenderResult
 * @property {string} html      Self-contained HTML document.
 * @property {string} svgInner  The <g> contents — for embedding in another doc.
 *                              Empty string for composite renderers.
 */

/**
 * @template [T=any]
 * @typedef {(payload: T) => RenderResult} RenderFn
 */

/** @typedef {'circle'|'square'|'diamond'|'triangle'|'invtri'} MarkerKind */

/** @param {string} s @returns {string} */
export function escapeHtml(s) {
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

/**
 * @param {Date} d @param {Date} dmin @param {Date} dmax @param {number} x0 @param {number} x1
 * @returns {number}
 */
export function dateToX(d, dmin, dmax, x0, x1) {
  const span = Math.max(1, Math.floor((dmax.getTime() - dmin.getTime()) / 86400000));
  const offset = Math.floor((d.getTime() - dmin.getTime()) / 86400000);
  return x0 + (offset / span) * (x1 - x0);
}

/** @param {number} p @param {number} y0 @param {number} y1 @returns {number} */
export function pctToY(p, y0, y1) {
  const clamped = Math.max(0, Math.min(100, p));
  return y1 - (clamped / 100) * (y1 - y0);
}

/** @param {Array<[number, number]>} pts @returns {string} */
export function smoothPath(pts) {
  if (!pts.length) return '';
  if (pts.length === 1) {
    const [x, y] = pts[0];
    return `M ${x.toFixed(2)},${y.toFixed(2)}`;
  }
  if (pts.length === 2) {
    const [[x0, y0], [x1, y1]] = pts;
    return `M ${x0.toFixed(2)},${y0.toFixed(2)} L ${x1.toFixed(2)},${y1.toFixed(2)}`;
  }
  const out = [`M ${pts[0][0].toFixed(2)},${pts[0][1].toFixed(2)}`];
  const n = pts.length;
  for (let i = 0; i < n - 1; i++) {
    const p0 = pts[i - 1] ?? pts[i];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[i + 2] ?? p2;
    const c1x = p1[0] + (p2[0] - p0[0]) / 6;
    const c1y = p1[1] + (p2[1] - p0[1]) / 6;
    const c2x = p2[0] - (p3[0] - p1[0]) / 6;
    const c2y = p2[1] - (p3[1] - p1[1]) / 6;
    out.push(
      `C ${c1x.toFixed(2)},${c1y.toFixed(2)} ` +
      `${c2x.toFixed(2)},${c2y.toFixed(2)} ` +
      `${p2[0].toFixed(2)},${p2[1].toFixed(2)}`
    );
  }
  return out.join(' ');
}

/** @param {Date} dmin @param {Date} dmax @param {number} [maxTicks=10] @returns {Date[]} */
export function xTicks(dmin, dmax, maxTicks = 10) {
  const spanDays = Math.max(1, Math.floor((dmax.getTime() - dmin.getTime()) / 86400000));
  const candidates = [7, 14, 30, 60, 90, 180, 365];
  let stride = 365;
  for (const c of candidates) {
    if (spanDays / Math.max(c, 1) <= maxTicks) { stride = c; break; }
  }
  /** @type {Date[]} */
  const ticks = [];
  let d = new Date(dmin.getTime());
  while (d.getTime() <= dmax.getTime()) {
    ticks.push(new Date(d.getTime()));
    d = new Date(d.getTime() + stride * 86400000);
  }
  if (ticks[ticks.length - 1].getTime() !== dmax.getTime()) ticks.push(new Date(dmax.getTime()));
  return ticks;
}

/**
 * @param {Array<Record<string, unknown>>} rows
 * @param {string} field
 * @param {Date} dmin @param {Date} dmax
 * @param {number} x0 @param {number} x1 @param {number} y0 @param {number} y1
 * @returns {Array<[number, number]>}
 */
export function seriesPts(rows, field, dmin, dmax, x0, x1, y0, y1) {
  /** @type {Array<[number, number]>} */
  const out = [];
  for (const r of rows) {
    const v = r[field];
    if (v === null || v === undefined) continue;
    const d = new Date(`${String(r.DATE)}T00:00:00Z`);
    out.push([dateToX(d, dmin, dmax, x0, x1), pctToY(Number(v), y0, y1)]);
  }
  return out;
}

/**
 * @param {MarkerKind} kind @param {number} x @param {number} y @param {string} color @param {number} [size=4]
 * @returns {string}
 */
export function markerSvg(kind, x, y, color, size = 4) {
  if (kind === 'circle') {
    return `<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="${size}" fill="${color}" stroke="none" />`;
  }
  if (kind === 'square') {
    const s = size;
    return `<rect x="${(x - s).toFixed(2)}" y="${(y - s).toFixed(2)}" width="${s * 2}" height="${s * 2}" fill="${color}" />`;
  }
  if (kind === 'diamond') {
    const s = size + 1;
    return `<polygon points="${x.toFixed(2)},${(y - s).toFixed(2)} ${(x + s).toFixed(2)},${y.toFixed(2)} ${x.toFixed(2)},${(y + s).toFixed(2)} ${(x - s).toFixed(2)},${y.toFixed(2)}" fill="${color}" />`;
  }
  if (kind === 'triangle') {
    const s = size + 1;
    return `<polygon points="${x.toFixed(2)},${(y - s).toFixed(2)} ${(x + s).toFixed(2)},${(y + s).toFixed(2)} ${(x - s).toFixed(2)},${(y + s).toFixed(2)}" fill="${color}" />`;
  }
  if (kind === 'invtri') {
    const s = size + 1;
    return `<polygon points="${x.toFixed(2)},${(y + s).toFixed(2)} ${(x + s).toFixed(2)},${(y - s).toFixed(2)} ${(x - s).toFixed(2)},${(y - s).toFixed(2)}" fill="${color}" />`;
  }
  return '';
}

/**
 * @param {MarkerKind | 'area'} kind @param {string} color @param {string} dash @param {string} label
 * @returns {string}
 */
export function legendItem(kind, color, dash, label) {
  const labelEsc = escapeHtml(label);
  if (kind === 'area') {
    const swatch =
      '<svg width="22" height="10" viewBox="0 0 22 10">' +
      `<rect x="0" y="0" width="22" height="10" fill="${color}" ` +
      `fill-opacity="0.2" stroke="${color}" stroke-width="1" />` +
      '</svg>';
    return `<span class="legend-item">${swatch}<span class="legend-label">${labelEsc}</span></span>`;
  }
  const dashAttr = dash ? ` stroke-dasharray="${dash}"` : '';
  const swatch =
    '<svg width="26" height="10" viewBox="0 0 26 10">' +
    `<line x1="0" y1="5" x2="26" y2="5" stroke="${color}" stroke-width="2"${dashAttr} />` +
    markerSvg(/** @type {MarkerKind} */ (kind), 13, 5, color, 4) +
    '</svg>';
  return `<span class="legend-item">${swatch}<span class="legend-label">${labelEsc}</span></span>`;
}

/**
 * @param {{ title: string, svgW: number, svgH: number, svgInner: string,
 *           legendHtml: string, cardW?: number, cardH?: number }} opts
 * @returns {string}
 */
export function htmlEnvelope({ title, svgW, svgH, svgInner, legendHtml, cardW = HTML_CARD_W, cardH = HTML_CARD_H }) {
  const titleEsc = escapeHtml(title);
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${titleEsc}</title>
<style>
  html, body { margin: 0; padding: 0; background: #ffffff; font-family: Inter, "Helvetica Neue", Arial, sans-serif; color: ${PVA01_TITLE_TEXT}; -webkit-font-smoothing: antialiased; }
  .chart-card { width: ${cardW}px; height: ${cardH}px; box-sizing: border-box; background: #ffffff; border-radius: 12px; padding: 14px 18px 8px; display: flex; flex-direction: column; }
  .chart-title { font-size: 14px; font-weight: 600; color: ${PVA01_TITLE_TEXT}; margin: 0 0 6px 0; line-height: 1.1; }
  .chart-svg { display: block; flex: 0 0 auto; }
  .axis-text { font-size: 11px; fill: ${PVA01_AXIS_TEXT}; }
  .axis-text-y { text-anchor: end; }
  .axis-text-x { text-anchor: middle; }
  .axis-title-text { font-size: 12px; fill: ${PVA01_AXIS_TEXT}; text-anchor: middle; }
  .grid-line { stroke: ${PVA01_GRID}; stroke-width: 1; stroke-dasharray: 2,3; }
  .legend-row { display: flex; flex-wrap: wrap; justify-content: center; align-items: center; gap: 6px 18px; font-size: 11px; color: ${PVA01_TITLE_TEXT}; padding-top: 6px; }
  .legend-item { display: inline-flex; align-items: center; gap: 6px; white-space: nowrap; }
  .legend-label { line-height: 1; }
</style>
</head>
<body>
<div class="chart-card">
  <h3 class="chart-title">${titleEsc}</h3>
  <svg class="chart-svg" width="${svgW}" height="${svgH}" viewBox="0 0 ${svgW} ${svgH}" xmlns="http://www.w3.org/2000/svg">
${svgInner}
  </svg>
  <div class="legend-row">
${legendHtml}
  </div>
</div>
</body>
</html>
`;
}

/** @param {string} title @returns {string} */
export function emptyHtml(title) {
  const titleEsc = escapeHtml(title);
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>${titleEsc}</title>
<style>
  html, body { margin: 0; padding: 0; background: #fff; font-family: Inter, sans-serif; color: ${PVA01_TITLE_TEXT}; }
  .chart-card { width: ${HTML_CARD_W}px; height: ${HTML_CARD_H}px; box-sizing: border-box; padding: 14px 18px 8px; display: flex; align-items: center; justify-content: center; }
  .chart-title { font-size: 14px; font-weight: 600; }
</style></head><body>
<div class="chart-card"><h3 class="chart-title">${titleEsc} — no data</h3></div>
</body></html>
`;
}

