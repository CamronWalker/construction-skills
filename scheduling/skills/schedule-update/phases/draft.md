# Phase: draft

## Goal

Produce `{dated_folder}/email-draft.json` — the complete state Claude and the colleague will iterate on in the browser before the `.eml` build step.

## Inputs

- `{dated_folder}/project-context.html` — recipients, signer info, SmartPM IDs (via `parse_project_context_html`).
- Last week's `{prev_dated_folder}/email-draft.json` — for carry-forward of items and narratives. If the previous week's run still has a `{prev_dated_folder}/*-email-preview.html` instead (legacy flow), fall back to `parse_email_html.parse_preview_html()` for the carry-forward shape.
- This week's `{dated_folder}/*.xer` + last week's XER for delta analysis (use the schedule plugin's XER parser).
- This week's meeting transcript at `{dated_folder}/meeting-transcript.md` if present.

## Outputs

- `{dated_folder}/email-draft.seed.json` — Claude's synthesized seed (carry-forward + new content). Persisted before the MCP call so Refresh can re-render against the same seed.
- `{dated_folder}/email-draft.json` — the cloud-finalized state (editorial + graph_data + graph_html).

## Process

### 1. Read prior state + this week's signals

Use the existing parsers. Do not Read the HTML files directly (see scheduling/CLAUDE.md's "HTML CRUD goes through the parse/generate pair" rule):

```python
import sys; sys.path.insert(0, 'scheduling/skills/schedule-update/references')
from parse_project_context_html import load_project_context
from email_draft_io import load_draft

ctx = load_project_context(schedules_root)            # current project context
prev_draft = None
if os.path.isfile(prev_dated_folder + '/email-draft.json'):
    prev_draft = load_draft(prev_dated_folder + '/email-draft.json')
elif os.path.isfile(prev_dated_folder + f'/{prev_date}-email-preview.html'):
    # Legacy fallback for the first run after this branch lands.
    from parse_email_html import parse_preview_html
    prev_draft = {'editorial': parse_preview_html(prev_dated_folder + f'/{prev_date}-email-preview.html')}
```

Read the XERs and the meeting transcript with the standard tools (Read + the XER parser).

### 2. Synthesize the seed

Build a dict matching the canonical editorial shape (per scheduling/CLAUDE.md "Email-preview JSON shape" + the cloud-editor spec's seed shape). The rule is **carry-forward then revise**: copy `prev_draft['editorial']` field-by-field, then apply this week's deltas. Standard moves:

- **Subject:** swap last week's date for this week's; keep project name + job number.
- **Items (successes / red_flags / stalled_tasks / key_items):** carry forward each entry's `text` + `status` + `date_archived`; reset `checked=True` for items that are still active; set `checked=False` for items that already shipped last week.
- **Narrative blocks (gain_loss_narrative, eot_recovery, logic_changes):** rewrite based on this week's XER deltas + transcript. Leave smartpm_changelog_url unchanged unless the URL pattern has shifted.
- **Attachments:** carry forward last week's attachments; mark items that no longer exist on disk as `status='archived'`. Add this week's new attachments (changes report PDF, etc.). Preserve `share_to_procore` flags from last week.
- **Signer block:** unchanged unless the colleague has rotated.
- **days_behind / gain_loss:** compute from XER comparison (week-over-week delta on contractual completion + schedule variance).
- **graph_order:** unchanged unless the colleague has reordered. Default order is the `graph_screenshots` list from project-context.html plus `smartpm-summary-report` last.

Write the seed JSON to disk:

```python
with open(dated_folder + '/email-draft.seed.json', 'w') as f:
    json.dump({'project': ctx['project']['job_number'],
                'report_date': report_date_iso,
                'editorial': seed_editorial,
                'smartpm': {'project_name': ctx['project']['smartpm_project_name'],
                            'scenario_id': None}},  # MCP resolves
              f, indent=2)
```

### 3. Generate the cloud draft

Call the `generate_weekly_email_draft` MCP tool (mounted at `/weekly-email/mcp` on westland-mcps):

```
mcp.generate_weekly_email_draft(
    project=ctx['project']['job_number'],
    report_date=report_date_iso,
    seed_json=<loaded seed>
)
```

The tool returns `{editor_url, expires_at, graphs_ready_count, graphs_total, smartpm_import_status}`.

### 4. Hand the URL to the colleague

Print the editor URL clearly. Tell them:
- Click it to open the editor in their browser.
- Edits autosave; no Save button needed.
- If `smartpm_import_status == 'processing'`, graphs are placeholders right now — they can start editing the narrative; ask Claude to refresh once SmartPM finishes (~20 min after XER upload).
- When done editing, come back here and say "done" (or equivalent — the next phase polls status).

### 5. (Optional, on colleague request) Refresh graphs

If the colleague asks Claude to refresh — typically because SmartPM was still processing at generate time — call `generate_weekly_email_draft` again with the **same seed** (read `email-draft.seed.json` from disk). The MCP tool preserves the editorial layer server-side and only refreshes graph_data + graph_html. Returns a new URL with a fresh signed token (same draft, new bookmark).

```python
seed = json.load(open(dated_folder + '/email-draft.seed.json'))
mcp.generate_weekly_email_draft(**seed)
```

The colleague's open browser tab keeps working; if it had been left open, autosaves continue against the same `(project, report_date)` key. They can hit Refresh in the editor (the button calls `/refresh-graphs` directly — no need to come back to Claude for the typical case). The Claude-driven path is the fallback when the URL has expired.

### 6. Wait for the colleague to finish

The colleague tells Claude they're done. Optionally call `get_weekly_email_status` to verify `status == 'editing'` and `last_edited_at` is recent enough to be plausible.

### 7. Finalize

Call `finalize_weekly_email`. Save the returned working JSON to disk:

```python
result = mcp.finalize_weekly_email(
    project=ctx['project']['job_number'],
    report_date=report_date_iso,
)
with open(dated_folder + '/email-draft.json', 'w') as f:
    json.dump(result['working_json'], f, indent=2)
```

`result['graphs_ready_count'] < result['graphs_total']` means some charts are still placeholders or errored — warn the colleague before proceeding to `phases/email.md`. They can choose to ship with placeholders (rare; only if the data is truly unavailable) or wait + re-run from step 3.

## What this phase replaces

The old flow wrote `{dated_folder}/{YYYY-MM-DD}-email-preview.html` and asked the colleague to open it in a browser to edit. That artifact is no longer produced. `references/generate_email_preview_html.py` and `references/parse_email_html.py` remain in the repo for one release cycle as a fallback for reading legacy preview HTML during the carry-forward step.

## What this phase explicitly does NOT do

- Build the `.eml` (that's `phases/email.md`).
- Upload to Procore (that's `phases/procore.md` — and it reads `email-draft.json` directly for `skip_procore` + `attachments[].share_to_procore`).
- Render chart PNGs in isolation (the cloud function renders + stores HTML+SVG chunks; the `.eml` build stacks them into one PNG).

## Cross-references

- Shape canonical to all email-related artifacts: scheduling/CLAUDE.md "Email-preview JSON shape — single source of truth".
- The MCP tools and HTTP routes: docs/superpowers/specs/2026-05-21-weekly-email-cloud-editor-design.md.
- The chart renderer package the cloud function uses: docs/superpowers/specs/2026-05-22-html-svg-chart-migration-javascript-design.md.
