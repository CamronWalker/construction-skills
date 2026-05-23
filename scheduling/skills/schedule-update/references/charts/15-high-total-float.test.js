import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderHighTotalFloat, META } from './15-high-total-float.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/15-high-total-float.json'),
  'utf-8'
));

describe('renderHighTotalFloat', () => {
  const { html, svgInner } = renderHighTotalFloat(fixture);

  it('uses the #2caffe line color', () => {
    expect(html).toContain('#2caffe');
  });

  it('uses the #b00020 circle-marker fill (red)', () => {
    expect(html).toContain('#b00020');
  });

  it('uses the #ffffff marker stroke', () => {
    expect(html).toMatch(/#fff(f{3})?/i);
  });

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('High Total Float Activities Over Time');
    expect(html).toContain(META.title);
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
    expect(() => renderHighTotalFloat(/** @type {any} */ ({ trend: 'not-an-array' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderHighTotalFloat(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderHighTotalFloat([]);
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });
});
