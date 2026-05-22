// svg-lib.test.js
import { describe, it, expect } from 'vitest';
import {
  dateToX, pctToY, smoothPath, xTicks, seriesPts,
  markerSvg, legendItem, htmlEnvelope, emptyHtml, renderPlaceholder,
} from './svg-lib.js';

describe('dateToX', () => {
  it('maps dmin → x0 and dmax → x1', () => {
    const dmin = new Date('2026-01-01T00:00:00Z');
    const dmax = new Date('2026-12-31T00:00:00Z');
    expect(dateToX(dmin, dmin, dmax, 100, 900)).toBeCloseTo(100, 6);
    expect(dateToX(dmax, dmin, dmax, 100, 900)).toBeCloseTo(900, 6);
  });
  it('treats dmin === dmax as span=1 (no divide-by-zero)', () => {
    const d = new Date('2026-01-01T00:00:00Z');
    expect(dateToX(d, d, d, 100, 900)).toBe(100);
  });
});

describe('pctToY', () => {
  it('inverts: 0% → y1, 100% → y0', () => {
    expect(pctToY(0,   100, 400)).toBe(400);
    expect(pctToY(100, 100, 400)).toBe(100);
  });
  it('clamps below 0 and above 100', () => {
    expect(pctToY(-50,  100, 400)).toBe(400);
    expect(pctToY(150,  100, 400)).toBe(100);
  });
});

describe('smoothPath', () => {
  it('returns empty string for empty input', () => {
    expect(smoothPath([])).toBe('');
  });
  it('returns a single M for one point', () => {
    expect(smoothPath([[10, 20]])).toMatch(/^M 10\.00,20\.00$/);
  });
  it('returns M+L for two points', () => {
    expect(smoothPath([[0, 0], [10, 10]])).toMatch(/^M 0\.00,0\.00 L 10\.00,10\.00$/);
  });
  it('emits M + C segments for three or more points', () => {
    const out = smoothPath([[0, 0], [10, 10], [20, 5]]);
    expect(out).toMatch(/^M 0\.00,0\.00 /);
    expect(out).toMatch(/ C /);
  });
});

describe('xTicks', () => {
  it('picks 7-day stride for short ranges', () => {
    const dmin = new Date('2026-01-01T00:00:00Z');
    const dmax = new Date('2026-01-31T00:00:00Z');
    const ticks = xTicks(dmin, dmax, 10);
    expect(ticks.length).toBeGreaterThanOrEqual(4);
    expect(ticks.length).toBeLessThanOrEqual(10);
  });
  it('always includes dmax as the last tick', () => {
    const dmin = new Date('2026-01-01T00:00:00Z');
    const dmax = new Date('2026-04-15T00:00:00Z');
    const ticks = xTicks(dmin, dmax, 6);
    expect(ticks[ticks.length - 1].getTime()).toBe(dmax.getTime());
  });
});

describe('markerSvg', () => {
  /** @type {import('./svg-lib.js').MarkerKind[]} */
  const kinds = ['circle', 'square', 'diamond', 'triangle', 'invtri'];
  for (const kind of kinds) {
    it(`emits SVG for kind=${kind}`, () => {
      expect(markerSvg(kind, 10, 20, '#abc', 4)).toMatch(/^<(circle|rect|polygon)\b/);
    });
  }
  it('returns empty string for unknown kind', () => {
    // @ts-expect-error — testing the runtime guard
    expect(markerSvg('unknown', 10, 20, '#abc', 4)).toBe('');
  });
});

describe('htmlEnvelope', () => {
  it('contains the title text escaped', () => {
    const html = htmlEnvelope({
      title: 'My <Chart> & Co',
      svgW: 1692, svgH: 312,
      svgInner: '<g/>',
      legendHtml: '',
    });
    expect(html).toContain('&lt;Chart&gt;');
    expect(html).not.toContain('<script');
  });
  it('has no <script> tag (rasteriser must render with JS disabled)', () => {
    const html = htmlEnvelope({
      title: 't', svgW: 100, svgH: 100, svgInner: '', legendHtml: '',
    });
    expect(html).not.toContain('<script');
  });
});

describe('renderPlaceholder', () => {
  it('throws on unknown slug', () => {
    expect(() => renderPlaceholder('not-a-real-slug')).toThrow(/unknown slug/i);
  });
  // Note: the "matches CHART_META dimensions" test moves into chart commits as
  // CHART_META gets populated. At commit 1, CHART_META is empty, so we only
  // verify the throw behavior here.
});
