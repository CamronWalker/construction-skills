#!/usr/bin/env node
/**
 * Rasterise a chart HTML file to PNG via headless Chromium.
 *
 * Each chart's JS renderer (the per-slug files in this directory, e.g.
 * 01-planned-vs-actual.js) emits a self-contained HTML+SVG document. The
 * CLI (cli.js) writes that HTML alongside its PNG output, then calls this
 * helper to rasterise it. The HTML stays as an auditable, browser-viewable
 * sibling that uses the same CSS the PNG was made from.
 *
 * Usage:
 *   node html_to_png.js <htmlPath> <pngPath> [width=1728] [height=432] [scale=2]
 *
 * Exit codes:
 *   0 — success
 *   1 — Chromium / screenshot error
 *   2 — bad args / file missing
 *
 * Resolves Playwright from references/node_modules.
 */

const path = require('path');
const fs = require('fs');

let chromium;
try {
  ({ chromium } = require('playwright'));
} catch (_) {
  try {
    ({ chromium } = require('@playwright/test'));
  } catch (err) {
    console.error('Playwright is not installed. Run `npm install` in references/.');
    process.exit(1);
  }
}

async function main() {
  const args = process.argv.slice(2);
  if (args.length < 2) {
    console.error(
      'Usage: node html_to_png.js <htmlPath> <pngPath> [width=1728] [height=432] [scale=2]'
    );
    process.exit(2);
  }
  const [htmlPathArg, pngPath] = args;
  const width  = parseInt(args[2] || '1728', 10);
  const height = parseInt(args[3] || '432', 10);
  const scale  = parseFloat(args[4] || '2');

  const htmlAbs = path.resolve(htmlPathArg);
  if (!fs.existsSync(htmlAbs)) {
    console.error(`HTML file not found: ${htmlAbs}`);
    process.exit(2);
  }

  // Build a file:// URL that works on Windows too. `path.resolve` returns
  // backslashes on win32 which break file URLs; swap to forward slashes
  // and prefix appropriately.
  const fileUrl =
    process.platform === 'win32'
      ? 'file:///' + htmlAbs.replace(/\\/g, '/')
      : 'file://' + htmlAbs;

  const browser = await chromium.launch({ headless: true });
  try {
    const ctx = await browser.newContext({
      viewport: { width, height },
      deviceScaleFactor: scale,
    });
    const page = await ctx.newPage();
    await page.goto(fileUrl, { waitUntil: 'networkidle', timeout: 30000 });
    // Make sure web fonts have settled before we screenshot — otherwise
    // the title/axis labels can paint in a fallback font for the first
    // frame and the PNG ships with the wrong glyphs.
    await page.evaluate(() => (document.fonts ? document.fonts.ready : Promise.resolve()));

    const card = await page.$('.chart-card');
    if (card) {
      await card.screenshot({ path: pngPath, omitBackground: false });
    } else {
      // Fallback: screenshot the viewport. Caller's HTML didn't follow the
      // expected envelope, but they still get a PNG.
      await page.screenshot({ path: pngPath, fullPage: false });
    }
  } catch (err) {
    console.error('ERROR: ' + (err && err.message ? err.message : err));
    if (err && err.stack) console.error(err.stack);
    process.exit(1);
  } finally {
    await browser.close().catch(() => {});
  }

  const stats = fs.statSync(pngPath);
  console.log(JSON.stringify({ path: pngPath, size: stats.size }));
}

main();
