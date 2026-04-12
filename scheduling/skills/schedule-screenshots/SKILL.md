---
name: schedule-screenshots
description: >
  Capture SmartPM screenshots for schedule update emails using Playwright via Chrome DevTools
  Protocol. Takes 17 screenshots: 1 Summary Report from the View Summary modal, and 16 individual
  trend graphs from the Graphs tab. For wide charts (Schedule Delay, End Date Variance), scrolls
  to the right to show latest data. Progressively disclosed from schedule-update-email.
  Also invocable independently via "take smartpm screenshots", "capture smartpm screenshots",
  "smartpm screenshots", "get the screenshots", or by running take-screenshots.bat in a project folder.
---

# SmartPM Screenshot Capture

Automate the capture of SmartPM screenshots required for weekly schedule update emails. Connects to the user's already-running Chrome browser via Playwright CDP — no credentials stored, uses the existing authenticated session.

## Screenshots Captured

### Summary Report (1 screenshot)
- `smartpm-summary-report.png` — View Summary modal from the Workspace page

### Trend Graphs (16 individual screenshots)

Each graph is captured individually from the Trends > Graphs tab:

| # | File | Chart |
|---|------|-------|
| 1 | `01-planned-vs-actual-percent-complete.png` | Planned VS Actual Percent Complete |
| 2 | `02-schedule-quality-grade-over-time.png` | Schedule Quality Grade Over Time |
| 3 | `03-project-health-index-over-time.png` | Project Health Index Over Time |
| 4 | `04-schedule-changes-over-time.png` | Schedule Changes Over Time |
| 5 | `05-schedule-delay-over-time.png` | Schedule Delay Over Time *(wide — scrolled right to latest data)* |
| 6 | `06-end-date-variance.png` | End Date Variance *(wide — scrolled right to latest data)* |
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

Charts are identified by their Angular component tags in DOM order:
`APP-CHART-PROGRESS-CURVE`, `APP-CHART-SCHEDULE-QUALITY-OVER-TIME`, `APP-CHART-PROJECT-HEALTH`,
`APP-CHART-SCHEDULE-CHANGES`, `APP-DELAY-WATERFALL`, `APP-END-DATE-VARIANCE`,
`APP-CHART-SCHEDULE-COMPRESSION`, `APP-CHART-VELOCITY`, `APP-CHART-SPI-OVER-TIME`,
`APP-CHART-HIT-RATE`, `APP-CHART-WINDOW-START-ACCURACY`, `APP-CHART-WINDOW-FINISH-ACCURACY`,
`APP-MISSING-LOGIC`, `APP-AVERAGE-TOTAL-FLOAT`, `APP-HIGH-TOTAL-FLOAT`, `APP-CRITICAL-PATH`

## Workflow

### Step 0: Pre-Flight Check

1. Verify Node.js is available: `node --version`
2. Check if Playwright is installed in `references/`. If `references/node_modules/playwright` does not exist, run `npm install` in the `references/` directory of this skill.
3. Check if Playwright browsers are installed. If not, run `npx playwright install chromium` in the `references/` directory.
4. No Chrome setup needed — the script launches its own Chromium with a persistent profile at `~/.smartpm-playwright-profile/`. First run requires manual SmartPM login; subsequent runs reuse the saved session.

### Step 1: Read Project Memory

Look for the most recent `*-project-memory.md` file in the current project folder:

```bash
ls -1 *-project-memory.md 2>/dev/null | sort -r | head -1
```

**If found:** Read the frontmatter to extract `smartpm_url`. Derive the URLs:
- Workspace URL: the `smartpm_url` value (ends with `/workspace`)
- Trends URL: replace `/workspace` with `/trends?tab=Graphs`

**If not found:** Ask the user for:
1. Project name and job number (or parse from the folder name — format: `YYYY-MM-DD -- JOB# ProjectName`)
2. SmartPM workspace URL

Then create the initial `YYYY-MM-DD-project-memory.md` file with today's date:

