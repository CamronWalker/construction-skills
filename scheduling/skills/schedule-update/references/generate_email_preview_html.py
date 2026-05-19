"""
Generate an editable HTML preview of a Westland schedule update email.

Self-contained HTML file that looks like the final email but with every
section wrapped in contenteditable markers so a human reviewer can edit
directly in a browser. A 'Save Edits' button downloads the edited HTML.
A 'Copy for Claude' button copies a JSON blob to clipboard as fallback.

Per-item cards:
    Each list item (red_flags, successes, etc.) and each attachment is a
    collapsed bullet by default. Clicking into one expands a card below
    the item with: Include checkbox, Bold/Italic/Priority buttons, Up/Down
    reorder, Remove. Unchecked items stay in the list (carry forward to
    next week) but are excluded from the email.

Git-diff states (per item):
    status = "active"   -> normal styling
    status = "new"      -> green ribbon (added this update)
    status = "removed"  -> red ribbon + strikethrough (unchecked this update,
                           was included last update)
    status = "archived" -> collapsed under a caret at the bottom of the list
                           with date_archived shown when expanded. Items that
                           stayed "removed" for more than one update.

Custom closing paragraphs:
    List of {label, text, checked}. Carries forward via parse_email_html.

Attachments:
    List of {filename, checked, status, date_archived}. Initial set is
    populated by the skill from project-context.md's expected_attachments
    globs. Users can + Browse to pick additional files or + Add by name.

WYSIWYG:
    Markdown `**bold**` and `==priority==` still work as shortcuts. The
    parser converts <b>/<strong> -> **...** and priority spans -> ==...==.
"""

import difflib
import html as html_mod
import os
import re

# Westland brand colors (match generate_email_msg.py)
RED = '#C94444'
GREEN = '#3A9E6B'
TEAL = '#0B4F66'
AMBER = '#E6A817'


def _esc(text):
    return html_mod.escape(str(text))


def _md_inline_to_html(text):
    """Convert inline markdown (==highlight== and **bold**) to HTML tags."""
    if not text:
        return ''
    s = _esc(text)
    s = re.sub(
        r'==(.+?)==',
        f'<span class="priority" style="color:{RED};font-weight:bold">\\1</span>',
        s,
        flags=re.DOTALL,
    )
    s = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', s, flags=re.DOTALL)
    return s


def _editable_span(field, value, changed=False):
    ch = ' data-changed="true"' if changed else ''
    return (
        f'<span contenteditable="true" '
        f'data-field="{_esc(field)}"{ch}>{_esc(value)}</span>'
    )


def _editable_block(field, value, tag='div', changed=False):
    ch = ' data-changed="true"' if changed else ''
    return (
        f'<{tag} class="block" contenteditable="true" '
        f'data-field="{_esc(field)}"{ch}>{_md_inline_to_html(value)}</{tag}>'
    )


def _item_fields(item, text_key='text'):
    """Normalize an item (string or dict) to a dict with standard fields."""
    if isinstance(item, dict):
        return {
            'text': item.get(text_key, item.get('text', '')),
            'filename': item.get('filename', ''),
            'checked': bool(item.get('checked', True)),
            'status': item.get('status', 'active'),
            'date_archived': item.get('date_archived', ''),
            'previous_text': item.get('previous_text', ''),
        }
    return {
        'text': str(item),
        'filename': str(item),
        'checked': True,
        'status': 'active',
        'date_archived': '',
        'previous_text': '',
    }


# Word-level regex — keeps punctuation attached to the adjacent word so the
# diff stays readable ("scope." is one token, not "scope" + ".").
_WORD_RE = re.compile(r'\S+|\s+')


def diff_words_html(old_text, new_text):
    """Return HTML showing a word-level diff between old_text and new_text.

    <ins class="diff-ins">X</ins>  = text added in new
    <del class="diff-del">X</del>  = text removed from old
    unchanged text passes through escaped.

    Also honors **bold** and ==priority== markdown in unchanged spans so the
    formatting still renders.
    """
    old_tokens = _WORD_RE.findall(old_text or '')
    new_tokens = _WORD_RE.findall(new_text or '')
    matcher = difflib.SequenceMatcher(a=old_tokens, b=new_tokens, autojunk=False)
    parts = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            parts.append(_md_inline_to_html(''.join(new_tokens[j1:j2])))
        elif op == 'delete':
            parts.append(
                f'<del class="diff-del">{_esc("".join(old_tokens[i1:i2]))}</del>'
            )
        elif op == 'insert':
            parts.append(
                f'<ins class="diff-ins">{_md_inline_to_html("".join(new_tokens[j1:j2]))}</ins>'
            )
        elif op == 'replace':
            parts.append(
                f'<del class="diff-del">{_esc("".join(old_tokens[i1:i2]))}</del>'
                f'<ins class="diff-ins">{_md_inline_to_html("".join(new_tokens[j1:j2])) }</ins>'
            )
    return ''.join(parts)


def _render_list_item(item):
    f = _item_fields(item)
    text = f['text']
    checked = f['checked']
    status = f['status']
    date_archived = f['date_archived']
    previous_text = f['previous_text']
    # An item is "edited" when previous_text is non-empty and differs from text
    edited = bool(previous_text) and previous_text.strip() != text.strip()
    checked_class = 'true' if checked else 'false'
    checked_attr = 'checked' if checked else ''
    archived_attr = (
        f' data-archived="{_esc(date_archived)}"' if date_archived else ''
    )
    edited_attr = ' data-edited="true"' if edited else ''
    previous_attr = (
        f' data-previous-text="{_esc(previous_text)}"' if edited else ''
    )
    # Content: show diff inline if edited, otherwise plain markdown render.
    if edited:
        content_html = diff_words_html(previous_text, text)
    else:
        content_html = _md_inline_to_html(text)
    return (
        f'<li class="list-item" data-checked="{checked_class}" '
        f'data-status="{_esc(status)}"{archived_attr}{edited_attr}{previous_attr}>'
        '<span class="drag-handle" draggable="true" title="Drag to reorder" '
        'aria-label="Drag handle">⋮⋮</span>'
        f'<div class="li-content" contenteditable="true">{content_html}</div>'
        '<div class="li-controls no-print" tabindex="-1">'
        '  <div class="li-status-note">'
        '    <span class="note-new">✨ New this update</span>'
        '    <span class="note-removed">− Removed from this update '
        '      (was included previously; will archive after another update)</span>'
        f'    <span class="note-archived">📁 Archived <span class="archived-date">'
        f'{_esc(date_archived) if date_archived else ""}</span></span>'
        '    <span class="note-edited">✏️ Edited this update — previous: '
        f'<span class="previous-text-note">{_esc(previous_text)}</span></span>'
        '  </div>'
        '  <label class="li-include">'
        f'    <input type="checkbox" data-item-checked {checked_attr}>'
        '    <span>Include in this email</span>'
        '  </label>'
        '  <div class="li-format">'
        '    <button type="button" onmousedown="event.preventDefault()" '
        '      onclick="fmt(\'bold\')" title="Bold (Ctrl+B)"><b>B</b></button>'
        '    <button type="button" onmousedown="event.preventDefault()" '
        '      onclick="fmt(\'italic\')" title="Italic (Ctrl+I)"><i>I</i></button>'
        '    <button type="button" onmousedown="event.preventDefault()" '
        '      onclick="togglePriority()" title="Priority: bold + red (Ctrl+Shift+P)" '
        '      class="priority-btn">!</button>'
        '  </div>'
        '  <div class="li-controls-right">'
        '    <button type="button" onclick="moveListItem(this,-1)" title="Move up">↑</button>'
        '    <button type="button" onclick="moveListItem(this,1)" title="Move down">↓</button>'
        '    <button type="button" onclick="removeListItem(this)" title="Remove" '
        '      class="remove-btn">× Remove</button>'
        '  </div>'
        '</div>'
        '</li>'
    )


def _editable_list(field, items, ordered=True):
    tag = 'ol' if ordered else 'ul'
    items = items or []
    active = [i for i in items if _item_fields(i)['status'] != 'archived']
    archived = [i for i in items if _item_fields(i)['status'] == 'archived']

    out = [
        '<div class="list-wrapper">',
        f'<{tag} class="editable-list" data-field="{_esc(field)}">',
    ]
    for item in active:
        out.append(_render_list_item(item))
    out.append(f'</{tag}>')

    if archived:
        out.append(
            '<button type="button" class="archived-toggle no-print" '
            'onclick="toggleArchived(this)">'
            f'<span class="caret">▶</span> {len(archived)} archived'
            '</button>'
        )
        # Separate sub-list — own numbering, doesn't merge with main list.
        # Parser reads {field}_archived and merges back into {field}.
        out.append(
            f'<{tag} class="editable-list archived-list" '
            f'data-field="{_esc(field)}_archived">'
        )
        for item in archived:
            out.append(_render_list_item(item))
        out.append(f'</{tag}>')

    out.append(
        '<div class="list-controls no-print">'
        '<button type="button" onclick="addListItem(this)" '
        'class="add-btn">+ Add item</button>'
        '</div>'
    )
    out.append('</div>')
    return '\n'.join(out)


def _format_days_value(days_behind):
    if days_behind > 0:
        return RED, 'Days Behind Schedule', f'{days_behind} Days'
    if days_behind < 0:
        return GREEN, 'Days Ahead of Schedule', f'{abs(days_behind)} Days'
    return GREEN, 'Days Ahead/Behind Schedule', 'On Schedule'


def _format_gain_loss_value(gain_loss):
    if gain_loss > 0:
        return GREEN, f'{gain_loss} Day Gain'
    if gain_loss < 0:
        return RED, f'{abs(gain_loss)} Day Loss'
    return GREEN, 'No change since last update.'


def _days_line_html(days_behind, previous_days_behind=None):
    color, label, value = _format_days_value(days_behind)
    prev_html = ''
    if previous_days_behind is not None and previous_days_behind != days_behind:
        # Render last week's value as a small grey strikethrough prefix
        # so the reviewer sees week-over-week movement at a glance.
        _, _, prev_value = _format_days_value(previous_days_behind)
        prev_html = (
            f'<span class="prev-metric" '
            f'data-field="previous_days_behind" '
            f'data-value="{previous_days_behind}" '
            f'style="color:#888; text-decoration:line-through; '
            f'margin-right:0.5em; font-weight:normal;">'
            f'{_esc(prev_value)}</span>'
        )
    return (
        f'<p class="days-line" data-metric="days_behind" '
        f'data-value="{days_behind}">'
        f'<span contenteditable="true" data-field="days_line_label" '
        f'style="color:{TEAL};">{_esc(label)}</span>'
        f'<span style="color:{TEAL};">: </span>'
        f'{prev_html}'
        f'<span contenteditable="true" data-field="days_line_value" '
        f'style="color:{color};">{_esc(value)}</span>'
        f'</p>'
    )


