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

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Monthly Activity Start & Finish Distribution');
    // Title is HTML-escaped (`& → &amp;`).
    expect(html).toContain('Monthly Activity Start &amp; Finish Distribution');
  });

  it('emits every column palette hex (6 series)', () => {
    // Actual Starts/Finishes (blue), Baseline Starts/Finishes (gray),
    // Planned Starts/Finishes (green).
    for (const hex of ['#B4C7E7', '#4472C4', '#cccccc', '#808080', '#C5E0B4', '#70AD47']) {
      expect(html).toContain(hex);
    }
  });

  it('emits the average-line color #F2A623', () => {
    expect(html).toContain('#F2A623');
  });

  it('emits all 7 legend labels', () => {
    for (const label of [
      'Current Starts (Actual)', 'Current Finishes (Actual)',
      'Baseline Starts', 'Baseline Finishes',
      'Current Starts (Planned)', 'Current Finishes (Planned)',
      'Average',
    ]) {
      expect(html).toContain(label);
    }
  });

  it('emits a solid #4472C4 data-date vertical marker (not dashed)', () => {
    // SmartPM convention: dark-blue solid stroke-width 3 at the boundary
    // between Actual and Planned months.
    expect(html).toMatch(/stroke="#4472C4"[^>]*stroke-width="3"/);
  });

  it('emits a data-date label like "DD MMM-YY"', () => {
    // Format: e.g. "26 May-26".
    expect(html).toMatch(/\d{1,2}\s(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{2}/);
  });

  it('formats X-axis ticks as "MMM-YY"', () => {
    // E.g. "Nov-22", "May-26". SmartPM convention (with hyphen, 2-digit year).
    expect(html).toMatch(/>(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-\d{2}</);
  });

  it('emits the rotated "Values" Y-axis title', () => {
    expect(html).toContain('Values');
    expect(html).toMatch(/transform="rotate\(-90/);
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
