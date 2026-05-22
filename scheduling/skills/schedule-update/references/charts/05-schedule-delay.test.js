import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderScheduleDelay, META } from './05-schedule-delay.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/05-schedule-delay-over-time.json'),
  'utf-8'
));

describe('renderScheduleDelay', () => {
  const { html, svgInner } = renderScheduleDelay(fixture);

  it('uses every series palette hex', () => {
    // In-Period Delay #b00020, In-Period Gains #388543,
    // Planned Impacts stroke #1476b7 + fill rgba(16, 91, 141, 0.3).
    for (const hex of ['#b00020', '#388543', '#1476b7']) {
      expect(html).toContain(hex);
    }
  });

  it('includes the semi-transparent Planned Impacts fill', () => {
    expect(html).toContain('rgba(16, 91, 141, 0.3)');
  });

  it('emits the canonical title (no ™) from META', () => {
    expect(META.title).toBe('Schedule Delay Over Time');
    expect(html).toContain(META.title);
  });

  it('emits all 3 legend labels', () => {
    for (const label of ['In-Period Delay', 'In-Period Gains', 'Planned Impacts']) {
      expect(html).toContain(label);
    }
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });

  it('renders all 27 non-baseline periods without throwing, emitting a bar per non-zero, non-null value', () => {
    // Period 0 is baseline (skipped). Across the 27 remaining periods:
    //   27 In-Period Delay bars (every period has a non-zero criticalPathDelay)
    //   13 In-Period Gains bars (most criticalPathRecovery values are 0)
    //   21 Planned Impacts bars
    //   = 61 bars total + 1 frame rect = at least 62 <rect> elements.
    const rectMatches = svgInner.match(/<rect/g) ?? [];
    expect(rectMatches.length).toBeGreaterThanOrEqual(62);
    // Sanity: rendering the full fixture didn't bail out.
    expect(svgInner).toContain(`stroke="${'#b00020'}"`);
  });

  it('formats X-axis ticks as "MMM DD, YYYY"', () => {
    // E.g. "Sep 30, 2025" or "May 19, 2026" etc. Look for any 3-letter month abbr.
    expect(html).toMatch(/(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) \d{2}, \d{4}/);
  });

  it('includes a Days of Delay axis title hint', () => {
    expect(html).toContain('Days of Delay');
  });

  it('throws TypeError when payload.data is not an array', () => {
    expect(() => renderScheduleDelay(/** @type {any} */ ({ data: 'not-an-array' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderScheduleDelay(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderScheduleDelay([]);
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });

  it('accepts the { data: [...] } envelope as well as a flat array', () => {
    const { html: envHtml } = renderScheduleDelay({ data: fixture });
    expect(envHtml).toContain(META.title);
    expect(envHtml).toContain('#b00020');
  });
});