def _gain_loss_line_html(gain_loss, previous_gain_loss=None):
    color, value = _format_gain_loss_value(gain_loss)
    prev_html = ''
    if previous_gain_loss is not None and previous_gain_loss != gain_loss:
        _, prev_value = _format_gain_loss_value(previous_gain_loss)
        prev_html = (
            f'<span class="prev-metric" '
            f'data-field="previous_gain_loss" '
            f'data-value="{previous_gain_loss}" '
            f'style="color:#888; text-decoration:line-through; '
            f'margin-right:0.5em; font-weight:normal;">'
            f'{_esc(prev_value)}</span>'
        )
    return (
        f'<p class="section-label" data-metric="gain_loss" '
        f'data-value="{gain_loss}">'
        'Schedule Gain / Loss Since The Last Update: '
        f'{prev_html}'
        f'<span contenteditable="true" data-field="gain_loss_value" '
        f'style="color:{color};">{_esc(value)}</span>'
        f'</p>'
    )


def _custom_paragraphs_html(paragraphs):
    out = [
        '<div class="custom-paragraphs" data-field="custom_paragraphs">',
        '<h4 class="no-print">Closing Paragraphs</h4>',
        '<p class="section-hint no-print">Toggle each paragraph on/off with its '
        'checkbox, edit label or body in place, and use the buttons to add, '
        'remove, or reorder. Whatever you leave here carries forward to next '
        'week\'s preview.</p>',
        '<div class="custom-paragraph-list">',
    ]
    for p in paragraphs or []:
        out.append(_render_custom_paragraph(p))
    out.append('</div>')
    out.append(
        '<button type="button" class="no-print add-btn" '
        'onclick="addCustomParagraph()">+ Add paragraph</button>'
    )
    out.append('</div>')
    return '\n'.join(out)


def _render_custom_paragraph(p):
    label = p.get('label', '') if isinstance(p, dict) else ''
    text = p.get('text', '') if isinstance(p, dict) else ''
    checked = p.get('checked', True) if isinstance(p, dict) else True
    checked_attr = 'checked' if checked else ''
    return '\n'.join([
        '<div class="custom-paragraph">',
        '  <div class="custom-paragraph-header no-print">',
        '    <span class="drag-handle" draggable="true" title="Drag to reorder" '
        'aria-label="Drag handle">⋮⋮</span>',
        f'    <label class="custom-paragraph-toggle">'
        f'<input type="checkbox" data-field="paragraph_checked" {checked_attr}> '
        f'Include</label>',
        '    <span class="custom-paragraph-label-wrap">'
        '<span class="custom-paragraph-label-prefix">Label:</span> '
        f'<span contenteditable="true" data-field="paragraph_label" '
        f'class="custom-paragraph-label">{_esc(label)}</span></span>',
        '    <div class="paragraph-controls">',
        '      <button type="button" onclick="moveParagraph(this,-1)">↑</button>',
        '      <button type="button" onclick="moveParagraph(this,1)">↓</button>',
        '      <button type="button" onclick="removeCustomParagraph(this)">× Remove</button>',
        '    </div>',
        '  </div>',
        '  <div class="block paragraph-body" contenteditable="true" '
        f'data-field="paragraph_text">{_md_inline_to_html(text)}</div>',
        '</div>',
    ])


def _attachments_html(attachments, changes_report=None, date_label='', skip_procore=False):
    """attachments: list of {filename, checked, status, date_archived} dicts.

    changes_report: optional dict {include: bool, filename: str} controlling
    whether a "Schedule Update Email Changelog" PDF should be attached. The
    skill generates the HTML + converts to PDF at draft time; the preview
    just captures the user's intent (on/off) and preferred filename.

    skip_procore: if True, the master "Skip Procore this week" toggle renders
    checked, suppressing XER import + Documents upload while still sending email.
    """
    items = attachments or []
    active = [a for a in items if _item_fields(a)['status'] != 'archived']
    archived = [a for a in items if _item_fields(a)['status'] == 'archived']

    cr = changes_report or {}
    cr_include = bool(cr.get('include', False))
    # Default filename: "YYYY-MM-DD Schedule Update Email (Change Report).pdf"
    # — explicit "Email" wording + parenthesized "Change Report" so nobody
    # confuses it with a schedule-activity changelog (logic changes, SmartPM
    # changelog, etc.).
    default_name = (
        f'{date_label} Schedule Update Email (Change Report).pdf'
        if date_label else 'Schedule Update Email (Change Report).pdf'
    )
    cr_filename = cr.get('filename', '') or default_name
    cr_checked_attr = 'checked' if cr_include else ''
    skip_procore_attr = 'checked' if skip_procore else ''           # NEW

    out = [
        '<div class="attachments-section" data-field="attachments">',
        '<h4 class="no-print">Attachments</h4>',
        '<p class="section-hint no-print">Files attached to the Outlook draft. '
        'Uncheck the leftmost ☐ to skip from the email. '
        'Tick the <span style="color:#0B4F66;font-weight:bold">P</span> on a row '
        'to publish that file to Procore. The folder is public — only check files '
        'safe to share publicly.</p>',
        # NEW — master skip-Procore toggle (sits BEFORE changes-report-option)
        '<div class="skip-procore-option" data-field="skip_procore_option">',
        '  <label class="skip-procore-toggle">',
        f'    <input type="checkbox" data-field="skip_procore" {skip_procore_attr}>',
        '    <span class="skip-procore-label">⏭ Skip Procore this week</span>',
        '  </label>',
        '  <span class="skip-procore-hint">Suppresses XER import + Documents '
        'upload. Email still sends.</span>',
        '</div>',
        # END NEW
        # Weekly Changes Report option — styled like an attachment row but lives
        # above the list since it's a generated artifact, not a file on disk.
        '<div class="changes-report-option" data-field="changes_report">',
        '  <label class="changes-report-toggle">',
        f'    <input type="checkbox" data-field="include_changes_report" {cr_checked_attr}>',
        '    <span class="changes-report-label">📊 Attach email changelog PDF</span>',
        '  </label>',
        '  <span class="changes-report-filename-wrap">',
        '    <span class="changes-report-filename-prefix">Filename:</span>',
        f'    <input type="text" data-field="changes_report_filename" '
        f'value="{_esc(cr_filename)}" class="changes-report-filename-input">',
        '  </span>',
        '  <span class="changes-report-hint">A printable PDF of this email '
        'showing what changed from last update — new lines in '
        '<span style="color:' + GREEN + '">green</span>, removed lines in '
        '<span style="color:' + RED + '">red</span>, and inline edits with a '
        'word-level diff. Generated at draft time.</span>',
        '</div>',
        '<ul class="attachment-list">',
    ]
    for a in active:
        out.append(_render_attachment_item(a))
    for a in archived:
        out.append(_render_attachment_item(a))
    out.append('</ul>')

    if archived:
        out.append(
            '<button type="button" class="archived-toggle no-print" '
            'onclick="toggleArchivedAttachments(this)">'
            f'<span class="caret">▶</span> {len(archived)} archived'
            '</button>'
        )

    out.append(
        '<div class="attachment-actions no-print">'
        '<input type="file" id="attachment-picker" style="display:none" '
        'multiple onchange="onPickAttachments(event)">'
        '<button type="button" class="add-btn" '
        "onclick=\"document.getElementById('attachment-picker').click()\">"
        '+ Browse files</button> '
        '<button type="button" class="add-btn" '
        'onclick="addAttachmentByName()">+ Add by name</button>'
        '</div>'
        '</div>'
    )
    return '\n'.join(out)


def _render_attachment_item(item):
    f = _item_fields(item)
    filename = f['filename'] or f['text']
    checked = f['checked']
    status = f['status']
    date_archived = f['date_archived']
    share_to_procore = bool(item.get('share_to_procore', False)) if isinstance(item, dict) else False  # NEW
    checked_class = 'true' if checked else 'false'
    checked_attr = 'checked' if checked else ''
    procore_class = 'true' if share_to_procore else 'false'        # NEW
    procore_attr = 'checked' if share_to_procore else ''           # NEW
    archived_attr = (
        f' data-archived="{_esc(date_archived)}"' if date_archived else ''
    )
    return (
        f'<li class="attachment-item" data-checked="{checked_class}" '
        f'data-status="{_esc(status)}" '
        f'data-share-procore="{procore_class}"{archived_attr}>'         # MODIFIED
        '<span class="drag-handle" draggable="true" title="Drag to reorder" '
        'aria-label="Drag handle">⋮⋮</span>'
        '<label class="attach-toggle" title="Include in email">'
        f'<input type="checkbox" data-item-checked {checked_attr}>'
        '</label>'
        '<label class="attach-procore-toggle" title="Share to Procore">'  # NEW
        f'<input type="checkbox" data-procore-checked {procore_attr}>'    # NEW
        '<span class="procore-badge">P</span>'                            # NEW
        '</label>'                                                        # NEW
        '<span class="attachment-status-icon" aria-hidden="true"></span>'
        f'<span class="attachment-name" contenteditable="true" '
        f'data-field="attachment_name">{_esc(filename)}</span>'
        '<span class="attachment-meta">'
        f'  <span class="note-archived">📁 Archived <span class="archived-date">'
        f'{_esc(date_archived)}</span></span>'
        '</span>'
        '<div class="attachment-controls no-print">'
        '  <button type="button" onclick="moveAttachment(this,-1)" title="Up">↑</button>'
        '  <button type="button" onclick="moveAttachment(this,1)" title="Down">↓</button>'
        '  <button type="button" onclick="removeAttachment(this)" title="Remove" '
        '    class="remove-btn">×</button>'
        '</div>'
        '</li>'
    )


def _default_custom_paragraphs(include_compliance, include_procurement):
    return [
        {
            'label': 'Schedule Compliance Report',
            'checked': include_compliance,
            'text': (
                'I have again included the Schedule Compliance Report in excel for your use. '
                'Please note: You will need to verify responsibility for the impacts. '
                'This report should be distributed to the Project Team each week and reviewed '
                'in detail during the OAC. Please include the form with the meeting minutes and '
                'add language to the minutes stating all parties reviewed the Schedule Compliance '
                'Report in detail and acknowledge doing so. If they wish to make any adjustments, '
                'or contest any information included in the report they may do so by responding '
                'to the meeting minutes within 24 hours, or as defined by the contract.'
            ),
        },
        {
            'label': 'Procurement & Progress Update Spreadsheets',
            'checked': include_procurement,
            'text': (
                'I have included the procurement and progress update spreadsheets. '
                'Please use these to fill out all actual dates and confirmed durations '
                'prior to each update. This will significantly reduce the time we spend '
                'updating each week to give us more time to work on recovery planning.'
            ),
        },
    ]


