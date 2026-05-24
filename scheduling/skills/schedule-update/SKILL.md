---
name: schedule-update
description: >
  Full weekly schedule update pipeline for Westland Construction. Handles all post-meeting
  steps: folder setup, SmartPM screenshot capture, email draft generation, editable HTML
  preview, Outlook draft, and Procore publish (XER + Documents upload). Progressively
  disclosed -- routes by command arg or detects current phase from file system. Use for:
  "schedule update", "weekly update", "update email", "weekly schedule report email",
  "weekly report email", "schedule report email", "prep the update email", "help me
  with the email", "take screenshots", "smartpm screenshots", "schedule email", "draft
  the email", "copy schedule folder", "update status", "where are we in the update",
  "generate email", "create draft", "procore upload", or any schedule update workflow.
  Two main entry points: `copy` for pre-meeting folder setup, and `report` for the
  colleague-friendly post-meeting flow (steps 6-10 as a guided conversation with an
  editable HTML email preview, ending with .eml + Procore publish).
---

# Schedule Update Pipeline — Router

## ⚠️ Before invoking any sub-command — read the right phase files

Each sub-command names the phase files you MUST read in full before acting. **Do not Read the `.py` or HTML scripts those phase files reference** — every phase file inlines the signatures and dict shapes you need. Reading the underlying script is a sign you skipped the phase file.

## ⚠️ Re-read phase files on every phase transition

A sub-command's full procedure lives in the phase files for that command (column 2 of the Command Matrix below). Reading them **once** at the start of the session is not enough — by the time you reach phase 3 of a multi-phase run, the earlier file's text is paraphrased in your working memory and lossy on details.

**Mechanical rule:**

When you build a `TaskCreate` list for any sub-command, the FIRST task for every phase the command pulls in must be `[re-read] phases/<file>.md`. The task description repeats the phase name in full. Example for `/schedule-update report`:

```
TaskCreate({
  subject: "[re-read] phases/report.md",
  description: "Re-read the full phases/report.md file. Do not start any step until it is loaded in current context."
})
TaskCreate({ subject: "Resolve folder + read project-context.html", ... })
TaskCreate({
  subject: "[re-read] phases/_carry_forward.md",
  description: "Re-read the full phases/_carry_forward.md file before invoking carry_forward.reconcile_items / transition_attachments."
})
TaskCreate({ subject: "Reconcile this week's items + attachments", ... })
TaskCreate({
  subject: "[re-read] phases/draft.md",
  description: "Re-read the full phases/draft.md file before building the v2 seed dict."
})
TaskCreate({ subject: "Assemble v2 seed and POST to generate_weekly_schedule_update_email_draft", ... })
```

Why this works: each re-read task forces the phase file's exact field names, function signatures, and ordering back into context just before the work that depends on them. After 100k+ of context the phase files' lemmas haven't drifted — just your recall of them.

Phase files all open with an identical preamble (next section) so when you hit one of these tasks you know exactly what to load.

### Command Matrix

| Invocation | Phase files (re-read each at phase entry) | Purpose |
|---|---|---|
| `/schedule-update copy` | `phases/copy.md` | Pre-meeting folder setup |
| `/schedule-update email` | `phases/email.md`, `phases/_carry_forward.md`, `phases/_attachments.md`, `phases/_render_graphs.md` | Camron's email draft path |
| `/schedule-update report` | `phases/report.md`, `phases/_carry_forward.md`, `phases/_attachments.md`, `phases/draft.md`, `phases/_render_graphs.md`, `phases/procore.md` | Colleague flow, steps 10–12 |
| `/schedule-update draft` | `phases/draft.md`, `phases/_attachments.md`, `phases/_render_graphs.md`, `phases/procore.md` | `.eml` / COM draft + Procore publish |
| `/schedule-update procore` | `phases/procore.md`, `phases/_attachments.md` | Retry / standalone Procore publish |
| `/schedule-update status` | `phases/status.md` | Phase detection |
| `/schedule-update` (no arg) | `phases/status.md` | Auto-detect, route to recommended step |
| `/write-weekly-schedule-email` | `commands/write-weekly-schedule-email.md` (thin shell) → same as `report` | Cowork drop-in |

**The `screenshots` sub-command is retired.** In v1 it captured 17 SmartPM graph PNGs locally; in v2 the Worker renders graphs server-side and returns them in the finalize payload. The local stacked-PNG rasterization step is internal to `phases/draft.md` (via `phases/_render_graphs.md`) and not a user-invocable command.

Read **every file in the column** for your invocation, in full, before taking any action.

---

## ⚠️ Absolute rule — XER files are immutable

**Every `.xer` in dated Schedules folders is an immutable project record.** Applies to every phase below:

- **READ** any `.xer` freely.
- **MODIFY** by writing a **new versioned file** alongside the existing one, incrementing the suffix each time (`...xer` → `...-v2.xer` → `...-v3.xer`).
- **NEVER** edit in place (Edit / MultiEdit / overwriting Write).
- **NEVER** delete.

Enforced at the tool layer by the `westland` plugin's PreToolUse hook (`westland/hooks/westland_share_guard.py`, matcher: `Edit|Write|MultiEdit|NotebookEdit|Bash`), which blocks in-place edits, overwrites of existing `.xer` files, and Bash delete commands (`rm`, `del`, `Remove-Item`, `find -delete`) targeting `.xer` paths. The `westland` plugin is a required organizational dependency — if the hook isn't firing, the `westland` plugin isn't loaded.

---

## ⚠️ Absolute rule — HTML artifacts go through their parse/generate scripts

**Every editable HTML artifact in this pipeline is read via its parser and written via its generator.** Applies to every phase below:

