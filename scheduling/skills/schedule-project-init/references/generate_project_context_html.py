"""
Generate the editable project-context.html — master project config file.

Replaces project-context.md as the source of truth for every scheduling
skill (recipients, signer, SmartPM URLs, expected attachments, graph
ordering, project log).

Mirrors the generate_email_preview_html pattern: self-contained HTML with
contenteditable fields, Save Edits button (File System Access API + fall-
back download), Copy for Claude JSON export.

Project Log semantics:
    - Each entry has an ISO date and a body.
    - Entries dated before today are rendered read-only (locked).
    - Today's entry (or a new one added via "+ Add entry") is editable.
    - On save, the skill can inject events during weekly updates — on the
      next open, those entries lock automatically when the calendar day
      rolls over.
"""

import base64
import html as html_mod
import os
import re

# Westland brand colors (match email templates)
RED = '#C94444'
GREEN = '#3A9E6B'
TEAL = '#0B4F66'
AMBER = '#d4a030'

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOGO_PATH = os.path.join(_SCRIPT_DIR, 'westland-logo.png')


def _esc(text):
    return html_mod.escape(str(text))


def _logo_data_uri(path):
    if not path or not os.path.isfile(path):
        return ''
    with open(path, 'rb') as f:
        b64 = base64.b64encode(f.read()).decode('ascii')
    return f'data:image/png;base64,{b64}'


# --- Recipient parsing: "Name <email>" or just "email" -----------------

_RE_NAME_EMAIL = re.compile(r'^\s*(.+?)\s*<\s*([^>]+)\s*>\s*$')


def split_recipient(entry):
    """Split a recipient string into (name, email)."""
    if not entry:
        return ('', '')
    m = _RE_NAME_EMAIL.match(entry)
    if m:
        return (m.group(1).strip(), m.group(2).strip())
    return ('', entry.strip())


def parse_recipients_string(raw):
    """Parse a semicolon or comma-separated recipients string into a list
    of {name, email} dicts."""
    if not raw:
        return []
    # Accept ';', ',' and newlines as separators
    parts = re.split(r'[;,\n]+', raw)
    out = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        name, email = split_recipient(p)
        out.append({'name': name, 'email': email})
    return out


def format_recipients(recipients):
    """Format a list of {name, email} dicts as a semicolon-separated
    string. Recipients with names render as "Name <email>", others as
    just "email"."""
    parts = []
    for r in recipients or []:
        name = (r.get('name') or '').strip()
        email = (r.get('email') or '').strip()
        if not email:
            continue
        if name:
            parts.append(f'{name} <{email}>')
        else:
            parts.append(email)
    return '; '.join(parts)


# --- Renderers ---------------------------------------------------------

def _editable_text(field, value, cls='', placeholder=''):
    cls_attr = f' class="{cls}"' if cls else ''
    ph = f' placeholder="{_esc(placeholder)}"' if placeholder else ''
    return (
        f'<input type="text" data-field="{_esc(field)}" '
        f'value="{_esc(value)}"{cls_attr}{ph}>'
    )


def _locked_text(field, value, cls=''):
    cls_attr = f' class="{cls}"' if cls else ''
    return (
        f'<input type="text" data-field="{_esc(field)}" '
        f'value="{_esc(value)}" readonly{cls_attr} '
        f'title="Locked — contact support to change">'
    )


def _render_recipients(field, recipients, label):
    out = [
        f'<div class="recipient-group" data-field="{_esc(field)}">',
        f'  <div class="recipient-label">{_esc(label)}:</div>',
        '  <div class="recipient-list">',
    ]
    for r in recipients or []:
        out.append(_render_recipient_row(r.get('name', ''), r.get('email', '')))
    out.append('  </div>')
    out.append(
        '  <button type="button" class="add-btn no-print" '
        f'onclick="addRecipient(this)">+ Add {_esc(label.lower())}</button>'
    )
    out.append('</div>')
    return '\n'.join(out)


def _render_recipient_row(name, email):
    return (
        '<div class="recipient-row">'
        '<span class="drag-handle" draggable="true" title="Drag to reorder" '
        'aria-label="Drag">⋮⋮</span>'
        f'<input type="text" data-field="recipient_name" '
        f'value="{_esc(name)}" placeholder="Full name (optional)" '
        'class="recipient-name">'
        f'<input type="text" data-field="recipient_email" '
        f'value="{_esc(email)}" placeholder="email@domain" '
        'class="recipient-email">'
        '<button type="button" class="remove-btn no-print" '
        'onclick="removeRecipient(this)">×</button>'
        '</div>'
    )


