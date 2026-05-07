#!/usr/bin/env node
/**
 * SmartPM v2 screenshot capture — CLI entry.
 *
 * Auto-logs in headless using credentials from `~/.claude/.env`
 * (SMARTPM_EMAIL, SMARTPM_PASSWORD), navigates to the Westland projects
 * cards page, finds the named project, and captures:
 *   - 1 Summary Report
 *   - 16 Trend Graphs
 *
 * Usage:
 *   node capture-smartpm.js "<project name>" "<output dir>"
 *
 * Optional env overrides (in ~/.claude/.env):
 *   SMARTPM_PROJECTS_URL  — defaults to Westland's v2 cards URL
 *   SMARTPM_BASE_URL      — defaults to https://live.smartpmtech.com
 *
 * Exit codes:
 *   0 — Success
 *   1 — Capture / browser error
 *   2 — Bad args / missing env
 *
 * Output (stdout): JSON describing every screenshot captured.
 */

const path = require('path');
const fs = require('fs');
const { execSync } = require('child_process');

// Auto-install playwright on first run if missing.
function ensurePlaywright() {
  try {
    require.resolve('playwright');
    return;
  } catch (_) { /* not installed */ }
  console.error('Playwright not found — installing automatically...');
  const refsDir = path.resolve(__dirname, '..');
  execSync('npm install', { cwd: refsDir, stdio: 'inherit' });
  try {
    execSync('npx playwright install chromium', { cwd: refsDir, stdio: 'inherit' });
  } catch (_) { /* browser may already be installed */ }
}

ensurePlaywright();

const { loadConfig } = require('./env-loader');
const {
  launchContext,
  captureAll,
  normalizePath,
} = require('./smartpm-client');

async function main() {
  const [projectNameArg, outputDirArg] = process.argv.slice(2);
  if (!projectNameArg || !outputDirArg) {
    console.error(
      'Usage: node capture-smartpm.js "<project name>" "<output dir>"\n' +
      '\n' +
      'project name — exact title shown on SmartPM v2 (smartpm_project_name\n' +
      '               from project-context.html, or project_name as fallback)\n' +
      'output dir   — folder to write the 17 PNGs into (created if missing)'
    );
    process.exit(2);
  }

  let config;
  try {
    config = await loadConfig({ interactive: false });
  } catch (err) {
    console.error('ERROR: ' + err.message);
    process.exit(2);
  }

  const outputDir = normalizePath(outputDirArg);
  fs.mkdirSync(outputDir, { recursive: true });

  let context;
  try {
    context = await launchContext({ headless: true });
    const page = context.pages()[0] || await context.newPage();

    console.error(`Capturing SmartPM screenshots for "${projectNameArg}"...`);
    console.error(`Output directory: ${outputDir}`);
    console.error(`Projects URL:     ${config.projectsUrl}`);

    const result = await captureAll(page, projectNameArg, outputDir, {
      projectsUrl: config.projectsUrl,
      credentials: { email: config.email, password: config.password, baseUrl: config.baseUrl },
    });

    console.error(`\nCaptured ${result.total} screenshots.`);
    console.log(JSON.stringify(result, null, 2));
  } catch (err) {
    console.error('ERROR: ' + (err && err.message ? err.message : err));
    if (err && err.stack) console.error(err.stack);
    process.exit(1);
  } finally {
    if (context) await context.close().catch(() => {});
  }
}

main();
