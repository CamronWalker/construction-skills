// meta.js — slug → { svgWidth, svgHeight, title } map + the placeholder renderer.
// Aggregates per-chart META exports for use by renderPlaceholder and by external
// consumers that need chart dimensions without invoking a renderer.
// At commit 1 the registry is empty; per-chart META imports get added as charts land.

import { htmlEnvelope, escapeHtml } from './svg-lib.js';
import { META as META01 } from './01-planned-vs-actual.js';
import { META as META02 } from './02-schedule-quality.js';
import { META as META03 } from './03-project-health.js';
import { META as META04 } from './04-schedule-changes.js';
import { META as META05 } from './05-schedule-delay.js';
import { META as META06 } from './06-end-date-variance.js';
import { META as META07 } from './07-schedule-compression.js';
import { META as META08 } from './08-velocity.js';
import { META as META09 } from './09-spi-over-time.js';
import { META as META13 } from './13-missing-logic.js';
import { META as META14 } from './14-average-total-float.js';
import { META as META15 } from './15-high-total-float.js';
import { META as META16 } from './16-critical-path-percentage.js';

/** @type {Record<string, { svgWidth: number, svgHeight: number, title: string }>} */
export const CHART_META = {
  '01-planned-vs-actual-percent-complete': META01,
  '02-schedule-quality-grade-over-time':   META02,
  '03-project-health-index-over-time':     META03,
  '04-schedule-changes-over-time':         META04,
  '05-schedule-delay-over-time':           META05,
  '06-end-date-variance':                  META06,
  '07-schedule-compression-index-over-time': META07,
  '08-velocity':                           META08,
  '09-spi-over-time':                      META09,
  '13-missing-logic':                      META13,
  '14-average-total-float':                META14,
  '15-high-total-float':                   META15,
  '16-critical-path-percentage':           META16,
};

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
