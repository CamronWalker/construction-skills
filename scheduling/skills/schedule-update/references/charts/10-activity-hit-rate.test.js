import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderActivityHitRate, META } from './10-activity-hit-rate.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/10-activity-hit-rate.json'),
  'utf-8'
));

describe('renderActivityHitRate', () => {
  const { html, svgInner } = renderActivityHitRate(fixture);

  it('uses the #1476b7 line stroke', () => {
    expect(html).toContain('#1476b7');
  });

  it('emits each per-point marker fill hex (red / yellow / green) across the fixture', () => {
    // Fixture spans values < 0.7, 0.7-0.9, and >= 0.9 — all 3 colors must appear.
    for (const hex of ['#b00020', '#f2c031', '#1AA462']) {
      expect(html).toContain(hex);
    }
  });

  it('uses #ffffff (or shorthand) for marker stroke', () => {
    expect(html).toMatch(/#fff(f{3})?/i);
  });

  it('emits both reference-plotline strokes with the 8,6 dash pattern', () => {
    // Yellow plotline at hit rate = 0.7 — #f2c031.
    // Green  plotline at hit rate = 1.0 — #388543.
    expect(html).toContain('#f2c031');
    expect(html).toContain('#388543');
    expect(html).toContain('stroke-dasharray="8,6"');
  });

  it('renders straight segments only (M-L-L-..., no C cubic curves)', () => {
    expect(svgInner).not.toMatch(/\sC\s/);
  });

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Activity Hit Rate (%)');
    // The "(%)" survives HTML escaping unchanged (no reserved chars).
    expect(html).toContain('Activity Hit Rate (%)');
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });

  it('throws TypeError when payload.hitRates is not an array', () => {
    expect(() => renderActivityHitRate(/** @type {any} */ ({ hitRates: 'not-an-array' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderActivityHitRate(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderActivityHitRate([]);
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });

  it('accepts a flat array as well as the { hitRates: [...] } envelope', () => {
    const { html: arrHtml } = renderActivityHitRate(fixture.hitRates);
    expect(arrHtml).toContain(META.title);
    expect(arrHtml).toContain('#1476b7');
  });
});
