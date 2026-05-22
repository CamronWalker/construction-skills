// registry.js — slug → renderer function map.
import { renderPlannedVsActual }    from './01-planned-vs-actual.js';
import { renderScheduleQuality }    from './02-schedule-quality.js';
import { renderProjectHealth }      from './03-project-health.js';
import { renderScheduleChanges }    from './04-schedule-changes.js';
import { renderScheduleDelay }      from './05-schedule-delay.js';
import { renderEndDateVariance }    from './06-end-date-variance.js';
import { renderScheduleCompression } from './07-schedule-compression.js';
import { renderVelocity }           from './08-velocity.js';
import { renderSpiOverTime }        from './09-spi-over-time.js';
import { renderActivityHitRate }    from './10-activity-hit-rate.js';
import { renderWindowStartAccuracy } from './11-window-start-accuracy.js';
import { renderWindowFinishAccuracy } from './12-window-finish-accuracy.js';
import { renderMissingLogic }       from './13-missing-logic.js';
import { renderAverageTotalFloat }  from './14-average-total-float.js';
import { renderHighTotalFloat }     from './15-high-total-float.js';
import { renderCriticalPathPercentage } from './16-critical-path-percentage.js';

/** @typedef {import('./svg-lib.js').RenderFn<any>} RenderFn */

/** @type {Record<string, RenderFn>} */
export const RENDERERS = {
  '01-planned-vs-actual-percent-complete': renderPlannedVsActual,
  '02-schedule-quality-grade-over-time':   renderScheduleQuality,
  '03-project-health-index-over-time':     renderProjectHealth,
  '04-schedule-changes-over-time':         renderScheduleChanges,
  '05-schedule-delay-over-time':           renderScheduleDelay,
  '06-end-date-variance':                  renderEndDateVariance,
  '07-schedule-compression-index-over-time': renderScheduleCompression,
  '08-velocity':                           renderVelocity,
  '09-spi-over-time':                      renderSpiOverTime,
  '10-activity-hit-rate':                  renderActivityHitRate,
  '11-window-start-accuracy':              renderWindowStartAccuracy,
  '12-window-finish-accuracy':             renderWindowFinishAccuracy,
  '13-missing-logic':                      renderMissingLogic,
  '14-average-total-float':                renderAverageTotalFloat,
  '15-high-total-float':                   renderHighTotalFloat,
  '16-critical-path-percentage':           renderCriticalPathPercentage,
};