def _build_preview_html(**kw):
    project_info = kw.get('project_info') or {}
    days_behind = kw.get('days_behind', 0)
    gain_loss = kw.get('gain_loss', 0)
    previous_days_behind = kw.get('previous_days_behind')
    previous_gain_loss = kw.get('previous_gain_loss')
    successes = kw.get('successes') or []
    gain_loss_narrative = kw.get('gain_loss_narrative', '')
    eot_recovery = kw.get('eot_recovery', '')
    logic_changes = kw.get('logic_changes', '')
    smartpm_changelog_url = kw.get('smartpm_changelog_url', '')
    red_flags = kw.get('red_flags') or []
    stalled_tasks = kw.get('stalled_tasks') or []
    key_items = kw.get('key_items') or []
    custom_paragraphs = kw.get('custom_paragraphs')
    if custom_paragraphs is None:
        custom_paragraphs = _default_custom_paragraphs(
            kw.get('include_compliance_report', False),
            kw.get('include_procurement_sheets', True),
        )
    attachments = kw.get('attachments') or []
    changes_report = kw.get('changes_report') or None
    date_label = kw.get('date_label', '')
    skip_procore = bool(kw.get('skip_procore', False))             # NEW
    changed_fields = set(kw.get('changed_narrative_fields') or [])
    summary_rel = kw.get('summary_screenshot_rel') or ''
    graph_rels = kw.get('graph_screenshot_rels') or []
    smartpm_project_url = kw.get('smartpm_project_url', '')
    smartpm_trends_url = kw.get('smartpm_trends_url', '')
    signer_name = kw.get('signer_name', '')
    signer_title = kw.get('signer_title', '')
    signer_mobile = kw.get('signer_mobile', '')

    title = (
        f"Schedule Update Preview - "
        f"{project_info.get('project_name', '')} - "
        f"{kw.get('date_label', '')}"
    )

    parts = []
    parts.append('<!DOCTYPE html>')
    parts.append('<html><head><meta charset="utf-8">')
    # Tell Chrome to stop serving the old preview after a regenerate. Without
    # this, "the html file looks the same" reports come in until the user
    # hard-refreshes (Ctrl+F5). Belt + suspenders: the user-facing message
    # also reminds about Ctrl+F5 in case the page is already open.
    parts.append('<meta http-equiv="cache-control" content="no-store">')
    parts.append(f'<title>{_esc(title)}</title>')
    parts.append('<style>')
    parts.append(_css())
    parts.append('</style>')
    parts.append('</head><body>')

    # Floating format toolbar (for narrative blocks; list items have own buttons)
    parts.append(
        '<div id="format-toolbar" class="no-print" style="display:none">'
        '  <button type="button" onmousedown="event.preventDefault()" '
        '    onclick="fmt(\'bold\')" title="Bold (Ctrl+B)"><b>B</b></button>'
        '  <button type="button" onmousedown="event.preventDefault()" '
        '    onclick="fmt(\'italic\')" title="Italic (Ctrl+I)"><i>I</i></button>'
        '  <button type="button" onmousedown="event.preventDefault()" '
        '    onclick="togglePriority()" title="Priority: bold + red (Ctrl+Shift+P)" '
        '    class="priority-btn">!</button>'
        '  <span class="toolbar-sep">|</span>'
        '  <span class="toolbar-context" id="toolbar-context">Formatting</span>'
        '</div>'
    )

    parts.append(
        '<div class="toolbar no-print">'
        '<button type="button" onclick="saveEdits()">💾 Save Edits (download)</button>'
        '<button type="button" onclick="copyForClaude()">📋 Copy for Claude</button>'
        '<span class="toolbar-hint">Edit any dashed field. '
        'When done → Save Edits → overwrite this file → tell Claude "done".</span>'
        '</div>'
    )
    parts.append(
        '<div class="instructions no-print">'
        '<strong>Editing:</strong> click into a list item to expand its card '
        '(Include checkbox, <b>B</b>/<i>I</i>/<span style="color:' + RED +
        ';font-weight:bold">!</span>, reorder, remove). '
        'Unchecked items stay in the list (carry to next week) but are '
        'excluded from this email. '
        '<span style="color:' + GREEN + '">Green</span> = new this update, '
        '<span style="color:' + RED + '">red</span> = removed this update, '
        'archived (dropped for >1 update) collapses under a caret.'
        '</div>'
    )

    # --- Email body ---
    parts.append('<div class="email-body">')

    # Section 1: Project info
    labels = [
        ('Project', 'project_name'),
        ('Job Number', 'job_number'),
        ('Contractual Completion Date', 'contractual_completion'),
        ('Projected Substantial Completion Date', 'projected_completion'),
    ]
    parts.append('<p class="info-block">')
    for label, key in labels:
        parts.append(
            f'<span class="info-label">{_esc(label)}:</span> '
            f'{_editable_span(key, project_info.get(key, ""))}<br>'
        )
    parts.append('</p>')

    # Section 2: Days behind/ahead
    parts.append(_days_line_html(days_behind, previous_days_behind))

    # Section 3: Summary screenshot
    if summary_rel:
        img_tag = (
            f'<img src="{_esc(summary_rel)}" alt="SmartPM Summary Report" '
            f'class="summary-img" data-field="summary_screenshot_rel" '
            f'data-src="{_esc(summary_rel)}">'
        )
        if smartpm_project_url:
            parts.append(
                f'<p class="screenshot"><a href="{_esc(smartpm_project_url)}" '
                f'target="_blank">{img_tag}</a></p>'
            )
        else:
            parts.append(f'<p class="screenshot">{img_tag}</p>')
    else:
        parts.append(
            '<p class="screenshot placeholder">'
            '[SmartPM Summary Report screenshot will be embedded here]</p>'
        )

    # Section 4: Successes
    parts.append('<p class="section-label">Successes:</p>')
    parts.append(_editable_list('successes', successes, ordered=False))

    # Section 5: Gain/Loss
    parts.append(_gain_loss_line_html(gain_loss, previous_gain_loss))
    parts.append(_editable_block(
        'gain_loss_narrative', gain_loss_narrative, 'p',
        changed='gain_loss_narrative' in changed_fields,
    ))

    # Section 6: EOT/Recovery
    parts.append('<p class="section-label">Status Of EOT / Recovery Efforts:</p>')
    parts.append(_editable_block(
        'eot_recovery', eot_recovery, 'p',
        changed='eot_recovery' in changed_fields,
    ))

    # Section 7: Logic changes
    parts.append('<p class="section-label">Significant Changes To Schedule Logic:</p>')
    parts.append(_editable_block(
        'logic_changes', logic_changes, 'p',
        changed='logic_changes' in changed_fields,
    ))
    if smartpm_changelog_url:
        parts.append(
            '<p class="email-text">Please refer to the attached Analytics Report, '
            'or review schedule changes in SmartPM for specifics.</p>'
        )
        parts.append(
            f'<p class="email-text"><a href="{_esc(smartpm_changelog_url)}" '
            f'target="_blank" data-field="smartpm_changelog_url">'
            f'{_esc(smartpm_changelog_url)}</a></p>'
        )

    # Section 8: Red Flags
    parts.append('<p class="section-label">Red Flags:</p>')
    parts.append(_editable_list('red_flags', red_flags, ordered=True))

    # Section 9: Stalled/slipping
    parts.append('<p class="section-label">Stalled Or Slipping Tasks:</p>')
    parts.append(_editable_list('stalled_tasks', stalled_tasks, ordered=True))

    # Section 10: Key Items
    parts.append('<p class="section-label">Key Items &amp; Issues To Focus On:</p>')
    parts.append(_editable_list('key_items', key_items, ordered=True))

    # Section 11: Performance graphs
    parts.append('<p class="section-label">Schedule Performance Graphs:</p>')
    parts.append(
        '<p class="email-text">The charts below show our actual starts and finishes '
        'compared to planned, schedule compression, and monthly activity finish '
        'distribution. You can get a better view of these charts and drill down to '
        'greater detail regarding specific activities and trade performance by logging '
        'on to SmartPM and clicking the View Trends link on the right side of the screen.</p>'
    )
    parts.append('<div class="graph-list" data-field="graph_screenshot_rels">')
    for rel in graph_rels:
        img_tag = (
            f'<img src="{_esc(rel)}" alt="{_esc(rel)}" class="graph-img" '
            f'data-src="{_esc(rel)}">'
        )
        if smartpm_trends_url:
            parts.append(
                f'<p class="screenshot"><a href="{_esc(smartpm_trends_url)}" '
                f'target="_blank">{img_tag}</a></p>'
            )
        else:
            parts.append(f'<p class="screenshot">{img_tag}</p>')
    parts.append('</div>')

    # Section 12: Closing paragraphs (editable list)
    parts.append(_custom_paragraphs_html(custom_paragraphs))

    # Sign-off — blank spacer between for visual breathing room
    parts.append('<p class="email-text">Please let me know if you have any questions.</p>')
    parts.append('<p class="email-text">&nbsp;</p>')
    parts.append('<p class="email-text">Thanks,</p>')

    # Signature
    parts.append(
        '<div class="signature">'
        f'<p><strong>{_editable_span("signer_name", signer_name)} | '
        f'<span style="color:{TEAL};">{_editable_span("signer_title", signer_title)}</span></strong></p>'
        f'<p style="color:{TEAL};">1411 West 1250 South, Suite 200</p>'
        f'<p style="color:{TEAL};">Orem, Utah 84058 USA</p>'
        f'<p><strong style="color:{TEAL};">O</strong> +1 801.374.6085'
        f' &nbsp; <strong style="color:{TEAL};">M</strong> '
        f'{_editable_span("signer_mobile", signer_mobile)}</p>'
        '<p><em>Building the Westland Way</em></p>'
        '</div>'
    )

    parts.append('</div>')  # /email-body

    # Attachments card — outside email-body, visually a control panel
    parts.append(_attachments_html(
        attachments, changes_report=changes_report, date_label=date_label,
        skip_procore=skip_procore,
    ))

    parts.append('<script>')
    parts.append(_script())
    parts.append('</script>')
    parts.append('</body></html>')
    return '\n'.join(parts)


