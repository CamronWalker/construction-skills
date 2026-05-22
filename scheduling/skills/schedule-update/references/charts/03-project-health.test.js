import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderProjectHealth, META } from './03-project-health.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/03-project-health-index-over-time.json'),
  'utf-8'
));

describe('renderProjectHealth', () => {
  const { html, svgInner } = renderProjectHealth(fixture);

  it('uses #2caffe for the line', () => {
    expect(html).toContain('#2caffe');
  });

  it('uses the GOOD marker color #1AA462 (at least one point)', () => {
    expect(html).toContain('#1AA462');
  });

  it('emits the title with the ™ glyph from META', () => {
    expect(META.title).toBe('Project Health Index™ Over Time');
    expect(html).toContain('Project Health Index');
    expect(html).toContain('™');
  });

  it('has empty legend row content', () => {
    expect(html).toMatch(/<div class="legend-row">\s*<\/div>/);
  });

  it('has at least one circle marker', () => {
    expect(svgInner).toMatch(/<circle\b/);
  });

  it('throws TypeError on malformed payload', () => {
    expect(() => renderProjectHealth(/** @type {any} */ ({ trend: 'nope' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderProjectHealth(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderProjectHealth([]);
    expect(empty).toContain('no data');
  });
});
