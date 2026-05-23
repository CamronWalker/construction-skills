// summary-report.test.js — composite renderer (cards + curve + milestones).
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

  it('contains all three section markers', () => {
    expect(html).toContain('class="summary-cards"');
    expect(html).toContain('class="summary-curve"');
    expect(html).toContain('class="summary-milestones"');
  });

  it('contains the top-level project name (HTML-escaped)', () => {
    expect(html).toContain('Wellington New Zealand Temple');
  });

  it('contains the milestone name passed at top level', () => {
    expect(html).toContain('Substantial Completion (Turnover to Owner)');
  });

  it('contains at least one milestone row', () => {
    expect(html).toMatch(/<tr class="milestone-row/);
  });

  it('renders the curve SVG inline', () => {
    // The curve section embeds a <svg ...> element with path data.
    expect(html).toContain('class="summary-curve"');
    expect(html).toContain('<svg');
    // Plan-vs-actual palette colors should show up in the curve SVG.
    expect(html).toContain('#2caffe');  // Planned (light blue)
    expect(html).toContain('#1476b7');  // Actual (dark blue)
  });

  it('shows the cards KPI values', () => {
    // Health 98%, SPI 0.99, quality grade "A-", compression 0%, etc.
    expect(html).toContain('98');               // health
    expect(html).toContain('0.99');             // SPI
    expect(html).toContain('A-');               // quality grade
    expect(html).toContain('553');              // critical path delay
  });

  it('throws TypeError when cards is missing', () => {
    const { cards: _omit, ...withoutCards } = fixture;
    expect(() => renderSummaryReport(/** @type {any} */ (withoutCards))).toThrow(TypeError);
  });

  it('throws TypeError when curve is missing', () => {
    const { curve: _omit, ...withoutCurve } = fixture;
    expect(() => renderSummaryReport(/** @type {any} */ (withoutCurve))).toThrow(TypeError);
  });

  it('throws TypeError when milestones is missing', () => {
    const { milestones: _omit, ...withoutMilestones } = fixture;
    expect(() => renderSummaryReport(/** @type {any} */ (withoutMilestones))).toThrow(TypeError);
  });

  it('throws TypeError when payload is null', () => {
    expect(() => renderSummaryReport(/** @type {any} */ (null))).toThrow(TypeError);
  });

  it('marks late milestones with the .late class', () => {
    // The fixture's row 1 has days_late=385 → must be flagged late.
    expect(html).toMatch(/<tr class="milestone-row late"/);
  });

  it('handles an empty milestones list without crashing', () => {
    const emptyMilestones = {
      ...fixture,
      milestones: { ...fixture.milestones, milestones: [] },
    };
    const { html: emptyHtml } = renderSummaryReport(emptyMilestones);
    // Either the table head only, or the explicit empty-state message.
    expect(emptyHtml).toContain('class="summary-milestones"');
    expect(emptyHtml).toMatch(/no milestones|<th/);
  });
});
