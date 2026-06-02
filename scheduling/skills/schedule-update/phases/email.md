# Phase: `email` — Build the .eml from the finalized draft

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `email` phase; any divergence from it is a bug.
> Loaded by SKILL.md's router when the user invokes `/schedule-update email`.
> Requires `phases/draft.md` to have already produced `{dated_folder}/{YYYY-MM-DD}-email.json`.

Builds the Outlook-openable `.eml` from the cloud-editor's finalized JSON. The old composition / preview-HTML step is now `phases/draft.md`; this phase is purely the build step.

## Inputs

- `{dated_folder}/{YYYY-MM-DD}-email.json` — produced by `phases/draft.md` via the weekly-email cloud editor (`generate_weekly_schedule_update_email_draft` → `finalize_weekly_schedule_update_email`).
- Project bindings (for SmartPM URLs) from Supabase — `get_project(job_number)` mapped via `project_context_db_mapping.project_row_to_context(row)` (see SKILL.md "Project bindings — the `ctx` dict shape"). The Westland logo is the static asset bundled at `schedule-project-init/references/westland-logo.png` — it is **not** read from the retired `project-context.html`.

If the `-email.json` file is missing, stop and tell the colleague:
> "No `{YYYY-MM-DD}-email.json` found for today's folder. Run `/schedule-update draft` first to open the cloud editor and finalize the draft."

## Process

### 1. Read the finalized draft

```python
import sys; sys.path.insert(0, 'scheduling/skills/schedule-update/references')
from email_draft_io import load_draft

draft = load_draft(dated_folder + f'/{report_date_iso}-email.json')
```

`draft` has the v2 top-level shape (see scheduling/CLAUDE.md "Email JSON shape"): `version: 2`, `report_date`, `project_info`, `this_week` (with v2 field names — recipients arrays, days_metric/gain_loss objects, closing_paragraphs, attachments name/procore), `last_week` (or null), `graphs`.

### 2. Build the .eml

```python
from email_draft_io import generate_email_from_draft

eml_path = generate_email_from_draft(
    draft_path=dated_folder + f'/{report_date_iso}-email.json',
    output_eml_path=dated_folder + f'/{report_date_iso}-update-email.eml',
    dated_folder=dated_folder,
    smartpm_project_url=draft['this_week'].get('smartpm_project_url', ''),
    smartpm_trends_url=draft['this_week'].get('smartpm_trends_url', ''),
)
```

This orchestrator does three things end-to-end:
- Renders the stacked-graphs PNG into `{dated_folder}/screenshots/{job_number}-{report_date}-all-graphs-stacked.png` via the renderer agent's `html_to_png.cjs`.
- Resolves `this_week.attachments` filenames against `dated_folder` (skipping files that aren't on disk).
- Calls the existing `generate_update_email_eml` with the resolved kwargs produced by `editorial_to_kwargs()` (including `prev_days_behind` / `prev_gain_loss` from `last_week` when present, and `closing_paragraphs_html` / `salutation` flattened from v2's `closing_paragraphs` / `closing_salutation`), `summary_screenshot_path=<stacked PNG>` and `graph_screenshot_paths=[]`.

All charts are embedded as one stacked PNG; per-chart artifacts are not used in the `.eml` body.

### 2 (alternative): COM Outlook draft

If the colleague explicitly asks to skip the `.eml` ("save it straight to Outlook Drafts" / "use the Outlook draft path"), call `generate_update_email_msg` instead. Same kwargs, same body — just writes via Outlook COM automation rather than to disk. `email_draft_io.editorial_to_kwargs()` returns a dict compatible with both builders.

**Pre-conditions for COM path:**
- Classic Outlook must be open (not just installed — open it from Start menu so it syncs to Exchange and the draft shows up in new Outlook).
- `pywin32` must be installed (`pip install pywin32`).

If `pywin32` is missing, prompt: "Install pywin32 with `pip install pywin32`, then retry." If Outlook COM fails entirely, fall back to the `.eml` path automatically and tell the colleague.

### 3. Verify the .eml opens in Outlook

Double-click `eml_path`. Outlook should open in compose mode with To/Cc/Subject editable. Inline images (logo + stacked graphs PNG) render. Attachments appear in the attachment pane.

### 4. Confirm

> "Draft written to `{eml_path}`. Double-click the `.eml` to open in Outlook (classic or new), review, then Send. Procore upload is a separate step — run `/schedule-update procore` next."

## What this phase explicitly does NOT do

- Edit or compose the email content — that's done in the browser editor during `phases/draft.md`.
- Upload to Procore — that's `phases/procore.md`. It reads `{YYYY-MM-DD}-email.json` directly for `this_week.skip_procore` + `this_week.attachments[].procore`.
- Render charts in isolation — the stacked PNG is the only chart artifact this phase touches.

## Cross-references

- `phases/draft.md` — produces the `{YYYY-MM-DD}-email.json` this phase consumes.
- `phases/procore.md` — separate publish step driven by the same JSON.
- `references/email_draft_io.py` — the seam between `{YYYY-MM-DD}-email.json` and the existing `.eml` / COM builders.
- scheduling/CLAUDE.md "Email JSON shape — single source of truth."
