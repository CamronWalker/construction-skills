// registry.js — slug → renderer function map.

/** @typedef {import('./svg-lib.js').RenderFn<any>} RenderFn */

/** @type {Record<string, RenderFn>} */
export const RENDERERS = {};
