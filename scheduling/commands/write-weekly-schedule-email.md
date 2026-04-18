---
description: Steps 6–10 of the weekly schedule update — SmartPM screenshots, email generation, editable HTML preview, Outlook draft. Expects CWD to be the weekly YYYY-MM-DD folder with steps 1–5 already done by a human.
---

# Write Weekly Schedule Email

You are being dropped into a Westland weekly schedule update (typically via Cowork) at the **email-building phase**. The human has already completed the manual steps of the update and is handing the email off to you.

## Expected starting state

CWD should be a dated schedule folder matching `YYYY-MM-DD` (e.g. `.../W1134 - Neiafu Tonga Temple Construction/Schedules/2026-04-17/`). The parent is the `Schedules` root and contains `project-context.html`.

These steps are already done by the human (per `Schedule Update Template.md`):

1. Schedule folder copied for today's date
2. Schedule updated (in meeting)
3. Schedule files exported to this folder (XER + PDFs)
4. XER uploaded to SmartPM
5. Meeting transcript placed in `meeting/` (if one exists)
6. PDF attachments exported into this folder
7. Next week's update Excel files created

## Your job — steps 6–10 (agent work)

Run the **`report`** flow from the `schedule-update` skill. That flow is designed for exactly this hand-off and covers:

- **Step 6 (agent):** Capture SmartPM graphs (17 screenshots) — skip if already present and complete.
- **Step 7 (agent):** Generate the update email content — mine the meeting transcript if present, otherwise run the XER-driven Q&A comparing this week's XER to last week's.
- **Step 8 (human):** Editable HTML preview — wait for the colleague to review and say `done`.
- **Step 9 (agent):** Create the Outlook draft from the edited preview; write the archive markdown.
- **Step 10 (human):** They send the email.

## How to start

1. **Verify location.** If CWD is not a `YYYY-MM-DD` folder, apply the schedule-update skill's folder resolution. If the dated folder for today does not exist or looks empty, stop and tell the user which of the human steps (1–5) still needs to happen before you can help.
2. **Read `project-context.html`** from the Schedules root. If missing, stop and tell the user to run `schedule-project-init` first.
3. **Warn about SmartPM processing.** If the XER was uploaded within the last ~30 minutes, SmartPM may still be processing the trends — offer to wait before capturing graphs.
4. **Enter the `report` flow** as described in the `schedule-update` skill (Steps 1–7 under the `report` section). Don't re-prompt the user for things already covered by the template (folder is set up, XER is exported, transcript is in place) — just get to work.

Keep the conversation tight. Ask 2–4 questions per turn, confirm each answer, and generate the editable HTML preview as the review artifact (not markdown in chat).
