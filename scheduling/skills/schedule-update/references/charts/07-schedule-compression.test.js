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

  it('emits the canonical title from META (including the ™ symbol)', () => {
    expect(META.title).toBe('Schedule Compression Index™ Over Time');
    expect(html).toContain('Schedule Compression Index');
    expect(html).toContain('™');
  });

  it('emits the 3-zone palette when all 3 zones are represented', () => {
    // Synthetic 3-row payload crossing both thresholds (15 and 25) to force
    // every zone color into the output.
    const sample = {
      trend: [
        { dataDate: '2024-01-01T08:00:00', scheduleCompressionIndex: 5,  indicator: 'GOOD' },
        { dataDate: '2024-02-01T08:00:00', scheduleCompressionIndex: 20, indicator: 'FINE' },
        { dataDate: '2024-03-01T08:00:00', scheduleCompressionIndex: 35, indicator: 'BAD'  },
      ],
    };
    const { html: out } = renderScheduleCompression(sample);
    expect(out).toContain('#1AA462');
    expect(out).toContain('#F5A623');
    expect(out).toContain('#DB495B');
  });

  it('emits both dashed threshold lines (yellow @ 15% and red @ 25%)', () => {
    expect(html).toContain('#E0B020');
    expect(html).toContain('#B41E2F');
    expect(html).toContain('stroke-dasharray="8,4"');
  });

  it('emits the legend swatch color #2caffe', () => {
    expect(html).toContain('#2caffe');
  });

  it('emits percent-suffixed Y-axis labels', () => {
    expect(html).toMatch(/\d+\s%/);
  });

  it('emits MM/DD/YY X-axis labels', () => {
    expect(html).toMatch(/\d{2}\/\d{2}\/\d{2}/);
  });

  it('emits the rotated "Values" Y-axis title', () => {
    expect(html).toContain('Values');
    expect(html).toMatch(/transform="rotate\(-90/);
  });

  it('uses Inter font family', () => {
    expect(html).toContain('Inter');
  });

  it('renders straight segments only (no cubic curves)', () => {
    expect(svgInner).not.toMatch(/\sC\s/);
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
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

  it('skips rows with null scheduleCompressionIndex', () => {
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
});
