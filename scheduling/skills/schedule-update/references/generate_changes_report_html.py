"""
Generate the Schedule Update Email (Change Report) — a rendered PDF of the
full weekly update email with inline red/green diff markup showing what
changed vs last week.

Structurally mirrors generate_email_msg._build_html_body (same sections,
inline styles, signature, screenshots) so the reader sees what the email
actually looks like — plus ins/del markup on narratives/lists where
Claude's content differed from last week's version.

Diff rendering rules:
    narratives with previous value + in changed_narrative_fields:
        rendered with word-level inline diff (<ins>/<del>)
    list items by status (v2 lifecycle: active -> removed -> dropped):
        active (no prev_idx match)          -> normal
        active + text differs from prev     -> inline word-level diff
        new + checked                       -> whole item wrapped in <ins>
        removed or active+unchecked         -> whole item wrapped in <del>
        archived                            -> omitted from the PDF

    key_items_archived is intentionally excluded from PDF output — archived
    items are hidden in the email body and the PDF alike; only the cloud
    editor exposes them.

Used at draft time. Entry point: `generate_changes_report_attachment(
output_path, ...)` — if output_path ends in .pdf it generates a sibling
.html, converts via html-to-pdf.js, deletes the .html on success, and
returns the .pdf path.
"""

import base64
import difflib
import html as html_mod
import os
import re
import subprocess
from pathlib import Path


def _file_uri(abs_path):
    # Path.as_uri emits RFC 8089 file URLs that work for UNC, drive, and
    # POSIX. Manual `'file:///' + p.replace('\\','/').lstrip('/')` mangled
    # UNC roots (\\orem-fs\Common\... became file:///orem-fs/... which
    # Chromium 404s on, blocking changes-report PDF on every project that
    # lives on the share). See post-mortem 2026-05-07 W1177 #1+#2.
    return Path(abs_path).as_uri()

# Westland brand colors (match generate_email_msg.py)
RED = '#C94444'
GREEN = '#3A9E6B'
TEAL = '#0B4F66'
AMBER = '#d4a030'

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOGO_PATH = os.path.join(_SCRIPT_DIR, 'westland-logo.png')


def _esc(text):
    return html_mod.escape(str(text))


def _md_inline_to_html(text):
    """Passthrough — input is HTML from the cloud editor's Trix surface.

    Kept as a thin passthrough so existing render callsites don't change
    shape during the cloud-editor migration. New code should not call
    this — pass HTML through directly.
    """
    return text or ''


# --- HTML-aware word diff (used by the changes-report PDF for week-over-week
#     inline diff markup on edited narratives) ---

_FMT_TAGS = {'b', 'strong', 'i', 'em', 'span'}
_TOKEN_RE = re.compile(r'<(/?)(\w+)([^>]*)>|(\s+)|([^\s<]+)')


def _tokenize_html(html):
    """Split HTML into word-tokens carrying their formatting tags."""
    tokens = []
    stack = []
    for m in _TOKEN_RE.finditer(html or ''):
        close, name, attrs, ws, word = m.group(1, 2, 3, 4, 5)
        if name:
            lname = name.lower()
            if lname not in _FMT_TAGS:
                tokens.append(m.group(0))
                continue
            if close == '/':
                for i in range(len(stack) - 1, -1, -1):
                    if stack[i][0] == lname:
                        stack.pop(i)
                        break
            else:
                stack.append((lname, m.group(0)))
        elif ws is not None:
            tokens.append(ws)
        elif word is not None:
            opening = ''.join(t[1] for t in stack)
            closing = ''.join(f'</{t[0]}>' for t in reversed(stack))
            tokens.append(opening + word + closing)
    return tokens


