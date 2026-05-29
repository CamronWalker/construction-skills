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

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Activity Hit Rate (%)');
    expect(html).toContain(META.title);
  });

  it('emits the 3-zone palette (red #b00020, yellow #f2c031, green #388543)', () => {
    expect(html).toContain('#b00020');
    expect(html).toContain('#f2c031');
    expect(html).toContain('#388543');
  });

  it('emits both dashed threshold lines with stroke-dasharray="8,6"', () => {
    // Yellow at 0.80, green at 0.90.
    expect(html).toContain('stroke-dasharray="8,6"');
  });

  it('emits the legend swatch color #2caffe', () => {
    expect(html).toContain('#2caffe');
  });

  it('emits percent-suffixed Y-axis labels', () => {
    // E.g. "0 %", "20 %", "100 %".
    expect(html).toMatch(/\d+\s%/);
  });

  it('emits MM/DD/YY X-axis labels', () => {
    expect(html).toMatch(/\d{2}\/\d{2}\/\d{2}/);
  });

  it('emits the rotated "Values" Y-axis title', () => {
    expect(html).toContain('Values');
    expect(html).toMatch(/transform="rotate\(-90/);
  });

  it('renders straight segments only (no cubic curves)', () => {
    expect(svgInner).not.toMatch(/\sC\s/);
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
    expect(arrHtml).toContain('#b00020');
  });
});
