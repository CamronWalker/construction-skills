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

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Window Start Accuracy');
    expect(html).toContain(META.title);
  });

  it('emits all 3 column hexes (red #b00020, yellow #f2c031, green #388543)', () => {
    expect(html).toContain('#b00020');
    expect(html).toContain('#f2c031');
    expect(html).toContain('#388543');
  });

  it('emits all 3 legend labels for the start trio', () => {
    for (const label of ['Started On Time', 'Started Late', 'Did Not Start']) {
      expect(html).toContain(label);
    }
  });

  it('emits MM/DD/YY X-axis labels', () => {
    expect(html).toMatch(/\d{2}\/\d{2}\/\d{2}/);
  });

  it('emits the rotated "Values" Y-axis title', () => {
    expect(html).toContain('Values');
    expect(html).toMatch(/transform="rotate\(-90/);
  });

  it('renders red (Did Not Start) at the bottom of each stack', () => {
    // Parse all data rects (small width, with a colored fill). The lowest
    // segment of each column (largest y+h) should be filled red.
    const rectRe = /<rect\s+x="([\d.]+)"\s+y="([\d.]+)"\s+width="([\d.]+)"\s+height="([\d.]+)"[^>]*fill="(#[0-9A-Fa-f]+)"/g;
    /** @type {Array<{x:number,y:number,w:number,h:number,f:string}>} */
    const rects = [];
    let m;
    while ((m = rectRe.exec(svgInner)) !== null) {
      rects.push({ x: +m[1], y: +m[2], w: +m[3], h: +m[4], f: m[5] });
    }
    // Skip the plot-area frame rect (no fill or very wide).
    const dataRects = rects.filter(r => r.w < 40 && r.f.toLowerCase() !== 'none');
    expect(dataRects.length).toBeGreaterThan(0);
    // Group by x; for each group, the rect with the largest y+h sits at the bottom.
    /** @type {Record<string, typeof dataRects>} */
    const byX = {};
    for (const r of dataRects) {
      const key = r.x.toFixed(1);
      (byX[key] ??= []).push(r);
    }
    let redBottomCount = 0;
    let multiSegCols = 0;
    for (const col of Object.values(byX)) {
      if (col.length < 2) continue;  // single-segment columns aren't a stack test
      multiSegCols++;
      const bottom = col.reduce((a, b) => (a.y + a.h > b.y + b.h ? a : b));
      if (bottom.f.toLowerCase() === '#b00020') redBottomCount++;
    }
    expect(multiSegCols).toBeGreaterThan(0);
    expect(redBottomCount).toBe(multiSegCols);
  });

  it('emits in-segment count labels in bold (Inter 11.2 px, weight 700)', () => {
    // SmartPM convention: black text on green/yellow, white on red.
    expect(html).toMatch(/font-weight="700"[^>]*fill="#000000"/);
    expect(html).toMatch(/font-weight="700"[^>]*fill="#ffffff"/);
  });

  it('emits a total label above each column (medium weight)', () => {
    expect(html).toMatch(/font-weight="500"/);
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
