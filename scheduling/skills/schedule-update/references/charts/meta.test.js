// meta.test.js
import { describe, it, expect } from 'vitest';
import { CHART_META } from './meta.js';
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
