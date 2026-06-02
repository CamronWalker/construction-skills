---
name: schedule-project-init
description: >
  Initialize a construction project's Supabase record (the wnd_projects row)
  that all scheduling skills read by job number. Gathers the project bindings
  conversationally — project name, SmartPM URLs + card title, Procore IDs — and
  persists them via the upsert_project MCP tool, then drops the generic weekly
  email launcher scripts into the Schedules root. Use this skill whenever the
  user says "initialize project", "project setup", "init project", "set up
  project", "create project context", "project init", or when another scheduling
  skill reports that the project's Supabase record (or project-context.html) is
  missing.
---

# Project Initialization

Create or update the project's **`wnd_projects` row** in Supabase — the per-job record that all scheduling skills read by `job_number`. The row carries the stable bindings (project name, SmartPM links, Procore IDs); an append-only **`wnd_project_log`** holds scope changes / EOT filings / major decisions.

This skill is **conversational + MCP**. It gathers the fields by asking the user, then writes them with the `upsert_project` MCP tool. It no longer generates `project-context.html` — the per-project HTML store was retired (the embedded base64 logo corrupted on tool I/O round-trips; the file went stale and never synced across machines). See `docs/superpowers/specs/2026-06-02-project-context-supabase-design.md` for the full rationale.

`job_number` (the `W####` parsed from the project folder) is the only key. Everything keys off it.

## What is stored where

The `wnd_projects` row is **lean** — only the stable bindings that aren't already carried in the weekly email JSON and aren't derivable from Procore. The binding columns (the exact `BINDING_COLUMNS` in `references/project_context_db_mapping.py`):

| Field | Notes |
|-------|-------|
| `project_name` | parsed from the folder; confirm with user |
| `smartpm_url` | workspace URL — must end in `/workspace` |
| `smartpm_trends_url` | derived: `/workspace` → `/trends?tab=Graphs` |
| `smartpm_changelog_url` | derived: `/workspace` → `/changelog` |
| `smartpm_project_name` | exact SmartPM v2 card title (may differ from folder) |
| `procore_company_id` | always `11093` for Westland |
| `procore_project_id` | the project's Procore ID |
| `procore_documents_folder_id` | Procore Documents folder for weekly uploads (optional at init; the Procore phase can discover it later) |

Plus `job_number` (the key) and server-managed `source` / `created_by_email` / `created_at` / `updated_at`.

**Deliberately NOT stored in `wnd_projects`** (and therefore NOT gathered here):

- **`contractual_completion`** — pulled from **Procore** at email-build time (Substantial Completion date on the Prime Contract via `list_prime_contracts`). Don't ask for it at init.
- **TO / CC recipients** and **signer name / title / mobile** — live in the weekly email JSON. They are seeded conversationally on the first weekly email and carried forward week-over-week by the `schedule-update` reconcile logic. Don't gather them here.
- **`graph_order`** — lives in the weekly email JSON; defaults to the canonical 8-slug order when absent. Don't gather it here.

## Folder Resolution

All scheduling skills share this logic to find the Schedules root:

1. If CWD basename matches `YYYY-MM-DD` (a dated folder) → root is the **parent** directory (`../`).
2. If CWD basename is `Schedules` → root is CWD.
3. If CWD contains a `Schedules/` child directory → root is that child.
4. Otherwise → ask the user for the Schedules folder path.

**Validate:** the parent of the resolved root should match the pattern `W\d+ - .+` (e.g., `W1134 - Neiafu Tonga Temple Construction`). The resolved folder itself should be named `Schedules`. The `W####` portion of that parent is the `job_number` — the key for every MCP call below.

## Workflow

### Step 1 — resolve Schedules root and check state

Apply the folder resolution logic above to get the Schedules root and parse `job_number` (Step 2). Then decide the path:

1. **Call `get_project(job_number)`** (Westland MCP tool).
   - **Hit** (a row comes back) → this project already has a Supabase record. Map it to the binding dict with `project_context_db_mapping.project_row_to_context(row)` and show the current values. Ask which fields to change, then run a partial `upsert_project` with only the changed bindings (Step 4). Skip the full gather.
   - **Miss** (`null`) → fall through to the next check.
