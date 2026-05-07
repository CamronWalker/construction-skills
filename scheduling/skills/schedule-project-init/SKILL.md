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

## CRUD discipline — never touch project-context.html directly

Before any step below: every read of `project-context.html` goes through `references/parse_project_context_html.py`. Every write goes through `references/generate_project_context_html.py`. No exceptions.

Forbidden: `Read` / `Edit` / `Write` / `MultiEdit` / shell `sed` / shell `cat >` / hand-typed HTML patches against the file. Even one-line scalar changes (signer name, a date, a `window.TODAY` value) must round-trip through `parse → mutate dict → generate`.

**Why:** the file embeds a ~17KB base64 PNG logo. Direct `Read`/`Write` round-trips through tool I/O have silently truncated bytes mid-payload (W1177 Lubumbashi, 2026-05-07), producing a file that opens but renders a broken logo. The generate/parse pair never moves the logo bytes through Claude's context — generate writes them straight to disk from `references/westland-logo.png`, parse ignores them. The unit tests in `tests/test_project_context_html.py` pin this contract.

If you find yourself reaching for `Edit` on this file, stop and ask: what field changed? Parse, mutate that key in the dict, re-generate. The tests guarantee the roundtrip is lossless for every documented field.

**Cowork environment note:** when the Schedules folder lives on a non-`C:\` drive (e.g. the `\\orem-fs\Common\Westland Project Files` share mounted as `G:\`), the bash sandbox may not see that path directly. The discipline still holds — **never** patch the file by hand to work around it. Options, in order of preference:

1. Run `generate_project_context_html.generate_project_context_html(output_path=...)` with `output_path` pointing at the real destination if the sandbox can reach it.
2. If the sandbox can't reach the destination, run the script in a local Claude Code session opened in the project folder (the colleague-facing `Write Weekly Schedule Email.bat` pattern works the same way — locally launched, full filesystem access).
3. Tell the user the destination is unreachable and ask them to run `python -m generate_project_context_html ...` themselves. Don't try to round-trip the HTML through `Write` to "deliver" it — the embedded ~17KB base64 PNG has historically corrupted mid-payload that way.

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
   - **SmartPM project name** — the **exact** title shown on SmartPM v2's `/projects/cards` page. The screenshot capture script uses this to find the right card. Default to the parsed project name from step 2; ask the user to confirm or override if SmartPM's spelling differs (e.g., `"Anchorage AK Temple"` in folders, but `"Anchorage Alaska Temple"` on SmartPM).
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

Copy **both** launcher files from `references/` into the Schedules root (same folder as `project-context.html`):

- `Write Weekly Schedule Email.bat` — thin wrapper. Uses `start "" powershell ... -File` so the PowerShell window is its own process (cmd shim exits instead of hosting PowerShell).
- `Write Weekly Schedule Email.ps1` — the actual logic. Clears inherited Claude env vars, `Set-Location $PSScriptRoot`, discovers the `claude` binary robustly (PATH + known install locations — some installers add the full exe path to PATH instead of its folder, which breaks `Get-Command`), and runs `claude --permission-mode auto '/write-weekly-schedule-email'`.

A colleague double-clicks the `.bat` in Explorer — they don't need to know Cowork, Claude Code, slash commands, or PowerShell. If the Claude Code CLI isn't installed (or isn't discoverable), the script prints the install link (https://claude.com/claude-code) and lists the locations it checked, in red, then stops — no silent flash.

The pattern mirrors the Iris task-watcher agent launcher (see `task-watcher.js` comment: "No bash, no MSYS2 DLL issues."). `auto` mode keeps the session autonomous while still respecting permission boundaries.

On re-run, if the .bat is missing (older project, file was moved), copy it again. If it exists, check whether the content matches the current template and offer to refresh it if not. Never overwrite silently.

Tell the user (on first init):
> "Dropped **Write Weekly Schedule Email.bat** next to `project-context.html`. Colleagues double-click it after the schedule meeting and Claude Code takes over from there — no Cowork, no slash commands to remember. Claude Code CLI and Node.js need to be installed on whichever machine runs it."

### Step 7 — seed SmartPM credentials (one-time per machine)

The weekly screenshot capture auto-logs into SmartPM v2 using credentials from `~/.claude/.env`. These are global per machine — once seeded, every project on that machine reuses them.

Check whether they're already set:

```bash
node "{schedule-update-skill-dir}/references/smartpm/env-loader.js" show
```

If the output reports `SMARTPM_EMAIL=<missing>` or `SMARTPM_PASSWORD=<missing>`, ask the user via `AskUserQuestion`:

- Header: `SmartPM creds`
- Q1: `What's your SmartPM login email?`
- Q2: `What's your SmartPM password?` (warn the user it'll be stored locally in `~/.claude/.env`; they can revoke by editing the file)

Once you have both, write them with:

```bash
node -e "require('{schedule-update-skill-dir}/references/smartpm/env-loader.js').upsertEnvFile({SMARTPM_EMAIL:'…', SMARTPM_PASSWORD:'…'})"
```

Never echo the password back to chat after capture. If creds are already set, skip this step silently.

Confirm to the user:
> "SmartPM credentials are saved to `~/.claude/.env`. Every project on this machine will reuse them — you only do this once."

## Note on attachments

Earlier versions had an `expected_attachments` glob-pattern list in the context. That was removed — the weekly preview HTML carries attachments forward automatically via `transition_attachments` (date-normalized fuzzy match against the dated folder), so the context doesn't need template patterns. On the very first week for a project, the `schedule-update` skill globs all `.pdf` / `.xlsm` / `.xer` files in the dated folder as the initial set; the user curates from there.

## Re-run Behavior

When `project-context.html` already exists, this skill acts as an editor:

1. Call `parse_project_context_html.parse_project_context_html(path)` — returns current values.
2. Display what's there and ask which fields to change.
3. Walk through only the affected fields.
4. Re-generate the HTML with the updated dict via `generate_project_context_html(...)`.

This is the intended way to update project config (recipient changes, signer change, graph reordering, project log entries, etc.). The CRUD discipline above governs **every** edit, including this one — parse → mutate → generate, never `Edit`.

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
| `references/Write Weekly Schedule Email.bat` | Colleague-facing double-click launcher. Copied into the Schedules root on init — uses `start` to spawn a new PowerShell window running the sibling .ps1. |
| `references/Write Weekly Schedule Email.ps1` | Actual launcher logic. Clears inherited Claude env vars, discovers `claude` robustly (PATH + known install locations), then runs `claude --permission-mode auto "/write-weekly-schedule-email"` from the Schedules root. |
| `tests/test_project_context_html.py` | Unit tests pinning the generate/parse contract — full-field roundtrip, empty-context defaults, recipient-string normalization, HTML special-char survival, today-vs-past log lock semantics, deterministic output, embedded-logo presence, and a Python 3.10 f-string compatibility guard. Run with `python tests/test_project_context_html.py -v`. |

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
