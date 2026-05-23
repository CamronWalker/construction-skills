import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderScheduleChanges, META } from './04-schedule-changes.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/04-schedule-changes-over-time.json'),
  'utf-8'
));

describe('renderScheduleChanges', () => {
  const { html, svgInner } = renderScheduleChanges(fixture);

  it('uses all 7 palette hex codes', () => {
    // Palette from charts.py:2071-2077 (Chrome MCP DOM inspection 2026-05-21).
    for (const hex of ['#D01010', '#FFC000', '#1AA462', '#0000FF', '#2196F3', '#1476B7', '#DB495B']) {
      expect(html).toContain(hex);
    }
  });

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Schedule Changes Over Time');
    expect(html).toContain(META.title);
  });

  it('emits each of the 7 legend labels', () => {
    // Labels from charts.py:_PVA04_SPLINE_SERIES (lines 2081-2089).
    for (const label of [
      'Critical Changes', 'Near Critical Changes', 'Activity Changes',
      'Logic Changes', 'Calendar Changes', 'Duration Changes',
      'Delayed Activity Changes',
    ]) {
      expect(html).toContain(label);
    }
  });

  it('does NOT include "Total Activities" (column intentionally dropped)', () => {
    expect(html).not.toContain('Total Activities');
  });

  it('returns non-empty svgInner', () => {
    expect(svgInner.length).toBeGreaterThan(100);
  });

  it('throws TypeError on malformed payload', () => {
    expect(() => renderScheduleChanges(/** @type {any} */ ({ summary: 'nope' }))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderScheduleChanges(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('renders empty-state for empty input', () => {
    const { html: empty } = renderScheduleChanges([]);
    expect(empty).toContain('no data');
  });
});
