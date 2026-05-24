"""
Generate a Westland Schedule Update Email as an Outlook draft.

Saves the email directly to the Outlook Drafts folder via COM automation.
The draft syncs to Exchange and appears in new Outlook — open Drafts, click Send.

Requires: pip install pywin32
Requires: Classic Microsoft Outlook installed and open on Windows.

Usage:
    from generate_email_msg import generate_update_email_msg

    generate_update_email_msg(
        output_path='Schedule Update Email - 2026-04-09',
        project_info={
            'project_name': 'Lubumbashi DRC Temple',
            'job_number': 'W1177',
            'contractual_completion': 'May 20, 2026',
            'projected_completion': 'December 10, 2026',
        },
        days_behind=204,
        gain_loss=-55,
        successes=['Catwalks and ladders delivered and installed.'],
        gain_loss_narrative='We lost 55 days since our last update...',
        eot_recovery='Trade nonperformance has been the primary issue...',
        logic_changes='Multiple changes to logic, sequencing...',
        smartpm_changelog_url='https://live.smartpmtech.com/...',
        red_flags=[
            '**Extended durations for work that should be complete.**',
            'Rework for several trades.',
        ],
        stalled_tasks=['Framing in each area is still not complete.'],
        key_items=[
            '**Material delays have been a constant concern.**',
            'Review production with OPI every single day.',
        ],
        include_compliance_report=True,
        include_procurement_sheets=True,
        summary_screenshot_path='screenshots/smartpm-summary-report.png',
        graph_screenshot_paths=[
            'screenshots/01-planned-vs-actual-percent-complete.png',
            'screenshots/07-schedule-compression-index-over-time.png',
        ],
        to_recipients='team@example.com',
        cc_recipients='director@example.com',
        subject='Schedule Update - Lubumbashi DRC Temple - 2026-04-09',
        smartpm_project_url='https://live.smartpmtech.com/project/workspace',
        smartpm_trends_url='https://live.smartpmtech.com/project/trends?tab=Graphs',
        signer_name='CAMRON WALKER',
        signer_title='SCHEDULER',
        signer_mobile='',
    )

List items carry HTML, not markdown.

    Item text is produced by the cloud editor's Trix surface and arrives
    here as HTML strings (e.g. `<strong>Steel delivery slipped two
    weeks.</strong>` or `<span style="color:#C94444;font-weight:bold">…
    </span>`). The builder passes this HTML through verbatim into the
    `<li>` element — Outlook's Word renderer respects inline span styles.

    Westland's priority conventions (canonical to scheduling/CLAUDE.md):
        <b>...</b>                                                       — bold
        <i>...</i>                                                       — italic
        <span style="background-color: #FFF4B8">...</span>               — highlight
        <span style="color: #9B2C2C">...</span>                          — important (Westland red)
"""

import os
import re
import html as html_mod
from datetime import date

try:
    import win32com.client
    HAS_WIN32COM = True
except ImportError:
    HAS_WIN32COM = False


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

