// registry.js — slug → renderer function map.
import { renderPlannedVsActual }    from './01-planned-vs-actual.js';
import { renderScheduleQuality }    from './02-schedule-quality.js';
import { renderProjectHealth }      from './03-project-health.js';
import { renderScheduleChanges }    from './04-schedule-changes.js';
import { renderScheduleDelay }      from './05-schedule-delay.js';
import { renderMissingLogic }       from './13-missing-logic.js';
import { renderAverageTotalFloat }  from './14-average-total-float.js';

/** @typedef {import('./svg-lib.js').RenderFn<any>} RenderFn */

/** @type {Record<string, RenderFn>} */
export const RENDERERS = {
  '01-planned-vs-actual-percent-complete': renderPlannedVsActual,
  '02-schedule-quality-grade-over-time':   renderScheduleQuality,
  '03-project-health-index-over-time':     renderProjectHealth,
  '04-schedule-changes-over-time':         renderScheduleChanges,
  '05-schedule-delay-over-time':           renderScheduleDelay,
  '13-missing-logic':                      renderMissingLogic,
  '14-average-total-float':                renderAverageTotalFloat,
};
