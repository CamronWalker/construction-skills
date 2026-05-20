"""
Generate a `.eml` file from a reviewed weekly schedule update preview.

Mirrors `generate_email_msg.generate_update_email_msg` (same kwargs,
same HTML body via the shared `_build_html_body`) but writes RFC 5322
to disk via `email.message.EmailMessage` instead of using Outlook COM.

Why this exists alongside the COM path:
    - Cowork sessions have no local Outlook to script. The `.eml` path
      writes a file the user double-clicks to open in classic or new
      Outlook for review and sending.
    - The `.eml` is portable — easy to archive, attach to a ticket, or
      hand to a colleague.
    - The COM path remains for users who want the draft auto-saved to
      Exchange Drafts (no double-click); see `generate_email_msg.py`.

Implementation notes baked in from the W1177 2026-05-07 test session:
    1. **Encode the HTML body as base64** (`cte='base64'`). Outlook's
       compose-mode loader (when `X-Unsent: 1` is set) mis-handles
       quoted-printable soft line breaks: `Bu=\\r\\nilding` renders as
       `Bu=ilding`. Base64 has no wrapping side effects.
    2. **Don't pass `filename=` to `add_related()` for inline images.**
       With `filename=` set, the part gets `Content-Disposition:
       attachment` AND `Content-ID`, so Outlook shows the image both
       inline and in the attachment pane (and sometimes neither
       reliably). Inline-only parts must have just `cid` and data.
    3. **`X-Unsent: 1`** tells Outlook this is a draft, not a sent
       message — opening the file lands you in compose mode, with
       To/Cc/Subject editable and a real Send button.
"""

from __future__ import annotations

import mimetypes
import os
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

# Reuse the canonical HTML body builder from the COM path so the email
# bytes are identical regardless of which output format the caller
# picks. If the body ever needs to diverge (e.g. .eml-specific quirks),
# revisit — but right now the lesson is "two paths, one body".
from generate_email_msg import (
    _build_html_body,
    _ensure_subject_has_date,
    DEFAULT_LOGO_PATH,
)


_INLINE_LOGO_CID = 'westland_logo'
_INLINE_SUMMARY_CID = 'summary_report'


def _normalize_recipients(value):
    """Translate Outlook-style `a@x; b@y` into RFC 5322 `a@x, b@y`.

    The `parse_project_context_html` parser emits semicolon-joined
    strings (Outlook's UI convention) and `generate_email_msg` passes
    those straight to `mail.To = ...` because Outlook COM accepts
    them. RFC 5322 wants comma-separated, so the .eml writer
    translates here. Empty / None fall through unchanged.
    """
    if not value:
        return ''
    # Split on either separator, drop empties, rejoin with comma+space.
    parts = []
    for chunk in value.replace(';', ',').split(','):
        chunk = chunk.strip()
        if chunk:
            parts.append(chunk)
    return ', '.join(parts)


def _add_inline_image(html_part, image_path, cid_name, subtype='png'):
    """Attach an image as an inline `cid:` part on the HTML alternative.

    Lesson from the W1177 test: if you pass `filename=...` here,
    Outlook flips the part to `Content-Disposition: attachment` and
    the image leaks into the attachment pane (and the inline reference
    breaks). Inline-only parts must have just `cid` + raw data.
    """
    with open(image_path, 'rb') as f:
        data = f.read()
    html_part.add_related(
        data,
        maintype='image',
        subtype=subtype,
        cid=f'<{cid_name}>',
    )


