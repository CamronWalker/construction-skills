#!/usr/bin/env node
/**
 * Rasterise a chart HTML file to PNG via headless Chromium.
 *
 * Two modes:
 *
 *  1. Single-card mode (default) — screenshots the first `.chart-card`
 *     element at its native CSS dimensions. Used by ad-hoc renders of a
 *     single chart card.
 *
 *  2. Full-page mode (`--full-page`) — screenshots the entire scrollable
 *     body. Used by the weekly email pipeline to capture the stacked
 *     gallery (all chart cards arranged vertically). Picks up the body's
 *     real height regardless of viewport.
 *
 * Argument forms (both accepted):
 *
 *   node html_to_png.cjs <htmlPath> <pngPath> [width=1728] [height=432] [scale=2]
 *   node html_to_png.cjs <htmlPath> <pngPath> [--width=N] [--height=N] [--scale=N] [--full-page]
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

/**
 * Parse argv supporting both positional (legacy) and flag (new) styles.
 * Returns { htmlPath, pngPath, width, height, scale, fullPage }.
 */
function parseArgs(argv) {
  const positional = [];
  const flags = {};
  for (const a of argv) {
    if (a.startsWith('--')) {
      const eq = a.indexOf('=');
      if (eq === -1) {
        flags[a.slice(2)] = true;
      } else {
        flags[a.slice(2, eq)] = a.slice(eq + 1);
      }
    } else {
      positional.push(a);
    }
  }
  if (positional.length < 2) return null;
  const htmlPath = positional[0];
  const pngPath  = positional[1];
  // Positional ordering: width, height, scale.
  const width  = flags.width  !== undefined ? parseInt(flags.width,  10) : parseInt(positional[2] || '1728', 10);
  const height = flags.height !== undefined ? parseInt(flags.height, 10) : parseInt(positional[3] || '432',  10);
  const scale  = flags.scale  !== undefined ? parseFloat(flags.scale)    : parseFloat(positional[4] || '2');
  const fullPage = Boolean(flags['full-page']);
  return { htmlPath, pngPath, width, height, scale, fullPage };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  if (!args) {
    console.error(
      'Usage: node html_to_png.cjs <htmlPath> <pngPath> [width=1728] [height=432] [scale=2] [--full-page]'
    );
    process.exit(2);
  }
  const { htmlPath, pngPath, width, height, scale, fullPage } = args;

  const htmlAbs = path.resolve(htmlPath);
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

    if (fullPage) {
      // Stacked-gallery mode: capture the whole scrollable body, ignoring
      // the viewport's fixed height. This is what produces the tall single-
      // PNG of all chart cards used by the weekly email.
      await page.screenshot({ path: pngPath, fullPage: true, omitBackground: false });
    } else {
      // Single-card mode: screenshot the first .chart-card element so the
      // PNG is exactly the card's native CSS dimensions (no surrounding
      // viewport whitespace). Falls back to viewport if no card exists.
      const card = await page.$('.chart-card');
      if (card) {
        await card.screenshot({ path: pngPath, omitBackground: false });
      } else {
        await page.screenshot({ path: pngPath, fullPage: false });
      }
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
