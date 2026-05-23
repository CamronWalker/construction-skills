import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderScheduleQuality, META } from './02-schedule-quality.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/02-schedule-quality-grade-over-time.json'),
  'utf-8'
));

describe('renderScheduleQuality', () => {
  const { html, svgInner } = renderScheduleQuality(fixture);

  it('uses the single #2caffe line color', () => {
    expect(html).toContain('#2caffe');
  });

  it('has NO Progress Target band fill (#808080 fill-opacity)', () => {
    expect(html).not.toMatch(/fill="#808080" fill-opacity/);
  });

  it('has NO stroke-dasharray="8,6" (single straight line, no plotline)', () => {
    expect(html).not.toContain('stroke-dasharray="8,6"');
  });

  it('has empty legend row content (single-series chart)', () => {
    // The legend-row div exists but contains only whitespace
    expect(html).toMatch(/<div class="legend-row">\s*<\/div>/);
  });

  it('emits the title with the ™ glyph from META', () => {
    expect(META.title).toBe('Schedule Quality Grade™ Over Time');
    expect(html).toContain('Schedule Quality Grade');
    expect(html).toContain('™');
  });

  it('Y-axis includes at least one canonical letter-grade label', () => {
    expect(html).toMatch(/>(A\+|A-?|B\+|B-?|C\+|C-?|D|F)<\/text>/);
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });

  it('throws TypeError when payload is not a list and lacks trend', () => {
    expect(() => renderScheduleQuality(/** @type {any} */ ({ trend: 'nope' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderScheduleQuality(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderScheduleQuality([]);
    expect(empty).toContain('no data');
  });
});
