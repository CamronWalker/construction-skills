// summary-report.js — composite "Summary Report" renderer.
//
// Single HTML document, no title / subtitle / curve. Two sections:
//   1. KPI cards  (Project Health Index pill thermometer, Schedule Performance,
//                  Schedule Feasibility) — three equal-width cards. Health has
//                  no card frame; Performance and Feasibility have an inset
//                  gray box with the section title floating above.
//   2. Milestones table + change-log block — column-divided table with all
//                  columns centered except the milestone name; late rows
//                  (days_late > 0) render in red. Change log shows
//                  Selected-Period Critical Path Delays and Last-Period
//                  Recoveries side by side, then a full-width
//                  Last-Period Schedule Changes row.
//
// Returns svgInner: '' (composite has no canonical SVG; consumers reading
// svgInner should fall back to the html field).

import { escapeHtml, parseDate } from './svg-lib.js';

// SmartPM palette — matches charts.py:_SCI_*.
const SCI_GREEN  = '#1AA462';
const SCI_YELLOW = '#FFC000';
const SCI_RED    = '#D01010';
const SMARTPM_RED = '#b00020';

// Report frame is narrower than the chart cards (HTML_CARD_W = 1728) because
// the wide Plan-vs-Actual curve was removed in May 2026. The remaining content
// (cards + milestones) reads cleaner at 1200 px.
const SUMMARY_W = 1200;

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  SUMMARY_W,
  svgHeight: 720,
  title:     'Schedule Summary Report',
};

/**
 * @typedef {Object} SummaryCards
 * @property {{ value: number }} health
 * @property {number} spi
 * @property {number} planned_pct
 * @property {number} actual_pct
 * @property {number} critical_path_delay_days
 * @property {number} planned_impact_days
 * @property {string} quality_grade
 * @property {number} compression_pct
 * @property {string} predicted_completion
 * @property {string} [last_predicted_completion]
 */

/**
 * @typedef {Object} SummaryMilestones
 * @property {string} [project_name]
 * @property {string} [milestone_name]
 * @property {string} [project_location]
 * @property {string} [data_date]
 * @property {Array<{ order: number, name: string,
 *                    contractual: string|null, current: string,
 *                    days_late: number, predicted: string,
 *                    compression_pct: number }>} milestones
 * @property {{ count: number, items: string[] }} [critical_path_delays]
 * @property {{ count: number, items: string[] }} [critical_path_recoveries]
 * @property {{ total: number, critical_path: number,
 *              acceleration_days: number|null }} [last_period_changes]
 */

/**
 * Composite payload. The `curve` field is accepted (and ignored) for
 * backward compatibility with existing chart payloads that still include it.
 *
 * @typedef {Object} SummaryReportPayload
 * @property {string}             [project_name]
 * @property {string}             [milestone_name]
 * @property {SummaryCards}       cards
 * @property {SummaryMilestones}  milestones
 * @property {unknown}            [curve]
 */

/**
 * @param {SummaryReportPayload} payload
 * @returns {import('./svg-lib.js').RenderResult}
 */
