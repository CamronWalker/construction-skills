"""
Westland schedule-update email — HTML body builder.

Builds the Outlook-compatible HTML body (inline styles only, for Outlook's
Word renderer) shared by the .eml writer in generate_email_eml.py. Item
text, the narrative fields, and closing paragraphs arrive as HTML from the
cloud editor's Trix surface and are passed through verbatim; _esc() is used
only for genuine non-HTML inputs (labels, addresses, project-info values,
URLs, metric badges).

Priority conventions (canonical in scheduling/CLAUDE.md "Email JSON shape"):
    <b>...</b>                                          — bold
    <i>...</i>                                          — italic
    <span style="background-color: #FFF4B8">...</span>  — highlight
    <span style="color: #9B2C2C">...</span>             — important (Westland red)
"""

import os
import re
import html as html_mod
from datetime import date


# Subject must end with a YYYY-MM-DD date so each weekly schedule-update
# email starts a fresh Outlook conversation (Outlook groups by subject
# stem; identical subjects collapse into one thread). The regex catches
# both ISO dates and the trailing form used in Westland's house style
# ("...Schedule Update - 2026-05-20").
_SUBJECT_DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}\s*$')


def _ensure_subject_has_date(subject, today=None):
    """Return `subject` with a trailing YYYY-MM-DD date guaranteed.

    - Empty `subject` is returned unchanged so callers that intentionally
      leave it blank (e.g. tests, Outlook-pick-default cases) aren't surprised.
    - If `subject` already ends with a YYYY-MM-DD, it's left alone.
    - Otherwise today's date is appended as ` - YYYY-MM-DD`.

    `today` is an injection point for tests; defaults to `date.today()`.
    """
    if not subject:
        return subject
    if _SUBJECT_DATE_RE.search(subject):
        return subject
    today = today or date.today()
    return f'{subject.rstrip()} - {today.isoformat()}'

# Westland brand colors
RED = '#C94444'
YELLOW = '#D4A030'
GREEN = '#3A9E6B'
TEAL = '#0B4F66'

# Default logo path (relative to this script's directory)
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_LOGO_PATH = os.path.join(_SCRIPT_DIR, 'westland-logo.png')

def _esc(text):
    """HTML-escape text — used only for labels, addresses, and other
    non-HTML inputs. Item text and custom-paragraph body text already
    arrive as HTML and are passed through verbatim (see scheduling/CLAUDE.md
    "Email JSON shape")."""
    return html_mod.escape(str(text))


def _build_signature(signer_name, signer_title, signer_mobile, has_logo):
    """Build the Westland email signature HTML block."""
    sig = []
    sig.append(
        '<table style="border-collapse:collapse; border-spacing:0; '
        'width:508pt; box-sizing:border-box;">'
        '<tbody><tr>'
    )

    # Left cell: logo with right border
    sig.append(
        '<td rowspan="5" style="border-right:1.5pt solid #A5A5A5; '
        'padding-right:5.4pt; padding-left:5.4pt; vertical-align:top; '
        'width:120pt;">'
    )
    if has_logo:
        sig.append(
            '<p style="margin:0; font-family:Arial,sans-serif; font-size:11pt;">'
            '<a href="http://www.westlandconstruction.com/" style="color:black;">'
            '<img src="cid:westland_logo" width="110" height="52" '
            'style="width:110pt; height:52pt; border:0;"></a></p>'
        )
    sig.append('</td>')

    # Right cell row 1: Name | Title
    sig.append(
        '<td style="padding-right:5.4pt; padding-left:5.4pt; width:388pt;">'
        '<p style="margin:0; font-family:Arial,sans-serif; font-size:10pt;">'
        f'<b style="color:black;">{_esc(signer_name)} | </b>'
        f'<b style="color:{TEAL};">{_esc(signer_title)}</b>'
        '</p></td></tr>'
    )

    # Right cell row 2: Address line 1
    sig.append(
        '<tr><td style="padding-right:5.4pt; padding-left:5.4pt; width:388pt;">'
        f'<p style="margin:0; font-family:Arial,sans-serif; font-size:9pt; color:{TEAL};">'
        '1411 West 1250 South,&nbsp;Suite 200</p></td></tr>'
    )

    # Right cell row 3: Address line 2
    sig.append(
        '<tr><td style="padding-right:5.4pt; padding-left:5.4pt; width:388pt;">'
        f'<p style="margin:0; font-family:Arial,sans-serif; font-size:9pt; color:{TEAL};">'
        'Orem, Utah&nbsp;&nbsp; 84058&nbsp;&nbsp;&nbsp; USA</p></td></tr>'
    )

    # Right cell row 4: Phone (office is fixed, mobile is per-person)
    phone_html = (
        f'<b style="color:{TEAL};">O</b>&nbsp;+1 801.374.6085'
    )
    if signer_mobile:
        phone_html += (
            f'&nbsp;&nbsp;&nbsp;&nbsp;<b style="color:{TEAL};">M</b>&nbsp;'
            f'{_esc(signer_mobile)}'
        )
    sig.append(
        '<tr><td style="padding-right:5.4pt; padding-left:5.4pt; width:388pt;">'
        '<p style="margin:0; font-family:Arial,sans-serif; font-size:9pt;">'
        f'{phone_html}&nbsp;&nbsp;&nbsp;</p></td></tr>'
    )

    # Right cell row 5: Tagline
    sig.append(
        '<tr><td style="padding-right:5.4pt; padding-left:5.4pt; width:388pt;">'
        '<p style="margin:0; font-family:\'Arial Nova Cond Light\',Arial,sans-serif; '
        'font-size:9pt;"><i>Building the Westland Way</i></p></td></tr>'
    )

    sig.append('</tbody></table>')
    return '\n'.join(sig)


