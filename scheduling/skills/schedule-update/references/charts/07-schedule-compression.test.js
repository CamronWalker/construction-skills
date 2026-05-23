import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderScheduleCompression, META } from './07-schedule-compression.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/07-schedule-compression-index-over-time.json'),
  'utf-8'
));

describe('renderScheduleCompression', () => {
  const { html, svgInner } = renderScheduleCompression(fixture);

  it('uses the #2caffe line color', () => {
    expect(html).toContain('#2caffe');
  });

  it('uses the #1AA462 circle-marker fill', () => {
    expect(html).toContain('#1AA462');
  });

  it('uses the #ffffff marker stroke (or shorthand) for circle outlines', () => {
    expect(html).toMatch(/#fff(f{3})?/i);
  });

  it('emits the canonical title from META (including the ™ symbol)', () => {
    expect(META.title).toBe('Schedule Compression Index™ Over Time');
    expect(html).toContain('Schedule Compression Index');
    expect(html).toContain('™');
  });

  it('emits the percent Y-axis (e.g. "%" in tick labels)', () => {
    expect(html).toContain('%');
  });

  it('has empty legend row content (single-series chart)', () => {
    expect(html).toMatch(/<div class="legend-row">\s*<\/div>/);
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });

  it('renders straight segments only (M-L-L-..., no C cubic curves)', () => {
    expect(svgInner).not.toMatch(/\sC\s/);
  });

  it('throws TypeError when payload.trend is not an array', () => {
    expect(() => renderScheduleCompression(/** @type {any} */ ({ trend: 'not-an-array' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderScheduleCompression(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input array', () => {
    const { html: empty } = renderScheduleCompression([]);
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });

  it('renders empty-state for empty trend envelope', () => {
    const { html: empty } = renderScheduleCompression({ trend: [] });
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });

  it('skips rows with null scheduleCompressionIndex (does NOT plot them as 0)', () => {
    // Two rows with values, one null in the middle. A null-as-0 bug would
    // show 3 markers, with the middle one anchored at the 0% gridline.
    // The renderer should produce exactly 2 <circle> markers.
    const sample = {
      trend: [
        { dataDate: '2024-01-01T08:00:00', scheduleCompressionIndex: 10, indicator: 'GOOD' },
        { dataDate: '2024-02-01T08:00:00', scheduleCompressionIndex: null, indicator: null },
        { dataDate: '2024-03-01T08:00:00', scheduleCompressionIndex: 20, indicator: 'FINE' },
      ],
    };
    const { svgInner: inner } = renderScheduleCompression(sample);
    const markerCount = (inner.match(/<circle\b/g) ?? []).length;
    expect(markerCount).toBe(2);
  });

  it('uses scheduleCompressionIndex, NOT scheduleCompression (the ratio)', () => {
    // A row with scheduleCompression=1.18 and scheduleCompressionIndex=18:
    // if the renderer reads .value or .scheduleCompression, it would plot
    // around 1.18% (collapsed near 0); reading .scheduleCompressionIndex
    // plots at 18%, which after auto-fit padding produces a "20%" tick.
    const sample = {
      trend: [
        { dataDate: '2024-01-01T08:00:00', scheduleCompression: 1.0, scheduleCompressionIndex: 0 },
        { dataDate: '2024-02-01T08:00:00', scheduleCompression: 1.18, scheduleCompressionIndex: 18 },
      ],
    };
    const { html: out } = renderScheduleCompression(sample);
    // Auto-fit on [0, 18] padded ±10% lands roughly [-2, 20], so a label
    // near 20% (or 19% / 18%) should appear in the Y-axis text.
    expect(out).toMatch(/(18|19|20|21)%/);
  });
});
