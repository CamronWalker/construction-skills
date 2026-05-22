import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderVelocity, META } from './08-velocity.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/08-velocity.json'),
  'utf-8'
));

describe('renderVelocity', () => {
  const { html, svgInner } = renderVelocity(fixture);

  it('emits every column palette hex', () => {
    // Current Starts #B4C7E7, Current Finishes #4472C4,
    // Baseline Starts #cccccc, Baseline Finishes #808080.
    for (const hex of ['#B4C7E7', '#4472C4', '#cccccc', '#808080']) {
      expect(html).toContain(hex);
    }
  });

  it('emits the average-line color #F2A623', () => {
    expect(html).toContain('#F2A623');
  });

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Monthly Activity Start & Finish Distribution');
    // Title is HTML-escaped in output (`& → &amp;`); accept the escaped form.
    expect(html).toContain('Monthly Activity Start &amp; Finish Distribution');
  });

  it('emits all 5 legend labels', () => {
    for (const label of [
      'Current Starts', 'Current Finishes',
      'Baseline Starts', 'Baseline Finishes',
      'Average',
    ]) {
      expect(html).toContain(label);
    }
  });

  it('emits the dashed data-date vertical plotline', () => {
    expect(html).toContain('stroke-dasharray="8,6"');
  });

  it('formats X-axis ticks as "MMM YYYY"', () => {
    // E.g. "Mar 2020", "Jun 2026". 3-letter month abbr + space + 4-digit year.
    expect(html).toMatch(/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{4}/);
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });

  it('throws TypeError when payload.velocityList is not an array', () => {
    expect(() => renderVelocity(/** @type {any} */ ({ velocityList: 'not-an-array' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderVelocity(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderVelocity({ velocityList: [] });
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });

  it('accepts a flat array as well as the { velocityList: [...] } envelope', () => {
    const { html: arrHtml } = renderVelocity(fixture.velocityList);
    expect(arrHtml).toContain('Monthly Activity Start &amp; Finish Distribution');
    expect(arrHtml).toContain('#4472C4');
  });
});
