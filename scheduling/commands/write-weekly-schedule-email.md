---
description: Steps 6–10 of the weekly schedule update — SmartPM screenshots, email generation, editable HTML preview, Outlook draft. Invoked by the `Write Weekly Schedule Email.bat` launcher at the Schedules root; drives the browser via Playwright MCP so colleagues don't need Node.
---

# Write Weekly Schedule Email

You are being dropped into a Westland weekly schedule update at the **email-building phase**. A colleague double-clicked `Write Weekly Schedule Email.bat` at the Schedules root, which launched Claude Code CLI in `auto` permission mode and queued this command.

The human has already completed the manual steps of the update and is handing the email off to you.

## Expected starting state

CWD is the **Schedules root folder** — the `.bat` does `cd /d "%~dp0"` before launching, and the script lives next to `project-context.html`. The grandparent should match `W\d+ - .+` (e.g. `W1134 - Neiafu Tonga Temple Construction/Schedules/`). Today's dated folder (`YYYY-MM-DD/`) should already exist inside the root.

These steps are already done by the human (per `Schedule Update Template.md`):

1. Schedule folder copied for today's date
2. Schedule updated (in meeting)
3. Schedule files exported to the dated folder (XER + PDFs)
4. XER uploaded to SmartPM
5. Meeting transcript placed in `{dated_folder}/meeting/` (if one exists)
6. PDF attachments exported into the dated folder
7. Next week's update Excel files created

## Preflight — run these before anything else

### 1. `project-context.html` must exist at the Schedules root

Check for `./project-context.html`. If it's missing, **stop** and tell the user:

> "No `project-context.html` at the Schedules root. This project hasn't been initialized — run the `schedule-project-init` skill first. Without it, the SmartPM URLs, recipients, and graph list aren't available, and the screenshots step will fail."

Do not try to proceed without it.

### 2. Playwright MCP must be installed

Browser automation for SmartPM screenshots runs through the Playwright MCP (centralized org-wide install, not a per-project `npm install`). Check for MCP tools with the prefix `mcp__*playwright*__browser_*` (e.g. `browser_navigate`, `browser_take_screenshot`, `browser_snapshot`). If none are present, **stop** and tell the user:

> "Playwright MCP isn't available in this Claude Code session. It should be installed org-wide on the CLI — ping Camron to enable it. (Do **not** fall back to the local Node/Playwright install; colleague machines don't have Node.)"

In this colleague flow, do not fall back to the `references/capture-smartpm.js` Node path — that path exists for Camron's workstation, not for colleagues.

### 3. Today's dated folder must exist

List `YYYY-MM-DD/` subdirectories. If there is no folder for today's date, show the most recent 2–3 dated folders and ask whether this week's update is in one of those or whether they skipped the `copy` step. Do not auto-create it — that's a pre-meeting human step.

## Your job — steps 6–10 (agent work)

Once the preflight passes, run the **`report`** flow from the `schedule-update` skill. That flow is designed for exactly this hand-off and covers:

- **Step 6 (agent):** Capture SmartPM graphs (17 screenshots) **via Playwright MCP** — see the `screenshots` section of the schedule-update skill (Step 3a, MCP path). Skip this if the `screenshots/` folder is already populated and complete for today.
- **Step 7 (agent):** Generate the update email content — mine the meeting transcript if present, otherwise run the XER-driven Q&A comparing this week's XER to last week's.
- **Step 8 (human):** Editable HTML preview — wait for the colleague to review and say `done`.
- **Step 9 (agent):** Create the Outlook draft from the edited preview; write the archive markdown.
- **Step 10 (human):** They send the email.

## Notes

- **SmartPM processing warning:** If the XER was uploaded within the last ~30 minutes, SmartPM may still be processing the trends — offer to wait before capturing graphs.
- **SmartPM login:** The Playwright MCP typically launches a fresh browser context, so expect a login prompt on the first screenshot step each session. Pause the workflow and ask the colleague to log in, then resume when they say `logged in`.
- **Classic Outlook must be open** on the colleague's machine (not just installed) for the `draft` step to succeed — COM automation needs a running instance. If Outlook isn't open, tell them to launch it from the Start menu first.
- Don't re-prompt the user for things already covered by the template (folder is set up, XER is exported, transcript is in place) — just get to work.
- Keep the conversation tight. Ask 2–4 questions per turn, confirm each answer, and generate the editable HTML preview as the review artifact (not markdown in chat).
