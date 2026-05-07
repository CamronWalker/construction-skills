/**
 * Debug test — captures untouched full-page screenshots of the cards
 * page and the trends page for the test project. Use this to inspect
 * sidebar overlap, layout issues, and any visual quirks that aren't
 * obvious from the cropped chart screenshots.
 *
 * Run alone:
 *   npx playwright test --config=tests/playwright.config.js full-page-debug
 *
 * Outputs land in `tests/test-results/full-page-debug/` (gitignored).
 */

const { test } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const { loadConfig } = require('../smartpm/env-loader');
const {
  launchContext,
  loginIfNeeded,
  isLoginPage,
  findProjectCard,
} = require('../smartpm/smartpm-client');

const TEST_PROJECT = process.env.TEST_PROJECT_NAME || 'Anchorage Alaska Temple';
// Same folder as the chart captures so you don't have to hunt for files.
const OUT_DIR = path.join(__dirname, 'test-results', 'captures');

let ctx;
let page;
let cfg;

test.beforeAll(async () => {
  cfg = await loadConfig({ interactive: false });
  fs.mkdirSync(OUT_DIR, { recursive: true });
  ctx = await launchContext({ headless: true });
  page = ctx.pages()[0] || await ctx.newPage();
});

test.afterAll(async () => {
  if (ctx) await ctx.close().catch(() => {});
});

test('full page: projects/cards (with search filter)', async () => {
  await page.goto(cfg.projectsUrl, { waitUntil: 'domcontentloaded', timeout: 60_000 });
  await page.waitForTimeout(3000);
  if (isLoginPage(page.url())) {
    await loginIfNeeded(page, { email: cfg.email, password: cfg.password });
  }
  // findProjectCard navigates to the search-filtered URL.
  await findProjectCard(page, TEST_PROJECT, { projectsUrl: cfg.projectsUrl });
  await page.waitForTimeout(2000);

  await page.screenshot({
    path: path.join(OUT_DIR, 'debug-cards-viewport.png'),
    fullPage: false,
  });
  await page.screenshot({
    path: path.join(OUT_DIR, 'debug-cards-fullpage.png'),
    fullPage: true,
  });
});

test('full page: trends page (after clicking View Trends)', async () => {
  // findProjectCard re-renders the cards page; click View Trends from there.
  const card = await findProjectCard(page, TEST_PROJECT, { projectsUrl: cfg.projectsUrl });
  await card.scrollIntoViewIfNeeded();
  await card.locator('text=View Trends').first().click({ timeout: 10_000 });
  await page.waitForTimeout(8000);

  // Force-render lazy charts.
  await page.evaluate(async () => {
    const step = window.innerHeight * 0.8;
    for (let y = 0; y < document.body.scrollHeight + step; y += step) {
      window.scrollTo(0, y);
      await new Promise((r) => setTimeout(r, 250));
    }
    window.scrollTo(0, 0);
  });
  await page.waitForTimeout(3000);
  await page.mouse.move(0, 0);
  await page.keyboard.press('Escape').catch(() => {});

  await page.screenshot({
    path: path.join(OUT_DIR, 'debug-trends-viewport.png'),
    fullPage: false,
  });
  await page.screenshot({
    path: path.join(OUT_DIR, 'debug-trends-fullpage.png'),
    fullPage: true,
  });

  console.log(`\nDebug screenshots saved to: ${OUT_DIR}`);
});