def _css():
    return f"""
body {{
  font-family: Arial, sans-serif;
  font-size: 11pt;
  color: #000;
  max-width: 820px;
  margin: 0 auto;
  padding: 20px;
  background: #f7f7f7;
}}

/* --- Action bars -------------------------------------------------- */
.toolbar {{
  position: sticky; top: 0;
  background: #fff; border: 1px solid #ccc;
  padding: 10px 14px; margin-bottom: 12px;
  border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  z-index: 99; display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}}
.toolbar button {{
  font-size: 14px; padding: 8px 14px; cursor: pointer;
  border: 1px solid {TEAL}; background: {TEAL}; color: #fff;
  border-radius: 4px;
}}
.toolbar button:hover {{ background: #0d627e; }}
.toolbar-hint {{ color: #555; font-size: 12px; }}

#format-toolbar {{
  position: fixed; top: 10px; right: 20px;
  background: #fff; border: 1px solid #ccc;
  padding: 6px 10px; border-radius: 6px;
  box-shadow: 0 4px 10px rgba(0,0,0,0.1);
  z-index: 200; display: flex; align-items: center; gap: 4px;
}}
#format-toolbar button {{
  font-size: 15px; padding: 4px 10px; cursor: pointer;
  border: 1px solid #ccc; background: #fff; border-radius: 3px;
  min-width: 32px;
}}
#format-toolbar button:hover {{ background: #f0f0f0; }}
#format-toolbar .priority-btn {{ color: {RED}; font-weight: bold; }}
#format-toolbar .toolbar-sep {{ color: #aaa; }}
#format-toolbar .toolbar-context {{ font-size: 11px; color: #666; }}

.instructions {{
  background: #fff8e1; border: 1px solid #ffb300;
  padding: 10px 14px; border-radius: 6px; margin-bottom: 16px;
  font-size: 12px;
}}

/* --- Email body --------------------------------------------------- */
.email-body {{
  background: #fff; padding: 30px 40px;
  border: 1px solid #ddd; border-radius: 4px;
}}
.info-block {{ margin: 0 0 6pt 0; }}
.info-label {{ color: {TEAL}; font-weight: bold; }}
.days-line {{ font-weight: bold; font-size: 12pt; margin: 12pt 0 18pt 0; }}
.section-label {{
  color: {TEAL}; font-weight: bold; font-size: 12pt;
  margin: 12pt 0 4pt 0;
}}
.email-text, .block {{ margin: 0 0 6pt 0; }}

/* --- Base contenteditable styling --------------------------------- */
[contenteditable="true"] {{
  background: #fbfbfb; outline: 1px dashed #d0d7de;
  padding: 2px 4px; border-radius: 2px; min-width: 40px;
}}
[contenteditable="true"]:focus {{
  outline: 2px solid {TEAL}; background: #fffde7;
}}
span[contenteditable="true"] {{ display: inline-block; }}
p[contenteditable="true"], div.block[contenteditable="true"] {{
  display: block; min-height: 1.5em; padding: 4px 6px;
}}

/* "Changed this week" indicator on narrative blocks + scalar spans.
   Applied by the generator if the skill detected a change from last
   week, or live by JS as soon as the user edits the field. */
p[contenteditable="true"][data-changed="true"],
div.block[contenteditable="true"][data-changed="true"],
span[contenteditable="true"][data-changed="true"] {{
  outline: 1px dashed {GREEN};
  background: #eafaf0;
}}
p[contenteditable="true"][data-changed="true"]:focus,
div.block[contenteditable="true"][data-changed="true"]:focus,
span[contenteditable="true"][data-changed="true"]:focus {{
  outline: 2px solid {TEAL}; background: #fffde7;
}}

/* --- List wrapper & list items ------------------------------------ */
.list-wrapper {{ margin: 0 0 8pt 0; }}
.editable-list {{
  padding-left: 52px; margin: 4pt 0 0 0;
}}

/* Main list: counter-based numbering that ONLY increments on checked items
   so the visible numbers match what will actually be in the email. */
ol.editable-list:not(.archived-list) {{
  list-style: none;
  counter-reset: list-num;
}}
ul.editable-list:not(.archived-list) {{ list-style: none; }}
ol.editable-list:not(.archived-list) > li.list-item[data-checked="true"] {{
  counter-increment: list-num;
}}
ol.editable-list:not(.archived-list) > li.list-item[data-checked="true"]::before {{
  content: counter(list-num) ".";
  position: absolute; left: -28px; top: 4px;
  color: #333; font-size: 11pt; text-align: right; min-width: 22px;
}}
ul.editable-list:not(.archived-list) > li.list-item[data-checked="true"]::before {{
  content: "\u2022";
  position: absolute; left: -16px; top: 4px;
  color: #333; font-size: 14px;
}}
/* Unchecked items: muted dash, no number — they don't count toward the total. */
ol.editable-list:not(.archived-list) > li.list-item[data-checked="false"]::before,
ul.editable-list:not(.archived-list) > li.list-item[data-checked="false"]::before {{
  content: "\u2014";
  position: absolute; left: -18px; top: 4px;
  color: #999;
}}

/* Archived sub-list keeps its own native numbering (own context). */
ol.archived-list {{ list-style-type: decimal; }}
ul.archived-list {{ list-style-type: disc; }}

li.list-item {{
  display: block; margin: 0 0 6px 0; padding: 0;
  position: relative;
}}
ol.archived-list > li.list-item, ul.archived-list > li.list-item {{
  display: list-item;
}}
li.list-item .li-content {{
  display: block; padding: 3px 8px; min-height: 1.4em;
  background: #fbfbfb; outline: 1px dashed #d0d7de;
  border-radius: 2px;
}}

/* --- Git-diff states derived from (status, checked) combination ---
   Only NEW items get the green "added this update" styling. Re-checking a
   removed or archived item is a revert, not a new addition — those fall
   through to default (active) styling.

   GREEN = truly new this update
     - new + checked           (added this update)
   RED = will NOT be in this email
     - active + unchecked      (user just unchecked)
     - new + unchecked         (added then cancelled)
     - removed + unchecked     (removed this update, will archive next update)
   GRAY = still archived (unchecked, lives in archived sub-list)
     - archived + unchecked
   DEFAULT (normal gray) = the rest, including reverts:
     - active + checked        (normal, unchanged)
     - removed + checked       (user reverted the removal)
     - archived + checked      (user un-archived — will be active next update)
*/
li.list-item[data-status="new"][data-checked="true"] .li-content {{
  outline: 1px dashed {GREEN};
  background: #eafaf0;
  color: inherit; text-decoration: none; opacity: 1; font-style: normal;
}}
li.list-item[data-status="active"][data-checked="false"] .li-content,
li.list-item[data-status="new"][data-checked="false"] .li-content,
li.list-item[data-status="removed"][data-checked="false"] .li-content {{
  outline: 1px dashed {RED};
  background: #fce8e6;
  text-decoration: line-through; color: #9a3333;
}}
li.list-item[data-status="archived"][data-checked="false"] .li-content {{
  outline: 1px dashed #999;
  background: #f5f5f5;
  opacity: 0.8; font-style: italic;
  text-decoration: none; color: inherit;
}}
/* Amber DASHED BORDER for edited items (text was tweaked this update).
   No background fill — we want the ins/del spans' red/green to stand out
   against the neutral item background, not fight with an amber wash. */
li.list-item[data-edited="true"][data-status="active"][data-checked="true"] .li-content {{
  outline: 1px dashed #d4a030;
  /* background intentionally stays the default #fbfbfb */
}}
/* Inline word diff inside content (shown for edited items). */
.li-content ins.diff-ins {{
  text-decoration: underline; text-decoration-color: {GREEN};
  background: #eafaf0; color: #2d7a4f;
  padding: 0 2px; border-radius: 2px;
}}
.li-content del.diff-del {{
  text-decoration: line-through; text-decoration-color: {RED};
  background: #fce8e6; color: #9a3333;
  padding: 0 2px; border-radius: 2px; margin-right: 2px;
}}
/* Focus always wins (solid teal) regardless of status/edited. Uses !important
   because the more-specific [data-edited][data-status][data-checked] rule
   would otherwise beat the :focus selector on specificity. */
li.list-item .li-content:focus {{
  outline: 2px solid {TEAL} !important;
  background: #fffde7 !important;
}}

/* --- Drag-and-drop handles & drop indicators --------------------- */
.drag-handle {{
  position: absolute;
  left: -50px; top: 3px;
  cursor: grab;
  color: #ccc;
  font-size: 14px;
  width: 18px; text-align: center;
  padding: 2px 0;
  border-radius: 2px;
  user-select: none;
  letter-spacing: -2px;
  font-family: monospace;
  line-height: 1;
}}
.drag-handle:hover {{ color: #666; background: #eef1f3; }}
.drag-handle:active {{ cursor: grabbing; color: {TEAL}; }}

/* Attachment items & custom paragraphs are flex containers — the handle
   sits inline instead of absolute-positioned. */
li.attachment-item .drag-handle,
.custom-paragraph .drag-handle {{
  position: static;
  left: auto; top: auto;
}}

.dragging {{ opacity: 0.4; }}
/* Drop indicators: a teal bar above or below the hover target */
.list-item.drag-over-above::before,
.attachment-item.drag-over-above::before,
.custom-paragraph.drag-over-above::before {{
  content: '';
  position: absolute; left: -4px; right: 0; top: -4px;
  height: 3px; background: {TEAL}; border-radius: 2px;
  pointer-events: none; z-index: 10;
}}
.list-item.drag-over-below::after,
.attachment-item.drag-over-below::after,
.custom-paragraph.drag-over-below::after {{
  content: '';
  position: absolute; left: -4px; right: 0; bottom: -4px;
  height: 3px; background: {TEAL}; border-radius: 2px;
  pointer-events: none; z-index: 10;
}}
.custom-paragraph, li.attachment-item {{ position: relative; }}

/* Archived list items live in a separate sub-list (<ol class="archived-list">)
   so they don't merge into the main list's numbering. Caret toggles its
   visibility. Re-checked archived items stay in the sub-list — if they
   should become active, that happens at next week's transition. */
.archived-list {{
  display: none;
  padding-left: 32px;
  margin: 4pt 0 0 0;
}}
ol.archived-list {{ list-style-type: decimal; }}
ul.archived-list {{ list-style-type: disc; }}
.list-wrapper.show-archived .archived-list {{ display: block; }}

/* Attachments: archived items stay in the same list but hidden by default. */
li.attachment-item[data-status="archived"] {{ display: none; }}
.attachments-section.show-archived li.attachment-item[data-status="archived"] {{
  display: flex;
}}

/* Per-item card (.li-controls) — hidden until focus-within the LI */
li.list-item .li-controls {{
  display: none;
  margin: 4px 0 10px 0; padding: 6px 10px;
  background: #f0f5f7; border: 1px dashed {TEAL};
  border-radius: 4px; align-items: center;
  gap: 10px; flex-wrap: wrap; font-size: 12px;
}}
li.list-item:focus-within .li-controls {{
  display: flex;
}}
li.list-item .li-include {{
  font-size: 12px; color: {TEAL}; font-weight: bold;
  display: inline-flex; align-items: center; gap: 4px;
}}
li.list-item .li-format, li.list-item .li-controls-right {{
  display: flex; gap: 3px;
}}
li.list-item .li-controls-right {{ margin-left: auto; }}
li.list-item .li-controls button {{
  font-size: 11px; padding: 3px 8px; cursor: pointer;
  border: 1px solid #aaa; background: #fff; border-radius: 3px;
  min-width: 28px;
}}
li.list-item .li-controls button:hover {{ background: #eee; }}
li.list-item .li-controls .priority-btn {{
  color: {RED}; font-weight: bold;
}}
li.list-item .li-controls .remove-btn {{
  color: {RED};
}}

/* Status notes inside the card — shown only when the current checked
   state matches the canonical state for that status. Reverts (e.g.
   removed + checked) hide the note since the item is being kept. */
li.list-item .li-status-note > span {{ display: none; font-size: 11px; }}
li.list-item[data-status="new"][data-checked="true"] .note-new {{
  display: inline-block; color: {GREEN}; font-weight: bold;
}}
li.list-item[data-status="removed"][data-checked="false"] .note-removed {{
  display: inline-block; color: {RED}; font-weight: bold;
}}
li.list-item[data-status="archived"][data-checked="false"] .note-archived {{
  display: inline-block; color: #666; font-style: italic;
}}
li.list-item[data-edited="true"][data-status="active"][data-checked="true"] .note-edited {{
  display: inline-block; color: #a07a15; font-style: italic;
  max-width: 100%; overflow: hidden; text-overflow: ellipsis;
}}
li.list-item[data-edited="true"][data-status="active"][data-checked="true"] .note-edited .previous-text-note {{
  font-style: normal; color: #6a5210; background: #fff8e1;
  padding: 1px 4px; border-radius: 2px;
}}
li.list-item .li-status-note:empty {{ display: none; }}

/* Archived caret toggle */
.archived-toggle {{
  margin: 4px 0 4px 32px; font-size: 11px; color: #666;
  background: none; border: none; cursor: pointer;
  padding: 4px 8px; text-align: left;
}}
.archived-toggle:hover {{ color: #000; }}
.archived-toggle .caret {{ display: inline-block; width: 12px; }}

.add-btn {{
  font-size: 11px; padding: 3px 9px; margin-right: 4px; cursor: pointer;
  border: 1px solid #aaa; background: #f5f5f5; border-radius: 3px;
}}
.add-btn:hover {{ background: #e9e9e9; }}
.list-controls {{ margin: 6px 0 0 32px; }}

.priority {{ color: {RED}; font-weight: bold; }}

/* --- Screenshots -------------------------------------------------- */
.screenshot {{ margin: 8pt 0; }}
.screenshot.placeholder {{
  font-style: italic; color: #888;
  border: 1px dashed #bbb; padding: 10px; text-align: center;
}}
.summary-img, .graph-img {{
  width: 100%; max-width: 100%; height: auto;
  border: 0; display: block;
}}

/* --- Custom closing paragraphs ------------------------------------ */
.custom-paragraphs {{
  background: #f0f5f7; border: 1px dashed {TEAL};
  padding: 12px 16px; border-radius: 6px; margin: 16pt 0;
}}
.custom-paragraphs h4 {{ margin: 0 0 4px 0; color: {TEAL}; }}
.section-hint {{ font-size: 11px; color: #555; margin: 0 0 8px 0; }}
.custom-paragraph {{
  background: #fff; border: 1px solid #dde5e8; border-radius: 4px;
  padding: 8px 10px; margin-bottom: 8px;
}}
.custom-paragraph-header {{
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 4px; flex-wrap: wrap;
}}
.custom-paragraph-toggle {{
  font-size: 12px; font-weight: bold; color: {TEAL};
  display: inline-flex; align-items: center; gap: 4px;
}}
.custom-paragraph-label-wrap {{ flex: 1; font-size: 12px; color: #555; }}
.custom-paragraph-label-prefix {{ color: #888; }}
.custom-paragraph-label {{ font-weight: bold; color: {TEAL}; }}
.paragraph-controls {{ display: flex; gap: 4px; }}
.paragraph-controls button, .custom-paragraphs .add-btn {{
  font-size: 11px; padding: 3px 9px; cursor: pointer;
  border: 1px solid #aaa; background: #f5f5f5; border-radius: 3px;
}}
.paragraph-body {{ margin-top: 4px; }}
.custom-paragraph:has(input:not(:checked)) .paragraph-body {{
  opacity: 0.5; text-decoration: line-through;
}}

/* --- Attachments section ----------------------------------------- */
.attachments-section {{
  background: #f0f5f7; border: 1px dashed {TEAL};
  padding: 12px 16px; border-radius: 6px; margin: 16pt 0;
}}
.attachments-section h4 {{ margin: 0 0 4px 0; color: {TEAL}; }}
.attachment-list {{
  list-style: none; padding: 0; margin: 6px 0;
}}
li.attachment-item {{
  display: flex; align-items: center; gap: 8px;
  background: #fff; border: 1px solid #dde5e8; border-radius: 3px;
  padding: 4px 8px; margin-bottom: 4px;
}}
/* Let long filenames wrap within the row instead of forcing overflow. */
.attachment-name {{
  flex: 1 1 auto; min-width: 0;
  white-space: normal; word-break: break-word; line-height: 1.4;
}}
li.attachment-item[data-status="archived"] {{ display: none; }}
.attachment-name {{
  flex: 1; font-family: Consolas, Menlo, monospace; font-size: 12px;
  padding: 2px 4px;
  background: #fbfbfb; outline: 1px dashed #d0d7de; border-radius: 2px;
}}
/* (status, checked)-derived state — same rules as list items. Only new
   items get green; reverts (removed/archived + checked) fall through to
   default styling. */
li.attachment-item[data-status="new"][data-checked="true"] .attachment-name {{
  outline: 1px dashed {GREEN}; background: #eafaf0;
  color: inherit; text-decoration: none; opacity: 1; font-style: normal;
}}
li.attachment-item[data-status="active"][data-checked="false"] .attachment-name,
li.attachment-item[data-status="new"][data-checked="false"] .attachment-name,
li.attachment-item[data-status="removed"][data-checked="false"] .attachment-name {{
  outline: 1px dashed {RED}; background: #fce8e6;
  text-decoration: line-through; color: #9a3333;
}}
li.attachment-item[data-status="archived"][data-checked="false"] .attachment-name {{
  outline: 1px dashed #999; background: #f5f5f5;
  opacity: 0.8; font-style: italic;
  text-decoration: none; color: inherit;
}}
.attachment-name:focus {{ outline: 2px solid {TEAL}; background: #fffde7; }}
.attach-toggle {{ display: inline-flex; align-items: center; }}
.attachment-meta .note-archived {{ display: none; font-size: 11px; color: #666; }}
li.attachment-item[data-status="archived"] .note-archived {{ display: inline; }}
.attachment-controls {{ display: flex; gap: 3px; }}
.attachment-controls button {{
  font-size: 11px; padding: 2px 7px; cursor: pointer;
  border: 1px solid #aaa; background: #f5f5f5; border-radius: 3px;
  min-width: 24px;
}}
.attachment-controls .remove-btn {{ color: {RED}; font-weight: bold; }}
.attachment-actions {{ margin-top: 6px; }}

/* Procore toggle on each attachment row */
.attach-procore-toggle {{
  display: inline-flex; align-items: center; gap: 3px;
  cursor: pointer; user-select: none;
}}
.attach-procore-toggle input[type="checkbox"] {{
  width: 13px; height: 13px;
}}
.procore-badge {{
  display: inline-block; background: {TEAL}; color: #fff;
  font-size: 9pt; font-weight: bold;
  padding: 0 4px; border-radius: 2px;
  font-family: Arial, sans-serif;
}}
li.attachment-item[data-share-procore="true"] {{
  border-left: 3px solid {TEAL};
}}

/* Skip Procore master toggle */
.skip-procore-option {{
  display: flex; align-items: center; gap: 10px;
  padding: 6px 10px; margin: 4px 0 8px 0;
  background: #fff8e1; border: 1px dashed {AMBER};
  border-radius: 4px;
}}
.skip-procore-toggle {{
  display: inline-flex; align-items: center; gap: 6px;
  cursor: pointer; font-weight: bold; color: #6b4f0e;
}}
.skip-procore-hint {{
  font-size: 11px; color: #555; font-style: italic;
}}

/* Changes-report toggle — generated artifact, not a disk file */
.changes-report-option {{
  background: #fff; border: 1px dashed {TEAL}; border-radius: 3px;
  padding: 8px 12px; margin-bottom: 10px;
  display: grid; grid-template-columns: auto 1fr; gap: 4px 10px;
  align-items: center;
  font-size: 12px;
}}
.changes-report-toggle {{
  display: inline-flex; align-items: center; gap: 6px;
  font-weight: bold; color: {TEAL};
  grid-column: 1;
}}
.changes-report-label {{ font-size: 12px; }}
.changes-report-filename-wrap {{
  display: inline-flex; align-items: center; gap: 6px;
  grid-column: 2;
}}
.changes-report-filename-prefix {{ color: #666; }}
.changes-report-filename-input {{
  flex: 1 1 auto; min-width: 200px;
  font-family: Consolas, Menlo, monospace; font-size: 12px;
  padding: 3px 6px;
  border: 1px solid #d0d7de; border-radius: 3px;
  background: #fbfbfb;
}}
.changes-report-filename-input:focus {{
  outline: 2px solid {TEAL}; border-color: {TEAL}; background: #fffde7;
}}
.changes-report-hint {{
  grid-column: 1 / -1;
  color: #666; font-size: 11px; font-style: italic;
  margin-top: 2px;
}}
.changes-report-option:has(input:not(:checked)) .changes-report-filename-input,
.changes-report-option:has(input:not(:checked)) .changes-report-filename-prefix {{
  opacity: 0.5;
}}

.signature {{
  margin-top: 24pt; border-top: 1px solid #eee;
  padding-top: 12pt; font-size: 10pt;
}}
.signature p {{ margin: 0; }}

@media print {{
  body {{ background: #fff; max-width: none; padding: 0; }}
  .no-print {{ display: none !important; }}
  .email-body {{ border: none; box-shadow: none; padding: 0; }}
  [contenteditable="true"] {{ outline: none; background: transparent; padding: 0; }}
  li.list-item .li-content {{ outline: none; background: transparent; border-left: none; }}
  li.list-item[data-status="archived"] {{ display: none !important; }}
}}
"""


