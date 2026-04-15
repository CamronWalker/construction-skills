---
name: schedule-update
description: >
  Full weekly schedule update pipeline for Westland Construction. Handles all post-meeting
  steps: folder setup, SmartPM screenshot capture, email draft generation, and Outlook draft
  creation. Progressively disclosed -- routes by command arg or detects current phase from
  file system. Use for: "schedule update", "weekly update", "update email", "take screenshots",
  "smartpm screenshots", "schedule email", "draft the email", "copy schedule folder", "update
  status", "where are we in the update", "generate email", "create draft", or any schedule
  update workflow. Absorbs schedule-update-email and schedule-screenshots.
---

# Schedule Update Pipeline

Unified skill for the Westland weekly schedule update workflow. One entry point covers the full
post-meeting pipeline: folder setup, SmartPM screenshots, email draft, and Outlook draft creation.

## Commands

Invoke with an optional command argument:

| Invocation | What it does |
|------------|-------------|
| `/schedule-update` | No arg -- detect current phase and guide to the next step |
| `/schedule-update copy` | Copy schedule folder for today's date (pre-meeting step) |
| `/schedule-update screenshots` | Capture SmartPM graphs via Playwright |
| `/schedule-update email` | Generate the weekly update email draft |
| `/schedule-update draft` | Create Outlook draft from approved email content |
| `/schedule-update status` | Show where the project is in the pipeline |

Every command reads `project-context.md` first. If it is missing, stop with:
> "No project-context.md found in the Schedules root. Run the `schedule-project-init` skill first."

---

## Shared Setup

### Folder Resolution

All commands use this logic to find the Schedules root:

1. If CWD basename matches `YYYY-MM-DD` (a dated folder) → root is the **parent** (`../`)
2. If CWD basename is `Schedules` → root is CWD
3. If CWD contains a `Schedules/` child directory → root is that child
4. Otherwise → ask the user for the Schedules folder path

The grandparent of the Schedules root should match `W\d+ - .+` (e.g., `W1134 - Neiafu Tonga Temple Construction`).

### project-context.md

Lives in the **root Schedules folder** (not inside dated subfolders). Created by `schedule-project-init`.

```yaml
---
project_name: Project Name
job_number: W####
contractual_completion: Month Day, Year
smartpm_url: https://live.smartpmtech.com/#/company/.../workspace
smartpm_trends_url: https://live.smartpmtech.com/#/company/.../trends?tab=Graphs
smartpm_changelog_url: https://live.smartpmtech.com/#/company/.../changelog
to_recipients: "person@example.com; person2@example.com"
cc_recipients: "director@example.com; scheduling@example.com"
signer_name: SIGNER NAME
signer_title: TITLE
signer_mobile: ""
procore_company_id: 11093
procore_project_id: 12345
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
  - "COMPLETED_*Progress Update Export*.xlsm"
  - "COMPLETED_*Procurement Update Export*.xlsm"
  - "*KPI Comparison*.xlsx"
graph_screenshots:
  - "06-end-date-variance.png"
  - "07-schedule-compression-index-over-time.png"
  - "08-velocity.png"
  - "11-window-start-accuracy.png"
  - "12-window-finish-accuracy.png"
  - "09-spi-over-time.png"
  - "10-activity-hit-rate.png"
---
```

### Weekly email file

Each dated folder gets a `YYYY-MM-DD-update-email.md` with two sections:

1. **Update Email** -- the email content (successes, red flags, key items, etc.)
2. **Project Log** -- cumulative delay notes for claims and delay analysis

---

## `copy` -- Pre-Meeting Folder Setup

Creates a new dated folder for today's schedule update.

### Step 1: Resolve root

Apply folder resolution above. Identify the Schedules root.

### Step 2: Find most recent dated folder

List all `YYYY-MM-DD` subdirectories in the Schedules root, sort descending, and take the most recent. This is the template folder.

If no dated folders exist, create the folder structure from scratch (ask the user what files/subfolders to include).

### Step 3: Create today's folder

Create `{root}/{YYYY-MM-DD}/` using today's date. Copy the **folder structure** (not file contents) from the most recent dated folder:
- Create matching subdirectories (`screenshots/`, `meeting/`, etc.)
- Do NOT copy schedule files, XER files, or PDFs -- those are project deliverables
- Copy any batch scripts (`.bat`, `.ps1`) from the template folder -- these are reusable tools

### Step 4: Report

List the created folder and its contents. Tell the user what's next:
> "Folder created at `{path}`. When you're ready to update the schedule, remind the team to send their Excel update file."