def _build_html_body(
    project_info,
    days_behind=0,
    gain_loss=0,
    successes=None,
    gain_loss_narrative='',
    eot_recovery='',
    logic_changes='',
    smartpm_changelog_url='',
    red_flags=None,
    stalled_tasks=None,
    key_items=None,
    include_compliance_report=False,
    include_procurement_sheets=False,
    has_summary_screenshot=False,
    graph_cid_names=None,
    smartpm_project_url='',
    smartpm_trends_url='',
    signer_name='',
    signer_title='',
    signer_mobile='',
    has_logo=False,
    closing_paragraphs_html='',
    salutation='',
    prev_days_behind=None,
    prev_gain_loss=None,
):
    """Build an Outlook-compatible HTML email body.

    Uses inline styles only (no <style> blocks) for compatibility with
    Outlook's Word-based HTML renderer. Item text + custom-paragraph
    body text arrive as HTML (from the cloud editor's Trix surface) and
    are passed through verbatim — Outlook respects inline span styles
    for priority red / highlight.
    """
    successes = successes or []
    red_flags = red_flags or []
    stalled_tasks = stalled_tasks or []
    key_items = key_items or []

    font = 'font-family:Arial,sans-serif; font-size:11pt;'
    heading = f'{font} font-size:12pt; font-weight:bold; color:{TEAL};'
    parts = []

    parts.append(
        '<!DOCTYPE html>\n'
        '<html><head><meta charset="utf-8"></head>\n'
        f'<body style="{font} color:#000000;">\n'
    )

    # --- Section 1: Project Information Header ---
    # Labels in teal+bold, values in black
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

    # --- Section 2: Days Ahead/Behind Schedule (label teal, value colored) ---
    if days_behind > 0:
        value_color = RED
        label = 'Days Behind Schedule'
        value = f'{days_behind} Days'
    elif days_behind < 0:
        value_color = GREEN
        label = 'Days Ahead of Schedule'
        value = f'{abs(days_behind)} Days'
    else:
        value_color = GREEN
        label = 'Days Ahead/Behind Schedule'
        value = 'On Schedule'
    # Strikethrough previous-metric badge when last week's days_behind
    # is supplied and differs from this week's.
    prev_badge_html = ''
    if (prev_days_behind is not None
            and prev_days_behind != days_behind):
        prev_value = (
            f'{prev_days_behind} Days' if prev_days_behind > 0
            else f'{abs(prev_days_behind)} Days' if prev_days_behind < 0
            else 'On Schedule'
        )
        prev_badge_html = (
            f' <span style="color:#9a3333; text-decoration:line-through; '
            f'font-weight:normal; font-size:10pt;">'
            f'{_esc(prev_value)}</span>'
        )
    parts.append(
        f'<p style="{font} font-weight:bold; font-size:12pt; '
        f'margin:12pt 0 18pt 0;">'
        f'<span style="color:{TEAL};">{_esc(label)}:</span> '
        f'<span style="color:{value_color};">{_esc(value)}</span>'
        f'{prev_badge_html}'
        f'</p>'
    )

    # --- Section 3: SmartPM Summary Report ---
    if has_summary_screenshot:
        img_tag = '<img src="cid:summary_report" width="100%" style="display:block; border:0; width:100%; height:auto;">'
        if smartpm_project_url:
            parts.append(
                f'<p style="margin:0 0 12pt 0;">'
                f'<a href="{_esc(smartpm_project_url)}">{img_tag}</a></p>'
            )
        else:
            parts.append(f'<p style="margin:0 0 12pt 0;">{img_tag}</p>')
    else:
        parts.append(
            '<p style="margin:0 0 12pt 0; font-style:italic; color:#666666;">'
            '[Insert SmartPM Summary Report screenshot here &mdash; '
            'hyperlink to SmartPM project URL]</p>'
        )

    # --- Section 4: Successes ---
    parts.append(f'<p style="{heading} margin:12pt 0 4pt 0;">Successes:</p>')
    rendered_successes = _filter_list_items(successes)
    if rendered_successes:
        parts.append('<ul style="margin:0 0 6pt 0;">')
        for s in rendered_successes:
            # Same priority handling as the ordered lists below — keeps
            # `**...**` and `==...==` rendering consistently across all
            # four lists in the email.
            parts.append(_format_list_item(s, font))
        parts.append('</ul>')

    # --- Section 5: Gain / Loss (heading + value on same line) ---
    if gain_loss > 0:
        gl_color = GREEN
        gl_text = f'{gain_loss} Day Gain'
    elif gain_loss < 0:
        gl_color = RED
        gl_text = f'{abs(gain_loss)} Day Loss'
    else:
        gl_color = GREEN
        gl_text = 'No change since last update.'
    prev_gl_badge_html = ''
    if (prev_gain_loss is not None
            and prev_gain_loss != gain_loss):
        prev_gl_text = (
            f'{prev_gain_loss} Day Gain' if prev_gain_loss > 0
            else f'{abs(prev_gain_loss)} Day Loss' if prev_gain_loss < 0
            else 'No change since last update.'
        )
        prev_gl_badge_html = (
            f' <span style="color:#9a3333; text-decoration:line-through; '
            f'font-weight:normal; font-size:10pt;">'
            f'{_esc(prev_gl_text)}</span>'
        )
    parts.append(
        f'<p style="{heading} margin:12pt 0 4pt 0;">'
        f'Schedule Gain / Loss Since The Last Update: '
        f'<span style="color:{gl_color};">{_esc(gl_text)}</span>'
        f'{prev_gl_badge_html}</p>'
    )
    if gain_loss_narrative:
        parts.append(
            f'<p style="{font} margin:0 0 6pt 0;">'
            f'{gain_loss_narrative}</p>'
        )

    # --- Section 6: EOT / Recovery ---
    parts.append(
        f'<p style="{heading} margin:12pt 0 4pt 0;">'
        'Status Of EOT / Recovery Efforts:</p>'
    )
    if eot_recovery:
        parts.append(
            f'<p style="{font} margin:0 0 6pt 0;">{eot_recovery}</p>'
        )

    # --- Section 7: Significant Logic Changes ---
    parts.append(
        f'<p style="{heading} margin:12pt 0 4pt 0;">'
        'Significant Changes To Schedule Logic:</p>'
    )
    if logic_changes:
        parts.append(
            f'<p style="{font} margin:0 0 6pt 0;">{logic_changes}</p>'
        )
    if smartpm_changelog_url:
        parts.append(
            f'<p style="{font} margin:0 0 2pt 0;">'
            'Please refer to the attached Analytics Report, '
            'or review schedule changes in SmartPM for specifics.</p>'
        )
        parts.append(
            f'<p style="{font} margin:0 0 6pt 0;">'
            f'<a href="{_esc(smartpm_changelog_url)}">'
            f'{_esc(smartpm_changelog_url)}</a></p>'
        )

    # --- Section 8: Red Flags ---
    parts.append(f'<p style="{heading} margin:12pt 0 4pt 0;">Red Flags:</p>')
    parts.append(_build_list(red_flags, font))

    # --- Section 9: Stalled or Slipping Tasks ---
    parts.append(
        f'<p style="{heading} margin:12pt 0 4pt 0;">'
        'Stalled Or Slipping Tasks:</p>'
    )
    parts.append(_build_list(stalled_tasks, font))

    # --- Section 10: Key Items & Issues ---
    parts.append(
        f'<p style="{heading} margin:12pt 0 4pt 0;">'
        'Key Items &amp; Issues To Focus On:</p>'
    )
    parts.append(_build_list(key_items, font))

    # --- Section 11: Performance Graphs ---
    parts.append(
        f'<p style="{heading} margin:12pt 0 4pt 0;">'
        'Schedule Performance Graphs:</p>'
    )
    parts.append(
        f'<p style="{font} margin:0 0 6pt 0;">'
        'The charts below show our actual starts and finishes compared to planned, '
        'schedule compression, and monthly activity finish distribution. You can get '
        'a better view of these charts and drill down to greater detail regarding '
        'specific activities and trade performance by logging on to SmartPM and '
        'clicking the View Trends link on the right side of the screen.</p>'
    )

    graph_cids = graph_cid_names or []
    for cid_name in graph_cids:
        img_tag = (
            f'<img src="cid:{cid_name}" width="100%" '
            'style="display:block; border:0; width:100%; height:auto;">'
        )
        if smartpm_trends_url:
            parts.append(
                f'<p style="margin:6pt 0;">'
                f'<a href="{_esc(smartpm_trends_url)}">{img_tag}</a></p>'
            )
        else:
            parts.append(f'<p style="margin:6pt 0;">{img_tag}</p>')

    if not graph_cids:
        parts.append(
            '<p style="margin:6pt 0; font-style:italic; color:#666666;">'
            '[Insert SmartPM performance graph screenshots here &mdash; '
            'hyperlink to View Trends URL]</p>'
        )

    # --- Section 12: Closing Paragraphs ---
    # Closing paragraphs: pre-joined HTML from email_draft_io._join_closing_paragraphs
    # (or empty). Renders verbatim — the Trix editor emits inline-style HTML that
    # Outlook's Word renderer respects.
    closing_html_block = closing_paragraphs_html or ''
    if closing_html_block:
        parts.append(closing_html_block)

    # --- Closing ---
    salutation_html = salutation or 'Thanks,'
    # Blank spacer paragraph — Camron prefers a visible gap before the salutation.
    parts.append(f'<p style="{font} margin:0;">&nbsp;</p>')
    parts.append(f'<p style="{font} margin:0 0 12pt 0;">{salutation_html}</p>')

    # --- Email Signature ---
    if signer_name:
        parts.append(_build_signature(signer_name, signer_title,
                                      signer_mobile, has_logo))

    parts.append('</body></html>')
    return '\n'.join(parts)


