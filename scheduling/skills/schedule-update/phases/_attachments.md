# _attachments — shared attachment data model

> **Phase preamble — on entering this phase, re-read this file in full before any tool call. Do not rely on summarized recall from earlier in the session.** This file is the procedure for the `_attachments` phase; any divergence from it is a bug.
> **Internal reference** (underscore-prefix). Not invoked directly; loaded by `email.md`, `report.md`, `draft.md`, and `procore.md` per the router command matrix (called as an internal dependency from another phase).

> **Most callers don't need this file directly.** `build_seed_dict` in [references/build_seed.py](../references/build_seed.py) calls `transition_attachments` and applies the Procore bootstrap rule internally. This file is reference material for the `procore` phase (which reads attachments from the finalized JSON) and for anyone extending the helper.

> The Worker schema at <https://westland-mcps.westland.workers.dev/westland-forms/weekly-schedule-update-email/schema> is the contract for the attachment row shape.

## Per-attachment dict shape (v2)

```python
{
    'name':     str,             # basename
    'ext':      str,             # OPTIONAL; lowercase, no dot
    'checked':  bool,            # include in email
    'procore':  bool,            # the P toggle — Procore Documents upload
    'status':   'active' | 'new' | 'removed',
    'prev_idx': int | None,
}
```

No `archived` status, no `date_archived` field. Lifecycle is
active → removed → dropped.

This dict shape is what `email_draft_io.load_draft(path)` returns inside `draft['this_week']['attachments']`, and what `carry_forward.transition_attachments()` returns to feed into the seed.

## Top-level keys also relevant

```python
draft = load_draft(dated_folder + f'/{report_date}-email.json')
draft['this_week']['attachments']     # list of dicts as above
draft['this_week']['skip_procore']    # bool — master "skip Procore this week" toggle
```

Filtering for the .eml builder (`checked=True` and `status != 'removed'`) happens inside `email_draft_io.editorial_to_kwargs`; the procore phase reads the raw `this_week.attachments` list and walks `procore` directly.

## Carry-forward rules

`carry_forward.transition_attachments(last_week_attachments, fresh_filenames, today_iso)` returns a list of dicts in the shape above. Two Procore-specific rules:

- **Preserve:** for any file that matches an attachment from last week (date-stripped fuzzy name match), `procore` is propagated verbatim from the prior week's dict. The user's previous decision survives the week boundary.
- **Bootstrap (new attachments only):** for genuinely new files (no last-week match), `procore` defaults per pattern:
  - `True` when the filename matches `View` (case-insensitive) OR matches `Update Request*.xlsm` (case-insensitive).
  - `False` otherwise.
- **Rationale:** the Procore folder is public. New, unfamiliar files require an explicit opt-in via the preview's `P` checkbox.

## Browser representation (cloud editor)

The cloud editor SPA renders each attachment row with a drag handle, an "include in email" checkbox, a `P` Procore toggle, and the filename. The Procore badge and master "Skip Procore this week" switch persist via the editor's autosave (`PUT /editorial`). The local skill does not own this HTML — it lives in the `westland-mcps` Worker.

## What to call, from each phase

| Phase | Reads | Writes |
|---|---|---|
| `email.md` (Camron path) | last week's `{prev_date}-email.json` for carry-forward + bootstrap | nothing local — seeds the cloud editor |
| `report.md` | same as email.md | same |
| `draft.md` | this week's `{YYYY-MM-DD}-email.json` for filtered lists in the `.eml` | `.eml` file |
| `procore.md` | this week's `{YYYY-MM-DD}-email.json` for the `procore` filter | nothing (Procore-side via MCP) |

## Do NOT

- Do NOT `Read` `email_draft_io.py` to learn the shape. This file is the canonical reference, and the cross-skill source of truth is scheduling/CLAUDE.md "Email JSON shape".
- Do NOT `Read` / `Edit` the JSON directly when you want to mutate it. Use `email_draft_io.load_draft(path)` to read; let the cloud editor handle writes.
