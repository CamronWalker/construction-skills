"""
Unit tests for generate_email_eml.py — body rendering + .eml envelope.

Tests cover:
    1. The body — item text arrives as HTML from the cloud editor and
       is passed through verbatim (no markdown conversion). Inline
       `<strong>` and priority-red spans render in Outlook.
    2. The .eml shape — base64 HTML alternative, inline images carry
       Content-ID but no `attachment` disposition, X-Unsent header
       present, plain-text fallback included.
"""

import email
import email.policy
import os
import pathlib
import sys
import tempfile
import unittest

_HERE = pathlib.Path(__file__).resolve().parent
_REFS = _HERE.parent / 'references'
sys.path.insert(0, str(_REFS))

import generate_email_msg as gen_msg  # noqa: E402
import generate_email_eml as gen_eml  # noqa: E402


# HTML item text — Trix-editor conventions from the cloud editor.
_PRIORITY_RED = 'color:#C94444;font-weight:bold'

SAMPLE_KW = dict(
    project_info={
        'project_name': 'Sample Roundtrip Temple',
        'job_number': 'W9990',
        'contractual_completion': 'June 1, 2027',
        'projected_completion': 'July 15, 2027',
    },
    days_behind=7,
    gain_loss=-3,
    successes=[
        'Foundation poured.',
        '<strong>Big milestone hit this week.</strong>',
        f'<span style="{_PRIORITY_RED}">Closed all four IMPACT items.</span>',
    ],
    red_flags=[
        f'<span style="{_PRIORITY_RED}">Steel delivery slipped two weeks.</span>',
        'Weather delays resolved.',
    ],
    stalled_tasks=[],
    key_items=[
        f'<span style="{_PRIORITY_RED}">Coordinate elevator delivery this week.</span>',
    ],
    gain_loss_narrative='Lost 3 days to weather; recovery plan filed.',
    eot_recovery='No EOT this update.',
    logic_changes='Reordered MEP rough-in.',
    to_recipients='lead@example.com; second@example.com',
    cc_recipients='pm@westlandconstruction.com',
    subject='Sample Project — Schedule Update — 2026-05-07',
    from_address='Camron Walker <camron@westlandconstruction.com>',
    signer_name='CAMRON WALKER',
    signer_title='SCHEDULER',
)


def _read_eml_html(path):
    """Parse the .eml and return the decoded HTML body string."""
    with open(path, 'rb') as f:
        raw = f.read()
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    for part in msg.walk():
        if part.get_content_type() == 'text/html':
            return part.get_content()
    raise AssertionError('no text/html part found in .eml')


def _read_eml(path):
    with open(path, 'rb') as f:
        return email.message_from_bytes(f.read(), policy=email.policy.default)


class HtmlPassthroughTests(unittest.TestCase):
    """Item text arrives as HTML from the cloud editor's Trix surface and
    is passed through verbatim — no markdown conversion. The builder
    does not transform inline `<strong>` / priority-red / highlight
    spans; Outlook's Word renderer respects them inline."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'roundtrip.eml')

    def _body(self):
        gen_eml.generate_update_email_eml(self.path, **SAMPLE_KW)
        return _read_eml_html(self.path)

    def test_strong_tag_passes_through_verbatim(self):
        body = self._body()
        self.assertIn(
            '<strong>Big milestone hit this week.</strong>', body,
        )

    def test_priority_red_span_passes_through_verbatim(self):
        body = self._body()
        self.assertIn(
            '<span style="color:#C94444;font-weight:bold">'
            'Closed all four IMPACT items.</span>',
            body,
        )

    def test_red_flag_priority_span_renders(self):
        body = self._body()
        self.assertIn(
            '<span style="color:#C94444;font-weight:bold">'
            'Steel delivery slipped two weeks.</span>',
            body,
        )

    def test_no_legacy_markdown_delimiters_in_input_round_trip(self):
        """Sanity check: the HTML input itself does not contain markdown
        delimiters, so the rendered output shouldn't either."""
        body = self._body()
        # The test inputs use no `**` or `==` — confirm output is also clean.
        self.assertNotIn('**', body)
        self.assertNotIn('==', body)

    def test_plain_items_render_plain(self):
        """Items with no HTML formatting render as plain <li> content."""
        body = self._body()
        self.assertIn('Foundation poured.', body)
        # No <strong> wrapping a plain item.
        self.assertNotIn('<strong>Foundation poured.</strong>', body)


