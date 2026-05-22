// registry.js — slug → renderer function map.
import { renderPlannedVsActual } from './01-planned-vs-actual.js';
import { renderScheduleQuality } from './02-schedule-quality.js';

/** @typedef {import('./svg-lib.js').RenderFn<any>} RenderFn */

/** @type {Record<string, RenderFn>} */
export const RENDERERS = {
  '01-planned-vs-actual-percent-complete': renderPlannedVsActual,
  '02-schedule-quality-grade-over-time':   renderScheduleQuality,
};
