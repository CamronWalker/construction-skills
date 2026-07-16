---
name: construction-daily-log-entry
description: >
  Draft and post daily-log entries to Procore — manpower, calls, and photos — with a dry-run
  preview before anything is written. Use when someone says "log manpower", "add a daily log",
  "post today's log", "log a call", "record who was on site", "add a photo to the daily log",
  "enter the crew counts", or wants field activity captured in Procore's Daily Log. Can also read
  the schedule for a scheduled-vs-actual sanity check on the day. Every write is confirmed by the
  user first. For turning emails into call-log entries use construction-email-to-log; to review or
  grade existing logs use construction-daily-log-review.
---

# Construction Daily Log Entry

Capture what happened on site into Procore's Daily Log — manpower counts, calls, and photos — quickly and correctly, with the user approving each write. Westland uses three daily-log types: **manpower**, **calls**, and **photos** (notes ride in the manpower `comments` field).

> Writes through the Procore MCP. See `construction-procore-toolbox` for project resolution and the two-stage write contract — every create here follows it.

## When to use

- "Log manpower / crew counts for today" / "post today's daily log"
- "Log a call with [party]" / "record the call about X"
- "Add these photos to the daily log"

## Workflow

1. **Resolve the project** — `find_project` → confirm → `projectId`.
2. **Set the date.** Default to today (local); honor "yesterday", a specific date, etc. State the date you're logging.
3. **Gather the entry data:**
   - **Manpower:** for each sub on site — resolve the company with `find_company_vendor` → `vendorId`; capture `numWorkers`, `hours`, and `comments` (the work performed — this is the record, make it specific).
   - **Call:** `subjectTo` (and `subjectFrom`), a `description` of what was discussed / decided / to follow up, and start/end time if known.
   - **Photo:** the image + a caption/description.
4. **Optional scheduled-vs-actual read.** If useful, `list_schedule_activities` for the date to compare what was scheduled against who actually showed — call out crews that were scheduled but absent, or work happening off-plan. Read-only; it just informs the log/comment.
5. **Dry-run every write.** Call `create_manpower_log` / `create_call_log` / `create_photo` **without** `confirm` → show the preview(s) → get an explicit yes → re-call with `confirm: true`. Batch the previews so the user approves the day's entries together.
6. **Report** what was created (with IDs) and flag anything that failed.

## Quick reference

| Entry | Tool | Required |
|-------|------|----------|
| Manpower | `create_manpower_log` | `projectId`, `date`, `vendorId`, `numWorkers`, `hours` |
| Call | `create_call_log` | `projectId`, `date`, `subjectTo`, `description` |
| Photo | `create_photo` | `projectId`, image, caption |
| Resolve a sub → vendorId | `find_company_vendor` | `searchText` |
| Scheduled-vs-actual | `list_schedule_activities` | `projectId` (read-only) |

## Common mistakes

- **Writing before the preview.** Always dry-run first; the preview is the approval point.
- **Bare manpower entries.** "12 men" with no company or hours won't hold up as a record — capture the company breakdown and put the work performed in `comments`.
- **Guessing the vendor.** Resolve with `find_company_vendor`; confirm on ambiguous matches.
- **Wrong date.** UTC rollover can shift the default — state the date you're logging so it's unambiguous.

**Voice:** see `westland-house-style` — comments should be concrete and factual (what trade, what area, what got done).