def generate_update_email_eml(
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
    custom_paragraphs=None,
    summary_screenshot_path=None,
    graph_screenshot_paths=None,
    from_address='',
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
):
    """Write a Westland schedule update email as a `.eml` file on disk.

    Same kwargs as `generate_update_email_msg`. The user double-clicks
    the resulting file to open it in Outlook (compose mode), reviews,
    and clicks Send.

    Args:
        output_path: Absolute path to write. Convention is
            `{dated_folder}/{YYYY-MM-DD}-update-email.eml`.
        from_address: Optional `From` header value (e.g.
            `'Camron Walker <camron@westlandconstruction.com>'`). Outlook
            re-derives the actual sender from the active profile when
            the file is opened, so this is mostly cosmetic — handy for
            archives or if the message is forwarded as-is.
        ...all other kwargs identical to `generate_update_email_msg`.

    Returns:
        The absolute path to the written `.eml` file.
    """
    # Resolve logo path
    if logo_path is None:
        logo_path = DEFAULT_LOGO_PATH
    has_logo = bool(logo_path and os.path.isfile(logo_path))

    # Resolve screenshot availability
    has_summary = bool(
        summary_screenshot_path and os.path.isfile(summary_screenshot_path)
    )

    # Build list of available graph screenshots with CID names. The
    # ordinals here line up with the cid placeholders that
    # `_build_html_body` emits.
    graph_images = []  # list of (path, cid_name)
    for i, gpath in enumerate(graph_screenshot_paths or []):
        if gpath and os.path.isfile(gpath):
            graph_images.append((gpath, f'graph_{i}'))

    # Build the HTML body using the same builder as the COM path so the
    # rendered email looks identical regardless of which output
    # mechanism a caller picks.
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
        custom_paragraphs=custom_paragraphs,
        has_summary_screenshot=has_summary,
        graph_cid_names=[cid for _, cid in graph_images],
        smartpm_project_url=smartpm_project_url,
        smartpm_trends_url=smartpm_trends_url,
        signer_name=signer_name,
        signer_title=signer_title,
        signer_mobile=signer_mobile,
        has_logo=has_logo,
    )

    # Build the message envelope
    msg = EmailMessage()
    subject = _ensure_subject_has_date(subject)
    if subject:
        msg['Subject'] = subject
    if from_address:
        msg['From'] = from_address
    if to_recipients:
        msg['To'] = _normalize_recipients(to_recipients)
    if cc_recipients:
        msg['Cc'] = _normalize_recipients(cc_recipients)
    msg['Date'] = formatdate(localtime=True)
    msg['Message-ID'] = make_msgid(domain='westlandconstruction.com')
    # X-Unsent: 1 → Outlook opens the file in compose mode (editable
    # To/Cc/Subject and a real Send button) rather than the read-only
    # "saved message" view.
    msg['X-Unsent'] = '1'

    # Plain-text fallback for clients that don't render HTML.
    msg.set_content(
        'This email contains an HTML body. '
        'Please view in an HTML-capable client.',
        subtype='plain',
    )
    # Base64-encode the HTML alternative — quoted-printable's soft line
    # breaks have historically corrupted Outlook's compose-mode render.
    msg.add_alternative(html_body, subtype='html', cte='base64')

    # The HTML alternative is the part we attach inline images to.
    # `msg.get_payload()` after add_alternative returns
    #   [text/plain, multipart/alternative]
    # and the multipart/alternative wraps the HTML part we just added.
    html_part = msg.get_payload()[1]

    if has_logo:
        _add_inline_image(html_part, logo_path, _INLINE_LOGO_CID)
    if has_summary:
        _add_inline_image(html_part, summary_screenshot_path, _INLINE_SUMMARY_CID)
    for img_path, cid_name in graph_images:
        _add_inline_image(html_part, img_path, cid_name)

    # Real file attachments (PDFs, Excel, change-report PDF, etc.).
    # Skip Office temp lock files (`~$Foo.xlsm`) the same way the COM
    # path does.
    for path in (attachment_paths or []):
        if not path or not os.path.isfile(path):
            continue
        if os.path.basename(path).startswith('~$'):
            continue
        ctype, _ = mimetypes.guess_type(path)
        if ctype is None:
            ctype = 'application/octet-stream'
        maintype, subtype = ctype.split('/', 1)
        with open(path, 'rb') as f:
            msg.add_attachment(
                f.read(),
                maintype=maintype,
                subtype=subtype,
                filename=os.path.basename(path),
            )

    # Make sure the parent directory exists (caller may pass an
    # output_path inside a not-yet-created dated folder).
    out_dir = os.path.dirname(os.path.abspath(output_path))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    with open(output_path, 'wb') as f:
        f.write(bytes(msg))

    return os.path.abspath(output_path)


if __name__ == '__main__':
    # Smoke test — generates a tiny .eml so you can sanity-check the
    # output by opening it in Outlook.
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument('output')
    args = ap.parse_args()
    generate_update_email_eml(
        args.output,
        project_info={
            'project_name': 'Sample Project',
            'job_number': 'W9999',
            'contractual_completion': 'June 1, 2027',
            'projected_completion': 'July 15, 2027',
        },
        days_behind=7,
        gain_loss=-3,
        successes=['Foundation poured.'],
        red_flags=['**Steel delivery slipped two weeks.**'],
        stalled_tasks=[], key_items=[],
        gain_loss_narrative='Lost 3 days to weather.',
        to_recipients='lead@example.com',
        cc_recipients='pm@example.com',
        subject='Sample Project - Schedule Update - 2026-05-07',
        from_address='Camron Walker <camron@westlandconstruction.com>',
    )
    print(f'Wrote {args.output} ({os.path.getsize(args.output):,} bytes)')