2. **On a miss, look for a legacy `project-context.html`** in the Schedules root. If present → **lazy migration** (see *Lazy migration* below), then you're done (the row now exists; offer to update any field).
3. **No row and no HTML** → fresh setup: confirm identity (Step 2), gather conversationally (Step 3), and `upsert_project(source='init')` (Step 4).

### Step 2 — parse project identity from the folder name

Read the **grandparent** folder (parent of `Schedules/`). Parse with the regex `^(W\d+)\s*-\s*(.+)$`:

- `job_number` = the `W####` portion (e.g., `W1134`)
- `project_name` = the rest (e.g., `Neiafu Tonga Temple Construction`)

If parsing fails, ask the user for both. `job_number` is required — it's the key for every MCP call.

Confirm:
> "I read the project as **W1134 — Neiafu Tonga Temple Construction**. Is that correct?"

### Step 3 — gather the bindings conversationally

Walk the binding fields in a single conversational pass (use AskUserQuestion where helpful). Collect them into one `bindings` dict keyed by the column names above. Only the binding set — do **not** ask for contractual completion, recipients, signer, or graph order (see *What is stored where*).

1. **SmartPM workspace URL** — must end in `/workspace`. Derive `smartpm_trends_url` (replace `/workspace` with `/trends?tab=Graphs`) and `smartpm_changelog_url` (replace with `/changelog`). Show all three for confirmation.
2. **SmartPM project name** — the **exact** title shown on SmartPM v2's `/projects/cards` page. The screenshot capture script uses this to find the right card. Default to the parsed project name from Step 2; ask the user to confirm or override if SmartPM's spelling differs (e.g., `"Anchorage AK Temple"` in folders, but `"Anchorage Alaska Temple"` on SmartPM).
3. **Procore project ID** — the project's Procore ID. (Company ID is always `11093` for Westland; pass it as `procore_company_id='11093'` — it isn't user-editable.)
4. **Procore Documents folder ID** *(optional)* — the folder weekly uploads land in. If the user doesn't know it yet, leave it blank; the `schedule-update` Procore phase discovers and writes it later.

### Step 4 — persist via `upsert_project`

Call the **`upsert_project`** MCP tool with `job_number` plus the gathered bindings:

```
upsert_project(
  job_number="W1134",
  project_name="Neiafu Tonga Temple Construction",
  smartpm_url="https://live.smartpmtech.com/projects/abc/workspace",
  smartpm_trends_url="https://live.smartpmtech.com/projects/abc/trends?tab=Graphs",
  smartpm_changelog_url="https://live.smartpmtech.com/projects/abc/changelog",
  smartpm_project_name="Neiafu Tonga Temple",
  procore_company_id="11093",
  procore_project_id="2646569",
  procore_documents_folder_id="",     # optional; discovered later if blank
  source="init",
)
```

`upsert_project` is a partial update — only the fields you pass change; `created_by_email` is stamped server-side from the Procore OAuth identity on create and preserved on update, and `updated_at` is set to `now()` on every write. On a re-run (Step 1 hit), pass only the bindings the user changed.

If the user noted any project-level event at init (e.g., "we already filed EOT #1"), record it with **`append_project_log`**:

```
append_project_log(job_number="W1134", body="EOT #1 filed — 14 calendar days.", category="eot")
```

`category` is free text; common values are `'note'` (default), `'eot'`, `'scope_change'`, `'schedule_published'`. `created_by_email` is stamped server-side; `created_at` defaults to `now()` but accepts an explicit ISO override (migration uses this to preserve historical dates).

Tell the user:
> "Initialized **W1134 — Neiafu Tonga Temple Construction** in the Westland project database. All scheduling skills read it by job number — no file to keep in sync."

### Step 5 — drop the weekly email launcher script

Copy **both** launcher files from `references/` into the Schedules root:

