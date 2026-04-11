---
name: schedule-update-email
description: >
  Generate a Westland schedule update email from XER data, previous update emails, and meeting
  transcripts. Use this skill whenever the user says "schedule update email", "weekly update email",
  "schedule email", "update report", "write the update email", "draft the schedule email", or wants
  to create the post-update communication following Westland procedures. Outputs a .docx file
  formatted for pasting into Outlook.
---

# Schedule Update Email Generator

Generate a Westland schedule update email following the Westland Schedule Update Email Procedure. The email is assembled from XER data, previous emails, and meeting transcripts, then output as a .docx file for pasting into Outlook.

## Inputs

1. **Current XER file** (just updated) — REQUIRED
2. **Previous update email** (text, .docx, or pasted content) — OPTIONAL but recommended for carrying forward red flags, stalled tasks, and key issues
3. **Meeting transcript** (from the schedule update meeting) — OPTIONAL but recommended for extracting successes, issues discussed, and recovery efforts

## Workflow

### Step 0: Read Project Memory

Look for the most recent `*-project-memory.md` file in the project folder:

```bash
ls -1 *-project-memory.md 2>/dev/null | sort -r | head -1
```

If found, read it for context: SmartPM URLs, previous weeks' metrics, carried-forward red flags, and historical trend data. Use this context when writing gain/loss narratives and identifying items to carry forward.

If not found, create the initial `YYYY-MM-DD-project-memory.md` after Step 1 (once project info and SmartPM URLs are gathered).

### Step 1: Parse XER & Extract Metrics

Parse the XER using the `schedule-xer` skill. Calculate:

- **Days behind/ahead:** Compare projected Substantial Completion date to contractual completion date. If SC milestone exists, use its early finish. Otherwise, use the project end date from the PROJECT table.
- **Gain/loss since last update:** Compare current days behind to the previous email's days behind figure. If no previous email, report current status only.
- **Critical path items:** Activities with total float = 0 or near-zero
- **Stalled tasks:** Activities past their early start with no actual start recorded (status = `TK_NotStart` but early start < data date)
- **Slipping tasks:** Activities that appear to be losing time — started but remaining duration suggests they'll finish late

### Step 2: Carry Forward from Previous Email

If the previous update email is provided, extract:
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

1. **Project Info Header** — Project name, job number, contractual completion, projected SC date (from XER)
2. **Days Behind/Ahead** — Calculated from XER (red text if behind, green if ahead)
3. **SmartPM Summary Report** — Check for `screenshots/smartpm-summary-report.png`. If found, embed it. If not, invoke the `schedule-screenshots` skill to capture it (or prompt user to run `take-screenshots.bat`). Prompt user for SmartPM project URL if not in project memory.
4. **Successes** — From transcript extraction + user additions
5. **Gain/Loss Narrative** — Calculated figure + user narrative explaining what drove the change
6. **EOT/Recovery Status** — From transcript + previous email + user input
7. **Significant Logic Changes** — Prompt user for summary of changes made during update
8. **SmartPM Changelog Link** — Prompt user for the SmartPM changelog URL
9. **Red Flags** — Carried forward + new from transcript + user additions. Bold/red for high priority.
10. **Stalled/Slipping Tasks** — From XER analysis + carried forward + user additions
11. **Key Items & Issues** — From transcript + previous email + user additions
12. **Performance Graphs** — Check for `screenshots/smartpm-performance-graphs-1.png` and `screenshots/smartpm-performance-graphs-2.png`. If found, embed them. If not, invoke the `schedule-screenshots` skill to capture them. Prompt user for View Trends URL if not in project memory.

Include closing paragraphs about Schedule Compliance Report and procurement spreadsheets as applicable.

### Step 5: User Review & Edit

Present the full draft email to the user. Allow section-by-section edits. Prompt:
> "Here's the draft email. Review each section — would you like to change anything?"

### Step 6: Generate .docx Output

Read `references/generate_email_docx.py` and use it to generate the formatted .docx file. Apply:
- Red/green color coding for days behind/ahead and gain/loss
- Bold section headers
- Numbered lists for red flags, stalled tasks, key items
- Placeholder markers for SmartPM screenshots

Save to: `<project-folder>/Schedule Update Email - [Date].docx`

If screenshots were captured (either pre-existing in `screenshots/` or via the `schedule-screenshots` skill), pass the file paths to `generate_email_docx.py` to embed them directly in the .docx. The SmartPM URLs from project memory are used for hyperlinking.

If no screenshots are available, the .docx will contain placeholder text as a fallback.

Remind the user to:
- Verify embedded SmartPM screenshots look correct (or insert manually if placeholders remain)
- Attach: Master Schedule PDF, Critical Path PDF, Near Critical PDF, 4-Week Lookahead PDF, SmartPM Analytics Report, and any other requested layouts
- Attach Schedule Compliance Report (Excel) and procurement/progress spreadsheets if applicable

### Step 7: Update Project Memory

After the .docx is generated, update (or create) the project memory file (`YYYY-MM-DD-project-memory.md`):

1. Read the most recent existing `*-project-memory.md` for prior history
2. Create a new file with today's date, carrying forward all previous entries
3. Add a new dated entry with this week's metrics:
   - Days behind/ahead
   - Gain/loss
   - Red flags (carried forward and new)
   - Stalled/slipping tasks
   - Key issues
   - Screenshots captured: yes/no

## SmartPM Screenshots

Before assembling sections 3 and 12, check if `<project-folder>/screenshots/` exists with the required PNGs:
- `smartpm-summary-report.png`
- `smartpm-performance-graphs-1.png`
- `smartpm-performance-graphs-2.png`

If found, use them directly. If not, invoke the `schedule-screenshots` skill to capture them, or prompt the user to run `take-screenshots.bat` from the project folder.

The `schedule-screenshots` skill uses Playwright via Chrome DevTools Protocol to connect to the user's already-running Chrome browser and capture screenshots from SmartPM — no manual screenshotting needed.

## Distribution Reminder

- **TO:** Project team
- **CC:** Project Director, all Scheduling Department members

---

## Reference Files

| File | When to Load |
|------|-------------|
| `references/email-template.md` | Full email template with all 12 sections, formatting rules, and attachments list |
| `references/generate_email_docx.py` | Python script for generating the .docx output. Requires `python-docx` — install with `pip install python-docx` if not available. |
| `references/Master Schedule Update Email Example.docx` | Original Westland email example (Neiafu Tonga Temple) for reference |
| `references/Schedule Update Email Procedure.docx` | Original Westland procedure document for reference |