def _render_string_list(field, items, placeholder='pattern'):
    """Editable ordered list of strings (for expected_attachments and
    graph_screenshots). Each item has a drag handle + text input + remove."""
    out = [f'<div class="string-list" data-field="{_esc(field)}">']
    for item in items or []:
        out.append(_render_string_list_row(item, placeholder))
    out.append(
        '<button type="button" class="add-btn no-print" '
        f'onclick="addStringListItem(this)">+ Add</button>'
    )
    out.append('</div>')
    return '\n'.join(out)


def _render_string_list_row(value, placeholder):
    return (
        '<div class="string-list-row">'
        '<span class="drag-handle" draggable="true" title="Drag to reorder" '
        'aria-label="Drag">⋮⋮</span>'
        f'<input type="text" data-field="item_value" value="{_esc(value)}" '
        f'placeholder="{_esc(placeholder)}">'
        '<button type="button" class="remove-btn no-print" '
        'onclick="removeStringListItem(this)">×</button>'
        '</div>'
    )


def _render_project_log(entries, today_iso):
    """Render project log. Entries dated != today get contenteditable=false
    + a locked visual. Today's entry is editable."""
    entries = entries or []
    # Sort newest first
    def _sort_key(e):
        return (e.get('date') or '', )
    entries_sorted = sorted(entries, key=_sort_key, reverse=True)

    out = [
        '<div class="project-log" data-field="project_log">',
        '<div class="log-hint no-print">Past entries are locked once the '
        'calendar day rolls. Today\'s entry stays editable until midnight.</div>',
        '<button type="button" class="add-btn no-print" '
        f'onclick="addLogEntry(this, \'{_esc(today_iso)}\')">'
        '+ Add entry (today)</button>',
        '<div class="log-entries">',
    ]
    for e in entries_sorted:
        date = e.get('date', '') or ''
        body = e.get('body', '') or ''
        is_today = (date == today_iso)
        out.append(_render_log_entry(date, body, is_today))
    out.append('</div></div>')
    return '\n'.join(out)


def _render_log_entry(date, body, is_today):
    lock_class = '' if is_today else ' locked'
    ce = 'true' if is_today else 'false'
    # Preserve line breaks in body as <br> for display
    body_html = _esc(body).replace('\n', '<br>')
    return (
        f'<div class="log-entry{lock_class}" data-date="{_esc(date)}">'
        f'<div class="log-entry-header">'
        f'<span class="log-date">{_esc(date)}</span>'
        f'{"<span class=\"log-lock\" title=\"Locked\">🔒</span>" if not is_today else ""}'
        f'{"<button type=\"button\" class=\"remove-btn no-print\" onclick=\"removeLogEntry(this)\" title=\"Remove\">×</button>" if is_today else ""}'
        f'</div>'
        f'<div class="log-body" contenteditable="{ce}" '
        f'data-field="log_body">{body_html}</div>'
        f'</div>'
    )


# --- Main build --------------------------------------------------------

