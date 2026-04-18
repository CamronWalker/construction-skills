---
description: Steps 6–10 of the weekly schedule update — SmartPM screenshots, email generation, editable HTML preview, Outlook draft. Invoked at the Schedules root (so Cowork can see project-context.html); expects steps 1–5 already done by a human.
---

# Write Weekly Schedule Email

You are being dropped into a Westland weekly schedule update (typically via Cowork) at the **email-building phase**. The human has already completed the manual steps of the update and is handing the email off to you.

## Expected starting state

CWD is the **Schedules root folder** (not a dated subfolder) — Cowork needs access here because `project-context.html` lives at this level. The grandparent should match `W\d+ - .+` (e.g. `W1134 - Neiafu Tonga Temple Construction/Schedules/`). Today's dated folder (`YYYY-MM-DD/`) should already exist inside the root.

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

The screenshots step (agent step 6) relies on browser automation to capture SmartPM trend graphs. Check that Playwright MCP tools are available in this session — look for tools with the prefix `mcp__*playwright*__browser_*` (e.g. `browser_navigate`, `browser_take_screenshot`). If none are present, **stop** and tell the user:

> "Playwright MCP doesn't appear to be installed in this Cowork session. I can't capture SmartPM graphs without it. Enable the Playwright MCP (it should be rolling out org-wide) and retry."

Do not fall back to the local Node/Playwright install under `references/` in the Cowork context — the colleague running this may not have Node set up.

### 3. Today's dated folder must exist

List `YYYY-MM-DD/` subdirectories. If there is no folder for today's date, show the most recent 2–3 dated folders and ask whether this week's update is in one of those or whether they skipped the `copy` step. Do not auto-create it — that's a pre-meeting human step.

## Your job — steps 6–10 (agent work)

Once the preflight passes, run the **`report`** flow from the `schedule-update` skill. That flow is designed for exactly this hand-off and covers:

- **Step 6 (agent):** Capture SmartPM graphs (17 screenshots) — skip if already present and complete.
- **Step 7 (agent):** Generate the update email content — mine the meeting transcript if present, otherwise run the XER-driven Q&A comparing this week's XER to last week's.
- **Step 8 (human):** Editable HTML preview — wait for the colleague to review and say `done`.
- **Step 9 (agent):** Create the Outlook draft from the edited preview; write the archive markdown.
- **Step 10 (human):** They send the email.

## Notes

- **SmartPM processing warning:** If the XER was uploaded within the last ~30 minutes, SmartPM may still be processing the trends — offer to wait before capturing graphs.
- Don't re-prompt the user for things already covered by the template (folder is set up, XER is exported, transcript is in place) — just get to work.
- Keep the conversation tight. Ask 2–4 questions per turn, confirm each answer, and generate the editable HTML preview as the review artifact (not markdown in chat).