def _diff_ops(a, b, min_equal_words=5):
    """LCS-based opcodes with short-equal-run coalescing."""
    m, n = len(a), len(b)
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m):
        for j in range(n):
            dp[i + 1][j + 1] = (
                dp[i][j] + 1 if a[i] == b[j] else max(dp[i + 1][j], dp[i][j + 1])
            )
    raw = []
    i, j = m, n
    while i > 0 or j > 0:
        if i > 0 and j > 0 and a[i - 1] == b[j - 1]:
            raw.append(('equal', i - 1, i, j - 1, j)); i -= 1; j -= 1
        elif j > 0 and (i == 0 or dp[i][j - 1] >= dp[i - 1][j]):
            raw.append(('insert', i, i, j - 1, j)); j -= 1
        else:
            raw.append(('delete', i - 1, i, j, j)); i -= 1
    raw.reverse()
    merged = []
    for op in raw:
        if merged and merged[-1][0] == op[0]:
            last = merged[-1]
            merged[-1] = (last[0], last[1], op[2], last[3], op[4])
        else:
            merged.append(op)
    out = []
    k = 0
    while k < len(merged):
        cur = merged[k]
        nxt = merged[k + 1] if k + 1 < len(merged) else None
        if cur[0] == 'delete' and nxt and nxt[0] == 'insert':
            out.append(('replace', cur[1], cur[2], nxt[3], nxt[4]))
            k += 2
        else:
            out.append(cur); k += 1
    if min_equal_words > 0:
        out = _coalesce_small_equals(out, a, b, min_equal_words)
    return out


def _coalesce_small_equals(ops, a_tokens, b_tokens, min_equal_words):
    out = list(ops)
    changed = True
    while changed:
        changed = False
        for idx in range(1, len(out) - 1):
            op = out[idx]
            if op[0] != 'equal':
                continue
            prev_op = out[idx - 1]
            next_op = out[idx + 1]
            if prev_op[0] == 'equal' or next_op[0] == 'equal':
                continue
            wc = 0
            for k in range(op[1], op[2]):
                tok = a_tokens[k] if k < len(a_tokens) else ''
                if tok and tok.strip():
                    wc += 1
            if wc >= min_equal_words:
                continue
            a_start = op[1] if prev_op[0] == 'insert' else prev_op[1]
            a_end = op[2] if next_op[0] == 'insert' else next_op[2]
            b_start = op[3] if prev_op[0] == 'delete' else prev_op[3]
            b_end = op[4] if next_op[0] == 'delete' else next_op[4]
            out[idx - 1:idx + 2] = [('replace', a_start, a_end, b_start, b_end)]
            changed = True
            break
    return out


def _diff_html(baseline_html, current_html):
    """Return diffed HTML with <ins class="diff-ins">/<del class="diff-del">."""
    a = _tokenize_html(baseline_html)
    b = _tokenize_html(current_html)
    parts = []
    for op, i1, i2, j1, j2 in _diff_ops(a, b):
        if op == 'equal':
            parts.append(''.join(a[i1:i2]))
        elif op == 'delete':
            parts.append(f'<del style="{_DEL_STYLE}">' + ''.join(a[i1:i2]) + '</del>')
        elif op == 'insert':
            parts.append(f'<ins style="{_INS_STYLE}">' + ''.join(b[j1:j2]) + '</ins>')
        elif op == 'replace':
            parts.append(f'<del style="{_DEL_STYLE}">' + ''.join(a[i1:i2]) + '</del>')
            parts.append(f'<ins style="{_INS_STYLE}">' + ''.join(b[j1:j2]) + '</ins>')
    return ''.join(parts)


# Inline styles — kept identical in the preview + PDF for parity
_INS_STYLE = (
    f'background:#eafaf0; color:#2d7a4f; '
    f'text-decoration:underline; text-decoration-color:{GREEN}; '
    'padding:0 2px; border-radius:2px;'
)
_DEL_STYLE = (
    f'background:#fce8e6; color:#9a3333; '
    f'text-decoration:line-through; text-decoration-color:{RED}; '
    'padding:0 2px; border-radius:2px;'
)


# --- Helpers to render narratives and list items with diff ------------

def _narrative_html(field_name, current, previous_narratives, changed_fields):
    """Return the narrative HTML, with word-level diff if the field changed."""
    if field_name in changed_fields:
        prev = (previous_narratives or {}).get(field_name, '') or ''
        if prev.strip() and prev.strip() != (current or '').strip():
            return _diff_html(
                _md_inline_to_html(prev), _md_inline_to_html(current)
            )
    return _md_inline_to_html(current)


