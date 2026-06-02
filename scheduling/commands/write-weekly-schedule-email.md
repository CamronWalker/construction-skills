---
description: Steps 6–10 of the weekly schedule update — SmartPM screenshots, email generation, editable HTML preview, Outlook draft. Invoked by the `Write Weekly Schedule Email.bat` launcher at the Schedules root; renders 17 chart PNGs from SmartPM MCP data via the bundled `@westland/charts` JS renderer (HTML+SVG → headless Chromium).
---

# Write Weekly Schedule Email

## ⚠️ Absolute rule — XER files are immutable

**Every `.xer` file in these folder trees is an immutable project record.** No in-place edits, no overwrites, no deletes — ever.

- **READ** any `.xer` freely (parse, analyze, compare against last week).
- **MODIFY** by writing a **new versioned file** alongside the existing one, incrementing the suffix each time:
  - `2026-04-17 NTVS ACME.xer` → `2026-04-17 NTVS ACME-v2.xer` → `...-v3.xer` → ...
- **NEVER** edit an existing `.xer` in place (Edit / MultiEdit / overwriting Write are all modifications).
- **NEVER** delete a `.xer` file.

Enforcement: the `westland` plugin (required org-wide dependency) ships a PreToolUse hook (`westland/hooks/westland_share_guard.py`) that physically blocks `Edit`, `Write` overwrite, `MultiEdit`, `NotebookEdit`, and Bash `rm` / `del` / `Remove-Item` / `find -delete` calls targeting `.xer` paths. If a step seems to require editing or deleting a `.xer`, you've misunderstood the workflow — stop and ask the colleague.

---

You are being dropped into a Westland weekly schedule update at the **email-building phase**. A colleague double-clicked `Write Weekly Schedule Email.bat` at the Schedules root, which launched Claude Code CLI in `auto` permission mode and queued this command.

The human has already completed the manual steps of the update and is handing the email off to you.

## Expected starting state

CWD is the **Schedules root folder** — the `.bat` does `cd /d "%~dp0"` before launching, and the script lives at the Schedules root. The grandparent should match `W\d+ - .+` (e.g. `W1134 - Neiafu Tonga Temple Construction/Schedules/`); parse `{job_number}` from it. Today's dated folder (`YYYY-MM-DD/`) should already exist inside the root.

These steps are already done by the human (per `Schedule Update Template.md`):

1. Schedule folder copied for today's date
2. Schedule updated (in meeting)
3. Schedule files exported to the dated folder (XER + PDFs)
4. XER uploaded to SmartPM
5. Meeting transcript placed in `{dated_folder}/meeting/` (if one exists)
6. PDF attachments exported into the dated folder
7. Next week's update Excel files created

## Preflight — run these before anything else

### 1. The project must be initialized in Supabase

Parse `{job_number}` from the `W#### - Name` grandparent folder and call `get_project(job_number)`.

- **Row returned** → proceed. The SmartPM URLs + Procore id bindings come from the row (mapped via `project_context_db_mapping.project_row_to_context`); recipients / signer come from carry-forward.
- **`get_project` returns null but a legacy `./project-context.html` exists at the Schedules root** → lazy-migrate it once (parse → `upsert_project(source='migrated')` → replay the log via `append_project_log` → rename with `retire_context_html`; see `phases/report.md` Step 1b / `schedule-project-init`), then proceed.
- **Null and no legacy `project-context.html`** → **stop** and tell the user:
  > "No project bindings found for `{job_number}` in Supabase, and no `project-context.html` to migrate. This project hasn't been initialized — run the `schedule-project-init` skill first. Without it, the SmartPM URLs and Procore bindings aren't available."

Do not try to proceed without bindings.

### 2. SmartPM MCP must be available

Screenshots are rendered from SmartPM data fetched via MCP (no SmartPM login, no browser automation). Look at your tool list for any tool whose name matches `mcp__<uuid>__smartpm_*`. If `ToolSearch` reports "no matching deferred tools", the SmartPM connector isn't connected — tell the colleague to run `/mcp` to reconnect, then re-run this command.

### 3. Node + Playwright must be available

The renderer requires Node.js (any 18+) and the bundled Playwright Chromium (used by `charts/html_to_png.cjs` to rasterise HTML to PNG). The first run on a machine auto-installs the npm dependencies into `references/node_modules/`. If `node --version` fails, install Node from https://nodejs.org and retry.

### 4. Today's dated folder must exist

List `YYYY-MM-DD/` subdirectories. If there is no folder for today's date, show the most recent 2–3 dated folders and ask whether this week's update is in one of those or whether they skipped the `copy` step. Do not auto-create it — that's a pre-meeting human step.

## Your job — steps 6–10 (agent work)

Once the preflight passes, run the **`report`** flow from the `schedule-update` skill. That flow is designed for exactly this hand-off and covers:

- **Step 6 (agent):** Capture SmartPM graphs (17 PNGs) by fetching each chart payload from SmartPM MCP, writing `{slug}.json` files to `{dated_folder}/.chart-payload/`, then rendering the batch via `node references/charts/cli.js`. See `phases/screenshots.md` for per-slug MCP recipes. Skip if the `screenshots/` folder is already populated and complete for today.
- **Step 7 (agent):** Generate the update email content — mine the meeting transcript if present, otherwise run the XER-driven Q&A comparing this week's XER to last week's.
- **Step 8 (human):** Editable HTML preview — wait for the colleague to review and say `done`.
- **Step 9 (agent):** Create the Outlook draft from the edited preview; write the archive markdown.
- **Step 10 (human):** They send the email.

## Notes

- **SmartPM processing warning:** If the XER was uploaded within the last ~30 minutes, SmartPM may still be processing the trends — offer to wait before fetching chart payloads.
- **MCP-only screenshots:** No SmartPM login, no headless browser navigation. Chart data comes from SmartPM MCP tools; rendering is a local HTML+SVG → PNG pipeline via headless Chromium (Playwright). If a SmartPM MCP call fails, surface the exact error so the colleague can decide.
- **Classic Outlook must be open** on the colleague's machine (not just installed) for the `draft` step to succeed — COM automation needs a running instance. If Outlook isn't open, tell them to launch it from the Start menu first.
- Don't re-prompt the user for things already covered by the template (folder is set up, XER is exported, transcript is in place) — just get to work.
- Keep the conversation tight. Ask 2–4 questions per turn, confirm each answer, and generate the editable HTML preview as the review artifact (not markdown in chat).
