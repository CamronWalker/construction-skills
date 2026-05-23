// 16-critical-path-percentage.js — Critical Path Activities Over Time.
// Single-series straight line with circle markers. Palette/style captured
// from SmartPM's live DOM via Chrome MCP on Wellington NZ Temple
// (project 113385, scenario 1644) on 2026-05-22. No Python reference.
//
// Reuses the renderTrendLine helper exported from ./13-missing-logic.js —
// chart 16 differs only in title, marker fill color (yellow), and Y-axis
// formatter (percent).

import { renderTrendLine } from './13-missing-logic.js';
import { HTML_CARD_W, HTML_CARD_H } from './svg-lib.js';

const MARKER_FILL = '#f2c031';

/**
 * @typedef {Array<{ dataDate: string, value: number }>} CriticalPathPercentagePayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Critical Path Activities Over Time',
};

/**
 * @param {CriticalPathPercentagePayload | { trend?: CriticalPathPercentagePayload }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderCriticalPathPercentage(payload) {
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
      throw new TypeError('expected CriticalPathPercentagePayload (array) or { trend: array }');
    }
  } else {
    throw new TypeError('expected CriticalPathPercentagePayload (array) or { trend: array }');
  }

  // Y-axis is percent (input is a fraction 0..1).
  /** @param {number} v @returns {string} */
  const fmt = (v) => `${(v * 100).toFixed(1)}%`;
  return renderTrendLine(rows, META.title, fmt, 0.01 /* min Y span = 1% */, MARKER_FILL);
}
