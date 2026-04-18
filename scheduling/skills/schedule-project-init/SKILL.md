---
name: schedule-project-init
description: >
  Initialize a construction project's Schedules folder with a persistent
  project-context.html file — an editable HTML with Westland header, recipient
  name+email rows, SmartPM URLs, signer info, graph selection, and a project
  log for scope changes / EOT filings / major decisions. Use this skill whenever
  the user says "initialize project", "project setup", "init project",
  "set up project", "create project context", "project init", or when another
  scheduling skill reports that project-context.html is missing.
---

# Project Initialization

Create or update the **`project-context.html`** file that all scheduling skills depend on. This file lives in the **root Schedules folder** (not inside dated subfolders) and carries forward across every weekly update.

`project-context.html` is an editable HTML file (same pattern as the weekly email preview). Colleagues can double-click it, edit fields in the browser, and click **Save Edits** to overwrite in place. A separate parser reads it into a Python dict for all downstream skill use.

## Folder Resolution

All scheduling skills share this logic to find the Schedules root:

1. If CWD basename matches `YYYY-MM-DD` (a dated folder) → root is the **parent** directory (`../`).
2. If CWD basename is `Schedules` → root is CWD.
3. If CWD contains a `Schedules/` child directory → root is that child.
4. Otherwise → ask the user for the Schedules folder path.

**Validate:** the parent of the resolved root should match the pattern `W\d+ - .+` (e.g., `W1134 - Neiafu Tonga Temple Construction`). The resolved folder itself should be named `Schedules`.

## Workflow

### Step 1 — resolve Schedules root and check state

Apply the folder resolution logic above. Then:

- If `project-context.html` exists → read it with `parse_project_context_html.parse_project_context_html(...)` and display current values. Ask the user which fields to update, then skip to the affected questions in Step 3.
- If it doesn't exist → proceed to Step 2 for a fresh setup.

### Step 2 — parse project identity from the folder name

Read the **grandparent** folder (parent of `Schedules/`). Parse with the regex `^(W\d+)\s*-\s*(.+)$`:

- `job_number` = the `W####` portion (e.g., `W1134`)
- `project_name` = the rest (e.g., `Neiafu Tonga Temple Construction`)

If parsing fails, ask the user for both.

Confirm:
> "I read the project as **W1134 — Neiafu Tonga Temple Construction**. Is that correct?"

### Step 3 — collect project configuration

Ask each question via AskUserQuestion, filling in every field.

1. **Contractual completion date** — "What is the contractual Substantial Completion date?"
2. **SmartPM workspace URL** — must end in `/workspace`. Derive `smartpm_trends_url` (replace `/workspace` with `/trends?tab=Graphs`) and `smartpm_changelog_url` (replace with `/changelog`). Show all three for confirmation.
3. **TO recipients** — "Who should receive the weekly update email?" Accept either plain emails (`a@b.com; c@d.com`) or `Name <email>` pairs. The generator stores them as `{name, email}` rows in the HTML — name is optional but rendered as `"Name <email>"` in Outlook when present.
4. **CC recipients** — same format.
5. **Signer name / title / mobile** — signature fields. Mobile is optional.
6. **Procore project ID** — the project's Procore ID. (Company ID is always `11093` for Westland and renders **locked** in the HTML — not editable by colleagues.)

### Step 4 — graph selection

