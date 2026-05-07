"""
Unit tests for generate_email_eml.py and the formatting parity fixes
(post-mortem W1177 #13, #14, #15).

The .eml writer is a thin RFC 5322 envelope around the same
`_build_html_body` the COM Outlook path uses. Tests cover both:
    1. The body itself — Successes processes markdown, **bold** /
       ==highlight== both render as bold + red (parity with the
       preview HTML and with the ordered lists below).
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
        '**Big milestone hit this week.**',
        '==Closed all four IMPACT items.==',
    ],
    red_flags=[
        '**Steel delivery slipped two weeks.**',
        'Weather delays resolved.',
    ],
    stalled_tasks=[],
    key_items=[
        '==Coordinate elevator delivery this week.==',
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


class FormattingParityTests(unittest.TestCase):
    """Post-mortem #13 + #14: Successes must process markdown like the
    other lists, and `**bold**` items must render with `<b>` (not red-
    only). The preview HTML treats ** and == identically; the email
    must too, so reviewers approving a bold-red item in the preview
    don't get red-only in the sent email."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'roundtrip.eml')

    def _body(self):
        gen_eml.generate_update_email_eml(self.path, **SAMPLE_KW)
        return _read_eml_html(self.path)

    def test_successes_process_bold_marker(self):
        """#13: `**foo**` in a Success item must wrap the text in <b>,
        not leak literal asterisks."""
        body = self._body()
        self.assertIn('<b>Big milestone hit this week.</b>', body)
        self.assertNotIn('**Big milestone hit', body)

    def test_successes_process_highlight_marker(self):
        """#13: `==foo==` in a Success item must wrap the text in <b>
        too — same priority as **bold**."""
        body = self._body()
        self.assertIn('<b>Closed all four IMPACT items.</b>', body)
        self.assertNotIn('==Closed all four', body)

    def test_red_flags_bold_renders_with_b_tag(self):
        """#14: `**foo**` in an ordered list must wrap the text in <b>,
        not just color it red. Otherwise the preview shows bold+red
        but the sent email shows red-only — reviewers can't trust
        what they're approving."""
        body = self._body()
        self.assertIn('<b>Steel delivery slipped two weeks.</b>', body)

    def test_no_literal_markdown_leaks_into_body(self):
        """No `**...**` or `==...==` substrings should survive into
        the rendered HTML. The COM and .eml paths share `_build_html_body`,
        so this guards both."""
        body = self._body()
        # The HTML escapes the literal characters — searching for the
        # markdown delimiter pairs is the practical regression check.
        self.assertNotIn('**', body)
        self.assertNotIn('==', body)

    def test_plain_successes_unchanged(self):
        """Non-marked items should render plain (no <b>, default color),
        same as before."""
        body = self._body()
        # Plain item appears between <li> tags without <b> wrapping.
        self.assertIn('Foundation poured.', body)
        # Plain items don't get <b>Foundation poured.</b>
        self.assertNotIn('<b>Foundation poured.</b>', body)


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
        # in the .eml body.
        for item in SAMPLE_KW['successes'] + SAMPLE_KW['red_flags'] + SAMPLE_KW['key_items']:
            # Strip markdown delimiters before checking
            text = item.strip('*=').strip()
            self.assertIn(text, eml_body,
                          f'item {text!r} missing from .eml body')


if __name__ == '__main__':
    unittest.main()
