// 06-end-date-variance.js — End Date Variance.
// Single-series straight line with circle markers. Palette/style captured
// from SmartPM's live DOM via Chrome MCP on Wellington NZ Temple
// (project 113385, scenario 1644) on 2026-05-22. Replaces the existing
// matplotlib approximation, which was never visually faithful to the
// SmartPM web view.
//
// Reuses the renderTrendLine helper exported from ./13-missing-logic.js.
// Chart 06 differs from charts 13/14/15/16 in two ways the helper handles
// via options:
//   - xFormat: 'long'  — `MMM DD, YYYY` instead of `MM/DD/YY`.
//   - valueGetter      — variance per row is computed against the FIRST
//                        (earliest) `sourceEndDate` baseline, not stored.
//   - includeZero: false — variance can stay well above 0 for a slipped
//                          project; clamping to 0 collapses the visual.

import { renderTrendLine } from './13-missing-logic.js';
import { HTML_CARD_W, HTML_CARD_H, parseDate, emptyHtml } from './svg-lib.js';

const MARKER_FILL = '#388543';

/**
 * @typedef {{ dataDate: string, sourceEndDate: string }} EndDateUpdate
 * @typedef {{ updates: Array<EndDateUpdate> }} EndDateVariancePayload
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
  if (Array.isArray(payload)) {
    updates = payload;
  } else if (payload && typeof payload === 'object') {
    const envelope = /** @type {any} */ (payload).updates;
    if (envelope === undefined || envelope === null) {
      updates = [];
    } else if (Array.isArray(envelope)) {
      updates = envelope;
    } else {
      throw new TypeError('expected EndDateVariancePayload ({ updates: array }) or array');
    }
  } else {
    throw new TypeError('expected EndDateVariancePayload ({ updates: array }) or array');
  }

  if (!updates.length) return { html: emptyHtml(META.title), svgInner: '' };

  // Baseline = the FIRST (earliest dataDate) update's sourceEndDate. The chart
  // plots days between that baseline and each row's sourceEndDate.
  // Sort by dataDate ascending so the baseline is deterministic regardless of
  // input order.
  const sorted = [...updates]
    .filter(r => r && r.dataDate && r.sourceEndDate)
    .sort((a, b) => parseDate(a.dataDate).getTime() - parseDate(b.dataDate).getTime());

  if (!sorted.length) return { html: emptyHtml(META.title), svgInner: '' };

  const baselineMs = parseDate(sorted[0].sourceEndDate).getTime();
  /** @param {EndDateUpdate} r @returns {number} */
  const valueGetter = (r) => {
    const t = parseDate(r.sourceEndDate).getTime();
    return Math.round((t - baselineMs) / 86400000);
  };

  /** @param {number} v @returns {string} */
  const fmt = (v) => `${v.toFixed(0)} days`;

  return renderTrendLine(
    sorted,
    META.title,
    fmt,
    5,            // minSpan = 5 days (Wellington's range was tight enough to need this)
    MARKER_FILL,
    { xFormat: 'long', valueGetter, includeZero: false },
  );
}
