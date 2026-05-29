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

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('SPI Over Time');
    expect(html).toContain(META.title);
  });

  it('emits the 3-zone palette when all 3 zones are represented', () => {
    // Synthetic payload crossing both SPI thresholds (0.80 and 0.90).
    const sample = {
      trend: [
        { dataDate: '2024-01-01T08:00:00', spi: 0.70 },  // red
        { dataDate: '2024-02-01T08:00:00', spi: 0.85 },  // yellow
        { dataDate: '2024-03-01T08:00:00', spi: 1.00 },  // green
      ],
    };
    const { html: out } = renderSpiOverTime(sample);
    expect(out).toContain('#b00020');
    expect(out).toContain('#f2c031');
    expect(out).toContain('#388543');
  });

  it('emits both dashed threshold lines with stroke-dasharray="8,6"', () => {
    // Yellow at SPI = 0.80, green at SPI = 0.90.
    expect(html).toContain('stroke-dasharray="8,6"');
  });

  it('emits the legend swatch color #2caffe', () => {
    expect(html).toContain('#2caffe');
  });

  it('emits MM/DD/YY X-axis labels', () => {
    expect(html).toMatch(/\d{2}\/\d{2}\/\d{2}/);
  });

  it('emits the rotated "Values" Y-axis title', () => {
    expect(html).toContain('Values');
    expect(html).toMatch(/transform="rotate\(-90/);
  });

  it('uses Inter font family', () => {
    expect(html).toContain('Inter');
  });

  it('renders straight segments only (no cubic curves)', () => {
    expect(svgInner).not.toMatch(/\sC\s/);
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
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
    // Both forms produce the same zone palette.
    expect(arrHtml).toContain('#388543');
  });
});