---

## `screenshots` -- Capture SmartPM Graphs

Captures 17 screenshots from SmartPM: 1 Summary Report + 16 individual trend graphs.

### Step 0: Pre-Flight

1. Verify Node.js: `node --version`
2. Check if Playwright is installed: look for `node_modules/playwright` in `{skill_dir}/references/`. If missing, run `npm install` in `{skill_dir}/references/`.
3. Playwright browser check: if Chromium not installed, run `npx playwright install chromium` in `{skill_dir}/references/`.

### Step 1: Read Project Context

Apply folder resolution. Read `project-context.md`. Extract:
- `smartpm_url` (Workspace URL, ends with `/workspace`)
- Derive Trends URL: replace `/workspace` with `/trends?tab=Graphs`

Determine the output directory: `{dated_folder}/screenshots/`

If `project-context.md` is missing, stop with the error above.
If the user provides a SmartPM URL directly, use it and proceed without project-context.md.

### Step 2: Write Checklist

Create `{dated_folder}/screenshots/` if it does not exist.
Write `screenshots/checklist.md` from the template at `{skill_dir}/references/checklist-template.md`,
filling in project name, date, and SmartPM URLs.

Print the checklist.

### Step 3: Run Capture Script

```bash
node "{skill_dir}/references/capture-smartpm.js" \
  "{workspace_url}" "{trends_url}" "{dated_folder}/screenshots"
```

The script:
- Launches Chromium with a persistent profile at `~/.smartpm-playwright-profile/`
- On first run: opens a browser window, waits up to 5 min for manual SmartPM login
- Summary Report: navigates to Workspace, opens "View Summary" modal, captures as `smartpm-summary-report.png`
- Trend graphs: navigates to Trends > Graphs tab, captures each `.highcharts-container` individually:

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

Angular component tags (DOM order): `APP-CHART-PROGRESS-CURVE`, `APP-CHART-SCHEDULE-QUALITY-OVER-TIME`,
`APP-CHART-PROJECT-HEALTH`, `APP-CHART-SCHEDULE-CHANGES`, `APP-DELAY-WATERFALL`, `APP-END-DATE-VARIANCE`,
`APP-CHART-SCHEDULE-COMPRESSION`, `APP-CHART-VELOCITY`, `APP-CHART-SPI-OVER-TIME`, `APP-CHART-HIT-RATE`,
`APP-CHART-WINDOW-START-ACCURACY`, `APP-CHART-WINDOW-FINISH-ACCURACY`, `APP-MISSING-LOGIC`,
`APP-AVERAGE-TOTAL-FLOAT`, `APP-HIGH-TOTAL-FLOAT`, `APP-CRITICAL-PATH`

**Errors:** Timeout = network or wrong URL. 0 charts = page didn't render fully (retry). Missing Playwright = run `npx playwright install chromium` in references/.

### Step 4: Verify

Read the captured PNGs visually. Confirm:
- `smartpm-summary-report.png` shows the Summary Report modal with milestones, health index, and S-curve
- Each graph file shows the correct chart with data points

If any screenshot looks wrong (blank, login page, wrong project), inform the user and offer to retry that capture.

**SmartPM processing warning:** If this command is called within 30 minutes of XER upload, SmartPM may still be processing. Check the Workspace page status. If processing is still running, warn the user and offer to wait.

### Step 5: Report

Mark checklist complete. Report:
- Total screenshots captured (17)
- File paths and sizes
- SmartPM URLs used

---

## `email` -- Generate Update Email Draft

Generates the Westland schedule update email from XER data, previous email, and meeting transcript.

### Step 0: Read Project Context & Previous Update

Apply folder resolution. Read `project-context.md` for all config.

To find the previous update email: list all `YYYY-MM-DD` sibling folders, sort descending, skip the current folder, check each for `*-update-email.md`. Use the first match.

### Step 1: Check Inputs

Before proceeding, verify which inputs are present:

| Input | Location | Required |
|-------|----------|----------|
| Current XER | `{dated_folder}/*.xer` | REQUIRED -- cannot generate without it |
| Previous email | Previous `YYYY-MM-DD-update-email.md` | Recommended -- carry forward red flags/stalled tasks |
| Meeting transcript | `{dated_folder}/meeting/*.txt` or `.md` or `.docx` | Recommended -- mine for successes/issues |
| Screenshots | `{dated_folder}/screenshots/*.png` | Needed for sections 3 and 12 |

