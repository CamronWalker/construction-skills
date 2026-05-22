// meta.test.js
import { describe, it, expect } from 'vitest';
import { CHART_META, renderPlaceholder } from './meta.js';
import { RENDERERS } from './registry.js';

describe('CHART_META', () => {
  it('has every required field per entry', () => {
    for (const [slug, meta] of Object.entries(CHART_META)) {
      expect(meta, slug).toHaveProperty('svgWidth');
      expect(meta, slug).toHaveProperty('svgHeight');
      expect(meta, slug).toHaveProperty('title');
      expect(typeof meta.svgWidth).toBe('number');
      expect(typeof meta.svgHeight).toBe('number');
      expect(typeof meta.title).toBe('string');
    }
  });
  it('matches the RENDERERS registry 1:1', () => {
    const metaSlugs = new Set(Object.keys(CHART_META));
    const rendererSlugs = new Set(Object.keys(RENDERERS));
    expect([...metaSlugs].sort()).toEqual([...rendererSlugs].sort());
  });
});

describe('renderPlaceholder', () => {
  it('throws on unknown slug with the offending slug name in the message', () => {
    expect(() => renderPlaceholder('not-a-real-slug')).toThrow(/unknown slug "not-a-real-slug"/);
  });
  // The "matches CHART_META dimensions" test lands in commit 2 when CHART_META
  // gets its first entry.
});