```markdown
---
project_name: {name}
job_number: {job_number}
smartpm_url: {workspace_url}
smartpm_trends_url: {trends_url}
smartpm_changelog_url: {changelog_url}
expected_attachments:
  - "Report 0.01*Master Schedule*.pdf"
  - "Report 0.02A*Critical Path*.pdf"
  - "Report 0.02B*Longest Critical Path*.pdf"
  - "Report 0.03*Near Critical*.pdf"
  - "Report 0.04A*Four Week Look Ahead*.pdf"
  - "Report 0.04B*Four Week Look Ahead*Construction*.pdf"
  - "Report 0.05*Impacts*.pdf"
  - "Report 0.06*Procurement Schedule*.pdf"
  - "Report 0.12*Construction Activities Only*.pdf"
  - "Report 0.13*Construction Activities With Baseline Variance*.pdf"
  - "*Schedule Analytics Report*.pdf"
  - "*KPI Comparison*.pdf"
  - "*Progress Update Export*.xlsm"
  - "*Procurement Update Export*.xlsm"
  - "*KPI Comparison*.xlsx"
---

# Project Memory — {job_number} {name}

## {today's date} (current)
- Screenshots captured: pending
```

The `expected_attachments` list uses glob patterns to match files in the project folder. Adjust the list per project — not all projects have every report type. The schedule-update-email skill reads this list in Step 6 to auto-collect attachment file paths.

### Step 2: Write Checklist

Create the `screenshots/` directory if it doesn't exist. Write `screenshots/checklist.md` using the checklist template from `references/checklist-template.md`, filling in the project name, date, and URLs.

Print the checklist to the console so the user can see the plan.

### Step 3: Run Capture Script

Execute the Playwright capture script:

```bash
node "{skill_references_path}/capture-smartpm.js" "{workspace_url}" "{trends_url}" "{output_dir}/screenshots"
```

The script will:
- Launch Chromium with a persistent profile (`~/.smartpm-playwright-profile/`)
- If not logged in, prompt the user to log in manually in the browser window (waits up to 5 min)
- Navigate to the Workspace page, click "View Summary", capture the Summary Report modal
- Navigate to the Trends Graphs page
- For each of the 16 `.highcharts-container` elements, use `element.screenshot()` to capture just that chart
- For wide charts (#5 and #6), scroll to the right first to show the most recent data
- Close the browser and print a JSON summary to stdout

**If login is needed:** A Chromium window opens and the script waits. Log in to SmartPM in that window. The session is saved to the persistent profile so future runs skip login.

**If the script exits with an error:** Read the error output and diagnose. Common issues:
- Timeout → SmartPM page didn't load (network issue or wrong URL)
- 0 charts found → Page didn't fully render; try running again
- Playwright not installed → Run `npx playwright install chromium` in the references/ directory

### Step 4: Verify Screenshots

Read the saved screenshot files visually to confirm they captured correctly:
- `smartpm-summary-report.png` — Shows the Summary Report modal with milestones, health index, and S-curve
- Each numbered graph file — Shows the correct chart with data points

If any screenshot looks wrong (blank, login page, wrong project), inform the user and offer to retry that specific capture.

### Step 5: Update Checklist & Report

Mark all checklist items as complete in `screenshots/checklist.md`. Update the project memory file's current entry with `Screenshots captured: yes`.

Report to the user:
- Total screenshots captured (17)
- File paths and sizes
- SmartPM URLs used (for hyperlinking in the email)

## Integration with schedule-update-email

When invoked from the email skill:
1. The email skill checks for `screenshots/` folder with the required PNGs
2. If missing, it loads this skill to capture them
3. This skill returns the file paths
4. The email skill passes them to `generate_email_docx.py` to embed in the .docx

When invoked standalone (via bat file or direct command):
1. Runs the full workflow above
2. Screenshots are saved and ready for the next email skill run

## Reference Files

| File | Purpose |
|------|---------|
| `references/capture-smartpm.js` | Playwright CDP script — connects to Chrome, navigates SmartPM, captures 17 screenshots. Run with `node capture-smartpm.js <workspace_url> <trends_url> <output_dir>`. |
| `references/package.json` | Node.js dependencies (playwright). Run `npm install` in references/ on first use. |
| `references/checklist-template.md` | Template for the progress checklist written to each project's screenshots/ folder. |
