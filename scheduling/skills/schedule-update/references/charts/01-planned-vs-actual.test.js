// 01-planned-vs-actual.test.js
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';
import { renderPlannedVsActual, META } from './01-planned-vs-actual.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/01-planned-vs-actual-percent-complete.json'),
  'utf-8',
));

describe('renderPlannedVsActual', () => {
  const { html, svgInner } = renderPlannedVsActual(fixture);

  it('uses all 6 series palette colors', () => {
    for (const hex of ['#b00020', '#2caffe', '#1476b7', '#388543', '#808080', '#cccccc']) {
      expect(html).toContain(hex);
    }
  });

  it('preserves the dashed Scheduled Completion line (stroke-dasharray="8,6")', () => {
    expect(html).toContain('stroke-dasharray="8,6"');
  });

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Planned VS Actual Percent Complete');
    expect(html).toContain(META.title);
  });

  it('emits each legend label', () => {
    for (const label of ['Progress Target', 'Late Date Planned', 'Planned (All Schedules)',
                          'Actual', 'Scheduled Completion', 'Early Date Planned']) {
      expect(html).toContain(label);
    }
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });

  it('throws TypeError on malformed payload (data is non-null non-array)', () => {
    expect(() => renderPlannedVsActual(/** @type {any} */ ({ data: 'not an array' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderPlannedVsActual(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('throws TypeError when payload is a primitive (string)', () => {
    expect(() => renderPlannedVsActual(/** @type {any} */ ('nope'))).toThrow(TypeError);
  });

  it('renders empty-state card when data array is empty', () => {
    const { html: empty } = renderPlannedVsActual({ ...fixture, data: [] });
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });
});
