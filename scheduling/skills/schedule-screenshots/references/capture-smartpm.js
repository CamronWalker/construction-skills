/**
 * SmartPM Screenshot Capture via Playwright Persistent Context
 *
 * Launches Chromium with a persistent user profile so SmartPM login
 * is preserved between runs. First run: you log in manually, then the
 * script continues. Subsequent runs: session is reused automatically.
 *
 * Captures:
 *   - 1 Summary Report (from View Summary modal on workspace page)
 *   - 16 individual trend graphs (from the Graphs tab on trends page)
 *
 * For horizontally-scrolling charts (Schedule Delay, End Date Variance),
 * the script scrolls to the right to show the most recent data.
 *
 * Usage:
 *   node capture-smartpm.js <workspace_url> <trends_url> <output_dir>
 *
 * Exit codes:
 *   0 — Success
 *   1 — General error
 *
 * Output (stdout): JSON with screenshot paths and status
 */

const path = require('path');
const fs = require('fs');
const os = require('os');
const { execSync } = require('child_process');

// Auto-install playwright if not available
let chromium;
try {
  ({ chromium } = require('playwright'));
} catch (_) {
  console.error('Playwright not found — installing automatically...');
  execSync('npm install --no-save playwright', {
    cwd: __dirname,
    stdio: 'inherit',
  });
  ({ chromium } = require('playwright'));
  // Install Chromium browser if needed
  try {
    execSync('npx playwright install chromium', {
      cwd: __dirname,
      stdio: 'inherit',
    });
  } catch (_) { /* browser may already be installed */ }
}

const PROFILE_DIR = path.join(os.homedir(), '.smartpm-playwright-profile');
const NAVIGATION_TIMEOUT = 45000;
const CHART_RENDER_WAIT = 5000;
const ELEMENT_WAIT = 1500;
const LOGIN_CHECK_INTERVAL = 3000;
const LOGIN_TIMEOUT = 300000; // 5 minutes to log in

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

const WIDE_CHART_INDICES = [4, 5];

