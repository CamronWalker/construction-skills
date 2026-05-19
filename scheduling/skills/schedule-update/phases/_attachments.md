# _attachments — shared attachment data model

> **Internal reference** (underscore-prefix). Not invoked directly; loaded by `email.md`, `report.md`, `draft.md`, and `procore.md` per the router command matrix.

## Per-attachment dict shape

```python
{
    'filename': str,
    'checked': bool,                 # included in email
    'status': 'active' | 'new' | 'removed' | 'archived',
    'date_archived': str,            # 'YYYY-MM-DD' or ''
    'share_to_procore': bool,        # included in Procore Documents upload (the folder is public)
}
```

This dict shape is what `parse_email_html.parse_preview_html()` returns inside the top-level `'attachments'` list, and what `generate_email_preview_html.generate_preview_html()` expects in its `attachments=` kwarg.

## Top-level keys also relevant

```python
parsed = parse_preview_html(preview_path)
parsed['attachments']        # list of dicts as above
parsed['attachment_names']   # filtered: filename strings, checked & non-archived only
parsed['attachment_paths']   # filtered: absolute paths, checked & non-archived only
parsed['skip_procore']       # bool — master "skip Procore this week" toggle
```

## Carry-forward rules

`carry_forward.transition_attachments(last_week_attachments, fresh_filenames, today_iso)` returns a list of dicts in the shape above. Two Procore-specific rules:

- **Preserve:** for any file that matches an attachment from last week (date-stripped fuzzy name match), `share_to_procore` is propagated verbatim from the prior week's dict. The user's previous decision survives the week boundary.
- **Bootstrap (new attachments only):** for genuinely new files (no last-week match), `share_to_procore` defaults per pattern:
  - `True` when the filename matches `View` (case-insensitive) OR matches `Update Request*.xlsm` (case-insensitive).
  - `False` otherwise.
- **Rationale:** the Procore folder is public. New, unfamiliar files require an explicit opt-in via the preview's `P` checkbox.

## HTML representation (preview)

Each `<li class="attachment-item">` carries:

```html
<li class="attachment-item"
    data-checked="true|false"
    data-status="active|new|removed|archived"
    data-share-procore="true|false"
    data-archived="YYYY-MM-DD">          <!-- only when archived -->
  <span class="drag-handle">⋮⋮</span>
  <label class="attach-toggle" title="Include in email">
    <input type="checkbox" data-item-checked checked|unchecked>
  </label>
  <label class="attach-procore-toggle" title="Share to Procore">
    <input type="checkbox" data-procore-checked checked|unchecked>
    <span class="procore-badge">P</span>
  </label>
  <!-- attachment name, controls, etc. -->
</li>
```

The master skip-Procore toggle sits inside `.attachments-section`:

```html
<div class="skip-procore-option" data-field="skip_procore_option">
  <label class="skip-procore-toggle">
    <input type="checkbox" data-field="skip_procore">
    <span class="skip-procore-label">⏭ Skip Procore this week</span>
  </label>
</div>
```

## What to call, from each phase

| Phase | Reads | Writes |
|---|---|---|
| `email.md` (Camron path) | last week's preview parser for carry-forward + bootstrap | this week's preview via generator |
| `report.md` | same as email.md | same |
| `draft.md` | this week's preview parser (filtered lists for the `.eml`) | `.eml` file |
| `procore.md` | this week's preview parser (`share_to_procore` filter for Procore uploads) | nothing (Procore-side via MCP) |

## Do NOT

- Do NOT `Read` `parse_email_html.py` or `generate_email_preview_html.py` to learn the shape. This file is the canonical reference.
- Do NOT `Read` / `Edit` the preview HTML directly. Always parse → mutate dict → generate.
