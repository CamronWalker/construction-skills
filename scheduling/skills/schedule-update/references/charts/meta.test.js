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
});

describe('renderPlaceholder (with populated CHART_META)', () => {
  it('emits HTML containing the chart card width for a known slug', () => {
    const { html, svgInner } = renderPlaceholder('01-planned-vs-actual-percent-complete');
    expect(html).toContain(`width="${CHART_META['01-planned-vs-actual-percent-complete'].svgWidth}"`);
    expect(html).toContain('Data not yet available');
    expect(svgInner).toContain('<text');
  });
  it('honors custom message + warn icon', () => {
    const { html } = renderPlaceholder('01-planned-vs-actual-percent-complete',
      { message: 'Render failed', icon: 'warn' });
    expect(html).toContain('Render failed');
    expect(html).toContain('#FFC000');
  });
});
