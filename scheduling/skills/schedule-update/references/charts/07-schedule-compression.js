// 07-schedule-compression.js — Schedule Compression Index™ Over Time.
// Single-series straight line with circle markers. Palette/style captured
// from SmartPM's live DOM via Chrome MCP on Wellington NZ Temple
// (project 113385, scenario 1644) on 2026-05-22. Replaces the existing
// matplotlib approximation, which was never visually faithful to the
// SmartPM web view.
//
// Reuses the renderTrendLine helper exported from ./13-missing-logic.js.
// Chart 07 differs from charts 13/14/15/16 in two ways the helper handles
// via options:
//   - markerFill: `#1AA462` (slightly different green from chart 13's #388543).
//   - valueGetter: pulls `scheduleCompressionIndex` (NOT `value` / NOT
//                  `scheduleCompression`). The fixture stores the index
//                  already in PERCENT units, e.g. `16` for 16%.

import { renderTrendLine } from './13-missing-logic.js';
import { HTML_CARD_W, HTML_CARD_H } from './svg-lib.js';

const MARKER_FILL = '#1AA462';

/**
 * @typedef {Object} CompressionTrendRow
 * @property {string}      dataDate
 * @property {number|null} [scheduleCompression]
 * @property {number|null} [scheduleCompressionIndex]
 * @property {string|null} [indicator]
 */

/**
 * @typedef {{ trend: Array<CompressionTrendRow> } | Array<CompressionTrendRow>} ScheduleCompressionPayload
 */

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Schedule Compression Index™ Over Time',
};

/**
 * @param {ScheduleCompressionPayload} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderScheduleCompression(payload) {
  /** @type {Array<CompressionTrendRow>} */
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
      throw new TypeError('expected ScheduleCompressionPayload ({ trend: array }) or array');
    }
  } else {
    throw new TypeError('expected ScheduleCompressionPayload ({ trend: array }) or array');
  }

  /** @param {CompressionTrendRow} r @returns {number | null} */
  const valueGetter = (r) => {
    const v = r?.scheduleCompressionIndex;
    return typeof v === 'number' && !Number.isNaN(v) ? v : null;
  };

  // The fixture stores the index already in percent units (e.g. 16 = 16%).
  // Display directly with a `%` suffix.
  /** @param {number} v @returns {string} */
  const fmt = (v) => `${v.toFixed(0)}%`;

  return renderTrendLine(
    rows,
    META.title,
    fmt,
    1,                // minSpan = 1% (avoid label collapse when all rows are 0%)
    MARKER_FILL,
    { valueGetter },  // xFormat defaults to 'short' (MM/DD/YY); includeZero defaults true
  );
}
