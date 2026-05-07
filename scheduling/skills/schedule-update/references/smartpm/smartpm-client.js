/**
 * SmartPM v2 client — login, project lookup, summary + trends capture.
 *
 * Designed to run **headless** with credentials from `~/.claude/.env`. No
 * MCP, no manual login, no UI. Tests in `../tests/` exercise the same
 * exports against the live site.
 *
 * Public API:
 *   launchContext({ profileDir })           — persistent Chromium context
 *   loginIfNeeded(page, { email, password, baseUrl })
 *   gotoProjectsCards(page, projectsUrl)
 *   findProjectCard(page, projectName)      — Locator for one card
 *   captureSummaryReport(page, projectName, outPath)
 *   captureTrendGraphs(page, projectName, outDir)
 *   captureAll(page, projectName, outDir)   — orchestrates summary + 16 trends
 *
 * The CLI entry point is `capture-smartpm.js` (sibling file).
 */

const path = require('path');
const fs = require('fs');
const os = require('os');

let chromium;
try {
  ({ chromium } = require('playwright'));
} catch (_) {
  ({ chromium } = require('@playwright/test'));
}

const { PNG } = require('pngjs');

/**
 * Add `pad` pixels of `[r, g, b, a]` border around a PNG buffer. Used to
 * give chart-card screenshots breathing room without relying on
 * Playwright's `page.screenshot({ clip })` (which has subpixel issues on
 * the left edge in some headless layouts).
 */
function padPng(buffer, pad, rgba = [255, 255, 255, 255]) {
  return padPngSides(buffer, pad, pad, pad, pad, rgba);
}

/** Asymmetric per-side padding: top, right, bottom, left. */
function padPngSides(buffer, top, right, bottom, left, rgba = [255, 255, 255, 255]) {
  if (top <= 0 && right <= 0 && bottom <= 0 && left <= 0) return buffer;
  const src = PNG.sync.read(buffer);
  const out = new PNG({
    width: src.width + left + right,
    height: src.height + top + bottom,
  });
  for (let i = 0; i < out.data.length; i += 4) {
    out.data[i] = rgba[0];
    out.data[i + 1] = rgba[1];
    out.data[i + 2] = rgba[2];
    out.data[i + 3] = rgba[3];
  }
  for (let y = 0; y < src.height; y++) {
    const srcStart = y * src.width * 4;
    const dstStart = ((y + top) * out.width + left) * 4;
    src.data.copy(out.data, dstStart, srcStart, srcStart + src.width * 4);
  }
  return PNG.sync.write(out);
}

const PROFILE_DIR = path.join(os.homedir(), '.smartpm-playwright-profile');
const NAVIGATION_TIMEOUT = 60000;
const CHART_RENDER_WAIT = 5000;
const ELEMENT_WAIT = 1500;
const LOGIN_TIMEOUT = 60000;

const CHART_NAMES = [
  '01-planned-vs-actual-percent-complete',
  '02-schedule-quality-grade-over-time',
  '03-project-health-index-over-time',
  '04-schedule-changes-over-time',
  '05-schedule-delay-over-time',
  '06-end-date-variance',
  '07-schedule-compression-index-over-time',
  '08-velocity',
  '09-spi-over-time',
  '10-activity-hit-rate',
  '11-window-start-accuracy',
  '12-window-finish-accuracy',
  '13-missing-logic',
  '14-average-total-float',
  '15-high-total-float',
  '16-critical-path-percentage',
];

// Wide charts that scroll horizontally — we scroll the inner container
// to the right to show the most recent data before screenshotting.
const WIDE_CHART_INDICES = [4, 5];

const LOGIN_PATTERNS = [
  '/login', '/auth', '/signin', '/sso',
  'accounts.google.com', 'microsoftonline.com',
];

function isLoginPage(url) {
  const lower = (url || '').toLowerCase();
  return LOGIN_PATTERNS.some((p) => lower.includes(p));
}