# MAPI property tags for inline image attachments
PR_ATTACH_CONTENT_ID = "http://schemas.microsoft.com/mapi/proptag/0x3712001F"
PR_ATTACHMENT_HIDDEN = "http://schemas.microsoft.com/mapi/proptag/0x7FFE000B"

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
            f'{_esc(gain_loss_narrative)}</p>'
        )

    # --- Section 6: EOT / Recovery ---
    parts.append(
        f'<p style="{heading} margin:12pt 0 4pt 0;">'
        'Status Of EOT / Recovery Efforts:</p>'
    )
    if eot_recovery:
        parts.append(
            f'<p style="{font} margin:0 0 6pt 0;">{_esc(eot_recovery)}</p>'
        )

    # --- Section 7: Significant Logic Changes ---
    parts.append(
        f'<p style="{heading} margin:12pt 0 4pt 0;">'
        'Significant Changes To Schedule Logic:</p>'
    )
    if logic_changes:
        parts.append(
            f'<p style="{font} margin:0 0 6pt 0;">{_esc(logic_changes)}</p>'
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


def _attach_inline_image(mail, image_path, cid_name):
    """Attach an image as an inline CID attachment.

    Sets MAPI properties so the image displays in the email body
    (via cid: reference) and is hidden from the attachment pane.
    """
    abs_path = os.path.abspath(image_path)
    mail.Attachments.Add(abs_path)
    attachment = mail.Attachments.Item(mail.Attachments.Count)
    pa = attachment.PropertyAccessor
    pa.SetProperty(PR_ATTACH_CONTENT_ID, cid_name)
    pa.SetProperty(PR_ATTACHMENT_HIDDEN, True)


def generate_update_email_msg(
    output_path,
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
    closing_paragraphs_html='',
    summary_screenshot_path=None,
    graph_screenshot_paths=None,
    to_recipients='',
    cc_recipients='',
    subject='',
    attachment_paths=None,
    smartpm_project_url='',
    smartpm_trends_url='',
    signer_name='CAMRON WALKER',
    signer_title='SCHEDULER',
    signer_mobile='',
    logo_path=None,
    from_address='',
    salutation='',
    prev_days_behind=None,
    prev_gain_loss=None,
):
    """Generate a Westland schedule update email as an Outlook draft.

    Creates an Outlook MailItem via COM automation, populates it with an
    HTML body containing color-coded status lines, inline CID images,
    and a Westland email signature, then saves it to the Outlook Drafts
    folder. The draft syncs to Exchange and appears in new Outlook —
    open Drafts and click Send.

    Item text arrives as HTML — use inline spans for high priority
    (see scheduling/CLAUDE.md "Email JSON shape" for the canonical
    `<strong>` / priority-red / highlight conventions).

    Args:
        output_path: Identifier for this email (not saved to disk)
        project_info: Dict with keys: project_name, job_number,
                      contractual_completion, projected_completion
        days_behind: Positive = behind (red), negative = ahead (green)
        gain_loss: Positive = days gained (green), negative = days lost (red)
        successes: List of item dicts ({text, checked, status, prev_idx})
        gain_loss_narrative: Explanation of what drove the gain/loss
        eot_recovery: EOT / recovery efforts narrative
        logic_changes: Significant logic changes narrative
        smartpm_changelog_url: URL to SmartPM change log
        red_flags: List of item dicts
        stalled_tasks: List of item dicts
        key_items: List of item dicts
        include_compliance_report: Whether to include compliance report paragraph
        include_procurement_sheets: Whether to include procurement sheets paragraph
        closing_paragraphs_html: Pre-rendered HTML string for the closing
                                 paragraphs block (from editorial_to_kwargs)
        summary_screenshot_path: Path to SmartPM summary report PNG (optional)
        graph_screenshot_paths: List of paths to individual graph PNGs (optional)
        to_recipients: Semicolon-separated To addresses
        cc_recipients: Semicolon-separated CC addresses
        subject: Email subject line
        attachment_paths: List of file paths to attach (PDFs, Excel, etc.)
        smartpm_project_url: URL to hyperlink the summary screenshot
        smartpm_trends_url: URL to hyperlink the performance graph screenshots
        signer_name: Name for email signature (e.g. 'CAMRON WALKER')
        signer_title: Title for email signature (e.g. 'SCHEDULER')
        signer_mobile: Mobile phone for signature (optional, office is hardcoded)
        logo_path: Path to Westland logo PNG for signature (defaults to
                   references/westland-logo.png)
        from_address: Sender address (accepted for editorial_to_kwargs compat;
                      not applied to the COM MailItem — Outlook uses the
                      default account).
        salutation: Closing salutation line (e.g. 'Thanks,')
        prev_days_behind: Previous week's days_behind for strikethrough badge
        prev_gain_loss: Previous week's gain_loss for strikethrough badge

    Returns:
        The output_path identifier.

    Raises:
        ImportError: If pywin32 is not installed.
        RuntimeError: If Outlook is not available via COM.
    """
    if not HAS_WIN32COM:
        raise ImportError(
            'pywin32 is required for .msg generation. '
            'Install with: pip install pywin32'
        )

    # Resolve logo path
    if logo_path is None:
        logo_path = DEFAULT_LOGO_PATH
    has_logo = bool(logo_path and os.path.isfile(logo_path))

    # Resolve screenshot availability
    has_summary = bool(
        summary_screenshot_path and os.path.isfile(summary_screenshot_path)
    )

    # Build list of available graph screenshots with CID names
    graph_images = []  # [(path, cid_name), ...]
    for i, gpath in enumerate(graph_screenshot_paths or []):
        if gpath and os.path.isfile(gpath):
            cid_name = f'graph_{i}'
            graph_images.append((gpath, cid_name))

    # Build HTML body
    html_body = _build_html_body(
        project_info=project_info,
        days_behind=days_behind,
        gain_loss=gain_loss,
        successes=successes,
        gain_loss_narrative=gain_loss_narrative,
        eot_recovery=eot_recovery,
        logic_changes=logic_changes,
        smartpm_changelog_url=smartpm_changelog_url,
        red_flags=red_flags,
        stalled_tasks=stalled_tasks,
        key_items=key_items,
        include_compliance_report=include_compliance_report,
        include_procurement_sheets=include_procurement_sheets,
        has_summary_screenshot=has_summary,
        graph_cid_names=[cid for _, cid in graph_images],
        smartpm_project_url=smartpm_project_url,
        smartpm_trends_url=smartpm_trends_url,
        signer_name=signer_name,
        signer_title=signer_title,
        signer_mobile=signer_mobile,
        has_logo=has_logo,
        closing_paragraphs_html=closing_paragraphs_html,
        salutation=salutation,
        prev_days_behind=prev_days_behind,
        prev_gain_loss=prev_gain_loss,
    )

    # Create Outlook MailItem via COM
    try:
        outlook = win32com.client.Dispatch('Outlook.Application')
    except Exception as exc:
        raise RuntimeError(
            'Could not connect to Outlook. Make sure Outlook is installed '
            f'and running. Error: {exc}'
        ) from exc

    mail = outlook.CreateItem(0)  # 0 = olMailItem

    # Set envelope fields
    if to_recipients:
        mail.To = to_recipients
    if cc_recipients:
        mail.CC = cc_recipients
    subject = _ensure_subject_has_date(subject)
    if subject:
        mail.Subject = subject

    # Attach inline images first (before setting HTMLBody)
    if has_logo:
        _attach_inline_image(mail, logo_path, 'westland_logo')
    if has_summary:
        _attach_inline_image(mail, summary_screenshot_path, 'summary_report')
    for img_path, cid_name in graph_images:
        _attach_inline_image(mail, img_path, cid_name)

    # Set HTML body (CID references resolve against attached images)
    mail.HTMLBody = html_body

    # Attach file attachments (PDFs, Excel, etc.) — skip Office temp lock files
    for path in (attachment_paths or []):
        if os.path.isfile(path) and not os.path.basename(path).startswith('~$'):
            mail.Attachments.Add(os.path.abspath(path))

    # Save draft to Outlook Drafts folder (syncs to Exchange → new Outlook)
    mail.Save()
    mail.Close(1)  # 1 = olDiscard — don't duplicate in Drafts

    return output_path
