# Scheduling Plugin — Instructions for Claude

Plugin-level guidance that applies to every skill under `scheduling/skills/`. The repo-root [CLAUDE.md](../CLAUDE.md) covers cross-plugin release conventions; this file is for scheduling-specific contracts.

## Email-preview JSON shape — single source of truth

The weekly schedule email pipeline (`schedule-update` skill) round-trips through one HTML artifact: `{YYYY-MM-DD}-email-preview.html`. Three places handle that HTML:

| Direction | Who | File |
|-----------|-----|------|
| Write | Python | [`generate_email_preview_html.py`](skills/schedule-update/references/generate_email_preview_html.py) |
| Read | Python | [`parse_email_html.py`](skills/schedule-update/references/parse_email_html.py) |
| Copy-to-clipboard for Claude | JS `collectFields()` inside the generated HTML | (in `generate_email_preview_html.py`) |

**These three views of the data MUST share one shape.** If they drift, the colleague clicks "Copy for Claude" expecting Claude to apply edits in one pass, and Claude has to re-`Read` the HTML to fill in the gap — wasteful, slow, and error-prone.

### The canonical shape

The shape `parse_email_html.parse_preview_html()` returns is the source of truth. Key fields the colleague edits live and Procore depends on:

```python
{
    'project_info': {...},
    'days_behind': int, 'gain_loss': int,
    'successes': [{'text', 'checked', 'status', 'date_archived'}, ...],
    'red_flags': [...], 'stalled_tasks': [...], 'key_items': [...],
    'gain_loss_narrative': str, 'eot_recovery': str, 'logic_changes': str,
    'smartpm_changelog_url': str,
    'custom_paragraphs': [{'label', 'text', 'checked'}, ...],
    'attachments': [
        {
            'filename':         str,
            'checked':          bool,   # include in this email
            'status':           str,    # 'active' | 'new' | 'archived'
            'date_archived':    str,
            'share_to_procore': bool,   # the P toggle — picks Procore upload set
        },
        ...
    ],
    'changes_report': {'include': bool, 'filename': str},
    'skip_procore':              bool,  # master "skip Procore this week" toggle
    'summary_screenshot_rel':    str,
    'graph_screenshot_rels':     [str, ...],
    'signer_name': str, 'signer_title': str, 'signer_mobile': str,
}
```

### The Procore fields are load-bearing

`attachments[].share_to_procore` and top-level `skip_procore` drive the Procore Documents upload via [`phases/procore.md`](skills/schedule-update/phases/procore.md). They are not cosmetic. Missing them in the JSON snapshot means the colleague's choice ("don't upload the owner summary to a public folder") is lost — that's a privacy bug, not a UX nit.

### When you change the shape

If you add, rename, or change the semantics of any field in this shape:

1. **Update all three views in the same commit:**
   - Render — `generate_email_preview_html.py` (the kwarg name + the HTML emission + the `ATTACHMENT_TEMPLATE` literal if it's an attachment field)
   - Parse — `parse_email_html.py` (the extraction + the `result` dict)
   - Copy — the `collectFields()` JS inside `generate_email_preview_html.py` (read directly from the input element, not stale data attributes — see existing pattern for `share_to_procore`)
2. **Add a test** that asserts all three agree: render → parse round-trip + a JS-source assertion that `collectFields()` mentions the field. Both patterns live in [`tests/test_email_preview_html.py`](skills/schedule-update/tests/test_email_preview_html.py) — copy the `test_round_trip_preserves_procore_fields` and `test_copy_for_claude_js_emits_procore_fields` shapes.
3. **Run the unit tests** — `python -m unittest discover -s scheduling/skills/schedule-update/tests` — before claiming done.

A passing round-trip test isn't enough on its own. The JS-source test is what catches the case where the Python sides agree but the colleague's clipboard JSON is missing the field — which is exactly the bug fix that introduced this doc.

### Live event listeners must mirror save-time sync

Editable HTML uses `data-*` attributes on rows (`data-checked`, `data-share-procore`, `data-status`) so CSS can style state without JS hooks. `_syncCheckboxes()` rebuilds those attributes at save time, but the editor also needs them fresh **as the user clicks** for the CSS highlight to track. If you add a new boolean checkbox to a row:

- Add a `change` listener that mirrors the checkbox state onto the row's `data-*` attribute (existing pattern: `data-item-checked` → `data-checked`, `data-procore-checked` → `data-share-procore`)
- Have `collectFields()` read directly from the input (`!!cb.checked`) rather than the data attribute, so a missing listener degrades to "stale CSS" not "stale JSON"

## XER files are immutable

Repeated from the skill files for visibility: never `Edit`, never overwrite-`Write`, never `rm` / `Remove-Item` a `.xer` in any project folder. Westland's PreToolUse hook blocks this physically; if you find yourself wanting to, you've misunderstood the workflow — write a new versioned file (`-v2.xer`, `-v3.xer`) alongside instead, or stop and ask.

## HTML CRUD goes through the parse/generate pair

This is the project-context.html lesson from W1177 applied generally: never `Read` → `Edit` → `Write` an embedded-image-bearing HTML directly. Round-tripping ~17KB base64 logos through tool I/O corrupts them. Use the dedicated parse + generate scripts for every artifact that has one (`generate_email_preview_html.py` / `parse_email_html.py` for the email preview; `generate_project_context_html.py` / `parse_project_context_html.py` for the project context).