If XER is missing, stop: "No XER file found in `{dated_folder}`. Export the updated schedule and place the XER here before running `email`."

If any recommended input is missing, list what's absent and ask whether to proceed without it or locate it. Do not auto-proceed without telling the user.

### Step 2: Check Screenshots

Check for `screenshots/` folder with at least `smartpm-summary-report.png` and the files listed in `graph_screenshots` from project-context.md.

If screenshots are missing or incomplete, ask: "Screenshots are missing. Run `/schedule-update screenshots` now, or should I proceed without them?" If the user asks to run screenshots first, do so (run the `screenshots` workflow above), then continue.

### Step 3: Parse XER & Extract Metrics

Parse the XER using the `schedule-xer` skill. Calculate:

- **Days behind/ahead:** Compare projected Substantial Completion date to contractual completion. Use SC milestone early finish if present; otherwise use project end date from PROJECT table.
- **Gain/loss since last update:** Compare to previous email's days-behind figure.
- **Critical path items:** Activities with total float = 0 or near-zero.
- **Stalled tasks:** `TK_NotStart` status with early start before data date.
- **Slipping tasks:** Started but remaining duration suggests late finish.

### Step 4: Carry Forward from Previous Email

If a previous email exists, extract:
- Red flags list
- Stalled/slipping tasks
- Key items & issues

Ask the user: "These items were on last week's list. Which should carry forward?" Present as a multi-select (keep / remove / update each item).

### Step 5: Mine Meeting Transcript

If a transcript is provided, extract:
- **Successes** (completions, deliveries, milestones hit)
- **Issues/concerns** (delays, material problems, trade performance)
- **Recovery efforts** (acceleration plans, added crews, revised sequences)
- **New red flags or risks**

Present extracted items for confirmation: "I found these items in the meeting transcript. Which should go in the email?" Do not include without user confirmation.

### Step 6: Assemble Draft Email

Build using `{skill_dir}/references/email-template.md` for structure. The 12 sections in order:

1. **Project Info Header** -- project name, job number, contractual completion, projected SC date. Labels teal, values black.
2. **Days Behind/Ahead** -- from XER. Full line red (`#C94444`) if behind, green (`#3A9E6B`) if ahead.
3. **SmartPM Summary Report** -- embed `screenshots/smartpm-summary-report.png`. If missing, invoke `screenshots` workflow.
4. **Successes** -- from transcript extraction + user additions.
5. **Gain/Loss Narrative** -- calculated figure + user narrative. Full line colored.
6. **EOT/Recovery Status** -- from transcript + previous email + user input.
7. **Significant Logic Changes** -- prompt user for summary of changes made during update.
8. **SmartPM Changelog Link** -- from project-context.md `smartpm_changelog_url`.
9. **Red Flags** -- carried forward + new from transcript + user additions. Items in `**bold**` render bold + red.
10. **Stalled/Slipping Tasks** -- from XER analysis + carried forward + user additions. `**bold**` = red.
11. **Key Items & Issues** -- from transcript + previous email + user additions. `**bold**` = red.
12. **Performance Graphs** -- graph screenshots from `screenshots/`, in order from `graph_screenshots` in project-context.md.

Include closing paragraphs about Schedule Compliance Report and procurement spreadsheets as applicable.

### Step 7: User Review

Present the full draft to the user. Allow section-by-section edits:
> "Here's the draft email. Review each section -- would you like to change anything?"

After the user approves, ask whether to:
- Save the draft to `YYYY-MM-DD-update-email.md` only (review later)
- Save AND generate the Outlook draft now (run `draft` workflow below)

### Step 8: Save Email File

Save `{dated_folder}/YYYY-MM-DD-update-email.md` with:

```yaml
---
date: YYYY-MM-DD
days_behind: {number}
gain_loss: {+/- days}
projected_completion: {date}
screenshots_captured: true/false
---
```

Followed by:
- **## Update Email** -- the full 12-section email content
- **## Project Log** -- cumulative notes on delays, late starts, impacts, decisions. Each week adds a dated entry. Do not overwrite previous entries.

Update `project-context.md` if any config changed (recipients, attachments, graphs).

---

## `draft` -- Create Outlook Draft

Creates the Outlook draft from the approved email content. Requires the `YYYY-MM-DD-update-email.md` file for the current dated folder to already exist (run `email` first).

### Step 1: Locate Email File

Find `{dated_folder}/YYYY-MM-DD-update-email.md`. If missing:
> "No update email file found for today's folder. Run `/schedule-update email` first."

### Step 2: Generate Draft

