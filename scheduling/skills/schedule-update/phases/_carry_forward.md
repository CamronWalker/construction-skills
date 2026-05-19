# _carry_forward — week-over-week state propagation

> **Internal reference** (underscore-prefix). Loaded by `email.md` and `report.md`.

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

## Last week's preview — what to pull

Find last week's preview file:

```
prev_date_folder = most_recent_sibling_dated_folder(schedules_root)  # skip today
prev_preview = '{prev_date_folder}/{PREV_DATE}-email-preview.html'
```

If no prior preview exists, treat as "first update" and skip carry-forward.

Parse it:

```python
import parse_email_html
last = parse_email_html.parse_preview_html(prev_preview)
```

Pull the carry-forward values from `last`:

| Field | Pass to generator as | Purpose |
|---|---|---|
| `last['days_behind']`, `last['gain_loss']` | `previous_days_behind=`, `previous_gain_loss=` | week-over-week strikethrough on the metric lines |
| `last['gain_loss_narrative']`, `last['eot_recovery']`, `last['logic_changes']` | `previous_narratives=` dict | inline narrative diff |
| `last['successes_full']`, `last['red_flags_full']`, `last['stalled_tasks_full']`, `last['key_items_full']` | through `transition_items()` or `reconcile_items()` | per-item state transitions |
| `last['attachments']` | through `transition_attachments()` | file carry-forward + Procore preservation |
| `last['custom_paragraphs']` | `custom_paragraphs=` verbatim | closing paragraphs (no diff semantics) |
| `last['changes_report']['include']` | `include_changes_report=` default | changelog PDF toggle |
| `last['skip_procore']` | `skip_procore=` default | inherit master Procore-skip toggle |

## Reconciliation recipe

For list items (red_flags / successes / stalled_tasks / key_items):

```python
from carry_forward import reconcile_items
red_flags_new = reconcile_items(
    last['red_flags_full'],
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

## Pass into generator

```python
import generate_email_preview_html
generate_email_preview_html.generate_preview_html(
    output_path=this_week_preview_path,
    # ... all the usual kwargs ...
    red_flags=red_flags_new,
    successes=successes_new,
    stalled_tasks=stalled_new,
    key_items=key_items_new,
    attachments=attachments_new,
    custom_paragraphs=last['custom_paragraphs'],
    previous_days_behind=last['days_behind'],
    previous_gain_loss=last['gain_loss'],
    previous_narratives={
        'gain_loss_narrative': last['gain_loss_narrative'],
        'eot_recovery': last['eot_recovery'],
        'logic_changes': last['logic_changes'],
    },
    changed_narrative_fields=changed_field_set,   # see below
    skip_procore=last.get('skip_procore', False),
)
```

## Changed narrative fields

Diff each narrative against last week's value (trim + case-insensitive compare). If changed, add to `changed_narrative_fields` so the generator outlines it in green dashed (visual flag for the reviewer):

```python
changed_narrative_fields = set()
for field in ('gain_loss_narrative', 'eot_recovery', 'logic_changes'):
    if (this_week[field] or '').strip().lower() != (last[field] or '').strip().lower():
        changed_narrative_fields.add(field)
```

## On save — phantom diff handling

The parser already drops `<del>` content and unwraps `<ins>` content, so the markdown archive and the `.eml` body never carry diff markup. Nothing for you to do here — just trust the parser.