def _build_html(ctx, today_iso, logo_path):
    project_name = ctx.get('project_name', '')
    job_number = ctx.get('job_number', '')
    contractual_completion = ctx.get('contractual_completion', '')
    smartpm_url = ctx.get('smartpm_url', '')
    smartpm_trends_url = ctx.get('smartpm_trends_url', '')
    smartpm_changelog_url = ctx.get('smartpm_changelog_url', '')
    to_recipients = ctx.get('to_recipients', [])
    cc_recipients = ctx.get('cc_recipients', [])
    signer_name = ctx.get('signer_name', '')
    signer_title = ctx.get('signer_title', '')
    signer_mobile = ctx.get('signer_mobile', '')
    procore_company_id = ctx.get('procore_company_id', '')
    procore_project_id = ctx.get('procore_project_id', '')
    graph_screenshots = ctx.get('graph_screenshots', [])
    project_log = ctx.get('project_log', [])

    title = f'Project Context — {project_name or job_number}'
    logo_src = _logo_data_uri(logo_path) if logo_path else ''
    logo_tag = (
        f'<img src="{logo_src}" alt="Westland" class="logo">'
        if logo_src else ''
    )

    parts = []
    parts.append('<!DOCTYPE html><html><head><meta charset="utf-8">')
    parts.append(f'<title>{_esc(title)}</title>')
    parts.append(f'<style>{_css()}</style>')
    parts.append('</head><body>')

    # --- Top action bar ---
    parts.append(
        '<div class="toolbar no-print">'
        '<button type="button" onclick="saveEdits()">💾 Save Edits</button>'
        '<button type="button" onclick="copyForClaude()">📋 Copy for Claude</button>'
        '<span class="toolbar-hint">Edit any field. When done → '
        'Save Edits → overwrite this file.</span>'
        '</div>'
    )

    # --- Header (project name + logo) ---
    parts.append('<header class="page-header">')
    parts.append('<div class="page-header-text">')
    parts.append(
        f'<h1>{_editable_text("project_name", project_name, cls="h1-input")}</h1>'
    )
    parts.append('<div class="subhead">')
    parts.append(
        f'{_editable_text("job_number", job_number, cls="job-input")}'
        ' · Project Context'
    )
    parts.append('</div></div>')
    if logo_tag:
        parts.append(f'<div class="page-header-logo">{logo_tag}</div>')
    parts.append('</header>')

    # --- Basics ---
    parts.append(_card_open('Basics'))
    parts.append('<div class="field-grid">')
    parts.append(_field_row(
        'Contractual Completion Date',
        _editable_text('contractual_completion', contractual_completion),
    ))
    parts.append(_field_row(
        'Procore Project ID',
        _editable_text('procore_project_id', str(procore_project_id),
                       placeholder='e.g. 2646569'),
    ))
    parts.append(_field_row(
        'Procore Company ID',
        _locked_text('procore_company_id', str(procore_company_id),
                     cls='locked-input'),
        note='Locked',
    ))
    parts.append('</div>')
    parts.append(_card_close())

    # --- SmartPM URLs ---
    parts.append(_card_open('SmartPM'))
    parts.append('<div class="field-grid">')
    parts.append(_field_row(
        'Workspace URL',
        _editable_text('smartpm_url', smartpm_url,
                       placeholder='https://live.smartpmtech.com/.../workspace',
                       cls='url-input'),
    ))
    parts.append(_field_row(
        'Trends URL',
        _editable_text('smartpm_trends_url', smartpm_trends_url,
                       cls='url-input'),
    ))
    parts.append(_field_row(
        'Changelog URL',
        _editable_text('smartpm_changelog_url', smartpm_changelog_url,
                       cls='url-input'),
    ))
    parts.append('</div>')
    parts.append(_card_close())

    # --- Signer ---
    parts.append(_card_open('Signer'))
    parts.append('<div class="field-grid">')
    parts.append(_field_row(
        'Name',
        _editable_text('signer_name', signer_name),
    ))
    parts.append(_field_row(
        'Title',
        _editable_text('signer_title', signer_title),
    ))
    parts.append(_field_row(
        'Mobile (optional)',
        _editable_text('signer_mobile', signer_mobile,
                       placeholder='+1 801.555.1234'),
    ))
    parts.append('</div>')
    parts.append(_card_close())

    # --- Recipients ---
    parts.append(_card_open('Recipients'))
    parts.append('<p class="section-hint">Weekly schedule update email '
                 'recipients. Name is optional — when present, rendered as '
                 '<code>Name &lt;email@domain&gt;</code>.</p>')
    parts.append(_render_recipients('to_recipients', to_recipients, 'TO'))
    parts.append(_render_recipients('cc_recipients', cc_recipients, 'CC'))
    parts.append(_card_close())

    # (No expected_attachments section — the weekly preview HTML carries
    # attachments forward week over week via transition_attachments. On the
    # very first week for a project, the skill bootstraps by globbing all
    # PDFs/xlsms/xer in the dated folder; thereafter the user's edits flow
    # forward automatically.)

    # --- Graph Screenshots ---
    parts.append(_card_open('Graph Screenshots (order)'))
    parts.append(
        '<p class="section-hint">Performance graphs to embed in each weekly '
        'email, in display order. Filenames from <code>screenshots/</code> '
        'captured by the screenshots command.</p>'
    )
    parts.append(_render_string_list(
        'graph_screenshots', graph_screenshots,
        placeholder='e.g. 06-end-date-variance.png',
    ))
    parts.append(_card_close())

    # --- Project Log ---
    parts.append(_card_open('Project Log'))
    parts.append(
        '<p class="section-hint">Project-level events — scope changes, EOT '
        'filings, contract amendments, major decisions. Distinct from the '
        'weekly status narrative. Past entries lock once the calendar day '
        'rolls over.</p>'
    )
    parts.append(_render_project_log(project_log, today_iso))
    parts.append(_card_close())

    parts.append('<script>')
    parts.append(f"window.TODAY = '{_esc(today_iso)}';")
    parts.append(_script())
    parts.append('</script>')
    parts.append('</body></html>')
    return '\n'.join(parts)


