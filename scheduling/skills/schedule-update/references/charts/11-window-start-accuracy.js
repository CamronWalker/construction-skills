// 11-window-start-accuracy.js — Window Start Accuracy.
// 3-series stacked column chart: Started On Time (green), Started Late
// (yellow), Did Not Start (red). Implementation lives in _hit-rate.js; this
// file is a thin wrapper that supplies the title, legend labels, and field
// names. Palette captured from SmartPM's live DOM via Chrome MCP on Wellington
// NZ Temple (project 113385, scenario 1644) on 2026-05-22.

import { HTML_CARD_W, HTML_CARD_H } from './svg-lib.js';
import { renderHitRateStacked } from './_hit-rate.js';

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Window Start Accuracy',
};

/**
 * @param {Array<Record<string, unknown>> | { hitRates?: Array<Record<string, unknown>> }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderWindowStartAccuracy(payload) {
  return renderHitRateStacked(payload, {
    title: META.title,
    legendLabels: ['Started On Time', 'Started Late', 'Did Not Start'],
    fields: { onTime: 'startedOnTime', late: 'startedLate', didNot: 'didNotStart' },
  });
}
