// summary-report.js — composite "Summary Report" renderer.
//
// Bundles three sections into a single self-contained HTML document:
//   1. KPI cards  (Project Health Index thermometer, Schedule Performance,
//                  Schedule Feasibility) — three flex-row cards
//   2. Plan-vs-Actual curve — simplified chart 01 (no Progress Target band,
//                  no Late Date Planned series; just Planned / Actual /
//                  Scheduled / data-date plotline)
//   3. Milestones table — header bullets above an HTML table with one row
//                  per milestone; late rows (days_late > 0) get the .late
//                  class so CSS can color the text red
//
// Ports charts.py:render_summary_cards + render_summary_plan_vs_actual +
// render_summary_milestones, plus the PIL stitching in
// render.py:_composite_summary_report — all into one HTML envelope.
//
// Returns svgInner: '' (composite has no canonical SVG; downstream consumers
// reading svgInner for embedding get the empty string and should fall back
// to the html field).

import {
  HTML_CARD_W,
  dateToX, pctToY, smoothPath, xTicks, parseDate,
  escapeHtml,
} from './svg-lib.js';

// SmartPM palette — matches charts.py:_SCI_* + the curve colors from chart 01.
const SCI_GREEN  = '#1AA462';
const SCI_YELLOW = '#FFC000';
const SCI_RED    = '#D01010';
const SMARTPM_RED = '#b00020';

// Curve palette — subset of chart 01.
const C_PLANNED   = '#2caffe';   // light blue — Planned
const C_ACTUAL    = '#1476b7';   // dark blue  — Actual
const C_SCHEDULED = '#388543';   // green dashed — Scheduled Completion
const C_DATA_DATE = '#cccccc';   // gray dashed — data-date plotline
const C_GRID      = '#e6e6e6';
const C_AXIS_TEXT = '#666';

