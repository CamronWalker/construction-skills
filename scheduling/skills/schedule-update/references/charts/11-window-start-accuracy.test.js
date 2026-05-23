import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderWindowStartAccuracy, META } from './11-window-start-accuracy.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/11-window-start-accuracy.json'),
  'utf-8'
));

describe('renderWindowStartAccuracy', () => {
  const { html, svgInner } = renderWindowStartAccuracy(fixture);

  it('emits all 3 column hexes (on-time green / late yellow / did-not red)', () => {
    for (const hex of ['#388543', '#f2c031', '#b00020']) {
      expect(html).toContain(hex);
    }
  });

  it('emits all 3 legend labels for the start trio', () => {
    for (const label of ['Started On Time', 'Started Late', 'Did Not Start']) {
      expect(html).toContain(label);
    }
  });

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Window Start Accuracy');
    expect(html).toContain(META.title);
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });

  it('renders stacked columns whose total height equals the sum of all 3 segments', () => {
    // First row: startedOnTime=5, startedLate=1, didNotStart=8 → total=14.
    // The 3 stacked rects at the first data date should sit directly on top of
    // each other (each segment's top y == the previous segment's bottom y, give
    // or take floating-point), and the combined height should equal one rect
    // sized for value 14 on the same axis.
    //
    // Parse all <rect> elements and find the 3 rects at the leftmost x.
    const rectRe = /<rect\s+x="([\d.]+)"\s+y="([\d.]+)"\s+width="([\d.]+)"\s+height="([\d.]+)"/g;
    /** @type {Array<{x:number,y:number,w:number,h:number}>} */
    const rects = [];
    let m;
    while ((m = rectRe.exec(svgInner)) !== null) {
      rects.push({ x: +m[1], y: +m[2], w: +m[3], h: +m[4] });
    }
    // Exclude the frame rect (width spans the full plot area).
    const dataRects = rects.filter(r => r.w < 30);
    expect(dataRects.length).toBeGreaterThanOrEqual(3);

    const minX = Math.min(...dataRects.map(r => r.x));
    const firstCol = dataRects.filter(r => Math.abs(r.x - minX) < 0.5);
    expect(firstCol.length).toBe(3);
    // Sort top-to-bottom by y ascending — top segment first.
    firstCol.sort((a, b) => a.y - b.y);
    // Adjacent segments should touch: bottom of [i] (y+h) == top of [i+1] (y).
    for (let i = 0; i < firstCol.length - 1; i++) {
      const bot = firstCol[i].y + firstCol[i].h;
      expect(Math.abs(bot - firstCol[i + 1].y)).toBeLessThan(0.5);
    }
  });

  it('throws TypeError when payload.hitRates is not an array', () => {
    expect(() => renderWindowStartAccuracy(/** @type {any} */ ({ hitRates: 'not-an-array' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderWindowStartAccuracy(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderWindowStartAccuracy([]);
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });

  it('accepts a flat array as well as the { hitRates: [...] } envelope', () => {
    const { html: arrHtml } = renderWindowStartAccuracy(fixture.hitRates);
    expect(arrHtml).toContain(META.title);
    expect(arrHtml).toContain('#388543');
  });
});
