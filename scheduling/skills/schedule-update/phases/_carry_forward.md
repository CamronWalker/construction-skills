# _carry_forward — week-over-week state propagation

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `_carry_forward` phase; any divergence from it is a bug.
> **Internal reference** (underscore-prefix). Loaded by `draft.md` and `report.md` (called as an internal dependency from another phase).

## Function signatures (inline)

```python
# carry_forward.reconcile_items(last_week_items, this_week_texts,
#                               today_iso=None, similarity_threshold=0.6)
#     -> (this_week_rows, last_week_baseline)
#
# v2: rows are {text, status, checked, edited(optional), prev_idx}.
# No date_archived. Status lifecycle: active → removed → dropped (no
# archived pile in these four lists).

# carry_forward.reconcile_key_items(last_week_key_items,
#                                   last_week_key_items_archived,
#                                   this_week_texts, today_iso=None,
#                                   similarity_threshold=0.6,
#                                   max_archived_days=90)
#     -> (this_week_rows, this_week_archived_rows, last_week_baseline)
#
# v2-only: key_items has a sibling key_items_archived list. Lifecycle
# active → removed → archived (1 week later) → archived for 90 days →
# dropped. Resurrection counts as 'new'.

# carry_forward.transition_attachments(last_week_attachments,
#                                      fresh_filenames=None,
#                                      today_iso=None)
#     -> list of {name, ext(optional), checked, procore, status, prev_idx}
#
# v2: name (not filename), procore (not share_to_procore), optional ext.
# No date_archived; no archived state. Lifecycle is
# active → removed → dropped.
```

## Last week's draft — what to pull

Find last week's dated folder and load its finalized `{prev_date}-email.json`:

```python
import os
import sys
sys.path.insert(0, 'scheduling/skills/schedule-update/references')
from email_draft_io import load_draft

prev_date_folder = most_recent_sibling_dated_folder(schedules_root)  # skip today
prev_draft_path = os.path.join(prev_date_folder, f'{prev_date}-email.json')

if os.path.isfile(prev_draft_path):
    last_draft = load_draft(prev_draft_path)
    last = last_draft['this_week']
else:
    last = None
```

If no prior `{prev_date}-email.json` exists, treat as "first update" and skip carry-forward — `last_week` in the new seed becomes `null`.

The top-level JSON shape is canonical in scheduling/CLAUDE.md "Email JSON shape — single source of truth". Inside `this_week`, list items are dicts (`{text, checked, status, date_archived, prev_idx}`) and item `text` is HTML.

Pull the carry-forward values from `last`:

| Field on `last` (this_week dict) | Pass to seed as | Purpose |
|---|---|---|
| `last['days_metric']`, `last['gain_loss']` | seed.last_week.days_metric / .gain_loss verbatim | week-over-week strikethrough on the metric lines |
| `last['gain_loss']['narrative']`, `last['eot_recovery']`, `last['logic_changes']` | seed.last_week.<field> | inline narrative diff in the editor |
| `last['successes']`, `last['red_flags']`, `last['stalled_tasks']` | through `reconcile_items()` → seed.this_week.<list> + seed.last_week.<list> | per-item state transitions + prev_idx |
| `last['key_items']`, `last['key_items_archived']` | through `reconcile_key_items()` → seed.this_week.key_items + seed.this_week.key_items_archived + seed.last_week.key_items | key_items + archived sibling reconciliation |
| `last['attachments']` | through `transition_attachments()` → seed.this_week.attachments | file carry-forward + procore preservation |
| `last['closing_paragraphs']` | seed.this_week.closing_paragraphs verbatim | closing paragraphs (no diff semantics) |
| `last['include_changes_report']`, `last['changes_report_filename']` | seed.this_week.include_changes_report / .changes_report_filename default | changelog PDF toggle |
| `last['skip_procore']` | seed.this_week.skip_procore default | inherit master Procore-skip toggle |
| `last['closing_salutation']` | seed.this_week.closing_salutation default | preserve colleague's last edit |

## Reconciliation recipe

For list items (red_flags / successes / stalled_tasks):

```python
from carry_forward import reconcile_items

red_flags_this_week, red_flags_last_week = reconcile_items(
    last['red_flags'],
    this_week_red_flag_html_strings,
    today_iso=today_iso,
)
```

For key_items (note the two-input + three-output signature):

```python
from carry_forward import reconcile_key_items

key_items_rows, key_items_archived_rows, key_items_baseline = reconcile_key_items(
    last['key_items'],
    last['key_items_archived'],
    this_week_key_item_html_strings,
    today_iso=today_iso,
)
# Use:
#   key_items_rows           → seed.this_week.key_items
#   key_items_archived_rows  → seed.this_week.key_items_archived
#   key_items_baseline       → seed.last_week.key_items (active only)
```

For attachments:

```python
import glob, os
from carry_forward import transition_attachments

fresh = []
for ext in ('*.pdf', '*.xlsm', '*.xer'):
    fresh.extend(
        os.path.basename(p) for p in glob.glob(os.path.join(dated_folder, ext))
        if not os.path.basename(p).startswith('~$')  # skip Office lock files
    )
attachments_new = transition_attachments(
    last['attachments'], fresh, today_iso=today_iso,
)
```

## Pass into the cloud-editor seed

The reconciled lists go into the seed JSON that `phases/draft.md` passes to the `generate_weekly_schedule_update_email_draft` MCP tool. See `phases/draft.md` § "Assemble the seed" for the full shape — the short version: every editorial field lives under `this_week`, `last_week` is a frozen copy of the prior week's `this_week`, and the Worker fills in `graphs`.

```python
seed_this_week = {
    **last,
    'subject':       this_week_subject,
    'days_metric':   {'direction': 'behind' if days_behind_int >= 0 else 'ahead',
                      'value': abs(days_behind_int)},
    'gain_loss':     {'direction': 'gain' if gl_int >= 0 else 'loss',
                      'value': abs(gl_int),
                      'narrative': this_week_narratives['gain_loss_narrative'],
                      'narrative_changed': narrative_changed_flag},
    'eot_recovery':        this_week_narratives['eot_recovery'],
    'logic_changes':       this_week_narratives['logic_changes'],
    'successes':           successes_this_week,
    'red_flags':           red_flags_this_week,
    'stalled_tasks':       stalled_this_week,
    'key_items':           key_items_rows,
    'key_items_archived':  key_items_archived_rows,
    'attachments':         attachments_new,
}
```

`last_week` in the seed is the prior week's `this_week` verbatim — the cloud editor uses it for diff overlays and the .eml builder reads `last_week.days_behind` / `last_week.gain_loss` for strikethrough-previous-metric badges.

## Changed narrative fields

Diff each narrative against last week's value (trim + case-insensitive compare). The cloud editor highlights changed fields in green on the browser side via the seed's `last_week` block — here in Claude's seed-synthesis step the diff is for awareness only:

```python
changed_narrative_fields = set()
prev_gl_narrative = ((last.get('gain_loss') or {}).get('narrative') or '').strip().lower()
this_gl_narrative = (this_week_narratives['gain_loss_narrative'] or '').strip().lower()
if prev_gl_narrative != this_gl_narrative:
    changed_narrative_fields.add('gain_loss_narrative')
for field in ('eot_recovery', 'logic_changes'):
    if (this_week_narratives[field] or '').strip().lower() != (last.get(field) or '').strip().lower():
        changed_narrative_fields.add(field)
```

## On save — phantom diff handling

The cloud editor stores HTML-typed editorial fields with no `<ins>` / `<del>` markup. Nothing for you to do here.