- **READ** via the parser. Never `Read` / `Grep` / `cat` the HTML directly.
- **WRITE** via the generator. Never `Edit` / `Write` / `MultiEdit` / `sed` / hand-typed HTML patches.
- Even one-line changes (a checkbox flip, an attachment add, a recipient swap) round-trip through **parse → mutate dict → generate**.

| Artifact | Lives at | Read with | Write with |
|----------|----------|-----------|------------|
| `project-context.html` | Schedules root | `parse_project_context_html.parse_project_context_html(path)` | `generate_project_context_html.generate_project_context_html(path, ctx)` |
| `{YYYY-MM-DD}-email.json` | dated folder | `email_draft_io.load_draft(path)` | Worker-side: `finalize_weekly_schedule_update_email` (no local writer) |

**Why:** `project-context.html` is ~47 KB with an embedded base64 logo that has historically corrupted mid-payload during direct tool I/O (W1177 Lubumbashi, 2026-05-07). Keep all HTML I/O inside the script pair. The weekly email no longer round-trips through HTML — content lives in the cloud editor and ships back as `{YYYY-MM-DD}-email.json` per the contract in scheduling/CLAUDE.md.

**Cowork note:** when the Schedules / dated folder lives on a non-`C:\` drive (e.g. `\\orem-fs\Common\Westland Project Files` mounted as `G:\`), the bash sandbox may not see it. The discipline still holds. Run the generator with `output_path` pointing at the real destination if reachable; otherwise hand the invocation to a local Claude Code session — never round-trip the HTML through `Write` to "deliver" it.

---

## Shared Setup

### Common pitfalls on UNC shares

Every Westland project lives on `\\orem-fs\Common\Westland Project Files\...` (mapped to `G:\` on most machines). A few traps:

- **Opening a file on the share from a shell.** `start "" "\\orem-fs\..."` from `cmd` errors with "UNC paths are not supported." Use PowerShell `Invoke-Item "\\orem-fs\..."` or shell out to `explorer.exe "\\orem-fs\..."` from Bash.
- **`file://` URLs for local files.** Prefer `pathlib.Path(abs).as_uri()` in Python and `pathToFileURL(abs).href` in Node. Manual `'file:///' + path.replace('\\','/')` mangles UNC roots.
- **Cowork sandbox + non-`C:\` drives.** Cowork's bash sandbox doesn't see `G:\` or UNC paths. Run the underlying script in a local Claude Code session, or stage files in `%TEMP%` and copy back.

### Folder Resolution

All phases use this logic to find the Schedules root:

1. If CWD basename matches `YYYY-MM-DD` (a dated folder) → root is the **parent** (`../`)
2. If CWD basename is `Schedules` → root is CWD
3. If CWD contains a `Schedules/` child directory → root is that child
4. Otherwise → ask the user for the Schedules folder path

The grandparent of the Schedules root should match `W\d+ - .+` (e.g., `W1134 - Neiafu Tonga Temple Construction`).

### project-context.html — dict shape

Lives in the **root Schedules folder**. Created and maintained by the `schedule-project-init` skill. Read via:

```python
from parse_project_context_html import load_project_context
ctx, html_path = load_project_context(schedules_root)
```

Returns `(None, None)` if the file doesn't exist — in that case, stop and tell the user to run `schedule-project-init`.

```python
{
  'project_name': str,
  'job_number': str,
  'contractual_completion': str,
  'smartpm_url': str, 'smartpm_trends_url': str, 'smartpm_changelog_url': str,
  'smartpm_project_name': str,
  'signer_name': str, 'signer_title': str, 'signer_mobile': str,
  'procore_company_id': str,            # locked in UI; always Westland '11093'
  'procore_project_id': str,            # auto-resolved on first Procore run
  'procore_documents_folder_id': str,   # auto-resolved on first Procore run
  'graph_screenshots': list[str],
  'to_recipients': list[{'name': str, 'email': str}],
  'cc_recipients': list[{'name': str, 'email': str}],
  'to_recipients_str': str,   # legacy "Name <email>; …" form
  'cc_recipients_str': str,
  'project_log': list[{'date': 'YYYY-MM-DD', 'body': str}],
}
```

Every phase reads `project-context.html` first. If it is missing, stop with:
> "No project-context.html found in the Schedules root. Run the `schedule-project-init` skill first."

If `procore_project_id` or `procore_documents_folder_id` is empty, the `procore` phase will resolve them on first run and write them back via the generator. No manual setup required.

### Weekly email file

Each dated folder gets a `YYYY-MM-DD-update-email.md` with two sections:

1. **Update Email** — the email content (successes, red flags, key items, etc.)
2. **Project Log** — cumulative delay notes for claims and delay analysis

---

## Full Pipeline Reference

| # | Step | Owner | Command |
|---|------|-------|---------|
| 1 | Copy schedule folder for today's date | Agent | `copy` |
| 2 | Email reminder to get Excel update file | Human | — |
| 3 | Update schedule using Excel file | Human | — |
| 4 | Make corrections, discussion, complete update | Human | (in meeting) |
| 5 | Export schedule files | Human | — |
| 6 | Upload XER to SmartPM (Worker ingests it server-side after the seed POST) | Human | — |
| 7 | Copy meeting transcript to meeting folder | Human | — |
| 8 | Export PDF attachments from schedule software | Human | — |
| 9 | Create next week's Excel files | Human | — |
| 10 | Build seed, POST to MCP, hand editor URL to colleague | Agent | `report` (drives `draft`) |
| 11 | Colleague edits in browser; Worker renders graphs async | Human + Worker | — |
| 12 | Colleague says "done"; finalize draft, build `.eml`, publish Procore | Agent | `draft` (auto-fans into `procore`) |
| 13 | Open `.eml`, review, Send | Human | — |

Colleague-friendly shortcut: `report` covers rows 10–12 in a single guided conversation.
