// html-to-pdf.js
// Convert a local HTML file to a PDF using Playwright's headless Chromium.
// Reuses the `playwright` install in this references/ folder (the same one
// capture-smartpm.js uses for SmartPM screenshots).
//
// Usage:
//   node html-to-pdf.js <input.html> <output.pdf>
//
// Options read from env:
//   PDF_FORMAT  — paper size (default: Letter)
//   PDF_MARGIN  — margin in inches (default: 0.5)

const path = require('path');
const fs = require('fs');
const { chromium } = require('playwright');

(async () => {
  const [,, inputPath, outputPath] = process.argv;
  if (!inputPath || !outputPath) {
    console.error('Usage: node html-to-pdf.js <input.html> <output.pdf>');
    process.exit(2);
  }
  const absIn = path.resolve(inputPath);
  const absOut = path.resolve(outputPath);
  if (!fs.existsSync(absIn)) {
    console.error('Input HTML not found:', absIn);
    process.exit(2);
  }

  const fmt = process.env.PDF_FORMAT || 'Letter';
  const margin = process.env.PDF_MARGIN || '0.5in';

  // Convert Windows path to file:// URL
  const fileUrl = 'file:///' + absIn.replace(/\\/g, '/').replace(/^\/+/, '');

  const browser = await chromium.launch({ args: ['--disable-web-security'] });
  try {
    const page = await browser.newPage();
    // Wait until network is idle so images / webfonts finish loading.
    await page.goto(fileUrl, { waitUntil: 'networkidle', timeout: 30000 });
    // Trigger print-media styles via CSS emulation so @media print rules fire.
    await page.emulateMedia({ media: 'print' });
    await page.pdf({
      path: absOut,
      format: fmt,
      printBackground: true,
      margin: { top: margin, right: margin, bottom: margin, left: margin },
      preferCSSPageSize: false,
    });
    console.log('PDF written:', absOut);
  } finally {
    await browser.close();
  }
})().catch(err => {
  console.error('html-to-pdf failed:', err && err.message ? err.message : err);
  process.exit(1);
});