/** Bash-style /c/Users/... → Windows C:\Users\... pass-through otherwise. */
function normalizePath(p) {
  if (process.platform === 'win32' && /^\/[a-zA-Z]\//.test(p)) {
    return p.replace(/^\/([a-zA-Z])\//, '$1:\\').replace(/\//g, '\\');
  }
  return p;
}

/**
 * Launch a persistent Chromium context. Headless by default. Pass
 * `headless: false` for debugging.
 */
async function launchContext({ profileDir = PROFILE_DIR, headless = true } = {}) {
  fs.mkdirSync(profileDir, { recursive: true });
  return chromium.launchPersistentContext(profileDir, {
    headless,
    viewport: { width: 1920, height: 1080 },
    args: ['--disable-blink-features=AutomationControlled'],
  });
}

/**
 * Auto-login flow. SmartPM v2 uses a two-step Auth0-style login:
 *   1. Email page → enter email → Sign in
 *   2. Password page → enter password → Sign in
 *
 * Detects a login page, fills credentials in sequence, and waits for the
 * post-login redirect. Returns silently if already logged in.
 *
 * Throws on:
 *   - Missing email/password
 *   - Login page not redirecting after submit (bad creds, MFA, captcha)
 *   - Timeout
 */
async function loginIfNeeded(page, { email, password } = {}) {
  if (!email || !password) {
    const err = new Error('SmartPM email and password are required');
    err.code = 'ENV_MISSING';
    throw err;
  }
  if (!isLoginPage(page.url())) {
    return { alreadyLoggedIn: true };
  }

  // Step 1 — email. SmartPM v2 renders Angular Material inputs with
  // auto-generated names/ids and `<input type="text">` (not "email"), with
  // a separate <label> not linked via `for`. Anchor by the visible "Email"
  // label and grab the input that follows it.
  const emailInput = page
    .locator('label:has-text("Email")')
    .locator('xpath=following::input[1]')
    .or(page.locator('input[type="email"], input[name*="email" i], input[id*="email" i]'))
    .or(page.locator('input[type="text"]'))
    .first();
  await emailInput.waitFor({ state: 'visible', timeout: LOGIN_TIMEOUT });
  await typeIntoAngularInput(emailInput, email);
  await clickSignIn(page, emailInput);

  // Step 2 — password. The form swaps in a password input. `type="password"`
  // is a reliable anchor here.
  const passwordInput = page
    .locator('input[type="password"]')
    .or(
      page
        .locator('label:has-text("Password")')
        .locator('xpath=following::input[1]')
    )
    .first();
  await passwordInput.waitFor({ state: 'visible', timeout: LOGIN_TIMEOUT });
  await typeIntoAngularInput(passwordInput, password);
  await clickSignIn(page, passwordInput);

  // Wait for redirect off the login page.
  await page.waitForURL(
    (url) => !isLoginPage(url.toString()),
    { timeout: LOGIN_TIMEOUT }
  );
  return { alreadyLoggedIn: false };
}

/**
 * Type a value into an Angular reactive-forms input. `.fill()` doesn't
 * mark the control dirty/touched, so the Sign in button stays disabled.
 * Pressing keys + dispatching a blur event reliably flips the form to
 * valid before we click submit.
 */
async function typeIntoAngularInput(locator, value) {
  await locator.click();
  await locator.fill('');
  await locator.pressSequentially(value, { delay: 10 });
  // Dispatch input + change + blur so Angular's reactive forms mark the
  // control dirty/valid even when the page is in the background.
  await locator.evaluate((el) => {
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.blur();
  });
}

/**
 * Click the Sign in / Log in / Continue button, waiting for it to become
 * enabled (Angular forms guard the disabled state until validation passes).
 * Falls back to pressing Enter on the active input.
 */
async function clickSignIn(page, fallbackInput) {
  const submit = page.getByRole('button', {
    name: /sign in|log in|continue|submit/i,
  }).first();
  if (await submit.count() > 0) {
    try {
      // Wait up to 10s for the button to enable; if it never does, try
      // pressing Enter as a fallback.
      await submit.waitFor({ state: 'visible', timeout: 5000 });
      await page.waitForFunction(
        (btn) => btn && !btn.hasAttribute('disabled') && btn.getAttribute('aria-disabled') !== 'true',
        await submit.elementHandle(),
        { timeout: 10_000 }
      );
      await submit.click();
      return;
    } catch (_) { /* fall through to Enter */ }
  }
  const fallback = page.locator('button[type="submit"]').first();
  if (await fallback.count() > 0) {
    try {
      await fallback.click({ timeout: 3000 });
      return;
    } catch (_) { /* fall through */ }
  }
  if (fallbackInput) await fallbackInput.press('Enter');
}

/**
 * Navigate to /projects/cards. Triggers login if the destination redirects
 * to the login page.
 */
async function gotoProjectsCards(page, projectsUrl, credentials) {
  await page.goto(projectsUrl, {
    waitUntil: 'domcontentloaded',
    timeout: NAVIGATION_TIMEOUT,
  });
  if (isLoginPage(page.url())) {
    await loginIfNeeded(page, credentials);
    // After login, navigate to the projects URL again — login may land elsewhere.
    if (!page.url().includes('/projects/cards')) {
      await page.goto(projectsUrl, {
        waitUntil: 'domcontentloaded',
        timeout: NAVIGATION_TIMEOUT,
      });
    }
  }
  // Wait for the cards list to render.
  await page.waitForSelector(
    'text=Run Summary Report, text=View Trends, text=Manage Schedules',
    { timeout: NAVIGATION_TIMEOUT }
  ).catch(() => { /* fall through — let the caller's lookup handle it */ });
  await page.waitForTimeout(CHART_RENDER_WAIT);
}

/**
 * Build the project's search URL by appending `?search=<encoded name>`
 * to the projects/cards URL. SmartPM v2 reads the `search` query param
 * and renders only the matching card.
 */
function buildSearchUrl(projectsUrl, projectName) {
  const sep = projectsUrl.includes('?') ? '&' : '?';
  return `${projectsUrl}${sep}search=${encodeURIComponent(projectName)}`;
}

/**
 * Navigate to the projects/cards page filtered to one project (via the
 * `?search=` query param) and return the first `<app-project-list-card>`.
 * The order of cards varies (alphabetical, recent activity, etc.), so
 * filtering by URL is the most reliable way to land on the right card —
 * the top card is always the one we want.
 */
async function findProjectCard(page, projectName, { projectsUrl } = {}) {
  if (!projectName) {
    throw new Error('findProjectCard: projectName is required');
  }
  if (!projectsUrl) {
    throw new Error('findProjectCard: projectsUrl is required');
  }
  const searchUrl = buildSearchUrl(projectsUrl, projectName);
  if (page.url() !== searchUrl) {
    await page.goto(searchUrl, {
      waitUntil: 'domcontentloaded',
      timeout: NAVIGATION_TIMEOUT,
    });
    await page.waitForTimeout(2500); // let Angular re-render the card list
  }
  const card = page.locator('app-project-list-card').first();
  await card.waitFor({ state: 'visible', timeout: NAVIGATION_TIMEOUT });
  return card;
}

/**
 * Click "Run Summary Report" on the project card and capture the report.
 * SmartPM v2 may render the report as a modal or a new page — both are
 * handled.
 */
async function captureSummaryReport(page, projectName, outPath, { projectsUrl } = {}) {
  const card = await findProjectCard(page, projectName, { projectsUrl });
  await card.scrollIntoViewIfNeeded();
  await card.locator('text=Run Summary Report').first().click({ timeout: 10000 });
  await page.waitForTimeout(3000);

  // Wait for the summary content. A modal or a new view both render
  // a "Project Name" label as the first row; use that as the anchor.
  await page.waitForSelector('text=Project Name', { timeout: NAVIGATION_TIMEOUT });
  await page.waitForTimeout(CHART_RENDER_WAIT);

  // Crop to the report content — exclude SmartPM's header and the
  // Close/Print buttons. Same approach as v1.
  const clip = await page.evaluate(() => {
    let topY = null;
    let bottomY = null;
    let projectNameEl = null;

    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      const text = walker.currentNode.textContent.trim();
      if (!topY && text.startsWith('Project Name')) {
        const el = walker.currentNode.parentElement;
        const r = el.getBoundingClientRect();
        if (r.top > 50) {
          topY = Math.max(0, r.top - 6);
          projectNameEl = el;
          break;
        }
      }
    }

    const walker2 = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker2.nextNode()) {
      const text = walker2.currentNode.textContent.trim();
      if (text === 'Close' || text === 'Print') {
        const el = walker2.currentNode.parentElement;
        const r = el.getBoundingClientRect();
        if (r.top > 400) {
          const btnTop = r.top - 10;
          if (!bottomY || btnTop < bottomY) bottomY = btnTop;
        }
      }
    }

    if (!topY) topY = 0;
    if (!bottomY) bottomY = window.innerHeight;

    let leftX = 2;
    let rightX = window.innerWidth - 2;
    if (projectNameEl) {
      let cur = projectNameEl;
      let bestLeft = null;
      let bestRight = null;
      while (cur && cur !== document.body) {
        const r = cur.getBoundingClientRect();
        if (r.width > 800 && r.width < window.innerWidth - 2) {
          bestLeft = r.left;
          bestRight = r.right;
        }
        cur = cur.parentElement;
      }
      if (bestLeft !== null && bestRight !== null) {
        leftX = Math.max(0, Math.ceil(bestLeft) + 1);
        rightX = Math.min(window.innerWidth, Math.floor(bestRight) - 1);
      }
    }

    // Add 6px of breathing room on left + right so the modal edges
    // aren't flush against the screenshot bounds. Done in the clip math
    // (not via PNG post-processing) so the captured pixels include the
    // modal's natural backdrop colour, not pure white.
    const PADDING_X = 6;
    leftX = Math.max(0, leftX - PADDING_X);
    rightX = Math.min(window.innerWidth, rightX + PADDING_X);

    return {
      x: leftX,
      y: Math.round(topY),
      width: rightX - leftX,
      height: Math.round(bottomY - topY),
    };
  });

  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  await page.screenshot({ path: outPath, clip });

  // Close the modal (or navigate back if it opened a new view).
  try {
    await page.getByText('Close').first().click({ timeout: 3000 });
    await page.waitForTimeout(500);
  } catch {
    await page.keyboard.press('Escape').catch(() => {});
    await page.waitForTimeout(500);
  }

  // If we ended up on a different URL (not the filtered cards page), go
  // back. Trends capture re-navigates via findProjectCard anyway, so this
  // is just defensive.
  if (projectsUrl && !page.url().includes('/projects/cards')) {
    await page.goto(buildSearchUrl(projectsUrl, projectName), {
      waitUntil: 'domcontentloaded',
      timeout: NAVIGATION_TIMEOUT,
    });
    await page.waitForTimeout(CHART_RENDER_WAIT);
  }

  return { path: outPath, size: fs.statSync(outPath).size };
}

