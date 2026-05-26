# Phase: draft

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `draft` phase; any divergence from it is a bug.
> Loaded by SKILL.md's router when the user invokes `/schedule-update draft` (or when called as an internal dependency from another phase).

## Goal

Produce `{dated_folder}/{YYYY-MM-DD}-email.json` — the complete state Claude and the colleague will iterate on in the browser before the `.eml` build step.

## Inputs

- `{dated_folder}/project-context.html` — recipients, signer info, SmartPM IDs (via `parse_project_context_html`).
- Last week's `{prev_dated_folder}/{prev_date}-email.json` — for carry-forward of items and narratives. Missing for week-1 projects; in that case `last_week` is `null` and the editor renders without diff overlays.
- This week's `{dated_folder}/*.xer` + last week's XER for delta analysis (via the Westland Scheduler Local MCP — see "Compute the XER deltas" below; do not Read the .xer files directly).
- This week's meeting transcript at `{dated_folder}/meeting-transcript.md` if present.

## Outputs

- `{dated_folder}/{YYYY-MM-DD}-email.seed.json` — Claude's synthesized seed (carry-forward + new content). Persisted before the MCP call so Refresh can re-render against the same seed.
- `{dated_folder}/{YYYY-MM-DD}-email.json` — the cloud-finalized state (`this_week` + `last_week` + `smartpm` + `graphs`).

## The seed shape

The seed is the v2 top-level email JSON shape minus `graphs` (the Worker renders those). See [scheduling/CLAUDE.md → Email JSON shape](../../../CLAUDE.md) for the full contract. Verbatim shape the MCP tool expects:

```jsonc
{
  "version":     2,
  "report_date": "YYYY-MM-DD",
  "project_info": {
    "project_name": "...", "job_number": "...",
    "contractual_completion": "...", "projected_completion": "..."
  },

  "this_week": {
    "subject": "...",
    "to_recipients": [{"name": "...", "email": "..."}],
    "cc_recipients": [{"name": "...", "email": "..."}],
    "days_metric": {"direction": "behind"|"ahead", "value": int},
    "gain_loss":   {"direction": "loss"|"gain", "value": int,
                    "narrative": "...", "narrative_changed": bool},

    "successes":          [/* {text, status, checked, edited?, prev_idx} */],
    "red_flags":          [/* same */],
    "stalled_tasks":      [/* same */],
    "key_items":          [/* same */],
    "key_items_archived": [/* {text, status='archived', checked, date_archived, prev_idx} */],

    "eot_recovery": "...", "logic_changes": "...",
    "smartpm_changelog_url": "...",
    "closing_paragraphs": [{"label": "...", "checked": true,
                             "text": "<div>...</div>"}],
    "closing_salutation": "Thanks,",
    "signer_name": "...", "signer_title": "...", "signer_mobile": "...",
    "attachments": [/* {name, ext?, checked, procore, status, prev_idx} */],
    "skip_procore": false,
    "include_changes_report": bool,
    "changes_report_filename": "...",
    "graph_order": [
      "01-planned-vs-actual-percent-complete",
      "06-end-date-variance",
      "07-schedule-compression-index-over-time",
      "08-velocity",
      "09-spi-over-time",
      "10-activity-hit-rate",
      "11-window-start-accuracy",
      "12-window-finish-accuracy",
      "smartpm-summary-report"
    ]
  },

  "last_week": { /* identical shape; null if week-1 */ }
}
```

Item rows are `{text, status, checked, edited(optional), prev_idx}` where `text` is HTML and `prev_idx` is an int (index into `last_week.<same-list>`) or `null` for status='new'. Attachment rows: `{name, ext, checked, procore, status, prev_idx}`.

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

Read the meeting transcript with the Read tool. **Do not Read the .xer files directly** — they're tab-delimited proprietary exports and the byte content is not what you need. Instead, drive the week-over-week analysis through the Westland Scheduler Local MCP tools (next step).

#### Compute the XER deltas

Load and invoke the comparison tools against this week's and last week's `*.xer`:

```text
ToolSearch select:get_milestones,compare_milestone_slip,compare_activity_changes,compare_date_slips
```