def _script():
    return r"""
// ---------- Format toolbar ----------
const FORMAT_TOOLBAR = document.getElementById('format-toolbar');
let LAST_EDITABLE = null;

function showToolbarFor(el) {
  LAST_EDITABLE = el;
  FORMAT_TOOLBAR.style.display = 'flex';
  const ctx = document.getElementById('toolbar-context');
  const field = el.dataset.field
    || (el.closest('[data-field]') || {}).dataset?.field
    || (el.closest('.list-item') ? 'list item' : '');
  ctx.textContent = field ? 'Editing: ' + field : 'Formatting';
}
function hideToolbar() {
  setTimeout(() => {
    if (!document.activeElement || !document.activeElement.isContentEditable) {
      FORMAT_TOOLBAR.style.display = 'none';
    }
  }, 150);
}
document.addEventListener('focusin', (e) => {
  if (e.target.isContentEditable) showToolbarFor(e.target);
});
document.addEventListener('focusout', (e) => {
  if (e.target.isContentEditable) hideToolbar();
});

function fmt(cmd) {
  if (LAST_EDITABLE) LAST_EDITABLE.focus();
  document.execCommand('styleWithCSS', false, false);
  document.execCommand(cmd, false, null);
}

function togglePriority() {
  if (LAST_EDITABLE) LAST_EDITABLE.focus();
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return;
  const range = sel.getRangeAt(0);
  let anc = sel.anchorNode;
  while (anc && anc !== document.body) {
    if (anc.nodeType === 1 && anc.classList && anc.classList.contains('priority')) {
      const parent = anc.parentNode;
      while (anc.firstChild) parent.insertBefore(anc.firstChild, anc);
      parent.removeChild(anc);
      return;
    }
    anc = anc.parentNode;
  }
  const span = document.createElement('span');
  span.className = 'priority';
  span.style.color = '#C94444';
  span.style.fontWeight = 'bold';
  try {
    span.appendChild(range.extractContents());
    range.insertNode(span);
    sel.removeAllRanges();
    const r2 = document.createRange();
    r2.selectNodeContents(span);
    sel.addRange(r2);
  } catch (e) { console.warn(e); }
}

document.addEventListener('keydown', (e) => {
  if (!document.activeElement || !document.activeElement.isContentEditable) return;
  if (e.ctrlKey && e.shiftKey && (e.key === 'P' || e.key === 'p')) {
    e.preventDefault();
    togglePriority();
  }
});

// ---------- List item management ----------
const LIST_ITEM_TEMPLATE = `
<li class="list-item" data-checked="true" data-status="new">
  <span class="drag-handle" draggable="true" title="Drag to reorder" aria-label="Drag handle">⋮⋮</span>
  <div class="li-content" contenteditable="true">New item</div>
  <div class="li-controls no-print" tabindex="-1">
    <div class="li-status-note">
      <span class="note-new">✨ New this update</span>
      <span class="note-removed">− Removed from this update</span>
      <span class="note-archived">📁 Archived <span class="archived-date"></span></span>
    </div>
    <label class="li-include"><input type="checkbox" data-item-checked checked> <span>Include in this email</span></label>
    <div class="li-format">
      <button type="button" onmousedown="event.preventDefault()" onclick="fmt('bold')"><b>B</b></button>
      <button type="button" onmousedown="event.preventDefault()" onclick="fmt('italic')"><i>I</i></button>
      <button type="button" onmousedown="event.preventDefault()" onclick="togglePriority()" class="priority-btn">!</button>
    </div>
    <div class="li-controls-right">
      <button type="button" onclick="moveListItem(this,-1)">↑</button>
      <button type="button" onclick="moveListItem(this,1)">↓</button>
      <button type="button" onclick="removeListItem(this)" class="remove-btn">× Remove</button>
    </div>
  </div>
</li>`;

function addListItem(btn) {
  // Always target the MAIN list, not the archived sub-list
  const list = btn.closest('.list-wrapper').querySelector('ol.editable-list:not(.archived-list), ul.editable-list:not(.archived-list)');
  if (!list) return;
  const wrap = document.createElement('div');
  wrap.innerHTML = LIST_ITEM_TEMPLATE.trim();
  const li = wrap.firstElementChild;
  list.appendChild(li);
  const content = li.querySelector('.li-content');
  content.focus();
  const range = document.createRange();
  range.selectNodeContents(content);
  const sel = window.getSelection();
  sel.removeAllRanges(); sel.addRange(range);
}

function keepButtonUnderMouse(btn, action) {
  // Run a reorder action while keeping the clicked button at the same
  // viewport Y. Fixes the "I have to chase the arrow with my mouse" bug.
  const beforeY = btn.getBoundingClientRect().top;
  action();
  const afterY = btn.getBoundingClientRect().top;
  const dy = afterY - beforeY;
  if (dy !== 0) window.scrollBy(0, dy);
}
function moveListItem(btn, dir) {
  const li = btn.closest('li');
  if (!li) return;
  keepButtonUnderMouse(btn, () => {
    if (dir < 0 && li.previousElementSibling) {
      li.parentNode.insertBefore(li, li.previousElementSibling);
    } else if (dir > 0 && li.nextElementSibling) {
      li.parentNode.insertBefore(li.nextElementSibling, li);
    }
  });
  const content = li.querySelector('.li-content');
  if (content) content.focus({preventScroll: true});
}
function removeListItem(btn) { btn.closest('li').remove(); }

// Sync data-checked with checkbox state on any data-item-checked checkbox
document.addEventListener('change', (e) => {
  if (e.target.matches('input[data-item-checked]')) {
    const item = e.target.closest('[data-checked]');
    if (item) item.dataset.checked = e.target.checked ? 'true' : 'false';
  }
});

// Mark narrative fields and scalar spans as "changed this week" on any
// user edit. Scoped: list items and attachment names have their own state
// model (status + checked), so we skip them here.
document.addEventListener('input', (e) => {
  const t = e.target;
  if (!t || !t.isContentEditable) return;
  if (t.classList.contains('li-content')) return;
  if (t.classList.contains('attachment-name')) return;
  // Walk up to the nearest element with data-field (handles nested markup).
  let el = t;
  while (el && !el.dataset?.field && el !== document.body) {
    el = el.parentElement;
  }
  if (el && el.dataset && el.dataset.field) {
    el.dataset.changed = 'true';
  }
});

// ---------- Live diff on edit (list items) ----------
// Each li.list-item keeps an HTML baseline. On focus we flatten any existing
// <ins>/<del> markup so the user edits clean content. On blur we tokenize
// the baseline HTML and the current HTML such that each word carries its
// wrapping formatting tags (<b>, <i>, <span class="priority">, …) as part
// of the token identity, then run a word-level LCS diff. Result: unchanged
// formatted text keeps its formatting; added/removed formatting shows as a
// replace op (old plain struck-through, new formatted underlined).

const _FMT_TAGS = new Set(['b', 'strong', 'i', 'em', 'span']);

function _diffTokenizeHtml(html) {
  // Returns array of tokens. Each word-token is the word PLUS its active
  // formatting tags so "<b>foo</b> bar" => ["<b>foo</b>", " ", "bar"].
  // Whitespace tokens are preserved so joins round-trip.
  const tokens = [];
  const stack = [];  // array of {name, openRaw}
  const re = /<(\/?)(\w+)([^>]*)>|(\s+)|([^\s<]+)/g;
  let m;
  while ((m = re.exec(html)) !== null) {
    if (m[2]) {
      const isClose = m[1] === '/';
      const name = m[2].toLowerCase();
      if (!_FMT_TAGS.has(name)) {
        // Non-formatting tag (br, etc.) — emit as its own token
        tokens.push(m[0]);
        continue;
      }
      if (isClose) {
        for (let i = stack.length - 1; i >= 0; i--) {
          if (stack[i].name === name) { stack.splice(i, 1); break; }
        }
      } else {
        stack.push({name, openRaw: m[0]});
      }
    } else if (m[4]) {
      tokens.push(m[4]);  // whitespace
    } else if (m[5]) {
      const opening = stack.map(t => t.openRaw).join('');
      const closing = stack.map(t => '</' + t.name + '>').reverse().join('');
      tokens.push(opening + m[5] + closing);
    }
  }
  return tokens;
}

function _diffOps(a, b, minEqualWords = 5) {
  const m = a.length, n = b.length;
  const dp = Array.from({length: m + 1}, () => new Int32Array(n + 1));
  for (let i = 0; i < m; i++) {
    for (let j = 0; j < n; j++) {
      dp[i+1][j+1] = (a[i] === b[j])
        ? dp[i][j] + 1
        : Math.max(dp[i+1][j], dp[i][j+1]);
    }
  }
  const raw = [];
  let i = m, j = n;
  while (i > 0 || j > 0) {
    if (i > 0 && j > 0 && a[i-1] === b[j-1]) {
      raw.unshift(['equal', i-1, i, j-1, j]); i--; j--;
    } else if (j > 0 && (i === 0 || dp[i][j-1] >= dp[i-1][j])) {
      raw.unshift(['insert', i, i, j-1, j]); j--;
    } else {
      raw.unshift(['delete', i-1, i, j, j]); i--;
    }
  }
  const merged = [];
  for (const op of raw) {
    const last = merged[merged.length - 1];
    if (last && last[0] === op[0]) { last[2] = op[2]; last[4] = op[4]; }
    else merged.push([...op]);
  }
  let out = [];
  for (let k = 0; k < merged.length; k++) {
    const cur = merged[k], nxt = merged[k+1];
    if (cur[0] === 'delete' && nxt && nxt[0] === 'insert') {
      out.push(['replace', cur[1], cur[2], nxt[3], nxt[4]]);
      k++;
    } else {
      out.push(cur);
    }
  }
  // Coalesce short equal runs sandwiched between two non-equal ops —
  // avoids the "tick-tock red/green every 2 words" pattern when sentences
  // mostly diverge but share a few tokens.
  if (minEqualWords > 0) out = _coalesceSmallEquals(out, a, b, minEqualWords);
  return out;
}

function _coalesceSmallEquals(ops, aTokens, bTokens, minEqualWords) {
  let out = [...ops];
  let changed = true;
  while (changed) {
    changed = false;
    for (let idx = 1; idx < out.length - 1; idx++) {
      const op = out[idx];
      if (op[0] !== 'equal') continue;
      const prev = out[idx - 1];
      const next = out[idx + 1];
      if (prev[0] === 'equal' || next[0] === 'equal') continue;
      // Count non-whitespace word tokens in the equal span
      let wc = 0;
      for (let k = op[1]; k < op[2]; k++) {
        const tok = aTokens[k];
        if (tok && tok.trim()) wc++;
      }
      if (wc >= minEqualWords) continue;
      const aStart = prev[0] === 'insert' ? op[1] : prev[1];
      const aEnd   = next[0] === 'insert' ? op[2] : next[2];
      const bStart = prev[0] === 'delete' ? op[3] : prev[3];
      const bEnd   = next[0] === 'delete' ? op[4] : next[4];
      out.splice(idx - 1, 3, ['replace', aStart, aEnd, bStart, bEnd]);
      changed = true;
      break;
    }
  }
  return out;
}

function _diffToHtml(baselineHtml, currentHtml) {
  const aTokens = _diffTokenizeHtml(baselineHtml);
  const bTokens = _diffTokenizeHtml(currentHtml);
  const ops = _diffOps(aTokens, bTokens);
  const parts = [];
  for (const [op, i1, i2, j1, j2] of ops) {
    if (op === 'equal') {
      parts.push(aTokens.slice(i1, i2).join(''));
    } else if (op === 'delete') {
      parts.push('<del class="diff-del">' + aTokens.slice(i1, i2).join('') + '</del>');
    } else if (op === 'insert') {
      parts.push('<ins class="diff-ins">' + bTokens.slice(j1, j2).join('') + '</ins>');
    } else if (op === 'replace') {
      parts.push('<del class="diff-del">' + aTokens.slice(i1, i2).join('') + '</del>');
      parts.push('<ins class="diff-ins">' + bTokens.slice(j1, j2).join('') + '</ins>');
    }
  }
  return parts.join('');
}

function _flattenDiffMarkup(el) {
  el.querySelectorAll('del').forEach(d => d.remove());
  el.querySelectorAll('ins').forEach(ins => {
    const parent = ins.parentNode;
    while (ins.firstChild) parent.insertBefore(ins.firstChild, ins);
    parent.removeChild(ins);
  });
  el.normalize();
}

function _contentHtmlForDiff(el) {
  // Return innerHTML with diff markup stripped (ins unwrapped, del dropped).
  // The remaining HTML still has semantic formatting tags (<b>, <span class=
  // "priority">, etc.) which the diff tokenizer attaches to words.
  const clone = el.cloneNode(true);
  clone.querySelectorAll('del').forEach(d => d.remove());
  clone.querySelectorAll('ins').forEach(ins => {
    const parent = ins.parentNode;
    while (ins.firstChild) parent.insertBefore(ins.firstChild, ins);
    parent.removeChild(ins);
  });
  return clone.innerHTML;
}

function _mdInlineToHtml(md) {
  // Mirrors Python _md_inline_to_html: converts ==…== → priority span,
  // **…** → <b>. Used to convert a plain-text baseline (previous_text from
  // the server) into HTML for diff tokenization.
  if (!md) return '';
  let s = md.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  s = s.replace(/==([\s\S]+?)==/g, '<span class="priority" style="color:#C94444;font-weight:bold">$1</span>');
  s = s.replace(/\*\*([\s\S]+?)\*\*/g, '<b>$1</b>');
  return s;
}

function _initDiffBaselines() {
  document.querySelectorAll('li.list-item').forEach(li => {
    const content = li.querySelector('.li-content');
    if (!content) return;
    if (li.dataset.previousText) {
      // Server-rendered edited item — baseline is the markdown-form previous
      // text, converted to HTML so the tokenizer attaches formatting.
      content.dataset.baseline = _mdInlineToHtml(li.dataset.previousText);
    } else {
      // Not currently edited — baseline is the current HTML (preserves any
      // pre-rendered formatting from markdown).
      _flattenDiffMarkup(content);
      content.dataset.baseline = content.innerHTML;
    }
  });
}
document.addEventListener('DOMContentLoaded', _initDiffBaselines);
if (document.readyState !== 'loading') _initDiffBaselines();

document.addEventListener('focusin', (e) => {
  const content = e.target.closest && e.target.closest('.li-content');
  if (!content) return;
  _flattenDiffMarkup(content);
});

document.addEventListener('focusout', (e) => {
  const content = e.target.closest && e.target.closest('.li-content');
  if (!content) return;
  const li = content.closest('.list-item');
  if (!li) return;
  // Only active items show the amber/diff treatment. New/removed/archived
  // use their own visual state.
  if (li.dataset.status !== 'active') return;
  const baseline = content.dataset.baseline || '';
  const current = _contentHtmlForDiff(content);
  // Compare stripped plain text — ignore whitespace-only noise.
  const baselineText = baseline.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
  const currentText = current.replace(/<[^>]+>/g, '').replace(/\s+/g, ' ').trim();
  const sameText = baselineText === currentText;
  const sameHtml = baseline.trim() === current.trim();
  if (!baseline || (sameText && sameHtml)) {
    li.removeAttribute('data-edited');
    li.removeAttribute('data-previous-text');
    return;
  }
  content.innerHTML = _diffToHtml(baseline, current);
  li.dataset.edited = 'true';
  // Keep the markdown-form previous text on the LI so save round-trips.
  // We derive it from the baseline HTML by reversing the md→html transform.
  li.dataset.previousText = _htmlToMdInline(baseline);
});

function _htmlToMdInline(html) {
  // Inverse of _mdInlineToHtml. Used to set data-previous-text from an
  // HTML baseline so the saved file keeps the markdown-form baseline.
  if (!html) return '';
  let s = html;
  s = s.replace(/<span\b[^>]*class="[^"]*priority[^"]*"[^>]*>([\s\S]*?)<\/span>/gi, '==$1==');
  s = s.replace(/<span\b[^>]*style="[^"]*color:\s*#c94444[^"]*"[^>]*>([\s\S]*?)<\/span>/gi, '==$1==');
  s = s.replace(/<(b|strong)\b[^>]*>([\s\S]*?)<\/\1>/gi, '**$2**');
  s = s.replace(/<(i|em)\b[^>]*>([\s\S]*?)<\/\1>/gi, '*$2*');
  s = s.replace(/<[^>]+>/g, '');
  const ta = document.createElement('textarea');
  ta.innerHTML = s;
  return ta.value;
}

// When Add Item creates a "new" status item, we skip diff tracking (per the
// status check above). Its baseline isn't needed.

// ---------- Drag and drop (reorder via handle) ----------
let DRAG_SRC = null;
function getDragItem(el) {
  return el.closest && el.closest('li.list-item, li.attachment-item, .custom-paragraph');
}
document.addEventListener('dragstart', (e) => {
  const handle = e.target.closest && e.target.closest('.drag-handle');
  if (!handle) return;
  const item = getDragItem(handle);
  if (!item) return;
  DRAG_SRC = item;
  item.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  // Firefox requires any data to be set for drag to proceed
  try { e.dataTransfer.setData('text/plain', 'item'); } catch(_) {}
  // Use the whole item as the drag ghost rather than just the handle
  try { e.dataTransfer.setDragImage(item, 20, 10); } catch(_) {}
});
document.addEventListener('dragend', () => {
  if (DRAG_SRC) DRAG_SRC.classList.remove('dragging');
  document.querySelectorAll('.drag-over-above, .drag-over-below').forEach(el => {
    el.classList.remove('drag-over-above', 'drag-over-below');
  });
  DRAG_SRC = null;
});
document.addEventListener('dragover', (e) => {
  if (!DRAG_SRC) return;
  const target = getDragItem(e.target);
  if (!target || target === DRAG_SRC) return;
  if (target.parentElement !== DRAG_SRC.parentElement) return; // same container only
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  const rect = target.getBoundingClientRect();
  const above = (e.clientY - rect.top) < rect.height / 2;
  document.querySelectorAll('.drag-over-above, .drag-over-below').forEach(el => {
    if (el !== target) el.classList.remove('drag-over-above', 'drag-over-below');
  });
  target.classList.remove(above ? 'drag-over-below' : 'drag-over-above');
  target.classList.add(above ? 'drag-over-above' : 'drag-over-below');
});
document.addEventListener('drop', (e) => {
  if (!DRAG_SRC) return;
  const target = getDragItem(e.target);
  if (!target || target === DRAG_SRC) return;
  if (target.parentElement !== DRAG_SRC.parentElement) return;
  e.preventDefault();
  const rect = target.getBoundingClientRect();
  const above = (e.clientY - rect.top) < rect.height / 2;
  if (above) {
    target.parentNode.insertBefore(DRAG_SRC, target);
  } else {
    target.parentNode.insertBefore(DRAG_SRC, target.nextSibling);
  }
  target.classList.remove('drag-over-above', 'drag-over-below');
});

// ---------- Archived caret ----------
function toggleArchived(btn) {
  const wrap = btn.closest('.list-wrapper');
  const expanded = wrap.classList.toggle('show-archived');
  btn.querySelector('.caret').textContent = expanded ? '▼' : '▶';
}
function toggleArchivedAttachments(btn) {
  const section = btn.closest('.attachments-section');
  const expanded = section.classList.toggle('show-archived');
  btn.querySelector('.caret').textContent = expanded ? '▼' : '▶';
}

// ---------- Custom paragraphs ----------
const DEFAULT_PARAGRAPH_TEMPLATE = `
<div class="custom-paragraph">
  <div class="custom-paragraph-header no-print">
    <span class="drag-handle" draggable="true" title="Drag to reorder" aria-label="Drag handle">⋮⋮</span>
    <label class="custom-paragraph-toggle"><input type="checkbox" data-field="paragraph_checked" checked> Include</label>
    <span class="custom-paragraph-label-wrap"><span class="custom-paragraph-label-prefix">Label:</span> <span contenteditable="true" data-field="paragraph_label" class="custom-paragraph-label">New paragraph</span></span>
    <div class="paragraph-controls">
      <button type="button" onclick="moveParagraph(this,-1)">↑</button>
      <button type="button" onclick="moveParagraph(this,1)">↓</button>
      <button type="button" onclick="removeCustomParagraph(this)">× Remove</button>
    </div>
  </div>
  <div class="block paragraph-body" contenteditable="true" data-field="paragraph_text">Paragraph text...</div>
</div>`;

function addCustomParagraph() {
  const list = document.querySelector('.custom-paragraph-list');
  const wrap = document.createElement('div');
  wrap.innerHTML = DEFAULT_PARAGRAPH_TEMPLATE.trim();
  const node = wrap.firstElementChild;
  list.appendChild(node);
  node.querySelector('.custom-paragraph-label').focus();
}
function removeCustomParagraph(btn) {
  const p = btn.closest('.custom-paragraph');
  if (p) p.remove();
}
function moveParagraph(btn, dir) {
  const p = btn.closest('.custom-paragraph');
  if (!p) return;
  keepButtonUnderMouse(btn, () => {
    if (dir < 0 && p.previousElementSibling) p.parentNode.insertBefore(p, p.previousElementSibling);
    else if (dir > 0 && p.nextElementSibling) p.parentNode.insertBefore(p.nextElementSibling, p);
  });
}

// ---------- Attachments ----------
const ATTACHMENT_TEMPLATE = `
<li class="attachment-item" data-checked="true" data-status="new" data-share-procore="false">
  <span class="drag-handle" draggable="true" title="Drag to reorder" aria-label="Drag handle">⋮⋮</span>
  <label class="attach-toggle" title="Include in email"><input type="checkbox" data-item-checked checked></label>
  <label class="attach-procore-toggle" title="Share to Procore"><input type="checkbox" data-procore-checked><span class="procore-badge">P</span></label>
  <span class="attachment-status-icon" aria-hidden="true"></span>
  <span class="attachment-name" contenteditable="true" data-field="attachment_name">FILENAME</span>
  <span class="attachment-meta"><span class="note-archived">📁 Archived <span class="archived-date"></span></span></span>
  <div class="attachment-controls no-print">
    <button type="button" onclick="moveAttachment(this,-1)">↑</button>
    <button type="button" onclick="moveAttachment(this,1)">↓</button>
    <button type="button" onclick="removeAttachment(this)" class="remove-btn">×</button>
  </div>
</li>`;

function onPickAttachments(event) {
  const files = event.target.files;
  for (const file of files) addAttachment(file.name, true, 'new');
  event.target.value = '';
}
function addAttachmentByName() {
  const name = prompt('Filename (must exist in this dated folder):');
  if (name && name.trim()) addAttachment(name.trim(), true, 'new');
}
function addAttachment(filename, checked, status) {
  const list = document.querySelector('.attachment-list');
  if (!list) return;
  const wrap = document.createElement('div');
  wrap.innerHTML = ATTACHMENT_TEMPLATE.trim();
  const item = wrap.firstElementChild;
  item.dataset.checked = checked ? 'true' : 'false';
  item.dataset.status = status || 'active';
  const cb = item.querySelector('input[data-item-checked]');
  if (checked) cb.setAttribute('checked', ''); else cb.removeAttribute('checked');
  cb.checked = !!checked;
  const nameEl = item.querySelector('.attachment-name');
  nameEl.textContent = filename;
  list.appendChild(item);
}
function removeAttachment(btn) { btn.closest('.attachment-item').remove(); }
function moveAttachment(btn, dir) {
  const item = btn.closest('.attachment-item');
  if (!item) return;
  keepButtonUnderMouse(btn, () => {
    if (dir < 0 && item.previousElementSibling) item.parentNode.insertBefore(item, item.previousElementSibling);
    else if (dir > 0 && item.nextElementSibling) item.parentNode.insertBefore(item.nextElementSibling, item);
  });
}

// ---------- Save / copy ----------
function _syncCheckboxes() {
  document.querySelectorAll('input[type=checkbox]').forEach(el => {
    if (el.checked) el.setAttribute('checked', '');
    else el.removeAttribute('checked');
  });
  document.querySelectorAll('li.attachment-item').forEach(li => {
    const inc = li.querySelector('input[data-item-checked]');
    const pro = li.querySelector('input[data-procore-checked]');
    li.setAttribute('data-checked', (inc && inc.checked) ? 'true' : 'false');
    li.setAttribute('data-share-procore', (pro && pro.checked) ? 'true' : 'false');
  });
}

function _buildSnapshotHtml() {
  _syncCheckboxes();   // NEW — keep data attributes and checkbox state aligned with reality
  document.querySelectorAll('[data-metric]').forEach(el => {
    el.setAttribute('data-value', el.dataset.value);
  });
  // Sync text-input values into the value attribute so they persist on save
  document.querySelectorAll('input[type=text]').forEach(el => {
    el.setAttribute('value', el.value || '');
  });
  const clone = document.documentElement.cloneNode(true);
  return '<!DOCTYPE html>\n' + clone.outerHTML;
}

function _suggestedFilename() {
  const m = location.pathname.match(/[^/]+$/);
  return (m && m[0]) ? decodeURIComponent(m[0]) : (document.title + '.html');
}

async function saveEdits() {
  const html = _buildSnapshotHtml();
  const blob = new Blob([html], {type: 'text/html;charset=utf-8'});

  // Preferred: File System Access API (Chrome/Edge). Opens a native Save As
  // dialog that lets the user overwrite the file in place and remembers the
  // location between saves in the same session.
  if (window.showSaveFilePicker) {
    try {
      // Reuse the last-picked handle if we have one — writes silently
      // without re-prompting.
      let handle = window._lastSaveHandle;
      if (!handle) {
        handle = await window.showSaveFilePicker({
          suggestedName: _suggestedFilename(),
          types: [{
            description: 'HTML Preview',
            accept: {'text/html': ['.html']},
          }],
        });
        window._lastSaveHandle = handle;
      }
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      flash('Saved to ' + (handle.name || 'file') + '. Tell Claude "done".');
      return;
    } catch (e) {
      if (e.name === 'AbortError') return;  // user cancelled
      // Permission or other error — fall through to download fallback
      console.warn('showSaveFilePicker failed:', e);
      window._lastSaveHandle = null;
    }
  }

  // Fallback: anchor download (Firefox, older browsers)
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = _suggestedFilename();
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
  flash('Saved. Drop the download in the same folder (overwrite), then tell Claude "done".');
}

function collectFields() {
  const out = {};
  document.querySelectorAll('[data-metric]').forEach(el => {
    const n = parseInt(el.dataset.value, 10);
    if (!isNaN(n)) out[el.dataset.metric] = n;
  });
  document.querySelectorAll('span[contenteditable="true"][data-field], p[contenteditable="true"][data-field], div.block[contenteditable="true"][data-field]').forEach(el => {
    if (el.closest('.custom-paragraph')) return;
    out[el.dataset.field] = htmlToMarkdown(el.innerHTML);
  });
  document.querySelectorAll('.editable-list[data-field]').forEach(list => {
    out[list.dataset.field] = Array.from(list.querySelectorAll('li.list-item')).map(li => ({
      text: htmlToMarkdown(li.querySelector('.li-content').innerHTML).trim(),
      checked: li.dataset.checked === 'true',
      status: li.dataset.status || 'active',
      date_archived: li.dataset.archived || '',
    }));
  });
  const paras = [];
  document.querySelectorAll('.custom-paragraph').forEach(p => {
    paras.push({
      label: p.querySelector('[data-field="paragraph_label"]').textContent.trim(),
      text: htmlToMarkdown(p.querySelector('[data-field="paragraph_text"]').innerHTML).trim(),
      checked: !!p.querySelector('input[type=checkbox]').checked,
    });
  });
  out.custom_paragraphs = paras;
  const atts = [];
  document.querySelectorAll('.attachment-item').forEach(it => {
    atts.push({
      filename: it.querySelector('.attachment-name').textContent.trim(),
      checked: it.dataset.checked === 'true',
      status: it.dataset.status || 'active',
      date_archived: it.dataset.archived || '',
    });
  });
  out.attachments = atts;
  // Changes report option
  const crCheckbox = document.querySelector('input[data-field="include_changes_report"]');
  const crFilename = document.querySelector('input[data-field="changes_report_filename"]');
  out.changes_report = {
    include: crCheckbox ? !!crCheckbox.checked : false,
    filename: crFilename ? (crFilename.value || '').trim() : '',
  };
  const gl = document.querySelector('.graph-list[data-field]');
  if (gl) out[gl.dataset.field] = Array.from(gl.querySelectorAll('img[data-src]')).map(i => i.dataset.src);
  const summary = document.querySelector('img[data-field="summary_screenshot_rel"]');
  if (summary) out.summary_screenshot_rel = summary.dataset.src || summary.getAttribute('src');
  return out;
}
function htmlToMarkdown(h) {
  if (!h) return '';
  let s = h;
  // Diff markup: drop <del> content (phantom), unwrap <ins> (keep content)
  s = s.replace(/<del\b[^>]*>[\s\S]*?<\/del>/gi, '');
  s = s.replace(/<ins\b[^>]*>([\s\S]*?)<\/ins>/gi, '$1');
  s = s.replace(/<span\b[^>]*class="[^"]*priority[^"]*"[^>]*>([\s\S]*?)<\/span>/gi, '==$1==');
  s = s.replace(/<span\b[^>]*style="[^"]*color:\s*#c94444[^"]*"[^>]*>([\s\S]*?)<\/span>/gi, '==$1==');
  s = s.replace(/<(b|strong)\b[^>]*>([\s\S]*?)<\/\1>/gi, '**$2**');
  s = s.replace(/<(i|em)\b[^>]*>([\s\S]*?)<\/\1>/gi, '*$2*');
  s = s.replace(/<br\s*\/?>/gi, '\n');
  s = s.replace(/<[^>]+>/g, '');
  const ta = document.createElement('textarea'); ta.innerHTML = s; return ta.value;
}
async function copyForClaude() {
  const data = collectFields();
  const json = JSON.stringify(data, null, 2);
  try { await navigator.clipboard.writeText(json); flash('Copied JSON to clipboard.'); }
  catch (e) { prompt('Copy this JSON:', json); }
}
function flash(msg) {
  const existing = document.getElementById('flash-msg');
  if (existing) existing.remove();
  const div = document.createElement('div');
  div.id = 'flash-msg'; div.textContent = msg;
  div.style.cssText = 'position:fixed;top:60px;right:20px;background:#3A9E6B;color:#fff;' +
    'padding:12px 16px;border-radius:4px;z-index:10000;box-shadow:0 4px 8px rgba(0,0,0,0.15);' +
    'font-family:Arial;font-size:14px;max-width:320px;';
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 5000);
}
"""