def _card_open(title):
    return (
        f'<section class="card"><h2 class="card-title">{_esc(title)}</h2>'
        '<div class="card-body">'
    )


def _card_close():
    return '</div></section>'


def _field_row(label, input_html, note=''):
    note_html = f'<span class="field-note">{_esc(note)}</span>' if note else ''
    return (
        '<div class="field-row">'
        f'<label class="field-label">{_esc(label)}</label>'
        f'<div class="field-value">{input_html}{note_html}</div>'
        '</div>'
    )


# --- CSS ---------------------------------------------------------------

def _css():
    return f"""
* {{ box-sizing: border-box; }}
body {{
  font-family: Arial, sans-serif; font-size: 11pt; color: #111;
  max-width: 980px; margin: 0 auto; padding: 20px;
  background: #f7f7f7;
}}

/* Sticky action bar */
.toolbar {{
  position: sticky; top: 0; z-index: 99;
  background: #fff; border: 1px solid #ccc;
  padding: 10px 14px; margin-bottom: 12px;
  border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.05);
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
}}
.toolbar button {{
  font-size: 14px; padding: 8px 14px; cursor: pointer;
  border: 1px solid {TEAL}; background: {TEAL}; color: #fff;
  border-radius: 4px;
}}
.toolbar button:hover {{ background: #0d627e; }}
.toolbar-hint {{ color: #555; font-size: 12px; }}

/* Page header */
.page-header {{
  display: flex; align-items: flex-start; gap: 20px;
  background: #fff; border: 1px solid #ddd; border-radius: 6px;
  padding: 20px 26px; margin-bottom: 14px;
}}
.page-header-text {{ flex: 1 1 auto; min-width: 0; }}
.page-header h1 {{
  color: {TEAL}; font-size: 22pt; font-weight: bold;
  margin: 0; line-height: 1.2;
}}
.h1-input {{
  font-size: 22pt; font-weight: bold; color: {TEAL};
  font-family: Arial, sans-serif; border: none;
  background: #fbfbfb; outline: 1px dashed #d0d7de;
  padding: 4px 8px; border-radius: 2px; width: 100%;
}}
.h1-input:focus {{ outline: 2px solid {TEAL}; background: #fffde7; }}
.subhead {{
  color: #666; font-size: 13pt; margin-top: 6px;
  display: flex; align-items: center; gap: 6px;
}}
.job-input {{
  width: 120px; font-family: Consolas, Menlo, monospace;
  font-size: 12pt; color: {TEAL}; font-weight: bold;
}}
.page-header-logo {{ flex: 0 0 auto; }}
.page-header-logo .logo {{ height: 72px; width: auto; display: block; }}

/* Section cards */
.card {{
  background: #fff; border: 1px solid #ddd; border-radius: 6px;
  padding: 16px 22px; margin-bottom: 14px;
}}
.card-title {{
  color: {TEAL}; font-size: 13pt; font-weight: bold;
  margin: 0 0 10px 0;
  border-bottom: 1px solid #eee; padding-bottom: 6px;
}}
.section-hint {{
  font-size: 11px; color: #555; margin: 4px 0 10px 0;
  line-height: 1.4;
}}
.section-hint code {{
  background: #f5f5f5; border: 1px solid #e0e0e0;
  padding: 1px 4px; border-radius: 2px;
  font-family: Consolas, Menlo, monospace; font-size: 11px;
}}

/* Field grid — 2-col label/value */
.field-grid {{ display: grid; grid-template-columns: 1fr; gap: 6px; }}
.field-row {{
  display: grid; grid-template-columns: 180px 1fr; gap: 12px;
  align-items: center;
}}
.field-label {{
  color: {TEAL}; font-weight: bold; font-size: 11pt;
}}
.field-value {{ display: flex; align-items: center; gap: 8px; }}
.field-value input[type="text"] {{
  flex: 1 1 auto; font-family: Arial, sans-serif; font-size: 11pt;
  padding: 4px 8px;
  background: #fbfbfb; outline: 1px dashed #d0d7de;
  border: none; border-radius: 2px;
}}
.field-value input[type="text"]:focus {{
  outline: 2px solid {TEAL}; background: #fffde7;
}}
.field-value input[type="text"].url-input {{
  font-family: Consolas, Menlo, monospace; font-size: 10pt;
}}
.field-value input[type="text"].locked-input {{
  background: #f0f0f0; color: #666; cursor: not-allowed;
  outline: 1px dashed #bbb;
}}
.field-note {{
  font-size: 10pt; color: #888; font-style: italic;
}}

/* Recipient rows */
.recipient-group {{ margin-bottom: 10px; }}
.recipient-label {{
  color: {TEAL}; font-weight: bold; font-size: 11pt;
  margin: 8px 0 4px 0;
}}
.recipient-list {{ margin-bottom: 4px; }}
.recipient-row {{
  display: flex; align-items: center; gap: 6px; margin-bottom: 3px;
  padding: 3px 6px; border-radius: 3px;
  position: relative;
}}
.recipient-row:hover {{ background: #f8f8f8; }}
.recipient-row .recipient-name {{
  flex: 0 0 220px; font-size: 10pt;
  padding: 4px 6px;
  background: #fbfbfb; outline: 1px dashed #d0d7de;
  border: none; border-radius: 2px;
}}
.recipient-row .recipient-email {{
  flex: 1 1 auto; font-family: Consolas, Menlo, monospace; font-size: 10pt;
  padding: 4px 6px;
  background: #fbfbfb; outline: 1px dashed #d0d7de;
  border: none; border-radius: 2px;
}}
.recipient-row input:focus {{
  outline: 2px solid {TEAL}; background: #fffde7;
}}

/* String lists (expected_attachments, graph_screenshots) */
.string-list-row {{
  display: flex; align-items: center; gap: 6px; margin-bottom: 3px;
  padding: 3px 6px; border-radius: 3px; position: relative;
}}
.string-list-row:hover {{ background: #f8f8f8; }}
.string-list-row input {{
  flex: 1 1 auto; font-family: Consolas, Menlo, monospace; font-size: 10pt;
  padding: 4px 6px;
  background: #fbfbfb; outline: 1px dashed #d0d7de;
  border: none; border-radius: 2px;
}}
.string-list-row input:focus {{
  outline: 2px solid {TEAL}; background: #fffde7;
}}

/* Drag handle — reuse pattern from email preview */
.drag-handle {{
  cursor: grab; color: #bbb; font-size: 14px;
  width: 18px; text-align: center;
  user-select: none; letter-spacing: -2px;
  font-family: monospace; line-height: 1;
  flex: 0 0 auto;
}}
.drag-handle:hover {{ color: #666; background: #eef1f3; border-radius: 2px; }}
.drag-handle:active {{ cursor: grabbing; color: {TEAL}; }}

/* Remove button */
.remove-btn {{
  font-size: 12px; color: {RED}; background: transparent;
  border: 1px solid transparent; border-radius: 2px;
  padding: 2px 6px; cursor: pointer;
  flex: 0 0 auto;
}}
.recipient-row:hover .remove-btn,
.string-list-row:hover .remove-btn {{
  border-color: {RED};
}}
.remove-btn:hover {{ background: #fce8e6; }}

.add-btn {{
  font-size: 11px; padding: 4px 10px; cursor: pointer;
  border: 1px solid #aaa; background: #f5f5f5; border-radius: 3px;
  margin-top: 4px;
}}
.add-btn:hover {{ background: #e9e9e9; }}

/* Project log */
.project-log .log-hint {{
  font-size: 11px; color: #555; font-style: italic;
  margin: 0 0 8px 0;
}}
.log-entries {{ margin-top: 10px; }}
.log-entry {{
  background: #fff; border: 1px solid #e0e0e0; border-radius: 4px;
  padding: 10px 14px; margin-bottom: 8px;
}}
.log-entry.locked {{
  background: #fafafa; border-color: #e8e8e8;
  opacity: 0.92;
}}
.log-entry-header {{
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 4px;
}}
.log-date {{
  color: {TEAL}; font-weight: bold; font-family: Consolas, Menlo, monospace;
  font-size: 11pt;
}}
.log-lock {{ color: #999; font-size: 10pt; }}
.log-body {{
  font-size: 11pt; line-height: 1.4;
  padding: 4px 6px; min-height: 1.5em;
  white-space: pre-wrap;
}}
.log-entry:not(.locked) .log-body {{
  background: #fbfbfb; outline: 1px dashed #d0d7de;
  border-radius: 2px;
}}
.log-entry:not(.locked) .log-body:focus {{
  outline: 2px solid {TEAL}; background: #fffde7;
}}
.log-entry.locked .log-body {{
  color: #333;
}}
.log-entry.locked .remove-btn {{ display: none; }}

/* Drop indicators for drag reorder */
.dragging {{ opacity: 0.4; }}
.drag-over-above::before,
.drag-over-below::after {{
  content: ''; position: absolute; left: 0; right: 0;
  height: 3px; background: {TEAL}; border-radius: 2px;
  pointer-events: none; z-index: 10;
}}
.drag-over-above::before {{ top: -4px; }}
.drag-over-below::after {{ bottom: -4px; }}

@media print {{
  body {{ background: #fff; max-width: none; padding: 0; }}
  .no-print {{ display: none !important; }}
  .card {{ border-color: #ccc; page-break-inside: avoid; }}
  .log-entry.locked {{ opacity: 1; }}
}}
"""


