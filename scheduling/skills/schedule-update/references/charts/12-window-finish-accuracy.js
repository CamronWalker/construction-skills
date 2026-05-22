// 12-window-finish-accuracy.js — Window Finish Accuracy.
// 3-series stacked column chart: Finished On Time (green), Finished Late
// (yellow), Did Not Finish (red). Implementation lives in _hit-rate.js; this
// file is a thin wrapper that supplies the title, legend labels, and field
// names. Palette captured from SmartPM's live DOM via Chrome MCP on Wellington
// NZ Temple (project 113385, scenario 1644) on 2026-05-22.

import { HTML_CARD_W, HTML_CARD_H } from './svg-lib.js';
import { renderHitRateStacked } from './_hit-rate.js';

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: HTML_CARD_H,
  title:     'Window Finish Accuracy',
};

/**
 * @param {Array<Record<string, unknown>> | { hitRates?: Array<Record<string, unknown>> }} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderWindowFinishAccuracy(payload) {
  return renderHitRateStacked(payload, {
    title: META.title,
    legendLabels: ['Finished On Time', 'Finished Late', 'Did Not Finish'],
    fields: { onTime: 'finishedOnTime', late: 'finishedLate', didNot: 'didNotFinish' },
  });
}