Default graph list for the weekly email (matches the `schedule-update` skill's `screenshots` command):

```
06-end-date-variance.png
07-schedule-compression-index-over-time.png
08-velocity.png
11-window-start-accuracy.png
12-window-finish-accuracy.png
09-spi-over-time.png
10-activity-hit-rate.png
```

Ask if the user wants to add, remove, or reorder. Full list available (see schedule-update SKILL.md).

### Step 5 — write `project-context.html`

Call `references/generate_project_context_html.generate_project_context_html(output_path, context, today_iso=..., logo_path=...)` with the collected fields. The generator produces a self-contained HTML with:

- **Header** — project name (editable h1), job number (editable), and the Westland logo embedded as a base64 PNG in the top-right.
- **Basics card** — contractual completion, Procore project ID (editable), Procore company ID (locked display).
- **SmartPM card** — three URL fields (workspace / trends / changelog).
- **Signer card** — name / title / mobile.
- **Recipients card** — separate TO and CC lists, each row with drag handle, name input, email input, remove button. `+ Add TO` / `+ Add CC` buttons.
- **Graph Screenshots card** — ordered list of graph PNG filenames with drag/reorder and `+ Add` / `× Remove`.
- **Project Log card** — one entry per project-level event (EOT filed, scope change, contract amendment, major decision). Entries dated before today render read-only with a 🔒 icon. Today's entry is editable. `+ Add entry (today)` button stamps a new entry with today's ISO date.

Save the file as `{schedules_root}/project-context.html`. Tell the user:
> "Created **project-context.html** in the Schedules root. Double-click it to open in your browser — all scheduling skills read from this file."

### Step 6 — drop the weekly email launcher script

Copy `references/Write Weekly Schedule Email.bat` into the Schedules root (same folder as `project-context.html`). This is the colleague-facing double-click launcher for the weekly email flow — it `cd`s to its own folder and runs `claude --dangerously-skip-permissions "/write-weekly-schedule-email"`, so a colleague doesn't need to know about Cowork, Claude Code, or slash commands; they just click the file in Explorer.

On re-run, if the .bat is missing (older project, file was moved), copy it again. If it exists, check whether the content matches the current template and offer to refresh it if not. Never overwrite silently.

Tell the user (on first init):
> "Dropped **Write Weekly Schedule Email.bat** next to `project-context.html`. Colleagues double-click it after the schedule meeting and Claude Code takes over from there — no Cowork, no slash commands to remember. Claude Code CLI and Node.js need to be installed on whichever machine runs it."

## Note on attachments

Earlier versions had an `expected_attachments` glob-pattern list in the context. That was removed — the weekly preview HTML carries attachments forward automatically via `transition_attachments` (date-normalized fuzzy match against the dated folder), so the context doesn't need template patterns. On the very first week for a project, the `schedule-update` skill globs all `.pdf` / `.xlsm` / `.xer` files in the dated folder as the initial set; the user curates from there.

## Re-run Behavior

When `project-context.html` already exists, this skill acts as an editor:

1. Call `parse_project_context_html.parse_project_context_html(path)` — returns current values.
2. Display what's there and ask which fields to change.
3. Walk through only the affected fields.
4. Re-generate the HTML with the updated dict.

This is the intended way to update project config (recipient changes, signer change, graph reordering, project log entries, etc.).

## Writing to the Project Log during weekly updates

The `schedule-update` skill should append a new project-log entry when a weekly update contains project-level events (scope changes, EOT filings, contract amendments, major decisions). Mechanics:

1. After parsing the weekly preview HTML at `draft` time, read `project-context.html` via `parse_project_context_html`.
2. If there are notable events this week, append `{date: today_iso, body: <summary>}` to the `project_log` list. If an entry for today already exists, append to its body (newline-separated) rather than creating a duplicate.
3. Re-generate `project-context.html` with the updated log.

On the next day, the entry you just wrote renders as locked (per the today-vs-past check in the generator). Colleagues can still see the history but won't accidentally edit it.

## Reference files

All reference files live in `references/` within this skill directory.

| File | Purpose |
|------|---------|
| `references/generate_project_context_html.py` | Builds the editable HTML — header + Westland logo + all cards + contenteditable fields + Save Edits / Copy for Claude JS. |
| `references/parse_project_context_html.py` | Parses an edited HTML back into a dict. Convenience helper `load_project_context(root)` returns `(ctx, html_path)` or `(None, None)` if the file is missing. |
| `references/westland-logo.png` | Signature/header logo, base64-embedded into the HTML so the file is self-contained. |
| `references/Write Weekly Schedule Email.bat` | Colleague-facing double-click launcher. Copied into the Schedules root on init — runs `claude --dangerously-skip-permissions "/write-weekly-schedule-email"` from the folder it lives in. |

## Folder structure reference

After initialization:

```
Schedules/
├── project-context.html              ← persistent project config (this skill creates it)
├── 2026-04-01/
│   ├── 2026-04-01-email-preview.html ← weekly preview (schedule-update skill)
│   ├── 2026-04-01-update-email.md    ← archive of the sent email
│   ├── screenshots/                  ← SmartPM screenshots
│   └── *.xer, *.pdf, *.xlsm          ← schedule files and reports
├── 2026-04-08/
│   └── ...
```
