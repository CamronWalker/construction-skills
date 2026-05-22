import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderSpiOverTime, META } from './09-spi-over-time.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/09-spi-over-time.json'),
  'utf-8'
));

describe('renderSpiOverTime', () => {
  const { html, svgInner } = renderSpiOverTime(fixture);

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
    // Yellow plotline at SPI = 0.7 — #f2c031 with stroke-dasharray="8,6".
    // Green plotline at SPI = 1.0 — #388543 with stroke-dasharray="8,6".
    expect(html).toContain('#f2c031');
    expect(html).toContain('#388543');
    expect(html).toContain('stroke-dasharray="8,6"');
  });

  it('renders straight segments only (M-L-L-..., no C cubic curves)', () => {
    // Single-series line should be polyline-like; no smoothPath curves.
    expect(svgInner).not.toMatch(/\sC\s/);
  });

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('SPI Over Time');
    expect(html).toContain(META.title);
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });

  it('skips spi: 0 rows so the line breaks at the gap (no marker at zero)', () => {
    // Fixture has at least one `spi: 0` row (e.g. 2022-11-23). Implementation
    // should split the data line into ≥ 2 subpaths at those gaps. Each subpath
    // is its own `<path d="M ...">`. Count distinct path moves.
    const moveCount = (svgInner.match(/d="M\s/g) ?? []).length;
    expect(moveCount).toBeGreaterThanOrEqual(2);
  });

  it('throws TypeError when payload.trend is not an array', () => {
    expect(() => renderSpiOverTime(/** @type {any} */ ({ trend: 'not-an-array' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderSpiOverTime(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderSpiOverTime([]);
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });

  it('accepts a flat array as well as the { trend: [...] } envelope', () => {
    const { html: arrHtml } = renderSpiOverTime(fixture.trend);
    expect(arrHtml).toContain(META.title);
    expect(arrHtml).toContain('#1476b7');
  });
});