# --- JS ----------------------------------------------------------------

def _script():
    return r"""
// ---------- Add / remove / reorder ----------

function addRecipient(btn) {
  const group = btn.closest('.recipient-group');
  const list = group.querySelector('.recipient-list');
  const row = document.createElement('div');
  row.className = 'recipient-row';
  row.innerHTML = `
    <span class="drag-handle" draggable="true" title="Drag to reorder" aria-label="Drag">⋮⋮</span>
    <input type="text" data-field="recipient_name" value="" placeholder="Full name (optional)" class="recipient-name">
    <input type="text" data-field="recipient_email" value="" placeholder="email@domain" class="recipient-email">
    <button type="button" class="remove-btn no-print" onclick="removeRecipient(this)">×</button>
  `;
  list.appendChild(row);
  row.querySelector('.recipient-email').focus();
}
function removeRecipient(btn) { btn.closest('.recipient-row').remove(); }

function addStringListItem(btn) {
  const list = btn.closest('.string-list');
  const row = document.createElement('div');
  row.className = 'string-list-row';
  const ph = list.dataset.field === 'graph_screenshots'
    ? 'e.g. 06-end-date-variance.png'
    : 'e.g. Report 01*.pdf';
  row.innerHTML = `
    <span class="drag-handle" draggable="true" title="Drag to reorder" aria-label="Drag">⋮⋮</span>
    <input type="text" data-field="item_value" value="" placeholder="${ph}">
    <button type="button" class="remove-btn no-print" onclick="removeStringListItem(this)">×</button>
  `;
  list.insertBefore(row, list.querySelector('.add-btn'));
  row.querySelector('input').focus();
}
function removeStringListItem(btn) { btn.closest('.string-list-row').remove(); }

function addLogEntry(btn, todayIso) {
  const log = btn.closest('.project-log');
  const entries = log.querySelector('.log-entries');
  // Check for an existing today entry — focus it if present
  const existing = entries.querySelector(`.log-entry[data-date="${todayIso}"]:not(.locked)`);
  if (existing) { existing.querySelector('.log-body').focus(); return; }
  const div = document.createElement('div');
  div.className = 'log-entry';
  div.dataset.date = todayIso;
  div.innerHTML = `
    <div class="log-entry-header">
      <span class="log-date">${todayIso}</span>
      <button type="button" class="remove-btn no-print" onclick="removeLogEntry(this)" title="Remove">×</button>
    </div>
    <div class="log-body" contenteditable="true" data-field="log_body"></div>
  `;
  entries.insertBefore(div, entries.firstChild);
  div.querySelector('.log-body').focus();
}
function removeLogEntry(btn) {
  const entry = btn.closest('.log-entry');
  if (entry && !entry.classList.contains('locked')) entry.remove();
}

// Lock past log entries on load (defense-in-depth; server already sets
// contenteditable correctly, but the client may have added today's entry
// which becomes "past" next day).
function lockPastLogEntries() {
  const today = window.TODAY;
  document.querySelectorAll('.log-entry').forEach(entry => {
    const d = entry.dataset.date || '';
    if (d && d !== today) {
      entry.classList.add('locked');
      const body = entry.querySelector('.log-body');
      if (body) body.setAttribute('contenteditable', 'false');
    }
  });
}
document.addEventListener('DOMContentLoaded', lockPastLogEntries);
if (document.readyState !== 'loading') lockPastLogEntries();

// ---------- Drag and drop reorder ----------
let DRAG_SRC = null;
function _getDragItem(el) {
  return el.closest && el.closest('.recipient-row, .string-list-row, .log-entry:not(.locked)');
}
document.addEventListener('dragstart', (e) => {
  const handle = e.target.closest && e.target.closest('.drag-handle');
  if (!handle) return;
  const item = _getDragItem(handle);
  if (!item) return;
  DRAG_SRC = item;
  item.classList.add('dragging');
  e.dataTransfer.effectAllowed = 'move';
  try { e.dataTransfer.setData('text/plain', 'item'); } catch(_) {}
  try { e.dataTransfer.setDragImage(item, 20, 10); } catch(_) {}
});
document.addEventListener('dragend', () => {
  if (DRAG_SRC) DRAG_SRC.classList.remove('dragging');
  document.querySelectorAll('.drag-over-above,.drag-over-below').forEach(el => {
    el.classList.remove('drag-over-above', 'drag-over-below');
  });
  DRAG_SRC = null;
});
document.addEventListener('dragover', (e) => {
  if (!DRAG_SRC) return;
  const t = _getDragItem(e.target);
  if (!t || t === DRAG_SRC) return;
  if (t.parentElement !== DRAG_SRC.parentElement) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = 'move';
  const r = t.getBoundingClientRect();
  const above = (e.clientY - r.top) < r.height / 2;
  document.querySelectorAll('.drag-over-above,.drag-over-below').forEach(el => {
    if (el !== t) el.classList.remove('drag-over-above', 'drag-over-below');
  });
  t.classList.remove(above ? 'drag-over-below' : 'drag-over-above');
  t.classList.add(above ? 'drag-over-above' : 'drag-over-below');
});
document.addEventListener('drop', (e) => {
  if (!DRAG_SRC) return;
  const t = _getDragItem(e.target);
  if (!t || t === DRAG_SRC) return;
  if (t.parentElement !== DRAG_SRC.parentElement) return;
  e.preventDefault();
  const r = t.getBoundingClientRect();
  const above = (e.clientY - r.top) < r.height / 2;
  if (above) t.parentNode.insertBefore(DRAG_SRC, t);
  else t.parentNode.insertBefore(DRAG_SRC, t.nextSibling);
  t.classList.remove('drag-over-above', 'drag-over-below');
});

// ---------- Save / Copy ----------

function _buildSnapshotHtml() {
  document.querySelectorAll('input[type=text]').forEach(el => {
    el.setAttribute('value', el.value || '');
  });
  const clone = document.documentElement.cloneNode(true);
  return '<!DOCTYPE html>\n' + clone.outerHTML;
}

function _suggestedFilename() {
  const m = location.pathname.match(/[^/]+$/);
  return (m && m[0]) ? decodeURIComponent(m[0]) : 'project-context.html';
}

async function saveEdits() {
  const html = _buildSnapshotHtml();
  const blob = new Blob([html], {type: 'text/html;charset=utf-8'});
  if (window.showSaveFilePicker) {
    try {
      let handle = window._lastSaveHandle;
      if (!handle) {
        handle = await window.showSaveFilePicker({
          suggestedName: _suggestedFilename(),
          types: [{description: 'HTML', accept: {'text/html': ['.html']}}],
        });
        window._lastSaveHandle = handle;
      }
      const w = await handle.createWritable();
      await w.write(blob); await w.close();
      flash('Saved to ' + (handle.name || 'file') + '. Tell Claude "done".');
      return;
    } catch (e) {
      if (e.name === 'AbortError') return;
      console.warn(e);
      window._lastSaveHandle = null;
    }
  }
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = _suggestedFilename();
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
  flash('Downloaded. Overwrite the project-context.html in the Schedules folder.');
}

function collectFields() {
  const out = {};
  // Scalar text inputs
  document.querySelectorAll('input[type=text][data-field]').forEach(el => {
    const name = el.dataset.field;
    if (['recipient_name','recipient_email','item_value'].includes(name)) return;
    if (el.closest('.recipient-row') || el.closest('.string-list-row')) return;
    out[name] = (el.value || '').trim();
  });
  // Recipients
  ['to_recipients','cc_recipients'].forEach(field => {
    const group = document.querySelector(`.recipient-group[data-field="${field}"]`);
    if (!group) return;
    out[field] = Array.from(group.querySelectorAll('.recipient-row')).map(row => ({
      name: (row.querySelector('.recipient-name').value || '').trim(),
      email: (row.querySelector('.recipient-email').value || '').trim(),
    })).filter(r => r.email);
  });
  // String lists
  document.querySelectorAll('.string-list[data-field]').forEach(list => {
    const field = list.dataset.field;
    out[field] = Array.from(list.querySelectorAll('.string-list-row input')).map(i =>
      (i.value || '').trim()
    ).filter(Boolean);
  });
  // Project log
  out.project_log = Array.from(document.querySelectorAll('.log-entry')).map(entry => ({
    date: entry.dataset.date || '',
    body: (entry.querySelector('.log-body').innerText || '').trim(),
  })).filter(e => e.date);
  return out;
}

async function copyForClaude() {
  const data = collectFields();
  const json = JSON.stringify(data, null, 2);
  try { await navigator.clipboard.writeText(json); flash('Copied JSON.'); }
  catch (e) { prompt('Copy this JSON:', json); }
}

function flash(msg) {
  const existing = document.getElementById('flash-msg');
  if (existing) existing.remove();
  const div = document.createElement('div');
  div.id = 'flash-msg'; div.textContent = msg;
  div.style.cssText = 'position:fixed;top:60px;right:20px;background:#3A9E6B;color:#fff;' +
    'padding:12px 16px;border-radius:4px;z-index:10000;box-shadow:0 4px 8px rgba(0,0,0,0.15);' +
    'font-family:Arial;font-size:14px;max-width:340px;';
  document.body.appendChild(div);
  setTimeout(() => div.remove(), 5000);
}
"""


