// meta.js — slug → { svgWidth, svgHeight, title } map + the placeholder renderer.
// Aggregates per-chart META exports for use by renderPlaceholder and by external
// consumers that need chart dimensions without invoking a renderer.
// At commit 1 the registry is empty; per-chart META imports get added as charts land.

import { htmlEnvelope, escapeHtml } from './svg-lib.js';

/** @type {Record<string, { svgWidth: number, svgHeight: number, title: string }>} */
export const CHART_META = {};

/**
 * Render a placeholder card matching the dimensions of the real chart for `slug`.
 *
 * @param {string} slug
 * @param {{ message?: string, icon?: 'clock'|'warn'|'none' }} [opts]
 * @returns {import('./svg-lib.js').RenderResult}
 * @throws {Error} unknown slug.
 */
export function renderPlaceholder(slug, opts = {}) {
  const meta = CHART_META[slug];
  if (!meta) throw new Error(`unknown slug "${slug}"`);
  const { svgWidth, svgHeight, title } = meta;
  const message = opts.message ?? 'Data not yet available';
  const icon = opts.icon ?? 'clock';
  const iconSvg = iconGlyph(icon, svgWidth / 2, svgHeight / 2 - 20);
  const svgInner =
    `<g>` +
    iconSvg +
    `<text x="${svgWidth / 2}" y="${svgHeight / 2 + 30}" text-anchor="middle" class="axis-text" font-size="16">${escapeHtml(message)}</text>` +
    `</g>`;
  const html = htmlEnvelope({ title, svgW: svgWidth, svgH: svgHeight, svgInner, legendHtml: '' });
  return { html, svgInner };
}

/** @param {'clock'|'warn'|'none'} icon @param {number} cx @param {number} cy @returns {string} */
function iconGlyph(icon, cx, cy) {
  if (icon === 'none') return '';
  if (icon === 'warn') {
    return `<polygon points="${cx},${cy - 14} ${cx + 14},${cy + 10} ${cx - 14},${cy + 10}" fill="#FFC000" stroke="#181d27" stroke-width="1" />` +
           `<text x="${cx}" y="${cy + 6}" text-anchor="middle" font-size="18" font-weight="700" fill="#181d27">!</text>`;
  }
  return `<circle cx="${cx}" cy="${cy}" r="14" fill="none" stroke="#666" stroke-width="2" />` +
         `<line x1="${cx}" y1="${cy}" x2="${cx}" y2="${cy - 9}" stroke="#666" stroke-width="2" />` +
         `<line x1="${cx}" y1="${cy}" x2="${cx + 7}" y2="${cy}" stroke="#666" stroke-width="2" />`;
}