/**
 * Click "View Trends" on the project card, wait for charts to render,
 * and capture each of the 16 trend graphs.
 */
async function captureTrendGraphs(page, projectName, outDir, { projectsUrl } = {}) {
  fs.mkdirSync(outDir, { recursive: true });

  const card = await findProjectCard(page, projectName, { projectsUrl });
  await card.scrollIntoViewIfNeeded();
  await card.locator('text=View Trends').first().click({ timeout: 10000 });
  await page.waitForTimeout(CHART_RENDER_WAIT);

  // The trends page renders one Highcharts container per graph. Some are
  // lazy — scroll the page from top to bottom once to force-render them all.
  await page.evaluate(async () => {
    const step = window.innerHeight * 0.8;
    for (let y = 0; y < document.body.scrollHeight + step; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 250));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(CHART_RENDER_WAIT);

  // Each chart is wrapped in <spm-card-container> which includes the title
  // bar (e.g. "Planned VS Actual Percent Complete"). The Highcharts SVG is
  // nested deeper, but capturing the card container gives us the title row
  // too — matching what the user sees in SmartPM.
  await page.waitForSelector('spm-card-container', { timeout: NAVIGATION_TIMEOUT });
  const cards = await page.locator('spm-card-container').filter({
    has: page.locator('.highcharts-container'),
  }).all();
  if (cards.length === 0) {
    throw new Error('No chart cards (spm-card-container with highcharts) found on the trends page');
  }

  // Move the mouse off any chart so hover tooltips don't appear in our
  // captures. Press Escape too in case an info popover is open.
  await page.mouse.move(0, 0);
  await page.keyboard.press('Escape').catch(() => {});

  // Hide overlays that bleed across the page on the trends route:
  // - nav.sidenav: SmartPM v2 left sidebar (72px collapsed, but if any
  //   hover state expands it during capture, it can paint over the card).
  // - cz-transBG / hs-interactives-modal-overlay: leftover dim overlays
  //   from CodeZync / HubSpot-style help widgets.
  await page.addStyleTag({
    content: `
      nav.sidenav,
      #cz_transBG, .cz-transBG,
      #hs-interactives-modal-overlay, #hs-web-interactives-top-anchor {
        display: none !important;
      }
    `,
  });
  await page.waitForTimeout(200);

  const screenshots = [];
  const limit = Math.min(cards.length, CHART_NAMES.length);
  for (let i = 0; i < limit; i++) {
    const chartName = CHART_NAMES[i];
    const filename = chartName + '.png';
    const filePath = path.join(outDir, filename);
    const card = cards[i];

    await card.scrollIntoViewIfNeeded();
    await page.waitForTimeout(ELEMENT_WAIT);

    // Wide charts (Schedule Delay, End Date Variance) extend past the card's
    // visible area — Highcharts wraps the SVG in `.highcharts-scrolling`
    // (and `.highcharts-inner-container`) which carry the horizontal
    // overflow. Scroll all such containers to the right so the latest data
    // is visible before capturing.
    if (WIDE_CHART_INDICES.includes(i)) {
      await card.evaluate((cardEl) => {
        const candidates = cardEl.querySelectorAll(
          '.highcharts-scrolling, .highcharts-inner-container'
        );
        for (const el of candidates) {
          if (el.scrollWidth > el.clientWidth + 10) {
            el.scrollLeft = el.scrollWidth;
          }
        }
      });
      await page.waitForTimeout(ELEMENT_WAIT);
    }

    // Capture the card as an element screenshot — most reliable; doesn't
    // hit Playwright's page-clip subpixel issues. Then add 6px of white
    // padding around it via PNG post-processing so the rounded corners
    // have breathing room.
    const elementBuffer = await card.screenshot();
    const padded = padPng(elementBuffer, 6, [255, 255, 255, 255]);
    fs.writeFileSync(filePath, padded);
    screenshots.push({
      name: chartName,
      file: filename,
      path: filePath,
      size: fs.statSync(filePath).size,
    });
  }
  return screenshots;
}

/**
 * Orchestrate: login → cards → summary → cards → trends. Returns a
 * JSON-shaped result describing every screenshot captured.
 */
async function captureAll(page, projectName, outDir, { projectsUrl, credentials } = {}) {
  fs.mkdirSync(outDir, { recursive: true });
  await gotoProjectsCards(page, projectsUrl, credentials);

  const summaryPath = path.join(outDir, 'smartpm-summary-report.png');
  const summary = await captureSummaryReport(page, projectName, summaryPath, { projectsUrl });
  const trends = await captureTrendGraphs(page, projectName, outDir, { projectsUrl });

  return {
    status: 'success',
    total: 1 + trends.length,
    screenshots: [{ name: 'summary-report', file: 'smartpm-summary-report.png', ...summary }, ...trends],
    urls: { projects: projectsUrl },
  };
}

module.exports = {
  CHART_NAMES,
  WIDE_CHART_INDICES,
  PROFILE_DIR,
  NAVIGATION_TIMEOUT,
  isLoginPage,
  normalizePath,
  launchContext,
  loginIfNeeded,
  gotoProjectsCards,
  findProjectCard,
  captureSummaryReport,
  captureTrendGraphs,
  captureAll,
};
