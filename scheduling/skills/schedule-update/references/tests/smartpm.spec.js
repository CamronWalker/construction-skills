/**
 * SmartPM v2 capture smoke tests.
 *
 * These exercise the live SmartPM site using credentials from
 * ~/.claude/.env. They require:
 *   - SMARTPM_EMAIL, SMARTPM_PASSWORD set
 *   - The test project (default "Anchorage Alaska Temple") exists in
 *     the SmartPM org
 *
 * Override the test project: TEST_PROJECT_NAME="Other Project" npx playwright test
 *
 * The first test logs in via a fresh, isolated profile and reuses it for
 * subsequent tests via the `loggedInPage` fixture.
 */

const { test, expect } = require('@playwright/test');
const path = require('path');
const fs = require('fs');

const { loadConfig } = require('../smartpm/env-loader');
const {
  launchContext,
  loginIfNeeded,
  gotoProjectsCards,
  findProjectCard,
  captureSummaryReport,
  captureTrendGraphs,
  CHART_NAMES,
} = require('../smartpm/smartpm-client');

const TEST_PROJECT = process.env.TEST_PROJECT_NAME || 'Anchorage Alaska Temple';
// All test artifacts (chart captures + full-page debug) land in this
// single folder so you don't have to hunt across the system. Gitignored.
const TEST_OUTPUT_DIR = path.join(__dirname, 'test-results', 'captures');

let sharedContext;
let sharedPage;
let sharedConfig;

test.beforeAll(async () => {
  sharedConfig = await loadConfig({ interactive: false });
  fs.mkdirSync(TEST_OUTPUT_DIR, { recursive: true });
  sharedContext = await launchContext({ headless: true });
  sharedPage = sharedContext.pages()[0] || await sharedContext.newPage();
});

test.afterAll(async () => {
  if (sharedContext) await sharedContext.close().catch(() => {});
});

test('@smoke env-loader returns required credentials', async () => {
  expect(sharedConfig.email).toBeTruthy();
  expect(sharedConfig.password).toBeTruthy();
  expect(sharedConfig.projectsUrl).toMatch(/projects\/cards/);
});

test('@smoke navigates to projects cards page (auto-login if needed)', async () => {
  await gotoProjectsCards(sharedPage, sharedConfig.projectsUrl, {
    email: sharedConfig.email,
    password: sharedConfig.password,
    baseUrl: sharedConfig.baseUrl,
  });
  expect(sharedPage.url()).toContain('/projects/cards');
});

test(`@smoke finds the test project card (${TEST_PROJECT})`, async () => {
  const card = await findProjectCard(sharedPage, TEST_PROJECT, {
    projectsUrl: sharedConfig.projectsUrl,
  });
  await expect(card.locator('text=Run Summary Report')).toBeVisible();
  await expect(card.locator('text=View Trends')).toBeVisible();
  // Sanity check: the top card after URL-search should match the project name.
  await expect(card.locator('a.project-name')).toContainText(TEST_PROJECT);
});

test('@smoke captures the Summary Report screenshot', async () => {
  const outPath = path.join(TEST_OUTPUT_DIR, 'smartpm-summary-report.png');
  const result = await captureSummaryReport(sharedPage, TEST_PROJECT, outPath, {
    projectsUrl: sharedConfig.projectsUrl,
  });
  expect(fs.existsSync(result.path)).toBe(true);
  expect(result.size).toBeGreaterThan(20_000);   // > 20KB sanity check
  expect(result.size).toBeLessThan(2_000_000);   // < 2MB sanity check
});

test('@smoke captures all 16 trend graphs', async () => {
  const screenshots = await captureTrendGraphs(sharedPage, TEST_PROJECT, TEST_OUTPUT_DIR, {
    projectsUrl: sharedConfig.projectsUrl,
  });
  expect(screenshots.length).toBe(CHART_NAMES.length);
  for (const shot of screenshots) {
    expect(fs.existsSync(shot.path)).toBe(true);
    expect(shot.size).toBeGreaterThan(5_000); // > 5KB — empty pngs are tiny
  }
  // All 16 expected filenames present
  const fileNames = new Set(screenshots.map((s) => s.file));
  for (const name of CHART_NAMES) {
    expect(fileNames.has(`${name}.png`)).toBe(true);
  }
});

test.afterAll(async () => {
  console.log(`\nTest screenshots kept at: ${TEST_OUTPUT_DIR}`);
});