# --- Public API --------------------------------------------------------

def generate_project_context_html(output_path, context, *, today_iso=None,
                                   logo_path=None):
    """Write the editable project-context.html.

    Args:
        output_path: absolute or relative path to write.
        context: dict with project fields. Recipient fields may be either
            semicolon-separated strings (legacy) or lists of {name,email}.
        today_iso: 'YYYY-MM-DD' used to mark today's log entry as editable.
                   Defaults to today.
        logo_path: path to westland-logo.png (defaults to references/).
    """
    from datetime import date as _date
    if today_iso is None:
        today_iso = _date.today().isoformat()
    if logo_path is None:
        logo_path = DEFAULT_LOGO_PATH

    # Normalize recipients: accept string or list of dicts
    ctx = dict(context or {})
    for key in ('to_recipients', 'cc_recipients'):
        val = ctx.get(key)
        if isinstance(val, str):
            ctx[key] = parse_recipients_string(val)
        elif isinstance(val, list):
            # Accept either list of dicts or list of strings
            out = []
            for item in val:
                if isinstance(item, dict):
                    out.append({
                        'name': (item.get('name') or '').strip(),
                        'email': (item.get('email') or '').strip(),
                    })
                elif isinstance(item, str):
                    n, e = split_recipient(item)
                    out.append({'name': n, 'email': e})
            ctx[key] = out
        else:
            ctx[key] = []

    html = _build_html(ctx, today_iso, logo_path)
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return output_path
