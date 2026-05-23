import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderCriticalPathPercentage, META } from './16-critical-path-percentage.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/16-critical-path-percentage.json'),
  'utf-8'
));

describe('renderCriticalPathPercentage', () => {
  const { html, svgInner } = renderCriticalPathPercentage(fixture);

  it('uses the #2caffe line color', () => {
    expect(html).toContain('#2caffe');
  });

  it('uses the #f2c031 circle-marker fill (yellow)', () => {
    expect(html).toContain('#f2c031');
  });

  it('uses the #ffffff marker stroke', () => {
    expect(html).toMatch(/#fff(f{3})?/i);
  });

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Critical Path Activities Over Time');
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
    expect(() => renderCriticalPathPercentage(/** @type {any} */ ({ trend: 'not-an-array' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderCriticalPathPercentage(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderCriticalPathPercentage([]);
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });
});
