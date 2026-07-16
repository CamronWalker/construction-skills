---
name: construction-email-to-log
description: >
  Turn important project emails into Procore call-log (communication) entries on the right day,
  so key correspondence lands in the Daily Log record. Use when someone says "log this email to
  Procore", "put this correspondence in the daily log", "record this email on the job", "log the
  email/call with [party]", "capture these emails in Procore", or wants recent important emails
  reflected in a project's Procore record. Reads mail via the mail MCP and writes call logs with a
  dry-run preview before each write. It does NOT forward mail to a Procore inbox — that isn't
  available via the MCP; call-log capture is the path.
---

# Construction Email to Log

Get important email correspondence onto the Procore project record by logging it as **call-log** entries on the date it happened. Procore's daily log has no email type and the MCP exposes no project email dropbox, so a call log (a dated communication with from/to and a description) is the reliable home for "this exchange happened on the job."

> Reads mail via the mail MCP; writes through the Procore MCP. See `construction-procore-toolbox` for project resolution and the two-stage write contract.

## What this skill does *not* do

It does **not** forward emails to a Procore project inbox address. That's a Procore UI feature the MCP doesn't surface (no daily-log or emails endpoint, no dropbox field). Don't promise or attempt it — capture the correspondence as call logs instead.

## When to use

- "Log these emails to Procore" / "capture this correspondence on the job"
- "Record the email exchange with the architect on the daily log"
- Bringing a week's important project emails into the Procore record.

## Workflow

1. **Resolve the project** — `find_project` → confirm → `projectId`.
2. **Gather the emails.** Pull recent/important mail via the mail MCP (by project, sender, or date window), or take a pasted thread. Summarize the candidates and **let the user pick which ones matter** — don't log everything indiscriminately.
3. **Map each email → a call log:**
   - `date` = the email's date.
   - `subjectFrom` / `subjectTo` = the parties (name + role, e.g. "Jane Doe (Architect)").
   - `description` = a tight summary: what was communicated, any decision, and follow-ups. Keep it factual and self-contained so the log stands on its own.
4. **Dry-run the batch.** Call `create_call_log` **without** `confirm` for each selected email → show the previews together → get an explicit yes → re-call with `confirm: true`.
5. **Report** the created call logs (with IDs) and flag any that failed.

## Quick reference

| Step | Tool |
|------|------|
| Find important emails | mail MCP (search/list recent) |
| Resolve project | `find_project` |
| Write the log | `create_call_log` (dry-run → confirm) |

## Common mistakes

- **Trying to forward to a Procore inbox.** Not available — use call logs.
- **Logging every email.** Curate with the user; log what matters to the record.
- **Writing before the preview.** Dry-run each call log first.
- **Vague descriptions.** The log should stand alone months later — capture the substance and any decision/follow-up, not just "emailed about RFI."

**Voice:** see `westland-house-style` — factual, concrete summaries; name parties and decisions plainly.
