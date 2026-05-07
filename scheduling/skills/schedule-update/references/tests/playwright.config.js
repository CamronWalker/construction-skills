// @playwright/test configuration for SmartPM v2 capture tests.
// Tests run against the live SmartPM site using credentials from
// ~/.claude/.env (SMARTPM_EMAIL, SMARTPM_PASSWORD).
//
// Use the `TEST_PROJECT_NAME` env var to override the test project
// (defaults to "Anchorage Alaska Temple").

const { defineConfig } = require('@playwright/test');
const path = require('path');

module.exports = defineConfig({
  testDir: __dirname,
  timeout: 180_000,
  expect: { timeout: 60_000 },
  fullyParallel: false,
  workers: 1,
  reporter: [['list'], ['json', { outputFile: path.join(__dirname, 'results.json') }]],
  use: {
    headless: true,
    viewport: { width: 1920, height: 1080 },
    actionTimeout: 30_000,
    navigationTimeout: 60_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  outputDir: path.join(__dirname, 'test-results'),
});