async function main() {
  const [workspaceUrl, trendsUrl, outputDir] = process.argv.slice(2);

  if (!workspaceUrl || !trendsUrl || !outputDir) {
    console.error('Usage: node capture-smartpm.js <workspace_url> <trends_url> <output_dir>');
    process.exit(1);
  }

  // Normalize bash-style /c/Users/... paths to Windows C:\Users\... paths
  const normalizedOutputDir = normalizePath(outputDir);
  fs.mkdirSync(normalizedOutputDir, { recursive: true });
  fs.mkdirSync(PROFILE_DIR, { recursive: true });

  let context;

  try {
    // Try headless first — fast and invisible. If login is needed, relaunch visible.
    console.error('Launching browser headless (profile: ' + PROFILE_DIR + ')...');
    context = await chromium.launchPersistentContext(PROFILE_DIR, {
      headless: true,
      viewport: { width: 1920, height: 1080 },
      args: ['--disable-blink-features=AutomationControlled'],
    });

    let page = context.pages()[0] || await context.newPage();

    // =============================================
    // PART 1: Summary Report
    // =============================================
    console.error('Navigating to Workspace: ' + workspaceUrl);
    await page.goto(workspaceUrl, { waitUntil: 'domcontentloaded', timeout: NAVIGATION_TIMEOUT });

    // Check if we need to log in — if so, close headless and relaunch visible
    if (isLoginPage(page.url())) {
      console.error('Login required — relaunching browser with visible window...');
      await context.close();

      context = await chromium.launchPersistentContext(PROFILE_DIR, {
        headless: false,
        viewport: { width: 1920, height: 1080 },
        args: ['--disable-blink-features=AutomationControlled'],
      });
      page = context.pages()[0] || await context.newPage();
      await page.goto(workspaceUrl, { waitUntil: 'domcontentloaded', timeout: NAVIGATION_TIMEOUT });

      console.error('');
      console.error('=== SmartPM login required ===');
      console.error('Please log in to SmartPM in the browser window.');
      console.error('The script will continue automatically once you are logged in.');
      console.error('Waiting up to 5 minutes...');
      console.error('');

      page = await waitForLogin(context, page, workspaceUrl);
    }

    // Navigate to workspace (in case login landed elsewhere)
    if (!page.url().includes('/workspace')) {
      console.error('Navigating to workspace...');
      await page.goto(workspaceUrl, { waitUntil: 'domcontentloaded', timeout: NAVIGATION_TIMEOUT });
    }

    // Wait for workspace to render
    console.error('Workspace loaded. Waiting for content to render...');
    await page.waitForTimeout(CHART_RENDER_WAIT);

    // Click "View Summary" button
    console.error('Clicking View Summary...');
    await page.locator('text=View Summary').first().click({ timeout: 10000 });
    await page.waitForTimeout(3000);

    // Screenshot the summary report modal — crop out SmartPM logo/header and Close/Print buttons
    const summaryPath = path.join(normalizedOutputDir, 'smartpm-summary-report.png');
    const summaryClip = await page.evaluate(() => {
      let topY = null;
      let bottomY = null;

      // Walk text nodes to find "Project Name:" — use the parent element's top
      // but look specifically for the label text (not the large container)
      const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) {
        const text = walker.currentNode.textContent.trim();
        if (!topY && text.startsWith('Project Name')) {
          // The text node's parent might be a large container — use its top
          // as the crop boundary regardless of container height
          const el = walker.currentNode.parentElement;
          const r = el.getBoundingClientRect();
          if (r.top > 50) { // must be below the logo area
            topY = Math.max(0, r.top - 6);
            break;
          }
        }
      }

      // Find Close/Print buttons — they're SPAN elements inside buttons
      const walker2 = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
      while (walker2.nextNode()) {
        const text = walker2.currentNode.textContent.trim();
        if (text === 'Close' || text === 'Print') {
          const el = walker2.currentNode.parentElement;
          const r = el.getBoundingClientRect();
          if (r.top > 400) { // must be in the lower part of the modal
            const btnTop = r.top - 10;
            if (!bottomY || btnTop < bottomY) bottomY = btnTop;
          }
        }
      }

      if (!topY) topY = 0;
      if (!bottomY) bottomY = window.innerHeight;
      return { x: 0, y: Math.round(topY), width: window.innerWidth, height: Math.round(bottomY - topY) };
    });
    await page.screenshot({ path: summaryPath, clip: summaryClip });
    console.error('Captured: smartpm-summary-report.png (cropped to content)');

    // Close the modal
    try {
      await page.getByText('Close').first().click({ timeout: 3000 });
      await page.waitForTimeout(500);
    } catch {
      // Modal might close differently — press Escape
      await page.keyboard.press('Escape');
      await page.waitForTimeout(500);
    }

    // =============================================
    // PART 2: Trend Graphs (16 individual charts)
    // =============================================
    console.error('Navigating to Trends: ' + trendsUrl);
    await page.goto(trendsUrl, { waitUntil: 'domcontentloaded', timeout: NAVIGATION_TIMEOUT });

    if (isLoginPage(page.url())) {
      console.error('Session lost during navigation. Please log in again.');
      await waitForLogin(page, trendsUrl);
    }

    // Wait for charts to render
    console.error('Waiting for charts to render...');
    await page.waitForTimeout(CHART_RENDER_WAIT);

    // Verify charts loaded
    const chartContainers = await page.locator('.highcharts-container').all();
    console.error('Found ' + chartContainers.length + ' chart containers');

    if (chartContainers.length === 0) {
      console.error('ERROR: No Highcharts charts found. Page may not have fully loaded.');
      console.error('Try running again — sometimes SmartPM takes longer to render.');
      process.exit(1);
    }

    const screenshots = [{
      name: 'summary-report',
      file: 'smartpm-summary-report.png',
      path: summaryPath,
      size: fs.statSync(summaryPath).size,
    }];

    for (let i = 0; i < chartContainers.length && i < CHART_NAMES.length; i++) {
      const chartName = CHART_NAMES[i];
      const filename = chartName + '.png';
      const filePath = path.join(normalizedOutputDir, filename);
      const container = chartContainers[i];

      console.error('Capturing ' + (i + 1) + '/' + chartContainers.length + ': ' + chartName);

      // Scroll chart into view
      await container.scrollIntoViewIfNeeded();
      await page.waitForTimeout(ELEMENT_WAIT);

      // For wide charts, scroll right and take a viewport-clipped screenshot
      // (element.screenshot captures the full 15000px+ width which is unreadable)
      if (WIDE_CHART_INDICES.includes(i)) {
        console.error('  Wide chart — scrolling chart to latest data...');
        const clipRect = await page.evaluate((idx) => {
          const containers = document.querySelectorAll('.highcharts-container');
          const chart = containers[idx];

          // First: scroll the PAGE vertically so the chart section is visible
          // Find the APP-*-SCROLL wrapper which is the actual scroll container
          let scrollWrapper = chart;
          for (let j = 0; j < 10; j++) {
            if (!scrollWrapper) break;
            const tag = scrollWrapper.tagName || '';
            if (tag.includes('SCROLL')) break;
            // Also check for overflow-x: auto/scroll via computed style
            const style = getComputedStyle(scrollWrapper);
            if (style.overflowX === 'auto' || style.overflowX === 'scroll') break;
            scrollWrapper = scrollWrapper.parentElement;
          }

          // Scroll the wrapper into view vertically (not the wide chart itself)
          if (scrollWrapper) {
            scrollWrapper.scrollIntoView({ block: 'center', inline: 'start' });
          }

          // Now scroll the chart's INTERNAL horizontal scroll to the far right
          // The scroll container is the element with overflow or the -SCROLL component
          if (scrollWrapper && scrollWrapper !== chart) {
            scrollWrapper.scrollLeft = scrollWrapper.scrollWidth;
          }
          // Also try any ancestor that is horizontally scrollable
          let el = chart.parentElement;
          for (let j = 0; j < 10; j++) {
            if (!el) break;
            if (el.scrollWidth > el.clientWidth + 100) {
              el.scrollLeft = el.scrollWidth;
              break;
            }
            el = el.parentElement;
          }

          // Return the scroll wrapper's viewport rect (not the wide chart element)
          const wrapperRect = scrollWrapper ? scrollWrapper.getBoundingClientRect() : chart.getBoundingClientRect();
          return {
            x: Math.max(0, Math.round(wrapperRect.left)),
            y: Math.max(0, Math.round(wrapperRect.top)),
            width: Math.min(Math.round(wrapperRect.width), window.innerWidth - Math.max(0, Math.round(wrapperRect.left))),
            height: Math.min(Math.round(wrapperRect.height), window.innerHeight - Math.max(0, Math.round(wrapperRect.top))),
          };
        }, i);
        await page.waitForTimeout(ELEMENT_WAIT);

        try {
          await page.screenshot({ path: filePath, clip: clipRect });
          const size = fs.statSync(filePath).size;
          screenshots.push({ name: chartName, file: filename, path: filePath, size });
          console.error('  Saved: ' + filename + ' (' + (size / 1024).toFixed(1) + ' KB)');
        } catch (err) {
          console.error('  WARNING: clipped screenshot failed (' + err.message + '), trying element...');
          await container.screenshot({ path: filePath });
          const size = fs.statSync(filePath).size;
          screenshots.push({ name: chartName, file: filename, path: filePath, size });
          console.error('  Saved (element fallback): ' + filename);
        }
      } else {
        // Standard chart — element.screenshot captures it cleanly
        try {
          await container.screenshot({ path: filePath });
          const size = fs.statSync(filePath).size;
          screenshots.push({ name: chartName, file: filename, path: filePath, size });
          console.error('  Saved: ' + filename + ' (' + (size / 1024).toFixed(1) + ' KB)');
        } catch (err) {
          console.error('  WARNING: element screenshot failed, using viewport fallback');
          try {
            await page.screenshot({ path: filePath, fullPage: false });
            const size = fs.statSync(filePath).size;
            screenshots.push({ name: chartName, file: filename, path: filePath, size });
            console.error('  Saved (fallback): ' + filename);
          } catch (err2) {
            console.error('  FAILED: ' + err2.message);
          }
        }
      }
    }

    // Output JSON summary to stdout
    const result = {
      status: 'success',
      total: screenshots.length,
      screenshots,
      urls: { workspace: workspaceUrl, trends: trendsUrl },
    };
    console.log(JSON.stringify(result, null, 2));

  } catch (err) {
    console.error('ERROR: ' + err.message);
    process.exit(1);
  } finally {
    if (context) await context.close();
  }
}