def _enrich_with_previous_text(items, last_week_items):
    """Return a new list of item dicts with `previous_text` resolved from prev_idx.

    For each item that has a valid `prev_idx` into `last_week_items`, a copy of
    the item dict is returned with `previous_text` set to the prior item's text.
    Items without a valid prev_idx are returned as-is (shallow copy).  The
    caller's input is never mutated.

    If `last_week_items` is None or empty, all items are returned without
    previous_text (correct for week-1 of v2 where there is no last_week).
    """
    result = []
    for item in (items or []):
        idx = item.get('prev_idx')
        if (
            idx is not None
            and last_week_items
            and 0 <= idx < len(last_week_items)
        ):
            enriched = dict(item)
            enriched['previous_text'] = last_week_items[idx].get('text', '')
            result.append(enriched)
        else:
            result.append(dict(item))
    return result


def _classify_item(item):
    """Return (kind, content_html) for a list item.

    kind: 'new' | 'removed' | 'edited' | 'normal'
    content_html: the inner HTML for the line (text + inline diff spans)

    Expects `previous_text` to have been pre-resolved onto the item dict via
    _enrich_with_previous_text before calling this function.
    """
    text = item.get('text', '')
    prev = item.get('previous_text', '') or ''
    status = (item.get('status') or 'active').lower()
    checked = item.get('checked', True)
    if status == 'new' and checked:
        return 'new', _md_inline_to_html(text)
    if status == 'removed' or (not checked and status != 'archived'):
        # Muted red text + strikethrough — NO filled background (avoids the
        # "boxed" look; the red dash marker already signals removal).
        return 'removed', (
            f'<span style="color:#9a3333; text-decoration:line-through;">'
            f'{_md_inline_to_html(text)}</span>'
        )
    if prev and prev.strip() != text.strip():
        return 'edited', _diff_html(
            _md_inline_to_html(prev), _md_inline_to_html(text)
        )
    return 'normal', _md_inline_to_html(text)


def _render_list(items, ordered, font):
    """Render a list with manually-drawn markers so removed items don't
    consume a number slot and new items get a green marker.

    Marker rules:
        normal   -> plain bullet/number
        new      -> GREEN bullet/number (bold)
        edited   -> AMBER bullet/number (bold) — inline diff shows the edits
        removed  -> RED em-dash (no number; removed items are skipped from
                    the running count)
    No item-level outline or background: the only boxed styling lives on
    inline <ins>/<del> spans inside edited items.
    """
    items = items or []
    visible = [
        it for it in items
        if (it.get('status') or 'active').lower() != 'archived'
    ]
    if not visible:
        return ''

    ul_style = 'list-style:none; padding-left:24pt; margin:0 0 6pt 0;'
    li_style = (
        f'{font} color:#000000; text-indent:-24pt; padding-left:24pt; '
        'margin-bottom:3pt;'
    )
    marker_base = (
        'display:inline-block; width:20pt; text-align:right; '
        'padding-right:4pt;'
    )

    out = [f'<ul style="{ul_style}">']
    counter = 0
    for it in visible:
        kind, content = _classify_item(it)

        if kind == 'removed':
            marker_text = '—'
            marker_color = RED
            marker_weight = 'bold'
        elif kind == 'new':
            counter += 1
            marker_text = (f'{counter}.' if ordered else '•')
            marker_color = GREEN
            marker_weight = 'bold'
        elif kind == 'edited':
            counter += 1
            marker_text = (f'{counter}.' if ordered else '•')
            marker_color = AMBER
            marker_weight = 'bold'
        else:  # normal
            counter += 1
            marker_text = (f'{counter}.' if ordered else '•')
            marker_color = '#000000'
            marker_weight = 'normal'

        marker = (
            f'<span style="{marker_base} color:{marker_color}; '
            f'font-weight:{marker_weight};">{_esc(marker_text)}</span>'
        )
        out.append(f'<li style="{li_style}">{marker}{content}</li>')
    out.append('</ul>')
    return '\n'.join(out)



