# Phase: `screenshots` — Capture SmartPM Graphs

> Loaded by SKILL.md's router when the user invokes `/schedule-update screenshots`.

Captures 17 screenshots from SmartPM v2: 1 Summary Report + 16 individual trend graphs. **Fully headless and auto-authenticated** — no manual login, no MCP, no visible browser.

<!-- Lifted from SKILL.md lines ~170–286, verbatim. Preserve all Step 0–5
     content including the 16-graph filename table, Step 3b tests block,
     and SmartPM processing warning. -->

## Step 0: Pre-Flight — credentials + Node setup

The script reads SmartPM credentials from `~/.claude/.env`:

| Key | Required | Purpose |
|-----|----------|---------|
| `SMARTPM_EMAIL` | yes | Auto-login email |
| `SMARTPM_PASSWORD` | yes | Auto-login password |
| `SMARTPM_PROJECTS_URL` | no | v2 projects/cards URL (defaults to Westland's org URL) |
| `SMARTPM_BASE_URL` | no | Defaults to `https://live.smartpmtech.com` |

**If credentials are missing**, the script throws `ENV_MISSING`. To set them up:

```bash
node "{skill_dir}/references/smartpm/env-loader.js" setup
```

Or ask the colleague for them via `AskUserQuestion` (header: "SmartPM creds", with email and password questions) and write them yourself by calling `upsertEnvFile({SMARTPM_EMAIL, SMARTPM_PASSWORD})` from `references/smartpm/env-loader.js`. Never log the password back to the user.

**Node + Playwright pre-flight:**
1. Verify Node.js: `node --version` (any 18+).
2. Check `node_modules/` exists in `{skill_dir}/references/`. If missing, run `npm install` in that folder. The capture script will auto-install on first run too.
3. Chromium binary is installed via `npx playwright install chromium` (the script handles this).

## Step 1: Read Project Context

Apply folder resolution. Read `project-context.html`. Extract:
- `smartpm_project_name` — exact title shown on SmartPM v2 `/projects/cards`. **Falls back to `project_name`** if blank. This is what the script types into the search filter.

Determine the output directory: `{dated_folder}/screenshots/`.

If `project-context.html` is missing, stop with the standard error.

## Step 2: Write Checklist

Create `{dated_folder}/screenshots/` if it doesn't exist.
Write `screenshots/checklist.md` from the template at `{skill_dir}/references/checklist-template.md`,
filling in project name, date, and the v2 cards URL.

Print the checklist.

## Step 3: Capture via Node script

```bash
node "{skill_dir}/references/smartpm/capture-smartpm.js" \
  "{smartpm_project_name or project_name}" "{dated_folder}/screenshots"
```

The script:
- Loads credentials from `~/.claude/.env`
- Launches headless Chromium with a persistent profile at `~/.smartpm-playwright-profile/`
- Auto-logs in via the v2 two-step Auth0-style flow (email page → password page)
- Navigates to `<projects_url>?search=<encoded project name>` — SmartPM v2 reads the `search` query param and renders only the matching card. **The first card is always the right one** because the URL filter is exact.
- Clicks **Run Summary Report** on that card → captures the report → saves as `smartpm-summary-report.png`
- Re-navigates to the same search URL, clicks **View Trends** → captures each `<spm-card-container>` (which includes the chart title row) for the 16 graphs:

| # | File | Chart |
|---|------|-------|
| 1 | `01-planned-vs-actual-percent-complete.png` | Planned VS Actual Percent Complete |
| 2 | `02-schedule-quality-grade-over-time.png` | Schedule Quality Grade Over Time |
| 3 | `03-project-health-index-over-time.png` | Project Health Index Over Time |
| 4 | `04-schedule-changes-over-time.png` | Schedule Changes Over Time |
| 5 | `05-schedule-delay-over-time.png` | Schedule Delay Over Time *(wide -- scroll right for latest)* |
| 6 | `06-end-date-variance.png` | End Date Variance *(wide -- scroll right for latest)* |
| 7 | `07-schedule-compression-index-over-time.png` | Schedule Compression Index Over Time |
| 8 | `08-velocity.png` | Velocity |
| 9 | `09-spi-over-time.png` | SPI Over Time |
| 10 | `10-activity-hit-rate.png` | Activity Hit Rate |
| 11 | `11-window-start-accuracy.png` | Window Start Accuracy |
| 12 | `12-window-finish-accuracy.png` | Window Finish Accuracy |
| 13 | `13-missing-logic.png` | Missing Logic |
| 14 | `14-average-total-float.png` | Average Total Float |
| 15 | `15-high-total-float.png` | High Total Float |
| 16 | `16-critical-path-percentage.png` | Critical Path Percentage |

For wide charts (#5 and #6), the script scrolls `.highcharts-scrolling` and `.highcharts-inner-container` to the right before capture so the latest data is visible.

**stdout:** JSON shape `{ status, total, screenshots: [{name, file, path, size}, ...], urls }`.

**Errors:**
- `ENV_MISSING` → run the setup command (Step 0) or ask the user for credentials.
- Login redirect timeout → bad creds, MFA challenge, or captcha. Surface the error and ask the user to log in manually once via `node smartpm/capture-smartpm.js` with `headless: false` (debug helper) and confirm the credentials are right.
- "No chart cards found" → trends page didn't render. Likely an upload-still-processing or stale cache; retry after 30 seconds.
- Sign in button stuck disabled → Angular form validation rejected the email. Confirm `SMARTPM_EMAIL` is the exact login email.

## Step 3b: Tests

Smoke tests live at `{skill_dir}/references/tests/smartpm.spec.js` (uses `@playwright/test`). Run:

```bash
cd "{skill_dir}/references" && npx playwright test --config=tests/playwright.config.js
```

Tests verify: env-loader returns creds, navigation auto-logs in, the test project card is found via URL search, the Summary Report is captured, and all 16 trend graphs are captured (file existence + size sanity). Default test project is "Anchorage Alaska Temple" — override via `TEST_PROJECT_NAME=...`.

## Step 4: Verify

Read the captured PNGs visually. Confirm:
- `smartpm-summary-report.png` shows the Summary Report modal with milestones, health index, and S-curve
- Each graph file shows the correct chart with data points

If any screenshot looks wrong (blank, login page, wrong project), inform the user and offer to retry that capture.

**SmartPM processing warning:** If this command is called within 30 minutes of XER upload, SmartPM may still be processing. Check the Workspace page status. If processing is still running, warn the user and offer to wait.

## Step 5: Report

Mark checklist complete. Report:
- Total screenshots captured (17)
- File paths and sizes
- SmartPM URLs used