/**
 * Wait for the user to log in. Monitors all pages in the context —
 * SSO flows may complete in a new tab. Returns the page to use going forward.
 */
async function waitForLogin(context, page, targetUrl) {
  const start = Date.now();
  while (Date.now() - start < LOGIN_TIMEOUT) {
    await page.waitForTimeout(LOGIN_CHECK_INTERVAL).catch(() => {});

    // Check all open pages — SSO might have opened a new tab
    const pages = context.pages();
    for (const p of pages) {
      try {
        const url = p.url();
        if (url.includes('smartpmtech.com') && !isLoginPage(url)) {
          console.error('Login complete! Found SmartPM page.');
          return p;
        }
      } catch {
        // Page might have been closed during SSO flow
      }
    }

    // Also check the original page
    try {
      const url = page.url();
      if (!isLoginPage(url)) {
        console.error('Login complete on original page.');
        return page;
      }
    } catch {
      // Original page closed — check if a new one exists
      const pages2 = context.pages();
      if (pages2.length > 0) {
        page = pages2[pages2.length - 1];
        continue;
      }
    }
  }
  console.error('ERROR: Login timed out after 5 minutes.');
  process.exit(1);
}

/**
 * Convert bash-style /c/Users/... paths to Windows C:\Users\... paths.
 * Passes through paths that are already in Windows format.
 */
function normalizePath(p) {
  if (process.platform === 'win32' && /^\/[a-zA-Z]\//.test(p)) {
    return p.replace(/^\/([a-zA-Z])\//, '$1:\\').replace(/\//g, '\\');
  }
  return p;
}

function isLoginPage(url) {
  const loginPatterns = ['/login', '/auth', '/signin', '/sso', 'accounts.google.com', 'microsoftonline.com'];
  return loginPatterns.some((p) => url.toLowerCase().includes(p));
}

main();