Read `{skill_dir}/references/generate_email_msg.py`. The script:
- Builds an HTML email body (Arial font, inline styles, Outlook Word-renderer compatible)
- Embeds screenshots as inline CID images hyperlinked to SmartPM URLs
- Attaches file attachments (PDFs, Excel) matched via `expected_attachments` glob patterns
- Includes the Westland email signature (logo, name, title, office phone, optional mobile)
- Saves the draft to Outlook Drafts via COM automation

**Pre-conditions:**
- Classic Outlook must be open (not just installed -- open it from Start menu for Exchange sync)
- `pywin32` must be installed (`pip install pywin32`)

Run the script. If `pywin32` is missing, prompt: "Install pywin32 with `pip install pywin32`, then retry." If COM fails entirely, fall back to `generate_email_docx.py` and inform the user.

### Step 3: Confirm

Tell the user: "Draft saved to your Outlook Drafts folder -- open Drafts in new Outlook, review, and click Send."

---

## `status` -- Pipeline Status

Shows where the project is in the weekly update pipeline based on what files exist.

### Detection Logic

| Check | Indicates |
|-------|-----------|
| Today's dated folder exists | Step 1 (copy) done |
| `{dated_folder}/*.xer` exists | Export done (step 5) |
| `{dated_folder}/meeting/` has files | Transcript copied (step 7) |
| `{dated_folder}/screenshots/` has all required PNGs | Screenshots done (step 10) |
| `{dated_folder}/YYYY-MM-DD-update-email.md` exists | Email drafted (step 11) |
| Outlook draft exists | Draft created (step 13) |

Report each phase as DONE / PENDING / NOT STARTED, and name the recommended next step.

---

## No-Arg Entry -- Phase Detection

When invoked without a command:

1. Resolve the Schedules root and read `project-context.md`
2. Determine the current dated folder (today's date or most recent existing)
3. Run the detection logic from `status` above
4. Based on the phase, route automatically:
   - If no dated folder for today → "Looks like you haven't started the update yet. Run `/schedule-update copy` to set up today's folder."
   - If folder exists but no XER → "Folder is set up. Export the schedule and drop the XER in `{path}`."
   - If XER exists but no screenshots → "XER is here. Run `/schedule-update screenshots` to capture SmartPM graphs."
   - If screenshots exist but no email → "Screenshots are ready. Run `/schedule-update email` to generate the draft."
   - If email exists but no Outlook draft → "Email draft is saved. Run `/schedule-update draft` to create the Outlook draft."
   - If draft created → "Draft is in Outlook. Send when ready."

---

## Full Pipeline Reference

| # | Step | Owner | Command |
|---|------|-------|---------|
| 1 | Copy schedule folder for today's date | Agent | `copy` |
| 2 | Email reminder to get Excel update file | Human | -- |
| 3 | Update schedule using Excel file | Human | -- |
| 4 | Make corrections, discussion, complete update | Human | (in meeting) |
| 5 | Export schedule files | Human | -- |
| 6 | Upload XER to SmartPM | Human | -- |
| 7 | Copy meeting transcript to meeting folder | Human | -- |
| 8 | Export PDF attachments from schedule software | Human | -- |
| 9 | Create next week's Excel files | Human | -- |
| 10 | Capture SmartPM graphs for email | Agent | `screenshots` |
| 11 | Generate update email draft | Agent | `email` |
| 12 | Review email draft | Human | -- |
| 13 | Create Outlook draft | Agent | `draft` |
| 14 | Send email | Human | -- |

---

## Reference Files

All reference files live in `references/` within this skill directory.

| File | Purpose |
|------|---------|
| `references/email-template.md` | Full email template -- 12 sections, formatting rules, attachment list |
| `references/generate_email_msg.py` | Outlook draft via COM automation. Requires `pywin32` and classic Outlook open. |
| `references/generate_email_docx.py` | Fallback: .docx output if Outlook unavailable. Requires `python-docx`. |
| `references/westland-logo.png` | Email signature logo (229x108 RGBA) |
| `references/capture-smartpm.js` | Playwright script -- captures 17 SmartPM screenshots. Run with Node.js. |
| `references/package.json` | Node.js dependencies for Playwright. Run `npm install` in `references/` on first use. |
| `references/checklist-template.md` | Template for the progress checklist written to each project's screenshots/ folder. |
| `references/Master Schedule Update Email Example.docx` | Original Westland email example (Neiafu Tonga Temple) for reference |
| `references/Schedule Update Email Procedure.docx` | Original Westland procedure document for reference |
