# Phase: draft

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `draft` phase; any divergence from it is a bug.
> Loaded by SKILL.md's router when the user invokes `/schedule-update draft` (or when called as an internal dependency from another phase).

## The goal in one sentence

Produce `{dated_folder}/{YYYY-MM-DD}-email.json` by POSTing one MCP call — `generate_weekly_schedule_update_email_draft` — with a v2 seed. Every step in this file is about gathering inputs to that one call.

The Worker schema at <https://westland-mcps.westland.workers.dev/westland-forms/weekly-schedule-update-email/schema> is the contract. The shape blocks below paraphrase it; if anything here disagrees with the schema URL, the URL wins.

## Inputs

- `{dated_folder}/project-context.html` — recipients, signer, SmartPM URLs (via `parse_project_context_html.load_project_context`).
- Last week's `{prev_dated_folder}/{prev_date}-email.json` (via `email_draft_io.load_draft`) — drives carry-forward. Missing on week-1 projects; `last_week` becomes `null`.
- This week's + last week's `*.xer` — driven through `westland-scheduler-mcp` tools. Never `Read` the .xer files directly.
- This week's transcript at `{dated_folder}/meeting-transcript.md` if present.

## Outputs

- `{dated_folder}/{YYYY-MM-DD}-email.seed.json` — the seed Claude built. Persisted before the POST so Refresh can re-render against the same seed.
- `{dated_folder}/{YYYY-MM-DD}-email.json` — the cloud-finalized state (`this_week` + `last_week` + `graphs`).

## Process

### 1. Resolve paths

