# Phase: `email` — Build the .eml from the finalized draft

> Loaded by SKILL.md's router when the user invokes `/schedule-update email`.
> Requires `phases/draft.md` to have already produced `{dated_folder}/email-draft.json`.

Builds the Outlook-openable `.eml` from the cloud-editor's finalized JSON. The old composition / preview-HTML step is now `phases/draft.md`; this phase is purely the build step.

## Inputs

- `{dated_folder}/email-draft.json` — produced by `phases/draft.md` via the weekly-email cloud editor (`generate_weekly_email_draft` → finalize).
- `{dated_folder}/project-context.html` — for SmartPM URLs and logo path (read via `parse_project_context_html`).

If `email-draft.json` is missing, stop and tell the colleague:
> "No `email-draft.json` found for today's folder. Run `/schedule-update draft` first to open the cloud editor and finalize the draft."

(Legacy projects where last week predated this branch may still have a `{YYYY-MM-DD}-email-preview.html` instead. Those are *read-only* fallbacks for carry-forward — see `phases/_carry_forward.md`. The build step always wants `email-draft.json`.)

## Process

### 1. Read the finalized draft

```python
import sys; sys.path.insert(0, 'scheduling/skills/schedule-update/references')
from email_draft_io import load_draft

draft = load_draft(dated_folder + '/email-draft.json')
```

### 2. Build the .eml

```python
from email_draft_io import generate_email_from_draft

eml_path = generate_email_from_draft(
    draft_path=dated_folder + '/email-draft.json',
    output_eml_path=dated_folder + f'/{report_date_iso}-update-email.eml',
    dated_folder=dated_folder,
    smartpm_project_url=draft['editorial'].get('smartpm_project_url', ''),
    smartpm_trends_url=draft['editorial'].get('smartpm_trends_url', ''),
)
```

This orchestrator does three things end-to-end:
- Renders the stacked-graphs PNG into `{dated_folder}/screenshots/{project}-{report_date}-all-graphs-stacked.png` via the renderer agent's `html_to_png.cjs`.
- Resolves `editorial.attachments` filenames against `dated_folder` (skipping files that aren't on disk).
- Calls the existing `generate_update_email_eml` with the resolved kwargs, including `summary_screenshot_path=<stacked PNG>` and `graph_screenshot_paths=[]`.

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
- Upload to Procore — that's `phases/procore.md`. It reads `email-draft.json` directly for `skip_procore` + `attachments[].share_to_procore`.
- Render charts in isolation — the stacked PNG is the only chart artifact this phase touches.

## Cross-references

- `phases/draft.md` — produces the `email-draft.json` this phase consumes.
- `phases/procore.md` — separate publish step driven by the same JSON.
- `references/email_draft_io.py` — the seam between `email-draft.json` and the existing `.eml` / COM builders.
- scheduling/CLAUDE.md "Email-preview JSON shape — single source of truth."
