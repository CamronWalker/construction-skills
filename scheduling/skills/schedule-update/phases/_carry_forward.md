# _carry_forward — week-over-week state propagation

> **Internal reference** (underscore-prefix). Loaded by `draft.md` and `report.md`.

## Function signatures (inline)

```python
# carry_forward.transition_items(last_week_items, new_texts=None,
#                                today_iso=None, max_archived_days=90)
#     -> list of {text, checked, status, date_archived}
#
# Apply git-diff state transitions to list items (red_flags, successes,
# stalled_tasks, key_items). 90-day prune drops stale archives.

# carry_forward.transition_attachments(last_week_attachments,
#                                      fresh_filenames=None,
#                                      today_iso=None, max_archived_days=90)
#     -> list of {filename, checked, status, date_archived, share_to_procore}
#
# Date-stripped fuzzy match against last week. Preserves share_to_procore
# verbatim. Bootstrap rule for new attachments: True for *View* / *Update
# Request*.xlsm, False otherwise. See _attachments.md for details.

# carry_forward.reconcile_items(last_week_items, this_week_texts,
#                               today_iso=None, similarity_threshold=0.6,
#                               max_archived_days=90)
#     -> list of {text, previous_text, status, checked, date_archived}
#
# Fuzzy-matches this week's plain-text list against last week's tracked items.
# Use this when Claude has freshly-generated text and needs to reconcile
# against last week's history.
```

## Last week's draft — what to pull

Find last week's dated folder and load its finalized `email-draft.json`:

```python
import os
import sys
sys.path.insert(0, 'scheduling/skills/schedule-update/references')
from email_draft_io import load_draft

prev_date_folder = most_recent_sibling_dated_folder(schedules_root)  # skip today
prev_draft_path = os.path.join(prev_date_folder, 'email-draft.json')

if os.path.isfile(prev_draft_path):
    last_draft = load_draft(prev_draft_path)
    last = last_draft['editorial']
else:
    last = None
```

If no prior `email-draft.json` exists, see "Legacy fallback" below. If neither exists, treat as "first update" and skip carry-forward.

Because the JSON shape mirrors the canonical parse-preview-html output (per scheduling/CLAUDE.md "Email-preview JSON shape — single source of truth"), the dict-of-dicts list shapes are already in place — there is no `_full` suffix on JSON fields; the lists are dicts to begin with.

Pull the carry-forward values from `last`:

| Field on `last` (editorial dict) | Pass to seed as | Purpose |
|---|---|---|
| `last['days_behind']`, `last['gain_loss']` | `previous_days_behind=`, `previous_gain_loss=` | week-over-week strikethrough on the metric lines |
| `last['gain_loss_narrative']`, `last['eot_recovery']`, `last['logic_changes']` | `previous_narratives=` dict | inline narrative diff |
| `last['successes']`, `last['red_flags']`, `last['stalled_tasks']`, `last['key_items']` | through `transition_items()` or `reconcile_items()` | per-item state transitions |
| `last['attachments']` | through `transition_attachments()` | file carry-forward + Procore preservation |
| `last['custom_paragraphs']` | `custom_paragraphs=` verbatim | closing paragraphs (no diff semantics) |
| `last['changes_report']['include']` | `include_changes_report=` default | changelog PDF toggle |
| `last['skip_procore']` | `skip_procore=` default | inherit master Procore-skip toggle |

## Reconciliation recipe

For list items (red_flags / successes / stalled_tasks / key_items):

```python
from carry_forward import reconcile_items
red_flags_new = reconcile_items(
    last['red_flags'],
    this_week_red_flag_texts,   # plain strings Claude wrote
    today_iso=today_iso,
)
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

The reconciled lists go into the seed JSON that `phases/draft.md` passes to the `generate_weekly_email_draft` MCP tool. Build the seed's `editorial` dict from `last` + this week's deltas:

```python
seed_editorial = {
    **last,  # carry forward everything by default
    'subject':       this_week_subject,        # date-stamped
    'days_behind':   this_week_days_behind,
    'gain_loss':     this_week_gain_loss,
    'gain_loss_narrative': this_week_narratives['gain_loss_narrative'],
    'eot_recovery':        this_week_narratives['eot_recovery'],
    'logic_changes':       this_week_narratives['logic_changes'],
    'successes':     successes_new,
    'red_flags':     red_flags_new,
    'stalled_tasks': stalled_new,
    'key_items':     key_items_new,
    'attachments':   attachments_new,
}
```

The seed shape is the same canonical editorial shape; the MCP tool persists it server-side and emits a browser editor URL. No more `generate_email_preview_html()` call — the cloud editor IS the new render+parse surface.

## Changed narrative fields

Diff each narrative against last week's value (trim + case-insensitive compare). The cloud editor highlights changed fields in green on the browser side; here in Claude's seed-synthesis step the diff is for awareness only — the editor doesn't take a `changed_narrative_fields` kwarg:

```python
changed_narrative_fields = set()
for field in ('gain_loss_narrative', 'eot_recovery', 'logic_changes'):
    if (this_week[field] or '').strip().lower() != (last[field] or '').strip().lower():
        changed_narrative_fields.add(field)
```

## Legacy fallback — last week predates the cloud-editor flow

For the first run after this branch merges (and any project where the previous week was on the old preview-HTML flow), `email-draft.json` won't exist yet. Fall back to parsing last week's preview HTML:

```python
prev_preview = os.path.join(prev_date_folder, f'{PREV_DATE}-email-preview.html')
if os.path.isfile(prev_preview):
    from parse_email_html import parse_preview_html
    last = parse_preview_html(prev_preview)
    # Note: parse_preview_html returns _full suffixed dicts (successes_full,
    # red_flags_full, etc.) — map them back to the canonical names before
    # using the carry-forward table above:
    last['successes']     = last.pop('successes_full',     last.get('successes',     []))
    last['red_flags']     = last.pop('red_flags_full',     last.get('red_flags',     []))
    last['stalled_tasks'] = last.pop('stalled_tasks_full', last.get('stalled_tasks', []))
    last['key_items']     = last.pop('key_items_full',     last.get('key_items',     []))
```

This fallback path only applies for the transition week. Once a project has a finalized `email-draft.json` from the new flow, that is the canonical input forever after.

## On save — phantom diff handling

The cloud editor stores plain-text editorial fields (no `<ins>` / `<del>` markup). The legacy parse_preview_html path already drops `<del>` content and unwraps `<ins>` content, so the markdown archive and the `.eml` body never carry diff markup. Nothing for you to do here.