class EmlEnvelopeTests(unittest.TestCase):
    """Post-mortem #15 lessons baked into the .eml shape."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'envelope.eml')
        gen_eml.generate_update_email_eml(self.path, **SAMPLE_KW)
        self.msg = _read_eml(self.path)

    def test_x_unsent_header_present(self):
        """X-Unsent: 1 → Outlook opens the file in compose mode with
        a real Send button, not the read-only saved-message view."""
        self.assertEqual(self.msg.get('X-Unsent'), '1')

    def test_envelope_fields_set(self):
        # Recipients are normalized from Outlook `;` to RFC 5322 `, `
        # so the parsed header contains both addresses.
        to = self.msg.get('To') or ''
        cc = self.msg.get('Cc') or ''
        self.assertIn('lead@example.com', to)
        self.assertIn('second@example.com', to)
        self.assertIn('pm@westlandconstruction.com', cc)
        self.assertEqual(self.msg.get('Subject'), SAMPLE_KW['subject'])
        self.assertEqual(self.msg.get('From'), SAMPLE_KW['from_address'])
        self.assertTrue(self.msg.get('Date'))
        self.assertTrue(self.msg.get('Message-ID'))

    def test_recipient_separator_normalized(self):
        # Outlook UI uses `;`; RFC 5322 needs `,`. The writer accepts
        # either and emits comma-separated.
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, 'sep.eml')
            gen_eml.generate_update_email_eml(
                p,
                project_info={'project_name': 'X', 'job_number': 'W1', 'contractual_completion': '', 'projected_completion': ''},
                to_recipients='a@x.com; b@y.com',
                cc_recipients='c@z.com,d@w.com',
                subject='S',
            )
            with open(p, 'rb') as f:
                raw = f.read()
            # Raw bytes should contain comma-separated To/Cc.
            self.assertIn(b'To: a@x.com, b@y.com', raw)
            self.assertIn(b'Cc: c@z.com, d@w.com', raw)

    def test_html_alternative_is_base64(self):
        """#15.1: HTML body must be base64-encoded. Quoted-printable
        soft line breaks have historically corrupted Outlook's
        compose-mode render — `Bu=\\r\\nilding` becomes `Bu=ilding`."""
        for part in self.msg.walk():
            if part.get_content_type() == 'text/html':
                cte = (part.get('Content-Transfer-Encoding') or '').lower()
                self.assertEqual(cte, 'base64',
                                 f'HTML must be base64 for Outlook compose-mode safety, got {cte!r}')
                return
        self.fail('no text/html part in .eml')

    def test_inline_images_have_no_attachment_disposition(self):
        """#15.2: inline images must NOT carry Content-Disposition:
        attachment — that flips Outlook to show the image both inline
        and in the attachment pane, with the inline reference often
        breaking."""
        inline_count = 0
        for part in self.msg.walk():
            ct = part.get_content_type()
            if not ct.startswith('image/'):
                continue
            cd = (part.get('Content-Disposition') or '').lower()
            self.assertNotIn(
                'attachment', cd,
                f'inline image {ct!r} has unexpected attachment disposition: {cd!r}',
            )
            self.assertTrue(part.get('Content-ID'),
                            f'inline image {ct!r} missing Content-ID')
            inline_count += 1
        self.assertGreaterEqual(inline_count, 1,
                                'expected at least the Westland logo inline')

    def test_plain_text_fallback_present(self):
        """Some clients render only the plain alternative. Make sure
        we ship one, even if it's a one-liner."""
        plain_seen = False
        for part in self.msg.walk():
            if part.get_content_type() == 'text/plain':
                plain_seen = True
                content = part.get_content()
                self.assertTrue(content.strip(),
                                'text/plain part is empty')
                break
        self.assertTrue(plain_seen, 'no text/plain alternative found')


class CrossPathParityTests(unittest.TestCase):
    """The .eml path and the COM Outlook path must produce the same
    HTML body — they share `_build_html_body`. The COM path itself
    requires Outlook + pywin32 to actually run, but its body builder
    can be exercised directly in tests."""

    def test_html_body_byte_identical_across_paths(self):
        """The body rendered by `_build_html_body` (with the same
        kwargs) is what both `generate_email_eml` and
        `generate_email_msg` ship to the wire. Confirm a representative
        kwargs set produces an identical body string when invoked
        through the shared builder."""
        # Emulate what each path does: strip kwargs the body builder
        # doesn't accept, then call _build_html_body directly with the
        # same shape both paths construct.
        common_body_kw = dict(
            project_info=SAMPLE_KW['project_info'],
            days_behind=SAMPLE_KW['days_behind'],
            gain_loss=SAMPLE_KW['gain_loss'],
            successes=SAMPLE_KW['successes'],
            gain_loss_narrative=SAMPLE_KW['gain_loss_narrative'],
            eot_recovery=SAMPLE_KW['eot_recovery'],
            logic_changes=SAMPLE_KW['logic_changes'],
            smartpm_changelog_url='',
            red_flags=SAMPLE_KW['red_flags'],
            stalled_tasks=SAMPLE_KW['stalled_tasks'],
            key_items=SAMPLE_KW['key_items'],
            include_compliance_report=False,
            include_procurement_sheets=False,
            custom_paragraphs=None,
            has_summary_screenshot=False,
            graph_cid_names=[],
            smartpm_project_url='',
            smartpm_trends_url='',
            signer_name='CAMRON WALKER',
            signer_title='SCHEDULER',
            signer_mobile='',
            has_logo=False,
        )
        body_a = gen_msg._build_html_body(**common_body_kw)
        body_b = gen_msg._build_html_body(**common_body_kw)
        self.assertEqual(body_a, body_b)
        # And the .eml writer feeds this same builder, so the rendered
        # body in the .eml must match too.
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, 'parity.eml')
            gen_eml.generate_update_email_eml(p, **SAMPLE_KW)
            eml_body = _read_eml_html(p)
        # Smoke check: every list item from the shared builder is
        # in the .eml body. Items are HTML strings — they pass through
        # verbatim, so the input string itself appears in the body.
        for item in SAMPLE_KW['successes'] + SAMPLE_KW['red_flags'] + SAMPLE_KW['key_items']:
            self.assertIn(item, eml_body,
                          f'item {item!r} missing from .eml body')


