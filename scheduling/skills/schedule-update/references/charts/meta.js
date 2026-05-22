// meta.js — slug → { svgWidth, svgHeight, title } map.
//
// Aggregates per-chart META exports for use by renderPlaceholder and by external
// consumers that need chart dimensions without invoking a renderer.
//
// IMPORTANT: We assign to globalThis so svg-lib.js's renderPlaceholder can read
// CHART_META without importing this file (avoids a circular dep — svg-lib.js
// → meta.js → NN-slug.js → svg-lib.js).

// At commit 1 the registry is empty; per-chart META imports get added as
// charts land.

/** @type {Record<string, { svgWidth: number, svgHeight: number, title: string }>} */
export const CHART_META = {};

globalThis.__WESTLAND_CHART_META__ = CHART_META;
