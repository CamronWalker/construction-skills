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

  it('uses the #2caffe line color', () => {
    expect(html).toContain('#2caffe');
  });

  it('uses the #388543 circle-marker fill', () => {
    expect(html).toContain('#388543');
  });

  it('uses the #ffffff marker stroke (or shorthand) for circle outlines', () => {
    expect(html).toMatch(/#fff(f{3})?/i);
  });

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('End Date Variance');
    expect(html).toContain(META.title);
  });

  it('renders MMM DD, YYYY X-axis labels (long format)', () => {
    // e.g. "Oct 07, 2025" — accept any month abbrev + 2-digit day + 4-digit year.
    expect(html).toMatch(/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s\d{2},\s\d{4}/);
  });

  it('Y-axis tick labels include a "days" unit', () => {
    expect(html).toMatch(/days/i);
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

  it('computes variance as days from the earliest sourceEndDate', () => {
    // Baseline = first sorted row's sourceEndDate, expressed as variance = 0.
    // The earliest row in the fixture has sourceEndDate 2024-02-29. Pass a tiny
    // 2-row payload to verify the math is days-from-baseline.
    const sample = {
      updates: [
        { dataDate: '2024-01-01T08:00:00', sourceEndDate: '2024-06-01T09:00:00' },  // baseline
        { dataDate: '2024-02-01T08:00:00', sourceEndDate: '2024-06-11T09:00:00' },  // +10 days
      ],
    };
    const out = renderEndDateVariance(sample);
    // The label formatter is `${v.toFixed(0)} days`. With 2 rows including 0,
    // and 5-day minimum span, the Y-axis must show a label near +10.
    expect(out.html).toMatch(/10 days|11 days|9 days/);
  });
});