export function renderSummaryReport(payload) {
  if (!payload || typeof payload !== 'object') {
    throw new TypeError('expected payload object');
  }
  if (!payload.cards || typeof payload.cards !== 'object') {
    throw new TypeError('expected payload.cards object');
  }
  if (!payload.milestones || typeof payload.milestones !== 'object') {
    throw new TypeError('expected payload.milestones object');
  }

  const cardsHtml = renderCardsSection(payload.cards);
  const milestonesHtml = renderMilestonesSection(payload.milestones);

  const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${escapeHtml(META.title)}</title>
<style>
  html, body { margin: 0; padding: 0; background: #fff;
    font-family: Inter, "Helvetica Neue", Arial, sans-serif;
    color: #181d27; -webkit-font-smoothing: antialiased; }
  .chart-card { width: ${SUMMARY_W}px; box-sizing: border-box;
    background: #fff; padding: 24px 32px; }

  /* ---- Cards section ----
     Card widths are unequal because the cards' content shapes differ:
       - Health holds a fixed-width 260 px thermometer pill.
       - Performance has SPI + two progress bars + two day-counters (densest).
       - Feasibility has three centered text columns.
     1 / 1.5 / 1.3 gives Performance the most room without making Health look
     starved next to it. */
  .summary-cards { display: flex; gap: 24px; margin-bottom: 24px;
    align-items: flex-start; }
  .summary-card { flex: 1 1 0; }
  .summary-card.card-performance { flex: 1.5 1 0; }
  .summary-card.card-feasibility { flex: 1.3 1 0; }
  .summary-card h4 { margin: 0 0 10px 0; font-size: 13px; font-weight: 700;
    color: #222; }
  .card-inner { background: #fafafa; border: 1px solid #e6e6e6;
    border-radius: 10px; padding: 16px 20px; min-height: 130px;
    box-sizing: border-box; }
  /* Health card has no inset box — the gradient pill is the card. */
  .card-health .thermo-wrap { padding: 4px 0; }

  .perf-row { display: flex; gap: 16px; align-items: stretch; }
  .perf-left { flex: 1.6 1 0; display: flex; flex-direction: column; gap: 4px; }
  .perf-metric { flex: 1 1 0; text-align: center; display: flex;
    flex-direction: column; justify-content: center; }
  .spi { font-size: 16px; font-weight: 700; color: #222; margin-bottom: 6px; }
  .bar-label { font-size: 11px; color: #444; line-height: 1.2; }
  .bar-track { background: #ececec; height: 6px; border-radius: 3px;
    margin: 2px 0 4px 0; overflow: hidden; }
  .bar-fill { height: 100%; border-radius: 3px; }
  .metric-label { font-size: 11px; color: #444; line-height: 1.2; }
  .metric-num { font-size: 28px; font-weight: 700; color: #222;
    line-height: 1.1; margin-top: 2px; }
  .metric-unit { font-size: 11px; color: #444; }

  .feas-row { display: flex; gap: 16px; }
  .feas-cell { flex: 1 1 0; text-align: center; display: flex;
    flex-direction: column; align-items: center; }
  .qg { font-size: 32px; font-weight: 700; line-height: 1; margin-top: 6px; }
  .comp { font-size: 28px; font-weight: 700; line-height: 1; margin-top: 6px; }
  .pc { margin-top: 4px; line-height: 1; }
  .pc-month { font-size: 12px; font-weight: 600; }
  .pc-day   { font-size: 26px; font-weight: 700; line-height: 1.05; }
  .pc-year  { font-size: 11px; font-weight: 600; }
  .pc-delta { font-size: 11px; margin-top: 4px; }

  /* ---- Milestones section ---- */
  .summary-milestones h4 { margin: 0 0 8px 0; font-size: 13px;
    font-weight: 700; color: #222; }
  .summary-milestones table { width: 100%; border-collapse: collapse;
    border: 1px solid #e6e6e6; border-radius: 6px; overflow: hidden;
    font-size: 12px; margin-top: 8px; }
  .summary-milestones th, .summary-milestones td { padding: 10px 12px;
    text-align: center; vertical-align: middle;
    border-bottom: 1px solid #e6e6e6; border-right: 1px solid #e6e6e6; }
  .summary-milestones td { padding: 12px 12px; }
  .summary-milestones th:last-child,
  .summary-milestones td:last-child { border-right: none; }
  .summary-milestones th:nth-child(2),
  .summary-milestones td:nth-child(2) { text-align: left; }
  .summary-milestones th { background: #F2F2F2; color: #222; font-weight: 700; }
  .milestone-row.late td { color: ${SMARTPM_RED}; }
  .empty-milestones { font-size: 12px; color: #888; padding: 8px 0;
    text-align: center; }

  /* ---- Change-log block ---- */
  .change-summary .cp-row { display: flex; gap: 24px; margin-top: 16px; }
  .change-summary .cp-col { flex: 1 1 0; font-size: 12px; color: #333; }
  .change-summary .cp-col strong { color: #222; }
  .change-summary .cp-col ul { margin: 6px 0 0 18px; padding: 0; }
  .change-summary .lpc-title { margin-top: 18px; font-size: 12px;
    color: #222; font-weight: 700; }
  .change-summary .lpc-grid { display: flex; gap: 24px; margin-top: 6px;
    font-size: 12px; color: #333; }
  .change-summary .lpc-grid > div { flex: 1 1 0; }
</style>
</head>
<body>
<div class="chart-card">
  ${cardsHtml}
  ${milestonesHtml}
</div>
</body>
</html>
`;
  return { html, svgInner: '' };
}

// =================================================================
// Section 1: Cards
// =================================================================

/** @param {SummaryCards} cards @returns {string} */
function renderCardsSection(cards) {
  return `<section class="summary-cards">
${renderHealthCard(cards)}
${renderPerformanceCard(cards)}
${renderFeasibilityCard(cards)}
</section>`;
}

/** @param {SummaryCards} cards @returns {string} */
function renderHealthCard(cards) {
  const value = Math.max(0, Math.min(100, Number(cards.health?.value ?? 0)));
  const valueColor =
    value >= 75 ? SCI_GREEN
    : value >= 50 ? SCI_YELLOW
    : SCI_RED;

  // Bar geometry: inner runs from x=18 to x=242 (width 224).
  const indX = 18 + (value / 100) * 224;
  // Clamp the % label's x so its right edge doesn't get clipped at the SVG
  // bound. At font-size 24, "100%" half-width is ~22 px.
  const labelX = Math.min(Math.max(indX, 26), 234);

  const svg = `<svg width="260" height="62" viewBox="0 0 260 62" xmlns="http://www.w3.org/2000/svg">
  <defs><linearGradient id="thermo-grad" x1="0%" x2="100%">
    <stop offset="0%" stop-color="${SCI_RED}"/>
    <stop offset="50%" stop-color="${SCI_YELLOW}"/>
    <stop offset="100%" stop-color="${SCI_GREEN}"/>
  </linearGradient></defs>
  <rect x="18" y="38" width="224" height="14" rx="7" ry="7" fill="url(#thermo-grad)" />
  <text x="${labelX.toFixed(1)}" y="26" text-anchor="middle" font-size="24" font-weight="700" fill="${valueColor}">${Math.round(value)}%</text>
  <circle cx="${indX.toFixed(1)}" cy="45" r="7" fill="#fff" stroke="#222" stroke-width="2" />
</svg>`;

  return `<div class="summary-card card-health">
  <h4>Project Health Index&trade;</h4>
  <div class="thermo-wrap">${svg}</div>
</div>`;
}

/** @param {SummaryCards} cards @returns {string} */
function renderPerformanceCard(cards) {
  const spi = Number(cards.spi ?? 0).toFixed(2);
  const plannedPct = Math.max(0, Math.min(100, Math.round(Number(cards.planned_pct ?? 0))));
  const actualPct  = Math.max(0, Math.min(100, Math.round(Number(cards.actual_pct  ?? 0))));
  const cpd = Math.round(Number(cards.critical_path_delay_days ?? 0));
  const pi  = Math.round(Number(cards.planned_impact_days ?? 0));

  return `<div class="summary-card card-performance">
  <h4>Schedule Performance</h4>
  <div class="card-inner">
    <div class="perf-row">
      <div class="perf-left">
        <div class="spi">SPI ${spi}</div>
        <div class="bar-label">Planned (${plannedPct}%)</div>
        <div class="bar-track"><div class="bar-fill" style="width:${plannedPct}%;background:${SMARTPM_RED};"></div></div>
        <div class="bar-label">Actual (${actualPct}%)</div>
        <div class="bar-track"><div class="bar-fill" style="width:${actualPct}%;background:${SCI_GREEN};"></div></div>
      </div>
      <div class="perf-metric">
        <div class="metric-label">Critical Path<br>Delay</div>
        <div class="metric-num">${cpd}</div>
        <div class="metric-unit">Days</div>
      </div>
      <div class="perf-metric">
        <div class="metric-label">Planned<br>Impact</div>
        <div class="metric-num">${pi}</div>
        <div class="metric-unit">Days</div>
      </div>
    </div>
  </div>
</div>`;
}

/** @param {SummaryCards} cards @returns {string} */
function renderFeasibilityCard(cards) {
  const qg = String(cards.quality_grade ?? '');
  const qgUp = qg.toUpperCase();
  // Binary A/B-vs-else tiering matches the matplotlib reference
  // (charts.py:990). A/B → green, everything else → red.
  const qgColor =
    qgUp.startsWith('A') || qgUp.startsWith('B') ? SCI_GREEN
    : SCI_RED;

  const comp = Math.round(Number(cards.compression_pct ?? 0));
  const compColor =
    comp >= 25 ? SCI_RED
    : comp >= 15 ? SCI_YELLOW
    : SCI_GREEN;
  const compDisplay = comp === 0 ? 'N/A' : (comp + '%');

  const pcStr = String(cards.predicted_completion ?? '');
  // Pre-prediction state (week 1 of a project, or before SmartPM has accumulated
  // enough schedule updates to compute a predicted end date): mirror SmartPM's
  // own "N/A / N/A" treatment in its dashboard so the cell isn't a blank slot.
  let pcMonth = '', pcDay = 'N/A', pcYear = 'N/A';
  let pcColor = SCI_GREEN;
  let deltaHtml = '';
  if (pcStr) {
    const pcd = parseDate(pcStr);
    pcMonth = pcd.toLocaleString('en-US', { month: 'short', timeZone: 'UTC' });
    pcDay   = String(pcd.getUTCDate()).padStart(2, '0');
    pcYear  = String(pcd.getUTCFullYear());

    const lastStr = cards.last_predicted_completion;
    if (lastStr) {
      const lastPcd = parseDate(lastStr);
      if (pcd.getTime() !== lastPcd.getTime()) {
        const slipped = pcd.getTime() > lastPcd.getTime();
        const arrow = slipped ? '&#9650;' : '&#9660;';   // ▲ or ▼
        const deltaColor = slipped ? SCI_RED : SCI_GREEN;
        pcColor = deltaColor;
        const lastMonth = lastPcd.toLocaleString('en-US', { month: 'short', timeZone: 'UTC' });
        const lastDay = String(lastPcd.getUTCDate()).padStart(2, '0');
        const lastYear = String(lastPcd.getUTCFullYear());
        deltaHtml = `<div class="pc-delta" style="color: ${deltaColor};">${arrow} ${lastMonth} ${lastDay}, ${lastYear}</div>`;
      }
    }
  }

  return `<div class="summary-card card-feasibility">
  <h4>Schedule Feasibility</h4>
  <div class="card-inner">
    <div class="feas-row">
      <div class="feas-cell">
        <div class="metric-label">Schedule<br>Quality Grade&trade;</div>
        <div class="qg" style="color: ${qgColor};">${escapeHtml(qg)}</div>
      </div>
      <div class="feas-cell">
        <div class="metric-label">Schedule Compression<br>Index&trade;</div>
        <div class="comp" style="color: ${compColor};">${compDisplay}</div>
      </div>
      <div class="feas-cell">
        <div class="metric-label">Predicted<br>Completion</div>
        <div class="pc" style="color: ${pcColor};">
          <div class="pc-month">${pcMonth}</div>
          <div class="pc-day">${pcDay}</div>
          <div class="pc-year">${pcYear}</div>
        </div>
        ${deltaHtml}
      </div>
    </div>
  </div>
</div>`;
}

// =================================================================
// Section 2: Milestones table + change-log block
// =================================================================

/**
 * @param {SummaryMilestones} m
 * @returns {string}
 */
function renderMilestonesSection(m) {
  const milestones = Array.isArray(m.milestones) ? m.milestones : [];
  const delays = m.critical_path_delays ?? { count: 0, items: [] };
  const recov  = m.critical_path_recoveries ?? { count: 0, items: [] };
  const lpc    = m.last_period_changes ?? { total: 0, critical_path: 0, acceleration_days: null };

  const headers = ['Order', 'Milestone', 'Contractual', 'Current', 'Days Late', 'Predicted', 'Compression'];
  const thead = `<thead><tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>`;

  let tbody = '';
  if (!milestones.length) {
    tbody = `<tbody><tr><td colspan="${headers.length}" class="empty-milestones">no milestones</td></tr></tbody>`;
  } else {
    const rows = milestones.map(row => {
      const daysLate = Number(row.days_late ?? 0);
      const lateClass = daysLate > 0 ? ' late' : '';
      const compression = Number(row.compression_pct ?? 0);
      return `<tr class="milestone-row${lateClass}">` +
        `<td>${escapeHtml(String(row.order ?? ''))}</td>` +
        `<td>${escapeHtml(String(row.name ?? ''))}</td>` +
        `<td>${escapeHtml(fmtDate(row.contractual))}</td>` +
        `<td>${escapeHtml(fmtDate(row.current))}</td>` +
        `<td>${escapeHtml(String(daysLate))}</td>` +
        `<td>${escapeHtml(fmtDate(row.predicted))}</td>` +
        `<td>${escapeHtml(String(compression))}%</td>` +
        `</tr>`;
    }).join('\n');
    tbody = `<tbody>${rows}</tbody>`;
  }

  const delayBullets = (delays.items ?? []).slice(0, 6)
    .map(it => `<li>${escapeHtml(String(it))}</li>`).join('');
  const recovBullets = (recov.items ?? []).slice(0, 6)
    .map(it => `<li>${escapeHtml(String(it))}</li>`).join('');
  const recovLabel = (recov.count ?? 0) === 0 ? 'N/A' : String(recov.count);
  const accelStr = lpc.acceleration_days === null || lpc.acceleration_days === undefined
    ? 'N/A' : String(lpc.acceleration_days);

  const changeSummary = `<div class="change-summary">
  <div class="cp-row">
    <div class="cp-col">
      <div><strong>Selected Period Critical Path Delays:</strong> ${Number(delays.count ?? 0)}</div>
      ${delayBullets ? '<ul>' + delayBullets + '</ul>' : ''}
    </div>
    <div class="cp-col">
      <div><strong>Last Period Critical Path Recoveries:</strong> ${escapeHtml(recovLabel)}</div>
      ${recovBullets ? '<ul>' + recovBullets + '</ul>' : ''}
    </div>
  </div>
  <div class="lpc-title">Last Period Schedule Changes</div>
  <div class="lpc-grid">
    <div>Total Changes: <strong>${Number(lpc.total ?? 0)}</strong></div>
    <div>Critical Path Changes: <strong>${Number(lpc.critical_path ?? 0)}</strong></div>
    <div>Acceleration Days: <strong>${escapeHtml(accelStr)}</strong></div>
  </div>
</div>`;

  return `<section class="summary-milestones">
  <h4>Milestones</h4>
  <table>
    ${thead}
    ${tbody}
  </table>
  ${changeSummary}
</section>`;
}

/**
 * ISO YYYY-MM-DD → MM/DD/YY. Returns 'N/A' for null/empty.
 * @param {string|null|undefined} iso
 * @returns {string}
 */
function fmtDate(iso) {
  if (!iso) return 'N/A';
  try {
    const d = parseDate(String(iso));
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(d.getUTCDate()).padStart(2, '0');
    const yy = String(d.getUTCFullYear()).slice(-2);
    return `${mm}/${dd}/${yy}`;
  } catch {
    return String(iso).slice(0, 10);
  }
}
