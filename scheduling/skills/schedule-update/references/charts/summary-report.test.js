// summary-report.test.js — composite renderer (cards + milestones).
//
// The Plan-vs-Actual curve was removed in May 2026 in favor of a SmartPM-
// styled cards + milestones layout. Payloads with a `curve` field are still
// accepted (the field is ignored) for backward compatibility.
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { renderSummaryReport, META } from './summary-report.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const fixture = JSON.parse(readFileSync(
  resolve(__dirname, 'tests/fixtures/smartpm-summary-report.json'),
  'utf-8'
));

describe('renderSummaryReport', () => {
  const { html, svgInner } = renderSummaryReport(fixture);

  it('emits the canonical title from META', () => {
    expect(META.title).toBe('Schedule Summary Report');
  });

  it('returns empty svgInner (composite has no canonical SVG)', () => {
    expect(svgInner).toBe('');
  });

  it('contains the two visible section markers', () => {
    expect(html).toContain('class="summary-cards"');
    expect(html).toContain('class="summary-milestones"');
  });

  it('does not render a Schedule Summary Report title or subtitle in the body', () => {
    expect(html).not.toMatch(/<h2 class="report-title"/);
    expect(html).not.toMatch(/<p class="report-subtitle"/);
  });

  it('does not render the legacy Plan-vs-Actual curve section', () => {
    expect(html).not.toContain('class="summary-curve"');
    expect(html).not.toContain('Planned VS Actual Percent Complete');
  });

  it('accepts (and ignores) a payload that still carries `curve`', () => {
    // Existing SmartPM chart payloads in the wild still include `curve`.
    // The renderer must not throw on them.
    expect(() => renderSummaryReport(fixture)).not.toThrow();
  });

  it('accepts a payload without `curve` at all', () => {
    const { curve: _omit, ...withoutCurve } = fixture;
    expect(() => renderSummaryReport(/** @type {any} */ (withoutCurve))).not.toThrow();
  });

  it('renders the horizontal pill thermometer SVG', () => {
    // The new Health card uses a 260×62 horizontal gradient pill, not a
    // 60×180 vertical thermometer.
    expect(html).toContain('width="260" height="62"');
    expect(html).toContain('linearGradient id="thermo-grad"');
    // Indicator is a circle, not a horizontal line.
    expect(html).toMatch(/<circle cx="[\d.]+" cy="45" r="7"/);
  });

  it('contains at least one milestone row', () => {
    expect(html).toMatch(/<tr class="milestone-row/);
  });

  it('marks late milestones with the .late class', () => {
    // The fixture's row 1 has days_late=385 → must be flagged late.
    expect(html).toMatch(/<tr class="milestone-row late"/);
  });

  it('shows the cards KPI values', () => {
    expect(html).toContain('98%');              // health
    expect(html).toContain('SPI 0.99');         // performance
    expect(html).toContain('A-');               // quality grade
    expect(html).toContain('553');              // critical path delay days
  });

  it('renders "N/A" for zero compression', () => {
    // The fixture has compression_pct = 0.
    expect(html).toContain('N/A');
  });

  it('renders the Last Period Schedule Changes block as an lpc-grid', () => {
    expect(html).toContain('lpc-title');
    expect(html).toContain('lpc-grid');
    expect(html).toContain('Last Period Schedule Changes');
  });

  it('throws TypeError when cards is missing', () => {
    const { cards: _omit, ...withoutCards } = fixture;
    expect(() => renderSummaryReport(/** @type {any} */ (withoutCards))).toThrow(TypeError);
  });

  it('throws TypeError when milestones is missing', () => {
    const { milestones: _omit, ...withoutMilestones } = fixture;
    expect(() => renderSummaryReport(/** @type {any} */ (withoutMilestones))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderSummaryReport(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('handles an empty milestones list without crashing', () => {
    const emptyMilestones = {
      ...fixture,
      milestones: { ...fixture.milestones, milestones: [] },
    };
    const { html: emptyHtml } = renderSummaryReport(emptyMilestones);
    expect(emptyHtml).toContain('class="summary-milestones"');
    expect(emptyHtml).toMatch(/no milestones|<th/);
  });
});
