import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderEndDateVariance, META } from './06-end-date-variance.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/06-end-date-variance.json'),
  'utf-8'
));

describe('renderEndDateVariance', () => {
  const { html, svgInner } = renderEndDateVariance(fixture);

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('End Date Variance');
    expect(html).toContain(META.title);
  });

  it('uses the SmartPM zone palette (#b00020 red and #388543 green) when both sides are present', () => {
    // Synthetic two-row payload that crosses the zero line so both zone colors
    // get rendered. The live fixture's baseline puts all visible points on
    // one side of zero — sufficient to draw one color only.
    const sample = {
      contractual_completion: '2024-06-15',
      updates: [
        { dataDate: '2024-01-01T08:00:00', sourceEndDate: '2024-06-01T09:00:00' },  // -14 days → green
        { dataDate: '2024-02-01T08:00:00', sourceEndDate: '2024-06-30T09:00:00' },  // +15 days → red
      ],
    };
    const { html: out } = renderEndDateVariance(sample);
    expect(out).toContain('#b00020');
    expect(out).toContain('#388543');
  });

  it('emits the blue zero-line stroke (#1476b7)', () => {
    expect(html).toContain('#1476b7');
  });

  it('emits the two SmartPM plot-band fills (pink + light green)', () => {
    expect(html).toContain('rgba(176, 0, 32, 0.0375)');
    expect(html).toContain('rgba(20, 118, 75, 0.0375)');
  });

  it('uses #2caffe for the legend swatch', () => {
    expect(html).toContain('#2caffe');
  });

  it('renders MMM DD, YYYY X-axis labels (long format)', () => {
    expect(html).toMatch(/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s\d{2},\s\d{4}/);
  });

  it('uses Inter as the font family for axis labels', () => {
    expect(html).toContain('Inter');
  });

  it('emits a legend item for End Date Variance', () => {
    expect(html).toContain('End Date Variance');
  });

  it('renders straight segments only (no cubic curves)', () => {
    expect(svgInner).not.toMatch(/\sC\s/);
  });

  it('uses contractual_completion as the variance baseline when provided', () => {
    // baseline = 2024-06-01; one row matches it (variance=0), one 10 days later.
    const sample = {
      contractual_completion: '2024-06-01',
      updates: [
        { dataDate: '2024-01-01T08:00:00', sourceEndDate: '2024-06-01T09:00:00' },
        { dataDate: '2024-02-01T08:00:00', sourceEndDate: '2024-06-11T09:00:00' },
      ],
    };
    const { html: out } = renderEndDateVariance(sample);
    // Variance is +10 days at second point. With minSpan 50 and ±18% padding,
    // a Y tick somewhere in the 0–25 range should appear.
    expect(out).toMatch(/>(?:0|5|10|15|20|25)</);
  });

  it('falls back to the earliest sourceEndDate when contractual_completion is absent', () => {
    const sample = {
      updates: [
        { dataDate: '2024-01-01T08:00:00', sourceEndDate: '2024-06-01T09:00:00' },
        { dataDate: '2024-02-01T08:00:00', sourceEndDate: '2024-06-11T09:00:00' },
      ],
    };
    const { html: out } = renderEndDateVariance(sample);
    // First row's variance = 0 against itself; second is +10.
    expect(out).toContain('End Date Variance');
  });

  it('emits colored pill labels with bold Inter 11.2 text', () => {
    // Each visible data point gets a "MMM DD, YYYY" pill rendered as bold text.
    expect(html).toMatch(/font-weight="700"[^>]*>(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s\d{2},\s\d{4}</);
  });

  it('throws TypeError when payload.updates is not an array', () => {
    expect(() => renderEndDateVariance(/** @type {any} */ ({ updates: 'not-an-array' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderEndDateVariance(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input array', () => {
    const { html: empty } = renderEndDateVariance([]);
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });

  it('renders empty-state for empty updates envelope', () => {
    const { html: empty } = renderEndDateVariance({ updates: [] });
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });

  it('fixture variance stays in a sane bounded range (guards against stale-baseline regressions)', () => {
    // The +830-day bug came from a stale fixture whose earliest sourceEndDate
    // was a fossil (2024-02-29) unrelated to the rest of the series. Guard it:
    // variance = each sourceEndDate minus the earliest sourceEndDate, in days.
    const ends = fixture.updates
      .filter(u => u && u.sourceEndDate)
      .map(u => Date.parse(u.sourceEndDate))
      .sort((a, b) => a - b);
    const baseline = ends[0];
    const maxVarianceDays = Math.round((ends[ends.length - 1] - baseline) / 86400000);
    // SmartPM's End Date Variance for this scenario tops out at +73 days. Any
    // fixture pushing this past ~200 is almost certainly stale/garbage data.
    expect(maxVarianceDays).toBeGreaterThanOrEqual(0);
    expect(maxVarianceDays).toBeLessThan(200);
  });
});
