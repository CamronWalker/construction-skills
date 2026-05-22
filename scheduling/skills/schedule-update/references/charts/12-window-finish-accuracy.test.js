import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderWindowFinishAccuracy, META } from './12-window-finish-accuracy.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/12-window-finish-accuracy.json'),
  'utf-8'
));

describe('renderWindowFinishAccuracy', () => {
  const { html, svgInner } = renderWindowFinishAccuracy(fixture);

  it('emits all 3 column hexes (on-time green / late yellow / did-not red)', () => {
    for (const hex of ['#388543', '#f2c031', '#b00020']) {
      expect(html).toContain(hex);
    }
  });

  it('emits all 3 legend labels for the finish trio', () => {
    for (const label of ['Finished On Time', 'Finished Late', 'Did Not Finish']) {
      expect(html).toContain(label);
    }
  });

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Window Finish Accuracy');
    expect(html).toContain(META.title);
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });

  it('renders stacked columns whose total height equals the sum of all 3 segments', () => {
    // First row: finishedOnTime=5, finishedLate=1, didNotFinish=5 → total=11.
    const rectRe = /<rect\s+x="([\d.]+)"\s+y="([\d.]+)"\s+width="([\d.]+)"\s+height="([\d.]+)"/g;
    /** @type {Array<{x:number,y:number,w:number,h:number}>} */
    const rects = [];
    let m;
    while ((m = rectRe.exec(svgInner)) !== null) {
      rects.push({ x: +m[1], y: +m[2], w: +m[3], h: +m[4] });
    }
    const dataRects = rects.filter(r => r.w < 30);
    expect(dataRects.length).toBeGreaterThanOrEqual(3);

    const minX = Math.min(...dataRects.map(r => r.x));
    const firstCol = dataRects.filter(r => Math.abs(r.x - minX) < 0.5);
    expect(firstCol.length).toBe(3);
    firstCol.sort((a, b) => a.y - b.y);
    for (let i = 0; i < firstCol.length - 1; i++) {
      const bot = firstCol[i].y + firstCol[i].h;
      expect(Math.abs(bot - firstCol[i + 1].y)).toBeLessThan(0.5);
    }
  });

  it('throws TypeError when payload.hitRates is not an array', () => {
    expect(() => renderWindowFinishAccuracy(/** @type {any} */ ({ hitRates: 'not-an-array' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderWindowFinishAccuracy(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderWindowFinishAccuracy([]);
    expect(empty).toContain('no data');
    expect(empty).not.toContain('<svg class="chart-svg"');
  });

  it('accepts a flat array as well as the { hitRates: [...] } envelope', () => {
    const { html: arrHtml } = renderWindowFinishAccuracy(fixture.hitRates);
    expect(arrHtml).toContain(META.title);
    expect(arrHtml).toContain('#388543');
  });
});