def _format_list_item(item_text, font):
    """Return one `<li>` HTML string with item HTML passed through verbatim.

    Item text arrives as HTML (from the cloud editor's Trix surface);
    bold / priority-red / highlight are encoded as inline-style spans
    that Outlook's Word renderer respects. The builder does not
    transform the HTML — what the editor produced, the email renders.
    """
    return f'<li style="{font}">{item_text}</li>'


def _filter_list_items(items):
    """Normalize items (strings or {text,checked,status} dicts) into a
    list of plain strings, dropping unchecked / archived entries."""
    rendered = []
    for item in items or []:
        if isinstance(item, dict):
            if not item.get('checked', True):
                continue
            if item.get('status') == 'archived':
                continue
            rendered.append(item.get('text', ''))
        else:
            rendered.append(str(item))
    return rendered


def _build_list(items, font):
    """Build an HTML ordered list. Item text passes through as HTML.

    Accepts list items as plain HTML strings OR as dicts
    ({text, checked, status, ...}). Dict items that are unchecked or
    archived are skipped.
    """
    rendered = _filter_list_items(items)
    if not rendered:
        return ''
    lines = ['<ol style="margin:0 0 6pt 0;">']
    for item in rendered:
        lines.append(_format_list_item(item, font))
    lines.append('</ol>')
    return '\n'.join(lines)