def generate_preview_html(output_path, **kwargs):
    """Write the editable preview HTML to output_path."""
    html = _build_preview_html(**kwargs)
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return output_path


if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('output')
    ap.add_argument('--sample', action='store_true')
    args = ap.parse_args()
    if args.sample:
        generate_preview_html(
            args.output,
            date_label='2026-04-17',
            project_info={
                'project_name': 'Sample Project',
                'job_number': 'W9999',
                'contractual_completion': 'June 1, 2027',
                'projected_completion': 'July 15, 2027',
            },
            days_behind=44,
            gain_loss=-7,
            successes=[
                {'text': 'Concrete pour completed.', 'status': 'active', 'checked': True},
                {'text': '**New milestone hit this week.**', 'status': 'new', 'checked': True},
            ],
            red_flags=[
                {'text': '**Steel delivery pushed 2 more weeks.**', 'status': 'active', 'checked': True},
                {'text': 'Weather delays resolved.', 'status': 'removed', 'checked': False},
                {'text': 'Old issue long gone.', 'status': 'archived', 'checked': False, 'date_archived': '2026-03-15'},
            ],
            stalled_tasks=[], key_items=[],
            custom_paragraphs=[
                {'label': 'Compliance', 'checked': True, 'text': 'Compliance text.'},
            ],
            attachments=[
                {'filename': 'Report 01.pdf', 'checked': True, 'status': 'active'},
                {'filename': 'Procurement.xlsm', 'checked': True, 'status': 'new'},
                {'filename': 'old-draft.pdf', 'checked': False, 'status': 'archived',
                 'date_archived': '2026-03-01'},
            ],
            signer_name='CAMRON WALKER', signer_title='SCHEDULER',
        )
        print(f'Sample written to {args.output}')
