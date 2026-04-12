---
name: schedule-update-email
description: >
  Generate a Westland schedule update email from XER data, previous update emails, and meeting
  transcripts. Use this skill whenever the user says "schedule update email", "weekly update email",
  "schedule email", "update report", "write the update email", "draft the schedule email", or wants
  to create the post-update communication following Westland procedures. Outputs an Outlook draft
  via COM automation — open Drafts in new Outlook, review, and click Send.
---

# Schedule Update Email Generator

Generate a Westland schedule update email following the Westland Schedule Update Email Procedure. The email is assembled from XER data, previous emails, and meeting transcripts, then saved as an Outlook draft via COM automation. The draft syncs to Exchange and appears in new Outlook — open Drafts, review, and click Send.

## Project Files

Each project folder contains two markdown files:

### `project-memory.md` (one per project, updated in place)

Project-level configuration that carries forward across all updates:

```yaml
---
project_name: Nauvoo House Visitors' Center
job_number: NTVC
contractual_completion: May 30, 2026
smartpm_url: https://live.smartpmtech.com/...
smartpm_trends_url: https://live.smartpmtech.com/.../trends?tab=Graphs
smartpm_changelog_url: https://live.smartpmtech.com/.../changelog
to_recipients: "person@example.com; person2@example.com"
cc_recipients: "director@example.com; scheduling@example.com"
signer_name: CAMRON WALKER
signer_title: SCHEDULER
signer_mobile: ""
expected_attachments:
  - "Report 0.01*Master Schedule*.pdf"
  - "*Schedule Analytics Report*.pdf"
  - "*Progress Update Export*.xlsm"
graph_screenshots:
  - "06-end-date-variance.png"
  - "07-schedule-compression-index-over-time.png"
  - "11-window-start-accuracy.png"
  - "12-window-finish-accuracy.png"
  - "09-spi-over-time.png"
  - "10-activity-hit-rate.png"
---
```

### `YYYY-MM-DD-update-email.md` (one per week)

Weekly email content and project log. Two sections:

1. **Update Email** — the content that becomes the email (successes, red flags, key items, etc.). Items wrapped in `**markdown bold**` render bold + red in the email (high priority).
2. **Project Log** — cumulative notes on delays, late starts, impacts, and decisions for future claims or delay analysis.

## Inputs

1. **Current XER file** (just updated) — REQUIRED
2. **Previous update email** (`YYYY-MM-DD-update-email.md` from last week, or text/.docx/pasted) — OPTIONAL but recommended
3. **Meeting transcript** (from the schedule update meeting) — OPTIONAL but recommended

## Workflow

### Step 0: Read Project Memory & Previous Update

Look for `project-memory.md` in the project folder. If found, read it for: SmartPM URLs, recipients, signer info, expected attachments, and graph selection.

Also look for the most recent `*-update-email.md` file to carry forward red flags, stalled tasks, and key items.

**If `project-memory.md` is not found**, run the **Project Setup Q&A** (see below).

### Step 1: Parse XER & Extract Metrics

Parse the XER using the `schedule-xer` skill. Calculate:

- **Days behind/ahead:** Compare projected Substantial Completion date to contractual completion date. If SC milestone exists, use its early finish. Otherwise, use the project end date from the PROJECT table.
- **Gain/loss since last update:** Compare current days behind to the previous email's days behind figure. If no previous email, report current status only.
- **Critical path items:** Activities with total float = 0 or near-zero
- **Stalled tasks:** Activities past their early start with no actual start recorded (status = `TK_NotStart` but early start < data date)
- **Slipping tasks:** Activities that appear to be losing time — started but remaining duration suggests they'll finish late

### Step 2: Carry Forward from Previous Update Email

If a previous `*-update-email.md` exists, extract:
- Red flags list
- Stalled/slipping tasks list
- Key items & issues list

For each carried-forward item, use AskUserQuestion to prompt:
> "These items were on last week's list. Which should carry forward?"

Present as a multi-select with options to keep, remove, or update each item.

### Step 3: Mine Meeting Transcript

If a meeting transcript is provided, extract:
- **Successes** mentioned (completions, deliveries, milestones hit)
- **Issues/concerns** discussed (delays, material problems, trade performance)
- **Recovery efforts** discussed (acceleration plans, added crews, revised sequences)
- **New red flags** or risks raised

Present extracted items to the user for confirmation before including them. Use AskUserQuestion:
> "I extracted these items from the meeting transcript. Which should be included in the email?"

### Step 4: Assemble Draft Email

Build the email following the Westland template (see `references/email-template.md` for full structure). The 12 sections in order:

