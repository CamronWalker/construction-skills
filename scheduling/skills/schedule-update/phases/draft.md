# Phase: draft

## Goal

Produce `{dated_folder}/{YYYY-MM-DD}-email.json` — the complete state Claude and the colleague will iterate on in the browser before the `.eml` build step.

## Inputs

- `{dated_folder}/project-context.html` — recipients, signer info, SmartPM IDs (via `parse_project_context_html`).
- Last week's `{prev_dated_folder}/{prev_date}-email.json` — for carry-forward of items and narratives. Missing for week-1 projects; in that case `last_week` is `null` and the editor renders without diff overlays.
- This week's `{dated_folder}/*.xer` + last week's XER for delta analysis (use the schedule plugin's XER parser).
- This week's meeting transcript at `{dated_folder}/meeting-transcript.md` if present.

## Outputs

- `{dated_folder}/{YYYY-MM-DD}-email.seed.json` — Claude's synthesized seed (carry-forward + new content). Persisted before the MCP call so Refresh can re-render against the same seed.
- `{dated_folder}/{YYYY-MM-DD}-email.json` — the cloud-finalized state (`this_week` + `last_week` + `smartpm` + `graphs`).

## The seed shape

The seed is the new top-level email JSON shape minus `graphs` (the Worker renders those). See [scheduling/CLAUDE.md → Email JSON shape](../../../CLAUDE.md) for the full contract. Verbatim shape the MCP tool expects:

```jsonc
{
  "version":     1,
  "report_date": "YYYY-MM-DD",
  "project_info": {
    "project_name": "...", "job_number": "...",
    "contractual_completion": "...", "projected_completion": "..."
  },

  "this_week": {
    "subject": "...", "to": "...", "cc": "...",
    "days_behind": int, "gain_loss": int,
    "successes":     [/* item rows */],
    "red_flags":     [/* item rows */],
    "stalled_tasks": [/* item rows */],
    "key_items":     [/* item rows */],
    "gain_loss_narrative": "...", "eot_recovery": "...", "logic_changes": "...",
    "smartpm_changelog_url": "...",
    "custom_paragraphs": [{"label": "...", "text": "<div>...</div>", "checked": true}],
    "attachments":      [/* {filename, checked, status, date_archived, share_to_procore, prev_idx} */],
    "changes_report":   {"include": bool, "filename": "..."},
    "skip_procore":     false,
    "graph_order":      [/* slug list, canonical render order */],
    "closing_line":     "Please let me know if you have any questions.",
    "salutation":       "Thanks,",
    "signer_name":      "...", "signer_title": "...", "signer_mobile": "..."
  },

  "last_week": { /* identical shape; frozen copy from last week's this_week; null if week-1 */ },

  "smartpm": { "project_name": "...", "scenario_id": null }
}
```

Item rows are `{text, checked, status, date_archived, prev_idx}` where `text` is HTML and `prev_idx` is an int (index into `last_week.<same-list>`) or `null` for status='new'. Attachment rows add `share_to_procore`.

## Process

### 1. Read prior state + this week's signals

Use the existing parsers. Do not Read the HTML files directly (see scheduling/CLAUDE.md's "HTML CRUD goes through the parse/generate pair" rule):

```python
import json, os, sys
sys.path.insert(0, 'scheduling/skills/schedule-update/references')
from parse_project_context_html import load_project_context
from email_draft_io import load_draft

ctx, _ = load_project_context(schedules_root)            # current project context

prev_draft = None
prev_email_json = os.path.join(prev_dated_folder, f'{prev_date}-email.json')
if os.path.isfile(prev_email_json):
    prev_draft = load_draft(prev_email_json)
# else: week-1 project — prev_draft stays None and last_week=null.
```

Read the XERs and the meeting transcript with the standard tools (Read + the XER parser).

### 2. Build `this_week` via structured carry-forward

The rule is **carry-forward then revise**: take `prev_draft['this_week']` field-by-field, then apply this week's deltas. Run list items through `carry_forward.reconcile_items` so `prev_idx` lands correctly:

```python
from carry_forward import reconcile_items, transition_attachments

prev_this_week = (prev_draft or {}).get('this_week', {}) or {}

# Each list: reconcile this week's HTML strings against last week's rows.
successes_rows, _    = reconcile_items(prev_this_week.get('successes'),     this_week_success_html,     today_iso=today)
red_flags_rows, _    = reconcile_items(prev_this_week.get('red_flags'),     this_week_red_flag_html,    today_iso=today)
stalled_rows, _      = reconcile_items(prev_this_week.get('stalled_tasks'), this_week_stalled_html,     today_iso=today)
key_items_rows, _    = reconcile_items(prev_this_week.get('key_items'),     this_week_key_item_html,    today_iso=today)

# Attachments: fresh-glob from disk, fuzzy-match against last week.
attachments_rows = transition_attachments(prev_this_week.get('attachments'), fresh_filenames, today_iso=today)
```

Standard moves for everything else:

- **Subject:** swap last week's date for this week's; keep project name + job number.
- **Narrative blocks (`gain_loss_narrative`, `eot_recovery`, `logic_changes`):** rewrite based on this week's XER deltas + transcript. Leave `smartpm_changelog_url` unchanged unless the URL pattern has shifted.
- **Signer block:** unchanged unless the colleague has rotated.
- **`days_behind` / `gain_loss`:** compute from XER comparison (week-over-week delta on contractual completion + schedule variance).
- **`graph_order`:** unchanged unless the colleague has reordered. Default order is the `graph_screenshots` list from `project-context.html` plus `smartpm-summary-report` last.
- **`closing_line` / `salutation`:** preserve from last week, or default to `"Please let me know if you have any questions."` and `"Thanks,"`.

### 3. Build `last_week` (frozen)

`last_week` is a **frozen verbatim copy** of last week's `this_week` — unchanged for the lifetime of this week's draft. The cloud editor reads it to render strikethroughs on changed metrics + diff badges on edited items; the local `.eml` builder reads `last_week.days_behind` / `last_week.gain_loss` to render strikethrough-previous-metric badges on the colored status lines.

```python
last_week_block = prev_this_week if prev_draft else None
```

No recursion; `last_week.last_week` is not a thing.

### 4. Assemble the seed and write it to disk

```python
seed = {
    'version': 1,
    'report_date': today_iso,
    'project_info': {
        'project_name': ctx['project_name'],
        'job_number':   ctx['job_number'],
        'contractual_completion': ctx['contractual_completion'],
        'projected_completion':   projected_completion_iso,
    },
    'this_week': {
        'subject':       this_week_subject,
        'to':            ctx['to_recipients_str'],
        'cc':            ctx['cc_recipients_str'],
        'days_behind':   this_week_days_behind,
        'gain_loss':     this_week_gain_loss,
        'successes':     successes_rows,
        'red_flags':     red_flags_rows,
        'stalled_tasks': stalled_rows,
        'key_items':     key_items_rows,
        'gain_loss_narrative':   this_week_gain_loss_narrative,
        'eot_recovery':          this_week_eot_recovery,
        'logic_changes':         this_week_logic_changes,
        'smartpm_changelog_url': ctx['smartpm_changelog_url'],
        'custom_paragraphs':     this_week_custom_paragraphs,   # carry forward verbatim
        'attachments':           attachments_rows,
        'changes_report':        {'include': True, 'filename': changes_report_filename},
        'skip_procore':          prev_this_week.get('skip_procore', False),
        'graph_order':           prev_this_week.get('graph_order') or default_graph_order,
        'closing_line':          prev_this_week.get('closing_line') or 'Please let me know if you have any questions.',
        'salutation':            prev_this_week.get('salutation')   or 'Thanks,',
        'signer_name':           ctx['signer_name'],
        'signer_title':          ctx['signer_title'],
        'signer_mobile':         ctx['signer_mobile'],
    },
    'last_week': last_week_block,
    'smartpm': {
        'project_name': ctx['smartpm_project_name'],
        'scenario_id':  None,    # MCP resolves
    },
}
with open(os.path.join(dated_folder, f'{today_iso}-email.seed.json'), 'w') as f:
    json.dump(seed, f, indent=2)
```

### 5. Generate the cloud draft

Call the `generate_weekly_schedule_update_email_draft` MCP tool (mounted at the `westland-forms/weekly-schedule-update-email` path on westland-mcps):

```
mcp.generate_weekly_schedule_update_email_draft(
    project=ctx['job_number'],
    report_date=today_iso,
    seed_json=<loaded seed>
)
```

The tool returns `{editor_url, expires_at, graphs_ready_count, graphs_total, smartpm_import_status}`.

### 6. Hand the URL to the colleague

Print the editor URL clearly. Tell them:
- Click it to open the editor in their browser.
- Edits autosave; no Save button needed.
- If `smartpm_import_status == 'processing'`, graphs are placeholders right now — they can start editing the narrative; ask Claude to refresh once SmartPM finishes (~20 min after XER upload).
- When done editing, come back here and say "done" (or equivalent — the next phase polls status).

### 7. (Optional, on colleague request) Refresh graphs

If the colleague asks Claude to refresh — typically because SmartPM was still processing at generate time — call `generate_weekly_schedule_update_email_draft` again with the **same seed** (read `{today_iso}-email.seed.json` from disk). The MCP tool preserves the editorial layer server-side and only refreshes `graphs`. Returns a new URL with a fresh signed token (same draft, new bookmark).

```python
seed = json.load(open(os.path.join(dated_folder, f'{today_iso}-email.seed.json')))
mcp.generate_weekly_schedule_update_email_draft(**seed)
```

The colleague's open browser tab keeps working; if it had been left open, autosaves continue against the same `(project, report_date)` key. They can hit Refresh in the editor (the button calls `/refresh-graphs` directly — no need to come back to Claude for the typical case). The Claude-driven path is the fallback when the URL has expired.

### 8. Wait for the colleague to finish

The colleague tells Claude they're done. Optionally call `get_weekly_schedule_update_email_status` to verify `status == 'editing'` and `last_edited_at` is recent enough to be plausible.

### 9. Finalize

Call `finalize_weekly_schedule_update_email`. Save the returned working JSON to disk:

```python
result = mcp.finalize_weekly_schedule_update_email(
    project=ctx['job_number'],
    report_date=today_iso,
)
with open(os.path.join(dated_folder, f'{today_iso}-email.json'), 'w') as f:
    json.dump(result['working_json'], f, indent=2)
```

`result['graphs_ready_count'] < result['graphs_total']` means some charts are still placeholders or errored — warn the colleague before proceeding to `phases/email.md`. They can choose to ship with placeholders (rare; only if the data is truly unavailable) or wait + re-run from step 5.

## What this phase replaces

The old flow wrote `{dated_folder}/{YYYY-MM-DD}-email-preview.html` and asked the colleague to open it in a browser to edit. That artifact is no longer produced, and the legacy `generate_email_preview_html.py` / `parse_email_html.py` scripts have been removed.

## What this phase explicitly does NOT do

- Build the `.eml` (that's `phases/email.md`).
- Upload to Procore (that's `phases/procore.md` — and it reads `{YYYY-MM-DD}-email.json` directly for `skip_procore` + `attachments[].share_to_procore`).
- Render chart PNGs in isolation (the cloud function renders + stores HTML+SVG chunks; the `.eml` build stacks them into one PNG).

## Cross-references

- Shape canonical to all email-related artifacts: [scheduling/CLAUDE.md → Email JSON shape](../../../CLAUDE.md).
- Worker schema: <https://westland-mcps.westland.workers.dev/westland-forms/weekly-schedule-update-email/schema>.
- The MCP tools and HTTP routes: docs/superpowers/specs/2026-05-21-weekly-email-cloud-editor-design.md.
- The chart renderer package the cloud function uses: docs/superpowers/specs/2026-05-22-html-svg-chart-migration-javascript-design.md.
