// index.js — public entry point.
// Re-exports the registry, metadata, placeholder renderer, and shared types
// so consumers can `import { RENDERERS } from '@westland/charts'` without
// thinking about file layout.
//
// Per-chart renderers are also re-exported by name as charts land so the
// westland-mcps consumer can type-narrow when it knows which renderer it's
// calling (`renderPlannedVsActual(typedPayload)` vs `RENDERERS[slug](anyPayload)`).

export { RENDERERS } from './registry.js';
export { CHART_META } from './meta.js';
export { renderPlaceholder } from './meta.js';
export { renderPlannedVsActual }    from './01-planned-vs-actual.js';
export { renderScheduleQuality }    from './02-schedule-quality.js';
export { renderProjectHealth }      from './03-project-health.js';
export { renderScheduleChanges }    from './04-schedule-changes.js';
export { renderScheduleDelay }      from './05-schedule-delay.js';
export { renderEndDateVariance }    from './06-end-date-variance.js';
export { renderScheduleCompression } from './07-schedule-compression.js';
export { renderVelocity }           from './08-velocity.js';
export { renderSpiOverTime }        from './09-spi-over-time.js';
export { renderActivityHitRate }    from './10-activity-hit-rate.js';
export { renderWindowStartAccuracy } from './11-window-start-accuracy.js';
export { renderWindowFinishAccuracy } from './12-window-finish-accuracy.js';
export { renderMissingLogic }       from './13-missing-logic.js';
export { renderAverageTotalFloat }  from './14-average-total-float.js';
export { renderHighTotalFloat }     from './15-high-total-float.js';
export { renderCriticalPathPercentage } from './16-critical-path-percentage.js';
export { renderSummaryReport }      from './summary-report.js';
