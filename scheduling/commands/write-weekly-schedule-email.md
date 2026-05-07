---
description: Steps 6–10 of the weekly schedule update — SmartPM screenshots, email generation, editable HTML preview, Outlook draft. Invoked by the `Write Weekly Schedule Email.bat` launcher at the Schedules root; runs the bundled headless Node script (`smartpm/capture-smartpm.js`) for screenshots, with auto-login from `~/.claude/.env`.
---

# Write Weekly Schedule Email

## ⚠️ Absolute rule — XER files are immutable

**Every `.xer` file in these folder trees is an immutable project record.** No in-place edits, no overwrites, no deletes — ever.

- **READ** any `.xer` freely (parse, analyze, compare against last week).
- **MODIFY** by writing a **new versioned file** alongside the existing one, incrementing the suffix each time:
  - `2026-04-17 NTVS ACME.xer` → `2026-04-17 NTVS ACME-v2.xer` → `...-v3.xer` → ...
- **NEVER** edit an existing `.xer` in place (Edit / MultiEdit / overwriting Write are all modifications).
- **NEVER** delete a `.xer` file.

Enforcement: the `westland` plugin (required org-wide dependency) ships a PreToolUse hook (`westland/hooks/check_xer_write.py`) that physically blocks `Edit`, `Write` overwrite, `MultiEdit`, `NotebookEdit`, and Bash `rm` / `del` / `Remove-Item` / `find -delete` calls targeting `.xer` paths. If a step seems to require editing or deleting a `.xer`, you've misunderstood the workflow — stop and ask the colleague.

---

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

### 2. SmartPM credentials must be in `~/.claude/.env`

The screenshots step auto-logs into SmartPM v2 via headless Playwright using credentials from `~/.claude/.env`:

- `SMARTPM_EMAIL` — required
- `SMARTPM_PASSWORD` — required
- `SMARTPM_PROJECTS_URL` — optional (defaults to Westland's org cards URL)

Check by running:

```bash
node "{schedule-update-skill-dir}/references/smartpm/env-loader.js" show
```

If either key reports `<missing>`, ask the colleague for them via `AskUserQuestion` (header: "SmartPM creds"; ask for email and password as separate questions). Once you have both values, write them to the env file:

```bash
node -e "require('{...}/references/smartpm/env-loader.js').upsertEnvFile({SMARTPM_EMAIL:'…', SMARTPM_PASSWORD:'…'})"
```

Never echo the password back to chat. Once seeded, this is one-time — subsequent projects on the same machine reuse it.

### 3. Node + Playwright must be available

The capture script requires Node.js (any 18+) and the bundled Playwright Chromium. The first run on a machine auto-installs the npm dependencies into `references/node_modules/`. If `node --version` fails, install Node from https://nodejs.org and retry.

### 4. Today's dated folder must exist

List `YYYY-MM-DD/` subdirectories. If there is no folder for today's date, show the most recent 2–3 dated folders and ask whether this week's update is in one of those or whether they skipped the `copy` step. Do not auto-create it — that's a pre-meeting human step.

## Your job — steps 6–10 (agent work)

Once the preflight passes, run the **`report`** flow from the `schedule-update` skill. That flow is designed for exactly this hand-off and covers:

- **Step 6 (agent):** Capture SmartPM graphs (17 screenshots) **via the bundled Node script** at `references/smartpm/capture-smartpm.js`. Auto-logs in headless using the credentials from preflight #2. Skip if the `screenshots/` folder is already populated and complete for today.
- **Step 7 (agent):** Generate the update email content — mine the meeting transcript if present, otherwise run the XER-driven Q&A comparing this week's XER to last week's.
- **Step 8 (human):** Editable HTML preview — wait for the colleague to review and say `done`.
- **Step 9 (agent):** Create the Outlook draft from the edited preview; write the archive markdown.
- **Step 10 (human):** They send the email.

## Notes

- **SmartPM processing warning:** If the XER was uploaded within the last ~30 minutes, SmartPM may still be processing the trends — offer to wait before capturing graphs.
- **SmartPM login:** Auto-login is headless via stored credentials. If it fails (bad creds, MFA, captcha), the script exits with `ENV_MISSING` or a redirect-timeout error — re-prompt for credentials and re-seed the env file. There is no manual-login fallback.
- **Classic Outlook must be open** on the colleague's machine (not just installed) for the `draft` step to succeed — COM automation needs a running instance. If Outlook isn't open, tell them to launch it from the Start menu first.
- Don't re-prompt the user for things already covered by the template (folder is set up, XER is exported, transcript is in place) — just get to work.
- Keep the conversation tight. Ask 2–4 questions per turn, confirm each answer, and generate the editable HTML preview as the review artifact (not markdown in chat).