def _render_attachments_list(attachments, heading_style, font):
    """Bulleted list of attached files using the same marker style as lists:
    green • for new, red — for removed, plain • otherwise."""
    items = attachments or []
    visible = [
        a for a in items
        if (a.get('status') or 'active').lower() != 'archived'
    ]
    if not visible:
        return ''

    ul_style = 'list-style:none; padding-left:20pt; margin:0 0 6pt 0;'
    li_style = (
        f'{font} color:#000000; text-indent:-20pt; padding-left:20pt; '
        'margin-bottom:2pt;'
    )
    marker_base = (
        'display:inline-block; width:16pt; text-align:right; '
        'padding-right:4pt;'
    )

    out = [f'<p style="{heading_style} margin:12pt 0 4pt 0;">Attachments:</p>']
    out.append(f'<ul style="{ul_style}">')
    for a in visible:
        filename = a.get('name') or a.get('filename', '')
        if not filename:
            continue
        status = (a.get('status') or 'active').lower()
        checked = a.get('checked', True)
        is_new = (status == 'new' and checked)
        is_removed = (status == 'removed' or (not checked and status != 'archived'))

        if is_removed:
            marker_text = '—'
            marker_color = RED
            marker_weight = 'bold'
            content = (
                f'<span style="color:#9a3333; text-decoration:line-through;">'
                f'{_esc(filename)}</span>'
            )
        elif is_new:
            marker_text = '•'
            marker_color = GREEN
            marker_weight = 'bold'
            content = _esc(filename)
        else:
            marker_text = '•'
            marker_color = '#000000'
            marker_weight = 'normal'
            content = _esc(filename)
        marker = (
            f'<span style="{marker_base} color:{marker_color}; '
            f'font-weight:{marker_weight};">{marker_text}</span>'
        )
        out.append(f'<li style="{li_style}">{marker}{content}</li>')
    out.append('</ul>')
    return '\n'.join(out)