```text
compare_milestone_slip(baseline_xer_path=<prev_xer>, current_xer_path=<current_xer>, milestone_id=<resolved>?)
compare_activity_changes(baseline_xer_path=<prev_xer>, current_xer_path=<current_xer>)
compare_date_slips(baseline_xer_path=<prev_xer>, current_xer_path=<current_xer>)
```

`compare_milestone_slip` auto-resolves the terminal milestone on single-terminal schedules. On phased work with multiple terminal milestones it raises `MilestoneAmbiguousError` — call `get_milestones(xer_path=<current_xer>)` first to enumerate candidates, then re-call with `milestone_id=<resolved_task_id_or_code>`.

Use the returned dicts to drive the narrative-rewrite step (§ 2 "Standard moves"):

- `compare_milestone_slip.sc_date_old` / `sc_date_new` / `sc_slip_days` → drives `days_metric` and the "Substantial Completion moved …" narrative.
- `compare_activity_changes.status_changes` / `added_tasks` / `removed_tasks` / `changed_durations` → drives `logic_changes` and surfaces completed-this-week tasks for `successes`.
- `compare_date_slips.date_slippage` → drives the "what slipped" rows for `red_flags` / `stalled_tasks`.

If `ToolSearch select:<tool>` returns nothing, invoke the `westland-scheduler-mcp-troubleshoot` skill — do not Read `schedule-toolbox/lib/*.py` as a fallback (the PreToolUse hook blocks those reads, and even with the hook disabled, in-place edits drift from the canonical analysis behavior).

### 2. Build `this_week` via structured carry-forward

The rule is **carry-forward then revise**: take `prev_draft['this_week']` field-by-field, then apply this week's deltas. Run list items through `carry_forward.reconcile_items` (and key_items through `reconcile_key_items`):

```python
from carry_forward import reconcile_items, reconcile_key_items, transition_attachments

prev_this_week = (prev_draft or {}).get('this_week', {}) or {}

successes_rows, _ = reconcile_items(prev_this_week.get('successes'),
                                     this_week_success_html, today_iso=today)
red_flags_rows, _ = reconcile_items(prev_this_week.get('red_flags'),
                                     this_week_red_flag_html, today_iso=today)
stalled_rows, _   = reconcile_items(prev_this_week.get('stalled_tasks'),
                                     this_week_stalled_html, today_iso=today)

# key_items: two inputs (active + archived), three outputs.
key_items_rows, key_items_archived_rows, _ = reconcile_key_items(
    prev_this_week.get('key_items'),
    prev_this_week.get('key_items_archived'),
    this_week_key_item_html,
    today_iso=today,
)

attachments_rows = transition_attachments(
    prev_this_week.get('attachments'),
    fresh_filenames,
    today_iso=today,
)
```

Standard moves for everything else:

- **Subject:** swap last week's date for this week's; keep project name + job number.
- **Narrative blocks (`gain_loss.narrative`, `eot_recovery`, `logic_changes`):** rewrite based on this week's XER deltas + transcript. Leave `smartpm_changelog_url` unchanged unless the URL pattern has shifted.
- **Signer block:** unchanged unless the colleague has rotated.
- **`days_metric` / `gain_loss`:** compute from the `compare_milestone_slip` result captured in § 1. `days_metric.value` = days between `sc_date_new` and the contractual completion; `direction` = `'behind'` when slipping vs contract, `'ahead'` when running early. `gain_loss.value` = `sc_slip_days`; `direction` = `'loss'` when SC slipped vs last week, `'gain'` when SC pulled in. `gain_loss.narrative` is one short paragraph and `narrative_changed` is `True` when it differs from `last['gain_loss']['narrative']`.
- **`graph_order`:** unchanged unless the colleague has reordered. Default is the 8-trend canonical order plus `'smartpm-summary-report'` last.
- **`closing_paragraphs` / `closing_salutation`:** preserve from last week, or default to a single-entry list `[{label: "Questions", checked: true, text: "<div>Please let me know if you have any questions.</div>"}]` and `"Thanks,"`.

### 3. Build `last_week` (frozen)

`last_week` is a **frozen verbatim copy** of last week's `this_week` — unchanged for the lifetime of this week's draft. The cloud editor reads it to render strikethroughs on changed metrics + diff badges on edited items; the local `.eml` builder reads `last_week.days_metric` / `last_week.gain_loss` to render strikethrough-previous-metric badges on the colored status lines.

