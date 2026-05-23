// 14-average-total-float.js — Average Activity Total Float Over Time.
// Single-series straight line with circle markers. Palette/style captured
// from SmartPM's live DOM via Chrome MCP on Wellington NZ Temple
// (project 113385, scenario 1644) on 2026-05-22. No Python reference.
//
// Reuses the renderTrendLine helper exported from ./13-missing-logic.js —
// the two charts differ only in title, Y-axis formatter, and Y-axis title.

import { renderTrendLine } from './13-missing-logic.js';
import { HTML_CARD_W, HTML_CARD_H } from './svg-lib.js';

/**
 * @typedef {Array<{ dataDate: string, value: number }>} AverageTotalFloatPayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Average Activity Total Float Over Time',
};

/**
 * @param {AverageTotalFloatPayload | { trend?: AverageTotalFloatPayload }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderAverageTotalFloat(payload) {
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
      throw new TypeError('expected AverageTotalFloatPayload (array) or { trend: array }');
    }
  } else {
    throw new TypeError('expected AverageTotalFloatPayload (array) or { trend: array }');
  }

  // Numeric days with explicit unit on each tick — keeps the colleague's eye
  // from reading them as percent / index after a glance at chart 13.
  /** @param {number} v @returns {string} */
  const fmt = (v) => `${v.toFixed(0)} days`;
  return renderTrendLine(rows, META.title, fmt, 1 /* min Y span = 1 day */);
}
