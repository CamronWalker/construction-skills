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
// Per-chart re-exports get added as charts land:
//   export { renderPlannedVsActual } from './01-planned-vs-actual.js';  // (commit 2)
//   ...
