// svg-lib.test.js
import { describe, it, expect } from 'vitest';
import {
  dateToX, pctToY, smoothPath, xTicks, seriesPts,
  markerSvg, legendItem, htmlEnvelope, emptyHtml,
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

describe('seriesPts', () => {
  it('returns empty array for empty rows', () => {
    expect(seriesPts([], 'FIELD',
      new Date('2026-01-01T00:00:00Z'), new Date('2026-12-31T00:00:00Z'),
      100, 900, 100, 400)).toEqual([]);
  });

  it('skips rows where the field value is null or undefined', () => {
    const dmin = new Date('2026-01-01T00:00:00Z');
    const dmax = new Date('2026-01-02T00:00:00Z');
    const out = seriesPts(
      [
        { DATE: '2026-01-01', V: 50 },
        { DATE: '2026-01-01', V: null },
        { DATE: '2026-01-02', V: undefined },
        { DATE: '2026-01-02', V: 75 },
      ],
      'V', dmin, dmax, 100, 900, 100, 400,
    );
    expect(out).toHaveLength(2);
    expect(out[0][1]).toBeCloseTo(pctToY(50, 100, 400), 6);
    expect(out[1][1]).toBeCloseTo(pctToY(75, 100, 400), 6);
  });

  it('maps DATE+value to (dateToX, pctToY) coordinates', () => {
    const dmin = new Date('2026-01-01T00:00:00Z');
    const dmax = new Date('2026-01-31T00:00:00Z');
    const out = seriesPts(
      [{ DATE: '2026-01-31', V: 100 }],
      'V', dmin, dmax, 0, 1000, 0, 500,
    );
    expect(out).toHaveLength(1);
    expect(out[0][0]).toBeCloseTo(1000, 6); // x at dmax
    expect(out[0][1]).toBeCloseTo(0, 6);    // y at 100% (top of plot)
  });
});

describe('legendItem', () => {
  it('emits an area swatch for kind="area"', () => {
    const html = legendItem('area', '#808080', '', 'Progress Target');
    expect(html).toContain('fill="#808080"');
    expect(html).toContain('fill-opacity="0.2"');
    expect(html).toContain('Progress Target');
  });

  it('emits a line + marker swatch for non-area kinds with dash pattern', () => {
    const html = legendItem('invtri', '#388543', '8,6', 'Scheduled Completion');
    expect(html).toContain('stroke="#388543"');
    expect(html).toContain('stroke-dasharray="8,6"');
    expect(html).toContain('<polygon');
    expect(html).toContain('Scheduled Completion');
  });

  it('escapes the label', () => {
    expect(legendItem('circle', '#000', '', 'A <Bad> Name')).toContain('A &lt;Bad&gt; Name');
  });
});

describe('emptyHtml', () => {
  it('escapes the title and contains the "no data" marker', () => {
    const html = emptyHtml('My <Title>');
    expect(html).toContain('&lt;Title&gt;');
    expect(html).toContain('no data');
  });
});

describe('htmlEnvelope (non-ASCII)', () => {
  it('preserves UTF-8 characters in the title', () => {
    const html = htmlEnvelope({
      title: 'Schedule Quality Grade™ — Trend',
      svgW: 1692, svgH: 312, svgInner: '<g/>', legendHtml: '',
    });
    expect(html).toContain('Schedule Quality Grade™ — Trend');
  });
});

