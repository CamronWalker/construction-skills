# Westland Schedule Update Email Template

This template defines the structure, sections, and formatting for the weekly schedule update email per Westland procedures. The email is assembled section by section, then output as an Outlook .msg draft file (HTML email with inline images). Double-click the .msg to open in Outlook, review, and click Send. Fallback: .docx output if Outlook is unavailable.

---

## Email Structure (sections in order)

### 1. Project Information Header

```
Project: [Project Name]
Job Number: [W####]
Contractual Completion Date: [Date]
Projected Substantial Completion Date: [Date]
```

### 2. Days Ahead/Behind Schedule

Format: `Days Ahead/Behind Schedule: X Days`
- The **entire line** (label + value) should be colored — not just the number
- Use **green** text (#008000) for days ahead or on schedule
- Use **red** text (#FF0000) for days behind

### 3. SmartPM Summary Report

Paste a screenshot of the SmartPM summary report from the Company Dashboard view.
Right-click the screenshot and hyperlink it to the SmartPM project URL.

### 4. Successes

```
Successes:
[Bullet list of wins from the update period — completed milestones, deliveries, trade performance]
```

### 5. Schedule Gain / Loss Since Last Update

Format: `Schedule Gain / Loss Since The Last Update: X Day Gain/Loss`
- The **entire line** (label + value) should be colored — not just the number
- Use **green** text (#008000) for gain
- Use **red** text (#FF0000) for loss

Follow with a narrative paragraph explaining what drove the change. Be specific about which activities, trades, or issues caused the gain or loss.

### 6. Status of EOT / Recovery Efforts

```
Status Of EOT / Recovery Efforts:
[Narrative describing current recovery strategy, pending EOTs, trade performance issues,
and what needs to happen to get back on track]
```

### 7. Significant Changes to Schedule Logic

```
Significant Changes To Schedule Logic:
[Narrative of logic changes — additions, deletions, relationship changes, scope changes captured]
```

Include the SmartPM changelog link:
```
Please refer to the attached Analytics Report, or review schedule changes in SmartPM for specifics.
[SmartPM changelog URL]
```

### 8. Red Flags

```
Red Flags:
1. [Red flag item — bold or red for high priority]
2. [Red flag item]
3. [Red flag item]
```

Carry forward unresolved items from previous emails. Bold or mark in red any that need immediate focus.

### 9. Stalled or Slipping Tasks

```
Stalled Or Slipping Tasks
1. [Task description — bold or red for high priority]
2. [Task description]
3. [Task description]
```

Carry forward unresolved items from previous emails. Bold or mark in red any that need immediate focus.

### 10. Key Items & Issues to Focus On

```
Key Items & Issues To Focus On
1. [Key item — bold or red for high priority]
2. [Key item]
```

### 11. Schedule Performance Graphs

```
Schedule Performance Graphs
The charts below show our actual starts and finishes compared to planned, schedule compression,
and monthly activity finish distribution. You can get a better view of these charts and drill down
to greater detail regarding specific activities and trade performance by logging on to SmartPM
and clicking the View Trends link on the right side of the screen.
```

Include individual graph screenshots from SmartPM View Trends, in this default order:
1. End Date Variance (`06-end-date-variance.png`)
2. Schedule Compression Index Over Time (`07-schedule-compression-index-over-time.png`)
3. Monthly Activity Start & Finish Distribution (`08-velocity.png`)
4. Window Start Accuracy (`11-window-start-accuracy.png`)
5. Window Finish Accuracy (`12-window-finish-accuracy.png`)
6. SPI Over Time (`09-spi-over-time.png`)
7. Activity Hit Rate (%) (`10-activity-hit-rate.png`)

This order can be customized per project via the `graph_screenshots` list in `project-memory.md`.
Each screenshot is hyperlinked to the SmartPM View Trends URL.

### 12. Attachments & Closing

```
I have again included the Schedule Compliance Report in excel for your use.
Please note: You will need to verify responsibility for the impacts.
This report should be distributed to the Project Team each week and reviewed in detail
during the OAC. Please include the form with the meeting minutes and add language to the
minutes stating all parties reviewed the Schedule Compliance Report in detail and acknowledge
doing so. If they wish to make any adjustments, or contest any information included in the
report they may do so by responding to the meeting minutes within 24 hours, or as defined
by the contract.

I have included the procurement and progress update spreadsheets.
Please use these to fill out all actual dates and confirmed durations prior to each update.
This will significantly reduce the time we spend updating each week to give us more time
to work on recovery planning.
```

---

## Attachments List

Include the following with each update email:
- Schedule layout PDFs: Master Schedule, Critical Path, Near Critical, Four Week Lookahead
- SmartPM Analytics Report
- Schedule Compliance Report (Excel) — if applicable
- Procurement and Progress Update Spreadsheets — if applicable
- Any other layouts requested by the project team

---

## Distribution

- **TO:** Project team
- **CC:** Project Director, all Scheduling Department members

---

## Email Options (per Westland procedure)

### Option A: Reply-All Method
Paste the master template into an email. Every update, reply-all to the last email update, then copy and edit the information.

### Option B: Document Method
Create a project-specific schedule update email document using this template. Save to your computer with the day's date. Each update, duplicate the document, update the information, save with the new date. Copy and paste into email.

---

## Formatting Notes

- Output targets HTML email (.msg format) with inline styles only — no `<style>` blocks (Outlook's Word renderer strips them)
- Font: Calibri 11pt to match Outlook's default compose font
- Section headers should be **bold** (12pt)
- Days behind/ahead and gain/loss: **entire line** colored red or green, bold
- Bold or red text for high-priority red flags, stalled tasks, and key issues
- Screenshots embedded as inline CID images, hyperlinked to their SmartPM source URLs
- The `schedule-screenshots` skill automates SmartPM screenshot capture via Playwright