1. **Project Info Header** — Project name, job number, contractual completion, projected SC date (from XER). Labels in teal, values in black.
2. **Days Behind/Ahead** — Calculated from XER. Entire line colored: red `#C94444` if behind, green `#3A9E6B` if ahead.
3. **SmartPM Summary Report** — Check for `screenshots/smartpm-summary-report.png`. If found, embed it. If not, invoke the `schedule-screenshots` skill.
4. **Successes** — From transcript extraction + user additions
5. **Gain/Loss Narrative** — Calculated figure + user narrative explaining what drove the change. Entire line colored.
6. **EOT/Recovery Status** — From transcript + previous email + user input
7. **Significant Logic Changes** — Prompt user for summary of changes made during update
8. **SmartPM Changelog Link** — From project memory
9. **Red Flags** — Carried forward + new from transcript + user additions. Items wrapped in `**bold**` render bold + red.
10. **Stalled/Slipping Tasks** — From XER analysis + carried forward + user additions. `**bold**` = red.
11. **Key Items & Issues** — From transcript + previous email + user additions. `**bold**` = red.
12. **Performance Graphs** — Individual graph screenshots from `screenshots/` folder, in the order specified by `graph_screenshots` in project memory.

Include closing paragraphs about Schedule Compliance Report and procurement spreadsheets as applicable.

### Step 5: User Review & Edit

Present the full draft email to the user. Allow section-by-section edits. Prompt:
> "Here's the draft email. Review each section — would you like to change anything?"

### Step 6: Generate Outlook Draft

Read `references/generate_email_msg.py` and use it to generate the Outlook draft. The script:
- Builds an HTML email body (Arial font, inline styles, Outlook Word-renderer compatible)
- Embeds screenshots as inline CID images hyperlinked to SmartPM URLs
- Attaches file attachments (PDFs, Excel) matched from `expected_attachments` glob patterns
- Includes the Westland email signature (logo, name, title, office phone, optional mobile)
- Saves the draft to Outlook Drafts folder via COM

Classic Outlook must be open (not just installed — open it from the Start menu before generating so the Exchange sync is active). If `pywin32` is not installed, prompt the user to install it (`pip install pywin32`) and retry. As a last-resort fallback, use `generate_email_docx.py` and inform the user.

Tell the user: "Draft saved to your Outlook Drafts folder — open Drafts in new Outlook, review, and click Send."

### Step 7: Save Update Email & Project Log

Save the weekly `YYYY-MM-DD-update-email.md` file with:
- Frontmatter: date, days_behind, gain_loss, projected_completion, screenshots_captured
- **Update Email** section: all 12 sections of email content (successes, red flags, etc.)
- **Project Log** section: detailed notes on delays, late starts, impacts, decisions — anything relevant for future claims or delay analysis. This section is cumulative; each week adds a dated entry.

Update `project-memory.md` if any settings changed (recipients, attachments, graphs).

## Project Setup Q&A

When `project-memory.md` does not exist, run this setup flow to create it:

1. **Project name and job number** — Parse from folder name (`YYYY-MM-DD -- JOB# ProjectName`) or ask user
2. **Contractual completion date** — Ask user
3. **SmartPM workspace URL** — Ask user (derive trends and changelog URLs from it)
4. **To recipients** — Ask user: "Who should receive the update email? (semicolon-separated)"
5. **CC recipients** — Ask user: "Who should be CC'd? (default: Project Director + Scheduling Department)"
6. **Signer** — Ask user: "Whose name and title for the email signature?" Default: CAMRON WALKER, SCHEDULER
7. **Signer mobile** — Ask user: "Mobile number for signature? (leave blank if none)"
8. **Previous email** — Ask user: "Paste or attach a previous update email so I can extract the format and carried-forward items"
9. **Expected attachments** — Scan the project folder for PDFs and Excel files. Present the list and ask which ones should be attached each week.
10. **Graph selection** — Present the default graph list and ask if any should be added or removed.

Save the results to `project-memory.md`.

## SmartPM Screenshots

Before assembling sections 3 and 12, check if `<project-folder>/screenshots/` exists with the required PNGs.

The summary report is always: `smartpm-summary-report.png`

The performance graphs are read from the `graph_screenshots` list in `project-memory.md`. Default order:
1. `06-end-date-variance.png`
2. `07-schedule-compression-index-over-time.png`
3. `08-velocity.png` (Monthly Activity Start & Finish Distribution)
4. `11-window-start-accuracy.png`
5. `12-window-finish-accuracy.png`
6. `09-spi-over-time.png`
7. `10-activity-hit-rate.png`

If screenshots are missing, invoke the `schedule-screenshots` skill to capture them, or prompt the user to run `take-screenshots.bat` from the project folder.

## Distribution Reminder

- **TO:** Project team (from `project-memory.md`)
- **CC:** Project Director, all Scheduling Department members (from `project-memory.md`)

---

## Reference Files

| File | When to Load |
|------|-------------|
| `references/email-template.md` | Full email template with all 12 sections, formatting rules, and attachments list |
| `references/generate_email_msg.py` | Python script for generating the Outlook draft via COM automation. Requires `pywin32` — install with `pip install pywin32`. Requires classic Outlook open. |
| `references/westland-logo.png` | Westland email signature logo (229x108 RGBA, works in dark and light mode) |
| `references/generate_email_docx.py` | Fallback: Python script for generating .docx output if Outlook is unavailable. Requires `python-docx`. |
| `references/Master Schedule Update Email Example.docx` | Original Westland email example (Neiafu Tonga Temple) for reference |
| `references/Schedule Update Email Procedure.docx` | Original Westland procedure document for reference |