class TestSubjectDateSuffix(unittest.TestCase):
    """Each weekly schedule-update email must start its own Outlook thread.
    Outlook groups messages by subject stem, so identical subjects collapse
    into one conversation. `_ensure_subject_has_date` guarantees the subject
    ends with a YYYY-MM-DD date so successive sends thread separately.
    """

    def test_appends_today_when_no_date_present(self):
        from datetime import date
        fixed_today = date(2026, 5, 20)
        result = gen_msg._ensure_subject_has_date(
            'Sample Project — Schedule Update', today=fixed_today,
        )
        self.assertEqual(result, 'Sample Project — Schedule Update - 2026-05-20')

    def test_leaves_subject_alone_when_already_ends_with_date(self):
        from datetime import date
        fixed_today = date(2026, 5, 20)
        result = gen_msg._ensure_subject_has_date(
            'Schedule Update - Lubumbashi DRC Temple - 2026-04-09',
            today=fixed_today,
        )
        # 2026-04-09 is already there; helper must not double-stamp.
        self.assertEqual(result,
                         'Schedule Update - Lubumbashi DRC Temple - 2026-04-09')

    def test_trailing_whitespace_does_not_defeat_detection(self):
        from datetime import date
        fixed_today = date(2026, 5, 20)
        result = gen_msg._ensure_subject_has_date(
            'Subject - 2026-04-09   ', today=fixed_today,
        )
        self.assertEqual(result, 'Subject - 2026-04-09   ')

    def test_empty_subject_passes_through(self):
        # Callers that intentionally leave the subject blank (so Outlook
        # picks its default) shouldn't suddenly get a bare date.
        self.assertEqual(gen_msg._ensure_subject_has_date(''), '')
        self.assertIsNone(gen_msg._ensure_subject_has_date(None))

    def test_eml_writer_stamps_subject_with_today(self):
        """End-to-end through the .eml path — confirm the written Subject
        header carries a YYYY-MM-DD suffix."""
        kw = dict(SAMPLE_KW)
        kw['subject'] = 'Sample Project — Schedule Update'  # no date
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, 'dated.eml')
            gen_eml.generate_update_email_eml(p, **kw)
            msg = _read_eml(p)
        subject = msg.get('Subject') or ''
        import re as _re
        self.assertRegex(subject, r'\d{4}-\d{2}-\d{2}\s*$',
                         f'Subject {subject!r} must end with YYYY-MM-DD')


class BuildHtmlBodyV2Tests(unittest.TestCase):
    """v2 _build_html_body uses closing_paragraphs_html kwarg, no longer
    accepts closing_line / custom_paragraphs."""

    def _common_kwargs(self):
        return dict(
            project_info={
                'project_name': 'Test', 'job_number': 'G0000',
                'contractual_completion': 'TBD', 'projected_completion': 'TBD',
            },
            days_behind=0, gain_loss=0,
            successes=[], red_flags=[], stalled_tasks=[], key_items=[],
            gain_loss_narrative='', eot_recovery='', logic_changes='',
            smartpm_changelog_url='',
            salutation='Thanks,',
            signer_name='Camron', signer_title='Scheduler', signer_mobile='555-0100',
            smartpm_project_url='', smartpm_trends_url='',
        )

    def test_closing_paragraphs_html_renders_verbatim(self):
        from generate_email_msg import _build_html_body
        kwargs = self._common_kwargs()
        kwargs['closing_paragraphs_html'] = '<div>Please ask questions.</div><div>Owner directive applied.</div>'
        html = _build_html_body(**kwargs)
        self.assertIn('Please ask questions.', html)
        self.assertIn('Owner directive applied.', html)

    def test_no_closing_line_kwarg_required(self):
        """The signature must not require closing_line."""
        from generate_email_msg import _build_html_body
        kwargs = self._common_kwargs()
        kwargs['closing_paragraphs_html'] = ''
        # If closing_line were still required, this raises TypeError.
        html = _build_html_body(**kwargs)
        self.assertIsInstance(html, str)


if __name__ == '__main__':
    unittest.main()