Bash/Glob only — no LLM thinking required. From the CWD, determine:
- `dated_folder` (today's `YYYY-MM-DD/`)
- `prev_dated_folder` (most recent prior dated folder)
- `current_xer` (newest `*.xer` in `dated_folder`)
- `prev_xer` (newest `*.xer` in `prev_dated_folder`)
- `schedules_root` (parent of both)

### 2. Lead with the data (parallel)

Fire these in a single turn so they overlap:

- **`weekly_update_review(baseline_xer_path=<prev_xer>, current_xer_path=<current_xer>)`** — the primary data call. One MCP round-trip; bundles activity changes, milestone slip, expected updates, DCMA delta, critical-path changes, gain/loss attribution. Capture the returned `review` dict — everything else in this phase reads from it.
- **`load_project_context(schedules_root)`** — recipients, signer, SmartPM URLs. Stdlib Python; runs locally.
- **Read** `{dated_folder}/meeting-transcript.md` if present.
- **Load prior state**:

  ```python
  import os, sys
  sys.path.insert(0, 'scheduling/skills/schedule-update/references')
  from email_draft_io import load_draft

  prev_draft = None
  prev_email_json = os.path.join(prev_dated_folder, f'{prev_date}-email.json')
  if os.path.isfile(prev_email_json):
      prev_draft = load_draft(prev_email_json)
  ```

  If the `.json` isn't there, see `_carry_forward.md` "Fallback chain" — last week's PDF / preview HTML / archive markdown can each yield a usable `prev_draft` dict for `build_seed_dict`.

The Worker schema at <https://westland-mcps.westland.workers.dev/westland-forms/weekly-schedule-update-email/schema> is the contract — fetch it any time you're unsure about a field, but it is not required before POST. On 422, refetching the schema is the first step in recovery (§7b).

### 3. Read what came back from `weekly_update_review`

The `review` dict drives both the colleague Q&A (step 4) and the metrics inside `build_seed_dict` (step 5).

If the call raised `MilestoneAmbiguousError` on a phased schedule, call `get_milestones(xer_path=<current_xer>)` to enumerate candidates and re-call `weekly_update_review` with `milestone_id=<resolved_task_id_or_code>`. Multi-terminal schedules without an explicit milestone_id still return — they just degrade `dcma_delta` / `critical_path_changes` / `gain_loss_attribution` to `None`.

How each field of the returned dict feeds `build_seed_dict`:

| `review[...]` field | Feeds |
|---|---|
| `milestone_slip.sc_date_new` | `projected_completion_iso` |
| `milestone_slip.sc_slip_days` | `abs(...)` → `gain_loss_value`; sign → `gain_loss_direction` (`'loss'` if positive slip, `'gain'` if negative or zero) |
| days between `milestone_slip.sc_date_new` and `ctx['contractual_completion']` | `days_metric_value` + `days_metric_direction` |
| `activity_changes.status_changes` (filter `new == TK_Complete`) | candidate rows for `successes_html` |
| `activity_changes.added_tasks` / `removed_tasks` / `changed_durations` | narrative input for `logic_changes` |
| `critical_path_changes` (when non-`None`) | narrative for `logic_changes` |
| `gain_loss_attribution` (when non-`None`) | narrative for `gain_loss_narrative` |
| `activities_to_start` / `activities_to_finish` | trade-specific Q&A when colleague asks |

The single-purpose comparison tools (`compare_milestone_slip`, `compare_activity_changes`, `compare_date_slips`) remain available for cases where you need just one slice — but for the weekly flow, `weekly_update_review` is faster and richer.

If `ToolSearch select:weekly_update_review` returns nothing, invoke the `westland-scheduler-mcp-troubleshoot` skill — do not fall back to reading `schedule-toolbox/lib/*.py` (the PreToolUse hook blocks it).

### 4. Gather narrative content (transcript or Q&A)

If a transcript is present, mine it for:
- Specific successes the team called out
- Red flags / risks raised
- Stalled tasks
- Key items for the coming week
- EOT/recovery updates
- Logic-change narrative

Otherwise drive the conversation from the XER deltas using the Q&A pattern in `report.md` step 2.

Each list item is one HTML string. `<div>plain text</div>` works. The four supported inline tags pass through verbatim into the email body:
- `<b>...</b>` — bold
- `<i>...</i>` — italic
- `<span style="background-color: #FFF4B8">...</span>` — yellow highlight
- `<span style="color: #9B2C2C">...</span>` — Westland brand red

### 5. Build the seed via `build_seed_dict`

One call. The helper applies carry-forward, defaults every optional field, validates required project-context fields, and returns a v2 seed shaped to the Worker schema.

```python
sys.path.insert(0, 'scheduling/skills/schedule-update/references')
from build_seed import build_seed_dict

seed = build_seed_dict(
    ctx=ctx,
    prev_draft=prev_draft,
    today_iso=today_iso,
    projected_completion_iso=sc_date_new,           # from compare_milestone_slip
    days_metric_value=days_vs_contract_abs,         # int >= 0
    days_metric_direction='behind' or 'ahead',
    gain_loss_value=abs(sc_slip_days),
    gain_loss_direction='loss' if sc_slip_days > 0 else 'gain',
    gain_loss_narrative=gain_loss_html,             # one-paragraph HTML
    eot_recovery=eot_recovery_html,
    logic_changes=logic_changes_html,
    successes_html=successes_list,
    red_flags_html=red_flags_list,
    stalled_tasks_html=stalled_list,
    key_items_html=key_items_list,
    fresh_filenames=attachment_basenames,           # globbed from dated_folder
    changes_report_filename=changes_report_pdf_basename_or_None,
    include_changes_report=True,
)
```

`build_seed_dict` handles internally:

- Carry-forward of `successes` / `red_flags` / `stalled_tasks` via `reconcile_items`
- Carry-forward of `key_items` + the archived sibling via `reconcile_key_items`
- Attachment transitions including per-row `procore` toggle preservation via `transition_attachments`
- Defaults for `closing_paragraphs`, `closing_salutation`, `graph_order` when prev_draft is missing them
- Required-field checks on `ctx` (raises `SeedBuildError` naming the missing field)
- Enum validation on the two `direction` discriminators (raises `ValueError`)

If you need to inspect or extend the helper, see [references/build_seed.py](../references/build_seed.py). Update it there when the schema changes — do not band-aid in callers.

### 6. Write the seed to disk

```python
import json
with open(os.path.join(dated_folder, f'{today_iso}-email.seed.json'), 'w') as f:
    json.dump(seed, f, indent=2)
```

Refresh in §9 re-uses this file unchanged.

### 7. POST to the cloud editor

```text
generate_weekly_schedule_update_email_draft(
    project=ctx['job_number'],
    report_date=today_iso,
    seed_json=<the seed dict>,
)
```

Returns `{editor_url, expires_at, graphs_ready_count, graphs_total, smartpm_import_status}`.

### 7b. On 422 — refetch schema, fix, re-POST

The Worker rejects with `{ violations: [{ code, field, fuzzyHint? }] }`. Recovery is mechanical:

1. `WebFetch https://westland-mcps.westland.workers.dev/westland-forms/weekly-schedule-update-email/schema.json` — your local prose paraphrase may have drifted; the live schema has not.
2. Locate the violation's `field` path in your seed dict.
3. Apply the violation's fix:

| Violation code | Fix |
|---|---|
| `SEED_VERSION_TOO_OLD` | Means a caller bypassed `build_seed_dict`. Use the helper. |
| `MISSING_REQUIRED_FIELD` | Add the field per the schema's type at that path. If the field belongs in `build_seed_dict`'s output and isn't there, that's a helper bug. |
| `INVALID_ENUM_VALUE` | Coerce to the closest allowed value. `fuzzyHint` may suggest one. |
| `INVALID_RECIPIENT_ARRAY` | Ensure `to_recipients` is non-empty and each row has a non-empty `email`. |
| `INVALID_GRAPH_ORDER` | Restore from `build_seed.CANONICAL_GRAPH_ORDER`. |

4. Re-POST.

If you hit the same violation twice in one session, `build_seed_dict` is missing a required field. Stop, surface the gap to the user, and update the helper — don't keep patching the seed in place.

### 8. Hand the URL to the colleague

Print the editor URL clearly. Tell them:
- Click to open in their browser.
- Edits autosave; no Save button.
- If `smartpm_import_status == 'processing'`, graphs are placeholders right now — they can start editing the narrative; the editor's Refresh button updates the graphs in place once SmartPM finishes (~20 min after XER upload).
- When done editing, come back and say "done" (or equivalent — the next phase polls status).

### 9. (Optional, on colleague request) Refresh graphs

If the colleague asks Claude to refresh — typically because SmartPM was still processing at generate time — call `generate_weekly_schedule_update_email_draft` again with the **same seed** loaded from disk. The Worker preserves the editorial layer server-side and only refreshes `graphs`.

```python
seed = json.load(open(os.path.join(dated_folder, f'{today_iso}-email.seed.json')))
generate_weekly_schedule_update_email_draft(
    project=ctx['job_number'],
    report_date=today_iso,
    seed_json=seed,
)
```

The colleague's open browser tab keeps working; autosaves continue against the same `(project, report_date)` key. The editor's Refresh button does this server-side without a round-trip through Claude — the Claude-driven path is the fallback when the URL has expired.

### 10. Wait for the colleague to finish

When the colleague says "done" (or equivalent), optionally call `get_weekly_schedule_update_email_status` to verify `status == 'editing'` and `last_edited_at` is recent.

### 11. Finalize

```python
result = finalize_weekly_schedule_update_email(
    project=ctx['job_number'],
    report_date=today_iso,
)
with open(os.path.join(dated_folder, f'{today_iso}-email.json'), 'w') as f:
    json.dump(result['working_json'], f, indent=2)
```

If `result['graphs_ready_count'] < result['graphs_total']`, some chart cards are placeholders or errored — warn the colleague before building the .eml. They can choose to ship with placeholders (rare) or wait + re-finalize.

### 12. Build the .eml

Before building, **re-read `phases/_render_graphs.md`** — the stacked-PNG rasterization recipe lives there. Then:

```python
from email_draft_io import generate_email_from_draft

eml_path = generate_email_from_draft(
    draft_path=os.path.join(dated_folder, f'{today_iso}-email.json'),
    output_eml_path=os.path.join(dated_folder, f'{today_iso}-update-email.eml'),
    dated_folder=dated_folder,
    smartpm_project_url=ctx.get('smartpm_url', ''),
    smartpm_trends_url=ctx.get('smartpm_trends_url', ''),
)
```

`generate_email_from_draft` internally loads the v2 draft, stacks `graphs.{slug}.html` chunks in `graph_order`, rasterizes to one PNG via `html_to_png.cjs`, resolves attachment basenames against `dated_folder`, flattens `this_week` → builder kwargs via `editorial_to_kwargs`, and writes the .eml.

## What this phase explicitly does NOT do

- Build the seed by hand. Use `build_seed_dict`.
- Re-run the three XER comparison tools after step 3.
- Upload to Procore (that's `phases/procore.md` — and it reads `{YYYY-MM-DD}-email.json` directly for `skip_procore` + `attachments[].procore`).
- Render per-slug chart PNGs. One stacked PNG holds everything (see `_render_graphs.md`).

## Cross-references

- Helper: [references/build_seed.py](../references/build_seed.py) — single source of truth for seed construction.
- Schema: <https://westland-mcps.westland.workers.dev/westland-forms/weekly-schedule-update-email/schema> (and `.json` for machine consumption).
- Shape paraphrase for humans: [scheduling/CLAUDE.md → Email JSON shape](../../../CLAUDE.md).
- The MCP tools and HTTP routes: docs/superpowers/specs/2026-05-21-weekly-email-cloud-editor-design.md.
- Chart renderer the Worker uses: docs/superpowers/specs/2026-05-22-html-svg-chart-migration-javascript-design.md.