- `Write Weekly Schedule Email.bat` — thin wrapper. Uses `start "" powershell ... -File` so the PowerShell window is its own process (cmd shim exits instead of hosting PowerShell).
- `Write Weekly Schedule Email.ps1` — the actual logic. Clears inherited Claude env vars, `Set-Location $PSScriptRoot`, discovers the `claude` binary robustly (PATH + known install locations — some installers add the full exe path to PATH instead of its folder, which breaks `Get-Command`), and runs `claude --permission-mode auto '/write-weekly-schedule-email'`.

A colleague double-clicks the `.bat` in Explorer — they don't need to know Cowork, Claude Code, slash commands, or PowerShell. The launchers carry **no project identity**; the skill they invoke resolves `job_number` from the folder and reads the Supabase row. If the Claude Code CLI isn't installed (or isn't discoverable), the script prints the install link (https://claude.com/claude-code) and lists the locations it checked, in red, then stops — no silent flash.

The pattern mirrors the Iris task-watcher agent launcher. `auto` mode keeps the session autonomous while still respecting permission boundaries.

On re-run, if the `.bat` is missing (older project, file was moved), copy it again. If it exists, check whether the content matches the current template and offer to refresh it if not. Never overwrite silently.

Tell the user (on first init):
> "Dropped **Write Weekly Schedule Email.bat** in the Schedules root. Colleagues double-click it after the schedule meeting and Claude Code takes over from there — no Cowork, no slash commands to remember. Claude Code CLI and Node.js need to be installed on whichever machine runs it."

## Lazy migration — retiring a legacy `project-context.html`

When `get_project(job_number)` returns `null` but a `project-context.html` exists in the Schedules root, migrate it into Supabase once, then retire the file. Use the helpers in `references/project_context_db_mapping.py` and the parser in `references/parse_project_context_html.py`:

1. **Parse** the file: `parse_project_context_html.parse_project_context_html(path)` → the parsed dict. (Never `Read`/`Edit`/`Write` the HTML directly — the embedded ~17 KB base64 logo corrupts on tool I/O. The parser ignores the logo bytes entirely.)
2. **Map bindings → upsert payload:** `parsed_context_to_project_row(parsed, job_number=job_number)` returns exactly `{job_number}` + the binding columns, dropping the cut fields (recipients, signer, graph, contractual completion). Call `upsert_project(**payload, source='migrated')`.
3. **Map log entries:** `parsed_context_to_log_entries(parsed)` returns one `{body, created_at, category}` dict per entry (category `'note'`, original date preserved as `created_at`). For each, call `append_project_log(job_number, body, category, created_at=created_at)` so historical dates survive.
4. **Retire the file:** `retire_context_html(path)` renames `project-context.html` → `project-context-migrated.html` (collision-safe) so nothing reads — or accidentally edits — the dead artifact.
5. The bindings dict for downstream use is `project_row_to_context(row)` over the row `upsert_project` returned (or re-fetch with `get_project`).

Recipients / signer / graph_order in the old HTML are **discarded** — every mid-stream project already carries them in its latest weekly email JSON. If there's no row and no HTML, tell the user to run this skill fresh (Steps 2–4).

## The DB-row ↔ context seam

`references/project_context_db_mapping.py` is the pure, stub-testable mapping between a `wnd_projects` row and the binding dict that downstream skills consume. No network or MCP calls live in it — the skill owns `get_project` / `upsert_project` / `append_project_log`.

| Function | Direction | Returns |
|----------|-----------|---------|
| `project_row_to_context(row)` | DB row → binding dict | only `BINDING_COLUMNS` keys (under the established `parse_project_context_html` names); missing/None → `''`. No recipients/signer/graph/contractual leak through. |
| `parsed_context_to_project_row(parsed, job_number=None)` | parser dict → upsert payload | `{job_number}` + binding columns; every cut field dropped. |
| `parsed_context_to_log_entries(parsed)` | parser `project_log` → log rows | `[{body, created_at, category}]`, order preserved, dates kept. |
| `retire_context_html(path)` | file rename | `project-context-migrated.html` (collision-safe); `FileNotFoundError` if source missing. |

Downstream callers (`schedule-update` report/draft, `write-weekly-schedule-email`) read the binding dict by the same key names the parser used, so swapping the store from HTML to Supabase is transparent to them.

## Note on attachments

Earlier versions had an `expected_attachments` glob-pattern list in the project context. That was removed — the weekly email JSON carries attachments forward automatically via `transition_attachments` (date-normalized fuzzy match against the dated folder), so the project record doesn't need template patterns. On the very first week for a project, the `schedule-update` skill globs all `.pdf` / `.xlsm` / `.xer` files in the dated folder as the initial set; the user curates from there.

## Re-run behavior

When `get_project(job_number)` returns an existing row, this skill acts as an editor:

1. Map the row with `project_row_to_context(row)` and display current bindings.
2. Ask which fields to change.
3. Call `upsert_project(job_number, <changed bindings only>)` — partial update, only the passed fields change.
4. To record a project-level event, call `append_project_log(job_number, body, category)`.

This is the intended way to update project config (SmartPM URL change, Procore folder, a new log entry). There is no HTML to round-trip — every edit is an MCP call.

## Reference files

All reference files live in `references/` within this skill directory.

| File | Purpose |
|------|---------|
| `references/project_context_db_mapping.py` | Pure mapping seam: `project_row_to_context`, `parsed_context_to_project_row`, `parsed_context_to_log_entries`, `retire_context_html`. Stub-testable; no network. |
| `references/parse_project_context_html.py` | Parses a legacy `project-context.html` into a dict — **only used by lazy migration**. Convenience helper `load_project_context(root)` returns `(ctx, html_path)` or `(None, None)` if the file is missing. |
| `references/project_context_schema.sql` | Reference copy of the `wnd_projects` + `wnd_project_log` table definitions (live schema applied in Supabase project `anwdfilrfczluhudtbzw` via `apply_migration`). |
| `references/westland-logo.png` | Signature/header logo (retained for the legacy parser's environment and any future use; no longer embedded by this skill). |
| `references/Write Weekly Schedule Email.bat` | Colleague-facing double-click launcher. Copied into the Schedules root on init — uses `start` to spawn a new PowerShell window running the sibling `.ps1`. |
| `references/Write Weekly Schedule Email.ps1` | Actual launcher logic. Clears inherited Claude env vars, discovers `claude` robustly (PATH + known install locations), then runs `claude --permission-mode auto "/write-weekly-schedule-email"` from the Schedules root. |
| `tests/test_project_context_db_mapping.py` | Unit tests pinning the mapping contract — row↔context, parsed→row payload shape, parsed→log entries, retire-html collision safety, plus a Python 3.10 f-string compatibility guard. |
| `tests/test_project_context_html.py` | Parser-only tests for the legacy `project-context.html` parser used by lazy migration. |

## MCP tool contracts (Westland connector)

| Tool | Input | Behavior |
|------|-------|----------|
| `get_project` | `job_number` | returns the `wnd_projects` row JSON, or `null` if none. |
| `upsert_project` | `job_number` + bindings + `source?` | create or update (partial); stamps `created_by_email` on create, `updated_at` always; returns the row. |
| `append_project_log` | `job_number`, `body`, `category?`, `created_at?` | resolves `project_id` from `job_number`, inserts a `wnd_project_log` row (server-stamped `created_by_email`; `created_at` defaults to now, ISO override accepted); returns the entry. |
| `list_project_log` | `job_number`, `limit?` (default 50) | recent entries, newest first. |

All four are Procore-OAuth gated (any Procore-authenticated user); no admin gate.

## Folder structure reference

After initialization:

```
Schedules/
├── Write Weekly Schedule Email.bat   ← colleague launcher (this skill drops it)
├── Write Weekly Schedule Email.ps1   ← launcher logic
├── 2026-04-01/
│   ├── 2026-04-01-email.json         ← weekly draft from cloud editor (schedule-update skill)
│   ├── 2026-04-01-update-email.md    ← archive of the sent email
│   ├── screenshots/                  ← SmartPM screenshots
│   └── *.xer, *.pdf, *.xlsm          ← schedule files and reports
├── 2026-04-08/
│   └── ...
```

Project identity no longer lives in a file here — it's the `wnd_projects` row keyed by `job_number`. A retired `project-context-migrated.html` may remain after a lazy migration; it's inert.
