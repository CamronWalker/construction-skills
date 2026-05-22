import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderAverageTotalFloat, META } from './14-average-total-float.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/14-average-total-float.json'),
  'utf-8'
));

describe('renderAverageTotalFloat', () => {
  const { html, svgInner } = renderAverageTotalFloat(fixture);

  it('uses the #2caffe line color', () => {
    expect(html).toContain('#2caffe');
  });

  it('uses the #388543 circle-marker fill', () => {
    expect(html).toContain('#388543');
  });

  it('uses the #ffffff marker stroke', () => {
    expect(html).toMatch(/#fff(f{3})?/i);
  });

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Average Activity Total Float Over Time');
    expect(html).toContain(META.title);
  });

  it('Y-axis tick labels include a "days" unit somewhere', () => {
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

  it('throws TypeError when payload.trend is not an array', () => {
    expect(() => renderAverageTotalFloat(/** @type {any} */ ({ trend: 'not-an-array' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderAverageTotalFloat(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderAverageTotalFloat([]);
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });
});