def _build_signature(signer_name, signer_title, signer_mobile, logo_path):
    """Westland signature with the logo embedded as base64 (so the PDF doesn't
    need the logo file nearby at render time)."""
    logo_tag = ''
    if logo_path and os.path.isfile(logo_path):
        with open(logo_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('ascii')
        logo_tag = (
            f'<p style="margin:0; font-family:Arial,sans-serif; font-size:11pt;">'
            f'<a href="http://www.westlandconstruction.com/" style="color:black;">'
            f'<img src="data:image/png;base64,{b64}" width="110" height="52" '
            f'style="width:110pt; height:52pt; border:0;"></a></p>'
        )
    phone_html = f'<b style="color:{TEAL};">O</b>&nbsp;+1 801.374.6085'
    if signer_mobile:
        phone_html += (
            f'&nbsp;&nbsp;&nbsp;&nbsp;<b style="color:{TEAL};">M</b>&nbsp;'
            f'{_esc(signer_mobile)}'
        )
    return '\n'.join([
        '<table style="border-collapse:collapse; border-spacing:0;'
        ' width:508pt; box-sizing:border-box; margin-top:12pt;"><tbody><tr>',
        '<td rowspan="5" style="border-right:1.5pt solid #A5A5A5;'
        ' padding-right:5.4pt; padding-left:5.4pt; vertical-align:top;'
        ' width:120pt;">',
        logo_tag,
        '</td>',
        '<td style="padding-right:5.4pt; padding-left:5.4pt; width:388pt;">'
        '<p style="margin:0; font-family:Arial,sans-serif; font-size:10pt;">'
        f'<b style="color:black;">{_esc(signer_name)} | </b>'
        f'<b style="color:{TEAL};">{_esc(signer_title)}</b></p></td></tr>',
        '<tr><td style="padding-right:5.4pt; padding-left:5.4pt; width:388pt;">'
        f'<p style="margin:0; font-family:Arial,sans-serif; font-size:9pt; color:{TEAL};">'
        '1411 West 1250 South,&nbsp;Suite 200</p></td></tr>',
        '<tr><td style="padding-right:5.4pt; padding-left:5.4pt; width:388pt;">'
        f'<p style="margin:0; font-family:Arial,sans-serif; font-size:9pt; color:{TEAL};">'
        'Orem, Utah&nbsp;&nbsp; 84058&nbsp;&nbsp;&nbsp; USA</p></td></tr>',
        '<tr><td style="padding-right:5.4pt; padding-left:5.4pt; width:388pt;">'
        '<p style="margin:0; font-family:Arial,sans-serif; font-size:9pt;">'
        f'{phone_html}&nbsp;&nbsp;&nbsp;</p></td></tr>',
        '<tr><td style="padding-right:5.4pt; padding-left:5.4pt; width:388pt;">'
        '<p style="margin:0; font-family:\'Arial Nova Cond Light\',Arial,sans-serif;'
        ' font-size:9pt;"><i>Building the Westland Way</i></p></td></tr>',
        '</tbody></table>',
    ])


# --- Main body builder -----------------------------------------------

def _prev_metric_html(kind, previous, current):
    """Return '<strike>was X</strike> ' for a changed metric, or ''.

    Neutral gray strikethrough — no red/green background — so the current
    metric's own red-for-behind/green-for-ahead color convention still reads
    cleanly alongside the diff indicator. `kind` is 'days_behind' or
    'gain_loss' (controls how the previous value is phrased).
    """
    if previous is None or previous == current:
        return ''
    if kind == 'days_behind':
        if previous > 0:
            prev_phrase = f'{previous} Days'
        elif previous < 0:
            prev_phrase = f'{abs(previous)} Days ahead'
        else:
            prev_phrase = 'on schedule'
    elif kind == 'gain_loss':
        if previous > 0:
            prev_phrase = f'{previous} Day gain'
        elif previous < 0:
            prev_phrase = f'{abs(previous)} Day loss'
        else:
            prev_phrase = 'no change'
    else:
        prev_phrase = str(previous)
    return (
        f'<span style="color:#888; text-decoration:line-through; '
        f'font-weight:normal; font-size:11pt;">was {_esc(prev_phrase)}</span> '
    )


def _build_diff_email_body(*,
        project_info, days_behind, gain_loss,
        previous_days_behind, previous_gain_loss,
        successes, gain_loss_narrative, eot_recovery, logic_changes,
        smartpm_changelog_url,
        red_flags, stalled_tasks, key_items,
        closing_paragraphs_html, attachments,
        summary_screenshot_abs, graph_screenshot_abs,
        smartpm_project_url, smartpm_trends_url,
        signer_name, signer_title, signer_mobile,
        logo_path,
        previous_narratives, changed_narrative_fields):
    """Build the email body HTML (sections 1-12 + sign-off + signature)
    with inline ins/del markup on narratives and list items that changed
    from last week."""
    font = 'font-family:Arial,sans-serif; font-size:11pt;'
    heading = f'{font} font-size:12pt; font-weight:bold; color:{TEAL};'
    changed = set(changed_narrative_fields or [])
    prev_narr = previous_narratives or {}

    parts = []

    # --- Section 1: Project Info Header ---
    info_lines = [
        ('Project', 'project_name'),
        ('Job Number', 'job_number'),
        ('Contractual Completion Date', 'contractual_completion'),
        ('Projected Substantial Completion Date', 'projected_completion'),
    ]
    parts.append('<p style="margin:0 0 6pt 0;">')
    for label, key in info_lines:
        val = _esc(project_info.get(key, ''))
        parts.append(
            f'<span style="{font} color:{TEAL}; font-weight:bold;">'
            f'{_esc(label)}:</span> '
            f'<span style="{font} color:#000000;">{val}</span><br>'
        )
    parts.append('</p>')

    # --- Section 2: Days Ahead/Behind (with previous-week strikethrough) ---
    if days_behind > 0:
        value_color, label, value = RED, 'Days Behind Schedule', f'{days_behind} Days'
    elif days_behind < 0:
        value_color, label, value = GREEN, 'Days Ahead of Schedule', f'{abs(days_behind)} Days'
    else:
        value_color, label, value = GREEN, 'Days Ahead/Behind Schedule', 'On Schedule'
    prev_db_html = _prev_metric_html('days_behind', previous_days_behind, days_behind)
    parts.append(
        f'<p style="{font} font-weight:bold; font-size:12pt; margin:12pt 0 18pt 0;">'
        f'<span style="color:{TEAL};">{_esc(label)}:</span> '
        f'{prev_db_html}'
        f'<span style="color:{value_color};">{_esc(value)}</span></p>'
    )

    # --- Section 3: SmartPM Summary Report screenshot ---
    if summary_screenshot_abs and os.path.isfile(summary_screenshot_abs):
        src = _file_uri(summary_screenshot_abs)
        img_tag = (
            f'<img src="{_esc(src)}" '
            'style="display:block; border:0; width:100%; '
            'max-width:100%; height:auto;">'
        )
        if smartpm_project_url:
            parts.append(
                f'<p style="margin:0 0 12pt 0;">'
                f'<a href="{_esc(smartpm_project_url)}">{img_tag}</a></p>'
            )
        else:
            parts.append(f'<p style="margin:0 0 12pt 0;">{img_tag}</p>')

    # --- Section 4: Successes ---
    parts.append(f'<p style="{heading} margin:12pt 0 4pt 0;">Successes:</p>')
    parts.append(_render_list(successes, ordered=False, font=font))

    # --- Section 5: Gain/Loss line + narrative ---
    if gain_loss > 0:
        gl_color, gl_text = GREEN, f'{gain_loss} Day Gain'
    elif gain_loss < 0:
        gl_color, gl_text = RED, f'{abs(gain_loss)} Day Loss'
    else:
        gl_color, gl_text = GREEN, 'No change since last update.'
    prev_gl_html = _prev_metric_html('gain_loss', previous_gain_loss, gain_loss)
    parts.append(
        f'<p style="{heading} margin:12pt 0 4pt 0;">'
        'Schedule Gain / Loss Since The Last Update: '
        f'{prev_gl_html}'
        f'<span style="color:{gl_color};">{_esc(gl_text)}</span></p>'
    )
    gln = _narrative_html('gain_loss_narrative', gain_loss_narrative,
                          prev_narr, changed)
    if gln:
        parts.append(f'<p style="{font} margin:0 0 6pt 0;">{gln}</p>')

    # --- Section 6: EOT / Recovery ---
    parts.append(
        f'<p style="{heading} margin:12pt 0 4pt 0;">'
        'Status Of EOT / Recovery Efforts:</p>'
    )
    eot = _narrative_html('eot_recovery', eot_recovery, prev_narr, changed)
    if eot:
        parts.append(f'<p style="{font} margin:0 0 6pt 0;">{eot}</p>')

    # --- Section 7: Significant Logic Changes ---
    parts.append(
        f'<p style="{heading} margin:12pt 0 4pt 0;">'
        'Significant Changes To Schedule Logic:</p>'
    )
    lc = _narrative_html('logic_changes', logic_changes, prev_narr, changed)
    if lc:
        parts.append(f'<p style="{font} margin:0 0 6pt 0;">{lc}</p>')
    if smartpm_changelog_url:
        parts.append(
            f'<p style="{font} margin:0 0 2pt 0;">'
            'Please refer to the attached Analytics Report, or review schedule '
            'changes in SmartPM for specifics.</p>'
        )
        parts.append(
            f'<p style="{font} margin:0 0 6pt 0;">'
            f'<a href="{_esc(smartpm_changelog_url)}">'
            f'{_esc(smartpm_changelog_url)}</a></p>'
        )

    # --- Section 8: Red Flags ---
    parts.append(f'<p style="{heading} margin:12pt 0 4pt 0;">Red Flags:</p>')
    parts.append(_render_list(red_flags, ordered=True, font=font))

    # --- Section 9: Stalled/Slipping ---
    parts.append(
        f'<p style="{heading} margin:12pt 0 4pt 0;">'
        'Stalled Or Slipping Tasks:</p>'
    )
    parts.append(_render_list(stalled_tasks, ordered=True, font=font))

    # --- Section 10: Key Items ---
    parts.append(
        f'<p style="{heading} margin:12pt 0 4pt 0;">'
        'Key Items &amp; Issues To Focus On:</p>'
    )
    parts.append(_render_list(key_items, ordered=True, font=font))

    # --- Section 11: Performance Graphs ---
    parts.append(
        f'<p style="{heading} margin:12pt 0 4pt 0;">'
        'Schedule Performance Graphs:</p>'
    )
    parts.append(
        f'<p style="{font} margin:0 0 6pt 0;">'
        'The charts below show our actual starts and finishes compared to '
        'planned, schedule compression, and monthly activity finish '
        'distribution. You can get a better view of these charts and drill '
        'down to greater detail regarding specific activities and trade '
        'performance by logging on to SmartPM and clicking the View Trends '
        'link on the right side of the screen.</p>'
    )
    for gp in (graph_screenshot_abs or []):
        if not (gp and os.path.isfile(gp)):
            continue
        src = _file_uri(gp)
        img_tag = (
            f'<img src="{_esc(src)}" '
            'style="display:block; border:0; width:100%; '
            'max-width:100%; height:auto;">'
        )
        if smartpm_trends_url:
            parts.append(
                f'<p style="margin:6pt 0;">'
                f'<a href="{_esc(smartpm_trends_url)}">{img_tag}</a></p>'
            )
        else:
            parts.append(f'<p style="margin:6pt 0;">{img_tag}</p>')

    # --- Section 12: Closing paragraphs (pre-rendered HTML from editorial_to_kwargs) ---
    if closing_paragraphs_html:
        parts.append(closing_paragraphs_html)

    # --- Section 13: Attachments (simple bulleted list, not in change-report
    #     in the actual email body but useful in the PDF) ---
    att_html = _render_attachments_list(attachments, heading, font)
    if att_html:
        parts.append(att_html)

    # --- Closing + signature ---
    parts.append(
        f'<p style="{font} margin:12pt 0 0 0;">'
        'Please let me know if you have any questions.</p>'
    )
    parts.append(f'<p style="{font} margin:0;">&nbsp;</p>')
    parts.append(f'<p style="{font} margin:0 0 12pt 0;">Thanks,</p>')
    if signer_name:
        parts.append(_build_signature(
            signer_name, signer_title, signer_mobile, logo_path,
        ))
    return '\n'.join(parts)


def _resolve_abs(rel_or_abs, base_dir):
    """Resolve a relative path against base_dir; leave absolutes alone."""
    if not rel_or_abs:
        return ''
    if os.path.isabs(rel_or_abs):
        return rel_or_abs
    return os.path.normpath(os.path.join(base_dir, rel_or_abs))


def generate_changes_report(output_path, *, project_info, date_label,
                            days_behind=0, gain_loss=0,
                            previous_days_behind=None,
                            previous_gain_loss=None,
                            successes=None,
                            gain_loss_narrative='', eot_recovery='',
                            logic_changes='', smartpm_changelog_url='',
                            red_flags=None, stalled_tasks=None,
                            key_items=None, closing_paragraphs_html='',
                            summary_screenshot_rel='',
                            graph_screenshot_rels=None,
                            smartpm_project_url='', smartpm_trends_url='',
                            signer_name='', signer_title='',
                            signer_mobile='', logo_path=None,
                            changed_narrative_fields=None,
                            previous_narratives=None,
                            last_week_lists=None,
                            # Ignored in this body-first version; kept for
                            # kwarg-compat with earlier callers:
                            lists=None, attachments=None):
    """Write a self-contained HTML of the full update email with diff markup.

    Resolves screenshot paths relative to the output_path's directory so a
    sibling `screenshots/` folder renders correctly when Playwright converts
    the HTML to PDF.

    Args:
        last_week_lists: Optional dict keyed by list name
                         ('successes', 'red_flags', 'stalled_tasks',
                         'key_items') containing last week's item rows.
                         When provided, `previous_text` is resolved onto each
                         this-week item via its `prev_idx` so that
                         _classify_item can render inline ins/del diffs for
                         edited items.  Pass None (or omit) for week-1 of v2
                         when no prior email exists — items render without diff
                         overlays, which is correct behavior.
    """
    if logo_path is None:
        logo_path = DEFAULT_LOGO_PATH

    project_info = project_info or {}
    out_dir = os.path.dirname(os.path.abspath(output_path))

    # Back-compat: the old `lists` kwarg grouped lists by section title.
    if lists and not (successes or red_flags or stalled_tasks or key_items):
        successes = lists.get('Successes', successes)
        red_flags = lists.get('Red Flags', red_flags)
        stalled_tasks = lists.get('Stalled Or Slipping Tasks', stalled_tasks)
        key_items = lists.get('Key Items & Issues', key_items)

    # v2: pre-resolve previous_text onto items via prev_idx so _classify_item
    # can render inline ins/del diffs for edited items.
    lw = last_week_lists or {}
    successes = _enrich_with_previous_text(successes, lw.get('successes'))
    red_flags = _enrich_with_previous_text(red_flags, lw.get('red_flags'))
    stalled_tasks = _enrich_with_previous_text(
        stalled_tasks, lw.get('stalled_tasks')
    )
    key_items = _enrich_with_previous_text(key_items, lw.get('key_items'))

    summary_abs = _resolve_abs(summary_screenshot_rel, out_dir)
    graph_abs = [
        _resolve_abs(g, out_dir) for g in (graph_screenshot_rels or [])
    ]

    body = _build_diff_email_body(
        project_info=project_info,
        days_behind=days_behind, gain_loss=gain_loss,
        previous_days_behind=previous_days_behind,
        previous_gain_loss=previous_gain_loss,
        successes=successes or [],
        gain_loss_narrative=gain_loss_narrative,
        eot_recovery=eot_recovery,
        logic_changes=logic_changes,
        smartpm_changelog_url=smartpm_changelog_url,
        red_flags=red_flags or [],
        stalled_tasks=stalled_tasks or [],
        key_items=key_items or [],
        closing_paragraphs_html=closing_paragraphs_html or '',
        attachments=attachments or [],
        summary_screenshot_abs=summary_abs,
        graph_screenshot_abs=graph_abs,
        smartpm_project_url=smartpm_project_url,
        smartpm_trends_url=smartpm_trends_url,
        signer_name=signer_name, signer_title=signer_title,
        signer_mobile=signer_mobile,
        logo_path=logo_path,
        previous_narratives=previous_narratives,
        changed_narrative_fields=changed_narrative_fields,
    )

    title = (
        f'Schedule Update Email (Change Report) — '
        f'{project_info.get("project_name", "")} — {date_label}'
    )
    # Minimal title strip — filename-style date first, then the descriptor.
    # No background box, no heavy border — just a subtle bottom rule.
    date_prefix = f'{_esc(date_label)} ' if date_label else ''
    header = (
        '<div style="font-family:Arial,sans-serif; padding:0 0 10px 0;'
        ' margin-bottom:16px; border-bottom:1px solid #ddd;">'
        f'<div style="color:{TEAL}; font-size:13pt; font-weight:bold;">'
        f'{date_prefix}Schedule Update Email (Change Report)</div>'
        '<div style="color:#666; font-size:10pt; margin-top:3px;">'
        f'{_esc(project_info.get("project_name", ""))} · '
        f'{_esc(project_info.get("job_number", ""))} &nbsp;·&nbsp; '
        f'Additions in <span style="color:{GREEN}; font-weight:bold;">green</span>, '
        f'removals in <span style="color:{RED}; font-weight:bold;">red</span>.'
        '</div></div>'
    )

    html = (
        '<!DOCTYPE html>\n'
        '<html><head><meta charset="utf-8">'
        f'<title>{_esc(title)}</title>'
        '<style>@page { margin: 0.5in; } body { margin:0; padding:30px 40px; }</style>'
        '</head>'
        f'<body style="font-family:Arial,sans-serif; font-size:11pt; color:#000000;">'
        f'{header}{body}'
        '</body></html>'
    )

    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    return output_path


def html_to_pdf(html_path, pdf_path, timeout=60):
    """Convert a local HTML file to a PDF via Playwright's headless Chromium."""
    script = os.path.join(_SCRIPT_DIR, 'html-to-pdf.js')
    if not os.path.isfile(script):
        raise RuntimeError(f'html-to-pdf.js missing at {script}')
    try:
        result = subprocess.run(
            ['node', script, os.path.abspath(html_path),
             os.path.abspath(pdf_path)],
            cwd=_SCRIPT_DIR,
            capture_output=True, text=True, timeout=timeout, check=False,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            'Node.js not found on PATH. Install Node or run with Node available.'
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f'html-to-pdf timed out after {timeout}s') from exc
    if result.returncode != 0:
        raise RuntimeError(
            f'html-to-pdf failed (exit {result.returncode}):\n'
            f'STDOUT: {result.stdout}\nSTDERR: {result.stderr}'
        )
    if not os.path.isfile(pdf_path):
        raise RuntimeError(
            f'html-to-pdf reported success but PDF not written at {pdf_path}'
        )
    return pdf_path


def generate_changes_report_attachment(output_path, *, keep_html=False,
                                       **kwargs):
    """Generate the email change-report as HTML or PDF based on extension.

    - .pdf  → write sibling .html, convert via html-to-pdf.js, delete the
      .html on success. On conversion failure the .html stays for debugging.
    - .html → HTML only.
    """
    ext = os.path.splitext(output_path)[1].lower()
    if ext == '.pdf':
        html_path = os.path.splitext(output_path)[0] + '.html'
        generate_changes_report(html_path, **kwargs)
        html_to_pdf(html_path, output_path)
        if not keep_html and os.path.isfile(html_path):
            try:
                os.remove(html_path)
            except OSError:
                pass
        return output_path
    return generate_changes_report(output_path, **kwargs)
