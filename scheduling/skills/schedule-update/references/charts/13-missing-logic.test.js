import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderMissingLogic, META } from './13-missing-logic.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/13-missing-logic.json'),
  'utf-8'
));

describe('renderMissingLogic', () => {
  const { html, svgInner } = renderMissingLogic(fixture);

  it('uses the #2caffe line color', () => {
    expect(html).toContain('#2caffe');
  });

  it('uses the #388543 circle-marker fill', () => {
    expect(html).toContain('#388543');
  });

  it('uses the #ffffff marker stroke (or shorthand) for circle outlines', () => {
    // White marker outline — accept either "#fff" or "#ffffff".
    expect(html).toMatch(/#fff(f{3})?/i);
  });

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Missing Logic Activities Over Time');
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
    // Single-series line should be polyline-like; no smoothPath curves.
    expect(svgInner).not.toMatch(/\sC\s/);
  });

  it('throws TypeError when payload.trend is not an array', () => {
    expect(() => renderMissingLogic(/** @type {any} */ ({ trend: 'not-an-array' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderMissingLogic(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderMissingLogic([]);
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });
});