/** @type {{ svgWidth: number, svgHeight: number, title: string }} */
export const META = {
  svgWidth:  HTML_CARD_W,
  svgHeight: 1100,
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
 * @typedef {Object} SummaryCurve
 * @property {Record<string,string>} [percentCompleteTypes]
 * @property {Array<{ DATE: string, ACTUAL: number|null, SCHEDULED: number|null,
 *                    PLANNED: number|null, LATE_DATE_PLANNED?: number|null,
 *                    PREDICTIVE?: number|null }>} data
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
 * @typedef {Object} SummaryReportPayload
 * @property {string}             [project_name]
 * @property {string}             [milestone_name]
 * @property {SummaryCards}       cards
 * @property {SummaryCurve}       curve
 * @property {SummaryMilestones}  milestones
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
  if (!payload.curve || typeof payload.curve !== 'object') {
    throw new TypeError('expected payload.curve object');
  }
  if (!payload.milestones || typeof payload.milestones !== 'object') {
    throw new TypeError('expected payload.milestones object');
  }

  const projectName = payload.project_name ?? payload.milestones.project_name ?? '';
  const milestoneName = payload.milestone_name ?? payload.milestones.milestone_name ?? '';

  const cardsHtml = renderCardsSection(payload.cards);
  const curveHtml = renderCurveSection(payload.curve);
  const milestonesHtml = renderMilestonesSection(
    payload.milestones,
    projectName,
    milestoneName,
  );

  const titleEsc = escapeHtml(META.title);
  const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>${titleEsc}</title>
<style>
  html, body { margin: 0; padding: 0; background: #fff;
    font-family: Inter, "Helvetica Neue", Arial, sans-serif;
    color: #181d27; -webkit-font-smoothing: antialiased; }
  .chart-card { width: ${HTML_CARD_W}px; box-sizing: border-box;
    background: #fff; padding: 24px 32px; }
  .report-title { font-size: 18px; font-weight: 700; margin: 0 0 6px 0;
    color: ${SMARTPM_RED}; }
  .report-subtitle { font-size: 12px; color: #555; margin: 0 0 16px 0; }

  /* ---- Cards section ---- */
  .summary-cards { display: flex; gap: 16px; margin-bottom: 24px; }
  .summary-card { flex: 1 1 0; background: #fff;
    border: 1px solid #e6e6e6; border-radius: 12px;
    padding: 14px 18px; box-sizing: border-box; min-height: 230px; }
  .summary-card h4 { margin: 0 0 12px 0; font-size: 13px; font-weight: 700;
    color: #222; }
  .summary-card .sublabel { font-size: 11px; color: #444; line-height: 1.25; }
  .summary-card .big { font-size: 28px; font-weight: 700; line-height: 1; }
  .summary-card .mid { font-size: 18px; font-weight: 700; line-height: 1; }
  .summary-card .small { font-size: 11px; color: #444; }

  /* ---- Curve section ---- */
  .summary-curve { margin-bottom: 24px; }
  .summary-curve h4 { margin: 0 0 8px 0; font-size: 13px; font-weight: 700;
    color: #222; }
  .axis-text { font-size: 11px; fill: ${C_AXIS_TEXT}; }
  .axis-text-y { text-anchor: end; }
  .axis-text-x { text-anchor: middle; }
  .grid-line { stroke: ${C_GRID}; stroke-width: 1; stroke-dasharray: 2,3; }
  .legend-row { display: flex; flex-wrap: wrap; align-items: center;
    gap: 6px 18px; font-size: 11px; color: #181d27; padding-top: 6px; }
  .legend-item { display: inline-flex; align-items: center; gap: 6px;
    white-space: nowrap; }

  /* ---- Milestones section ---- */
  .summary-milestones h4 { margin: 0 0 8px 0; font-size: 13px; font-weight: 700;
    color: #222; }
  .summary-milestones .meta-row { font-size: 12px; color: #333;
    margin: 0 0 4px 0; }
  .summary-milestones .meta-row strong { color: #222; }
  .summary-milestones .change-summary { font-size: 12px; color: #333;
    margin: 12px 0 8px 0; }
  .summary-milestones .change-summary ul { margin: 4px 0 4px 18px;
    padding: 0; }
  .summary-milestones table { width: 100%; border-collapse: collapse;
    font-size: 12px; margin-top: 8px; }
  .summary-milestones th, .summary-milestones td { padding: 6px 12px;
    text-align: left; border-bottom: 1px solid #e6e6e6; }
  .summary-milestones th { background: #F2F2F2; color: #222;
    font-weight: 700; }
  .milestone-row.late td { color: ${SMARTPM_RED}; }
  .milestone-row .num { text-align: right; }
  .empty-milestones { font-size: 12px; color: #888; padding: 8px 0; }
</style>
</head>
<body>
<div class="chart-card">
  <h2 class="report-title">${titleEsc}</h2>
  <p class="report-subtitle">${escapeHtml(projectName)}${milestoneName ? ' &mdash; ' + escapeHtml(milestoneName) : ''}</p>
  ${cardsHtml}
  ${curveHtml}
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

/**
 * @param {SummaryCards} cards
 * @returns {string}
 */
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
  const color = value >= 75 ? SCI_GREEN : value >= 50 ? SCI_YELLOW : SCI_RED;

  // Vertical thermometer SVG — 60px wide, 180px tall, color bands and an
  // indicator line at the actual value.
  const w = 60, h = 180;
  const barX = 22, barW = 16;
  // Band coordinates: bottom = 0%, top = 100%.
  // Red 0-50, Yellow 50-75, Green 75-100.
  const redY    = h - (50 / 100) * h;   // top of red band
  const yelY    = h - (75 / 100) * h;   // top of yellow band
  const greenY  = 0;                    // top of green band
  const indY    = h - (value / 100) * h;

  const svg = `<svg width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" xmlns="http://www.w3.org/2000/svg">
  <rect x="${barX}" y="${redY}"   width="${barW}" height="${h - redY}" fill="${SCI_RED}" />
  <rect x="${barX}" y="${yelY}"   width="${barW}" height="${redY - yelY}" fill="${SCI_YELLOW}" />
  <rect x="${barX}" y="${greenY}" width="${barW}" height="${yelY - greenY}" fill="${SCI_GREEN}" />
  <line x1="${barX - 6}" y1="${indY}" x2="${barX + barW + 6}" y2="${indY}" stroke="#222" stroke-width="2.5" />
</svg>`;

  return `<div class="summary-card">
  <h4>Project Health Index&trade;</h4>
  <div style="display: flex; align-items: center; gap: 16px;">
    ${svg}
    <div>
      <div class="big" style="color: ${color};">${Math.round(value)}%</div>
      <div class="small">Overall Health</div>
    </div>
  </div>
</div>`;
}

/** @param {SummaryCards} cards @returns {string} */
function renderPerformanceCard(cards) {
  const spi = Number(cards.spi ?? 0);
  const plannedPct = Math.max(0, Math.min(100, Math.round(Number(cards.planned_pct ?? 0))));
  const actualPct  = Math.max(0, Math.min(100, Math.round(Number(cards.actual_pct  ?? 0))));
  const cpd = Math.round(Number(cards.critical_path_delay_days ?? 0));
  const pi  = Math.round(Number(cards.planned_impact_days ?? 0));

  return `<div class="summary-card">
  <h4>Schedule Performance</h4>
  <div style="display: flex; gap: 16px;">
    <div style="flex: 1.4 1 0;">
      <div class="mid" style="color: #333;">SPI ${spi.toFixed(2)}</div>
      <div style="margin-top: 12px;">
        <div class="sublabel">Planned (${plannedPct}%)</div>
        <div style="background: #f0f0f0; height: 8px; border-radius: 4px; margin: 4px 0 10px 0;">
          <div style="background: ${SMARTPM_RED}; width: ${plannedPct}%; height: 100%; border-radius: 4px;"></div>
        </div>
        <div class="sublabel">Actual (${actualPct}%)</div>
        <div style="background: #f0f0f0; height: 8px; border-radius: 4px; margin: 4px 0 0 0;">
          <div style="background: ${SCI_GREEN}; width: ${actualPct}%; height: 100%; border-radius: 4px;"></div>
        </div>
      </div>
    </div>
    <div style="flex: 1 1 0; display: flex; justify-content: space-around; align-items: center;">
      <div style="text-align: center;">
        <div class="sublabel">Critical Path<br>Delay</div>
        <div class="big" style="color: #222; margin-top: 6px;">${cpd}</div>
        <div class="small">Days</div>
      </div>
      <div style="text-align: center;">
        <div class="sublabel">Planned<br>Impact</div>
        <div class="big" style="color: #222; margin-top: 6px;">${pi}</div>
        <div class="small">Days</div>
      </div>
    </div>
  </div>
</div>`;
}

/** @param {SummaryCards} cards @returns {string} */
function renderFeasibilityCard(cards) {
  const qg = String(cards.quality_grade ?? '');
  const comp = Math.round(Number(cards.compression_pct ?? 0));
  const pcStr = String(cards.predicted_completion ?? '');
  const lastPcStr = cards.last_predicted_completion;

  const qgUp = qg.toUpperCase();
  const qgColor =
    qgUp.startsWith('A') || qgUp.startsWith('B') ? SCI_GREEN
    : qgUp.startsWith('C') ? SCI_YELLOW
    : SCI_RED;

  const compColor = comp >= 25 ? SCI_RED : comp >= 15 ? SCI_YELLOW : SCI_GREEN;

  /** @type {string} */
  let pcMonth = '', pcDay = '', pcYear = '';
  if (pcStr) {
    const d = parseDate(pcStr);
    pcMonth = d.toLocaleString('en-US', { month: 'short', timeZone: 'UTC' });
    pcDay   = String(d.getUTCDate()).padStart(2, '0');
    pcYear  = String(d.getUTCFullYear());
  }

  let deltaHtml = '';
  if (lastPcStr && pcStr) {
    const newDate = parseDate(pcStr);
    const oldDate = parseDate(lastPcStr);
    const slipped = newDate.getTime() > oldDate.getTime();
    if (newDate.getTime() !== oldDate.getTime()) {
      const arrow = slipped ? '&#9650;' : '&#9660;';   // ▲ or ▼
      const dColor = slipped ? SCI_RED : SCI_GREEN;
      const oldDay = String(oldDate.getUTCDate()).padStart(2, '0');
      const oldMonth = oldDate.toLocaleString('en-US', { month: 'short', timeZone: 'UTC' });
      const oldYear = String(oldDate.getUTCFullYear());
      deltaHtml = `<div class="small" style="color: ${dColor}; margin-top: 4px;">${arrow} ${oldMonth} ${oldDay}, ${oldYear}</div>`;
    }
  }

  return `<div class="summary-card">
  <h4>Schedule Feasibility</h4>
  <div style="display: flex; gap: 8px; align-items: center; justify-content: space-around;">
    <div style="text-align: center;">
      <div class="sublabel">Schedule<br>Quality Grade&trade;</div>
      <div style="font-size: 30px; font-weight: 700; color: ${qgColor}; margin-top: 8px; line-height: 1;">${escapeHtml(qg)}</div>
    </div>
    <div style="text-align: center;">
      <div class="sublabel">Schedule Compression<br>Index&trade;</div>
      <div class="big" style="color: ${compColor}; margin-top: 8px;">${comp}%</div>
    </div>
    <div style="text-align: center;">
      <div class="sublabel">Predicted<br>Completion</div>
      <div style="margin-top: 6px;">
        <div style="font-size: 12px; color: ${SCI_GREEN};">${pcMonth}</div>
        <div style="font-size: 26px; font-weight: 700; color: ${SCI_GREEN}; line-height: 1;">${pcDay}</div>
        <div style="font-size: 11px; color: ${SCI_GREEN};">${pcYear}</div>
      </div>
      ${deltaHtml}
    </div>
  </div>
</div>`;
}

// =================================================================
// Section 2: Plan-vs-Actual curve (simplified chart 01)
// =================================================================

/**
 * @param {SummaryCurve} curve
 * @returns {string}
 */
function renderCurveSection(curve) {
  const rows = Array.isArray(curve?.data) ? curve.data : [];

  if (!rows.length) {
    return `<section class="summary-curve">
  <h4>Planned VS Actual Percent Complete</h4>
  <div style="font-size: 12px; color: #888;">(no curve data)</div>
</section>`;
  }

  const svgW = HTML_CARD_W - 64;   // matches outer padding 32px each side
  const svgH = 360;
  const padT = 14, padR = 32, padB = 30, padL = 56;
  const x0 = padL, x1 = svgW - padR;
  const y0 = padT, y1 = svgH - padB;

  const dates = rows.map(r => parseDate(String(r.DATE)));
  const dmin = new Date(Math.min(...dates.map(d => d.getTime())));
  const dmax = new Date(Math.max(...dates.map(d => d.getTime())));

  // Find data-date: last row with non-null ACTUAL.
  /** @type {Date|null} */
  let dataDate = null;
  for (const r of rows) {
    if (r.ACTUAL !== null && r.ACTUAL !== undefined) {
      dataDate = parseDate(String(r.DATE));
    }
  }

  /** @param {string} field @returns {Array<[number, number]>} */
  const seriesPts = (field) => {
    /** @type {Array<[number, number]>} */
    const out = [];
    for (const r of rows) {
      const v = /** @type {any} */ (r)[field];
      if (v === null || v === undefined) continue;
      const d = parseDate(String(r.DATE));
      out.push([dateToX(d, dmin, dmax, x0, x1), pctToY(Number(v), y0, y1)]);
    }
    return out;
  };

  const ptsPlanned   = seriesPts('PLANNED');
  const ptsActual    = seriesPts('ACTUAL');
  const ptsScheduled = seriesPts('SCHEDULED');

  // Gridlines + Y labels at 0/25/50/75/100.
  const gridlines = [];
  const yLabels = [];
  for (const pct of [0, 25, 50, 75, 100]) {
    const y = pctToY(pct, y0, y1);
    gridlines.push(`<line x1="${x0}" y1="${y.toFixed(1)}" x2="${x1}" y2="${y.toFixed(1)}" class="grid-line" />`);
    yLabels.push(`<text x="${x0 - 8}" y="${(y + 4).toFixed(1)}" class="axis-text axis-text-y">${pct} %</text>`);
  }

  // X labels.
  const xLabels = [];
  for (const d of xTicks(dmin, dmax)) {
    const x = dateToX(d, dmin, dmax, x0, x1);
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0');
    const dd = String(d.getUTCDate()).padStart(2, '0');
    const yy = String(d.getUTCFullYear()).slice(-2);
    xLabels.push(`<text x="${x.toFixed(1)}" y="${y1 + 18}" class="axis-text axis-text-x">${mm}/${dd}/${yy}</text>`);
  }

  let plotLine = '';
  if (dataDate) {
    const dx = dateToX(dataDate, dmin, dmax, x0, x1);
    plotLine = `<line x1="${dx.toFixed(1)}" y1="${y0}" x2="${dx.toFixed(1)}" y2="${y1}" stroke="${C_DATA_DATE}" stroke-width="2" stroke-dasharray="8,6" />`;
  }

  const seriesSvg = [];
  if (plotLine) seriesSvg.push(plotLine);
  if (ptsPlanned.length) {
    seriesSvg.push(`<path d="${smoothPath(ptsPlanned)}" fill="none" stroke="${C_PLANNED}" stroke-width="2" />`);
  }
  if (ptsActual.length) {
    seriesSvg.push(`<path d="${smoothPath(ptsActual)}" fill="none" stroke="${C_ACTUAL}" stroke-width="2" />`);
  }
  if (ptsScheduled.length) {
    seriesSvg.push(`<path d="${smoothPath(ptsScheduled)}" fill="none" stroke="${C_SCHEDULED}" stroke-width="2" stroke-dasharray="8,6" />`);
  }

  const frame = `<rect x="${x0}" y="${y0}" width="${x1 - x0}" height="${y1 - y0}" fill="none" stroke="${C_GRID}" stroke-width="1" />`;

  const svgInner = [...gridlines, frame, ...yLabels, ...xLabels, ...seriesSvg].join('\n');

  // Inline legend
  const legend = [
    { color: C_PLANNED,   dash: '',    label: 'Planned' },
    { color: C_ACTUAL,    dash: '',    label: 'Actual' },
    { color: C_SCHEDULED, dash: '8,6', label: 'Scheduled Completion' },
    { color: C_DATA_DATE, dash: '8,6', label: 'Data Date' },
  ];
  const legendHtml = legend.map(({ color, dash, label }) => {
    const dashAttr = dash ? ` stroke-dasharray="${dash}"` : '';
    return `<span class="legend-item">` +
      `<svg width="26" height="10" viewBox="0 0 26 10">` +
      `<line x1="0" y1="5" x2="26" y2="5" stroke="${color}" stroke-width="2"${dashAttr} />` +
      `</svg>` +
      `<span>${escapeHtml(label)}</span>` +
      `</span>`;
  }).join('\n');

  return `<section class="summary-curve">
  <h4>Planned VS Actual Percent Complete</h4>
  <svg width="${svgW}" height="${svgH}" viewBox="0 0 ${svgW} ${svgH}" xmlns="http://www.w3.org/2000/svg">
${svgInner}
  </svg>
  <div class="legend-row">${legendHtml}</div>
</section>`;
}

// =================================================================
// Section 3: Milestones table + change-log summary
// =================================================================

/**
 * @param {SummaryMilestones} m
 * @param {string} topProjectName
 * @param {string} topMilestoneName
 * @returns {string}
 */
function renderMilestonesSection(m, topProjectName, topMilestoneName) {
  const milestones = Array.isArray(m.milestones) ? m.milestones : [];
  const cpd = m.critical_path_delays ?? { count: 0, items: [] };
  const cpr = m.critical_path_recoveries ?? { count: 0, items: [] };
  const lpc = m.last_period_changes ?? { total: 0, critical_path: 0, acceleration_days: null };

  const projectName = topProjectName || m.project_name || '';
  const milestoneName = topMilestoneName || m.milestone_name || '';
  const projectLocation = m.project_location || '';
  const dataDateStr = m.data_date ? fmtDate(m.data_date) : '';

  // Header bullets (project metadata).
  const headerRows = [
    `<div class="meta-row"><strong>Project Name:</strong> ${escapeHtml(projectName)}</div>`,
    `<div class="meta-row"><strong>Milestone Name:</strong> ${escapeHtml(milestoneName)}</div>`,
    `<div class="meta-row"><strong>Project Location:</strong> ${escapeHtml(projectLocation)}</div>`,
    `<div class="meta-row"><strong>Data Date:</strong> ${escapeHtml(dataDateStr)}</div>`,
  ].join('\n');

  // Milestones table.
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
        `<td class="num">${escapeHtml(String(row.order ?? ''))}</td>` +
        `<td>${escapeHtml(String(row.name ?? ''))}</td>` +
        `<td>${escapeHtml(fmtDate(row.contractual))}</td>` +
        `<td>${escapeHtml(fmtDate(row.current))}</td>` +
        `<td class="num">${escapeHtml(String(daysLate))}</td>` +
        `<td>${escapeHtml(fmtDate(row.predicted))}</td>` +
        `<td class="num">${escapeHtml(String(compression))}%</td>` +
        `</tr>`;
    }).join('\n');
    tbody = `<tbody>${rows}</tbody>`;
  }

  // Change-log summary bullets.
  const cpdCount = Number(cpd.count ?? 0);
  const cprCount = Number(cpr.count ?? 0);
  const cprLabel = cprCount === 0 ? 'N/A' : String(cprCount);

  const cpdItems = (cpd.items ?? []).slice(0, 6);
  const cprItems = (cpr.items ?? []).slice(0, 6);

  const cpdBullets = cpdItems.length
    ? `<ul>${cpdItems.map(it => `<li>${escapeHtml(String(it))}</li>`).join('')}</ul>`
    : '';
  const cprBullets = cprItems.length
    ? `<ul>${cprItems.map(it => `<li>${escapeHtml(String(it))}</li>`).join('')}</ul>`
    : '';

  const total = Number(lpc.total ?? 0);
  const cp    = Number(lpc.critical_path ?? 0);
  const accel = lpc.acceleration_days;
  const accelStr = accel === null || accel === undefined ? 'N/A' : String(accel);

  const changeSummary = `<div class="change-summary">
  <div><strong>Selected Period Critical Path Delays:</strong> ${cpdCount}</div>
  ${cpdBullets}
  <div style="margin-top: 8px;"><strong>Last Period Critical Path Recoveries:</strong> ${escapeHtml(cprLabel)}</div>
  ${cprBullets}
  <div style="margin-top: 8px;"><strong>Last Period Schedule Changes</strong></div>
  <div>Total Changes: ${total} &nbsp;&nbsp; Critical Path Changes: ${cp} &nbsp;&nbsp; Acceleration Days: ${escapeHtml(accelStr)}</div>
</div>`;

  return `<section class="summary-milestones">
  <h4>Milestones</h4>
  ${headerRows}
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