```python
last_week_block = prev_this_week if prev_draft else None
```

No recursion; `last_week.last_week` is not a thing.

### 4. Assemble the seed and write it to disk

```python
seed = {
    'version': 2,
    'report_date': today_iso,
    'project_info': {
        'project_name': ctx['project_name'],
        'job_number':   ctx['job_number'],
        'contractual_completion': ctx['contractual_completion'],
        'projected_completion':   projected_completion_iso,
    },
    'this_week': {
        'subject':       this_week_subject,
        'to_recipients': ctx['to_recipients'],   # [{name, email}, ...] array
        'cc_recipients': ctx['cc_recipients'],   # same
        'days_metric':   this_week_days_metric,  # {direction, value}
        'gain_loss':     this_week_gain_loss,    # {direction, value, narrative, narrative_changed}
        'successes':           successes_rows,
        'red_flags':           red_flags_rows,
        'stalled_tasks':       stalled_rows,
        'key_items':           key_items_rows,
        'key_items_archived':  key_items_archived_rows,
        'eot_recovery':         this_week_eot_recovery,
        'logic_changes':        this_week_logic_changes,
        'smartpm_changelog_url': ctx['smartpm_changelog_url'],
        'closing_paragraphs':   this_week_closing_paragraphs,
        'closing_salutation':   this_week_closing_salutation,
        'signer_name':          ctx['signer_name'],
        'signer_title':         ctx['signer_title'],
        'signer_mobile':        ctx['signer_mobile'],
        'attachments':          attachments_rows,
        'skip_procore':         prev_this_week.get('skip_procore', False),
        'include_changes_report':  bool(prev_this_week.get('include_changes_report', True)),
        'changes_report_filename': changes_report_filename,
        'graph_order':          prev_this_week.get('graph_order') or default_graph_order_with_summary,
    },
    'last_week': prev_this_week if prev_draft else None,
}
with open(os.path.join(dated_folder, f'{today_iso}-email.seed.json'), 'w') as f:
    json.dump(seed, f, indent=2)
```

If the current draft.md mentions a top-level `'smartpm'` key in the seed dict (it was in v1), this replacement drops it — the Worker resolves SmartPM from `project_info.job_number` in v2.

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

### 10. Build the .eml

Before building the .eml, **re-read `phases/_render_graphs.md`** — the stacked-PNG rasterization recipe lives there. Then call `email_draft_io.generate_email_from_draft(...)`, which internally:

1. Loads the v2 draft.
2. Stacks `graphs.{slug}.html` chunks in `graph_order` order.
3. Rasterizes to one PNG via `html_to_png.cjs`.
4. Resolves attachment names against `dated_folder`.
5. Calls `editorial_to_kwargs` to flatten v2 → builder kwargs.
6. Calls `generate_update_email_eml` to write the .eml.

If `graphs_ready_count < graphs_total` from the finalize response, warn the colleague before building (some chart cards will be placeholders).

## What this phase replaces

The old flow wrote `{dated_folder}/{YYYY-MM-DD}-email-preview.html` and asked the colleague to open it in a browser to edit. That artifact is no longer produced, and the legacy `generate_email_preview_html.py` / `parse_email_html.py` scripts have been removed.

## What this phase explicitly does NOT do

- Build the `.eml` (that's `phases/email.md`).
- Upload to Procore (that's `phases/procore.md` — and it reads `{YYYY-MM-DD}-email.json` directly for `skip_procore` + `attachments[].procore`).
- Render chart PNGs in isolation (the cloud function renders + stores HTML+SVG chunks; the `.eml` build stacks them into one PNG).

## Cross-references

- Shape canonical to all email-related artifacts: [scheduling/CLAUDE.md → Email JSON shape](../../../CLAUDE.md).
- Worker schema: <https://westland-mcps.westland.workers.dev/westland-forms/weekly-schedule-update-email/schema>.
- The MCP tools and HTTP routes: docs/superpowers/specs/2026-05-21-weekly-email-cloud-editor-design.md.
- The chart renderer package the cloud function uses: docs/superpowers/specs/2026-05-22-html-svg-chart-migration-javascript-design.md.
