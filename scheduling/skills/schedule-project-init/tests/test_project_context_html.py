"""
Unit tests for the project-context.html generate/parse pair.

Contract: HTML CRUD on project-context.html happens through these two
scripts only. Claude (and humans) must never Read/Edit/Write the HTML
directly. These tests pin that contract by exercising the full
generate -> parse roundtrip, plus regression guards for past failures.

Run from repo root:
    python -m unittest scheduling.skills.schedule-project-init.tests.test_project_context_html

or directly:
    python scheduling/skills/schedule-project-init/tests/test_project_context_html.py
"""

import os
import pathlib
import re
import sys
import tempfile
import unittest

_HERE = pathlib.Path(__file__).resolve().parent
_REFS = _HERE.parent / 'references'
sys.path.insert(0, str(_REFS))

import generate_project_context_html as gen  # noqa: E402
import parse_project_context_html as parse_mod  # noqa: E402


FULL_CTX = {
    'project_name': 'Lubumbashi DR Congo Temple',
    'job_number': 'W1177',
    'contractual_completion': '2027-09-30',
    'smartpm_url': 'https://live.smartpmtech.com/projects/abc/workspace',
    'smartpm_trends_url': 'https://live.smartpmtech.com/projects/abc/trends?tab=Graphs',
    'smartpm_changelog_url': 'https://live.smartpmtech.com/projects/abc/changelog',
    'smartpm_project_name': 'Lubumbashi DR Congo Temple',
    'signer_name': 'Carter Brown',
    'signer_title': 'Project Scheduler',
    'signer_mobile': '+1 801.555.1234',
    'procore_company_id': '11093',
    'procore_project_id': '2646569',
    'graph_screenshots': [
        '06-end-date-variance.png',
        '07-schedule-compression-index-over-time.png',
        '08-velocity.png',
    ],
    'project_log': [
        {'date': '2026-04-15', 'body': 'EOT #1 filed — 14 calendar days.'},
        {'date': '2026-05-07', 'body': 'Re-init context with new signer.'},
    ],
    'to_recipients': [
        {'name': 'Owner Rep', 'email': 'owner@example.com'},
        {'name': '', 'email': 'arch@example.com'},
    ],
    'cc_recipients': [
        {'name': 'PM', 'email': 'pm@westlandconstruction.com'},
    ],
}


class RoundtripTests(unittest.TestCase):
    """Generate then parse — every field that goes in must come out."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'project-context.html')

    def _write_and_parse(self, ctx, today_iso='2026-05-07'):
        gen.generate_project_context_html(
            self.path, ctx, today_iso=today_iso,
        )
        self.assertTrue(os.path.isfile(self.path))
        return parse_mod.parse_project_context_html(self.path)

    def test_full_roundtrip(self):
        out = self._write_and_parse(FULL_CTX)
        for k in (
            'project_name', 'job_number', 'contractual_completion',
            'smartpm_url', 'smartpm_trends_url', 'smartpm_changelog_url',
            'smartpm_project_name', 'signer_name', 'signer_title',
            'signer_mobile', 'procore_company_id', 'procore_project_id',
        ):
            self.assertEqual(
                out[k], FULL_CTX[k],
                f'scalar field {k!r} did not survive roundtrip',
            )
        self.assertEqual(out['graph_screenshots'], FULL_CTX['graph_screenshots'])
        self.assertEqual(out['to_recipients'], FULL_CTX['to_recipients'])
        self.assertEqual(out['cc_recipients'], FULL_CTX['cc_recipients'])
        # Project log: parser sorts newest first via the generator; both
        # entries should be present with correct date+body.
        log_by_date = {e['date']: e['body'] for e in out['project_log']}
        for e in FULL_CTX['project_log']:
            self.assertIn(e['date'], log_by_date)
            self.assertEqual(log_by_date[e['date']], e['body'])

    def test_empty_context_is_safe(self):
        out = self._write_and_parse({})
        for k in (
            'project_name', 'job_number', 'contractual_completion',
            'smartpm_url', 'smartpm_trends_url', 'smartpm_changelog_url',
            'smartpm_project_name', 'signer_name', 'signer_title',
            'signer_mobile', 'procore_project_id',
        ):
            self.assertEqual(out[k], '', f'{k!r} should default to empty')
        self.assertEqual(out['graph_screenshots'], [])
        self.assertEqual(out['project_log'], [])
        self.assertEqual(out['to_recipients'], [])
        self.assertEqual(out['cc_recipients'], [])

    def test_recipients_string_input_normalizes(self):
        ctx = dict(FULL_CTX)
        ctx['to_recipients'] = 'Owner Rep <owner@example.com>; arch@example.com'
        ctx['cc_recipients'] = 'pm@westlandconstruction.com'
        out = self._write_and_parse(ctx)
        self.assertEqual(out['to_recipients'], [
            {'name': 'Owner Rep', 'email': 'owner@example.com'},
            {'name': '', 'email': 'arch@example.com'},
        ])
        self.assertEqual(out['cc_recipients'], [
            {'name': '', 'email': 'pm@westlandconstruction.com'},
        ])

    def test_html_special_chars_survive(self):
        """Quotes, ampersands, angle brackets in scalar fields must not
        corrupt the HTML or get double-escaped on read-back."""
        ctx = dict(FULL_CTX)
        ctx['signer_title'] = 'Director of "Special" Projects & Ops'
        ctx['project_name'] = 'A <weird> project & co.'
        out = self._write_and_parse(ctx)
        self.assertEqual(out['signer_title'], ctx['signer_title'])
        self.assertEqual(out['project_name'], ctx['project_name'])

    def test_log_today_is_editable_past_is_locked(self):
        ctx = dict(FULL_CTX)
        gen.generate_project_context_html(
            self.path, ctx, today_iso='2026-05-07',
        )
        html = pathlib.Path(self.path).read_text(encoding='utf-8')
        # Today's entry → contenteditable="true"
        today_block = _entry_block(html, '2026-05-07')
        self.assertIn('contenteditable="true"', today_block)
        self.assertNotIn('class="log-entry locked"', today_block)
        # Past entry → contenteditable="false" + locked class
        past_block = _entry_block(html, '2026-04-15')
        self.assertIn('contenteditable="false"', past_block)
        self.assertIn('locked', past_block)

    def test_deterministic_output(self):
        """Two generate calls with identical input must produce identical
        bytes — re-runs should not churn the file gratuitously."""
        gen.generate_project_context_html(
            self.path, FULL_CTX, today_iso='2026-05-07',
        )
        first = pathlib.Path(self.path).read_bytes()
        second_path = os.path.join(self.tmp.name, 'second.html')
        gen.generate_project_context_html(
            second_path, FULL_CTX, today_iso='2026-05-07',
        )
        second = pathlib.Path(second_path).read_bytes()
        self.assertEqual(first, second)

    def test_logo_embedded(self):
        """Logo is embedded as base64 — file must be self-contained."""
        gen.generate_project_context_html(
            self.path, FULL_CTX, today_iso='2026-05-07',
        )
        html = pathlib.Path(self.path).read_text(encoding='utf-8')
        self.assertIn('data:image/png;base64,', html)


class Python310CompatTests(unittest.TestCase):
    """The cowork sandbox runs Python 3.10. The generator must parse and
    import there. PEP 701 (Python 3.12) relaxed f-string grammar to allow
    backslash-escaped quotes inside expression braces — using that syntax
    silently breaks cowork. Guard against reintroduction."""

    def test_no_backslash_quotes_inside_fstrings(self):
        src = (_REFS / 'generate_project_context_html.py').read_text(
            encoding='utf-8',
        )
        # Strip raw-string blocks — the JS payload in _script() is r"""...""" and
        # legitimately contains escaped JS template syntax that doesn't reach
        # the Python f-string parser.
        src_no_raw = re.sub(
            r'r"""[\s\S]*?"""', '', src,
        )
        src_no_raw = re.sub(
            r"r'''[\s\S]*?'''", '', src_no_raw,
        )
        # f-string opener with a backslash-escaped quote anywhere in the
        # same logical f-string (single-line scan — multi-line f-strings
        # aren't used here).
        bad_single = re.findall(r"""f'[^'\n]*\\"[^'\n]*'""", src_no_raw)
        bad_double = re.findall(r'''f"[^"\n]*\\'[^"\n]*"''', src_no_raw)
        self.assertEqual(
            bad_single + bad_double, [],
            'Found f-string with backslash-escaped quote inside braces. '
            'Requires Python 3.12+ (PEP 701); cowork ships 3.10. '
            'Hoist the conditional HTML out of the f-string into a '
            'plain string variable before the return.',
        )


# ---------- helpers ----------------------------------------------------

def _entry_block(html, date):
    """Return the substring covering one .log-entry div for the given
    data-date — a coarse extraction sufficient for asserting attribute
    presence on that specific entry."""
    pattern = re.compile(
        r'<div class="log-entry[^"]*" data-date="' + re.escape(date)
        + r'">[\s\S]*?</div>\s*</div>',
    )
    m = pattern.search(html)
    if not m:
        raise AssertionError(f'no log-entry block found for date {date!r}')
    return m.group(0)


class ProcoreDocumentsFolderTests(unittest.TestCase):
    """Field added 2026-05 for the Procore Documents upload workflow."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, 'project-context.html')

    def test_parser_reads_field_from_static_html(self):
        # Don't depend on the generator (that's Task 2). Hand-craft minimal HTML.
        html = (
            '<!DOCTYPE html><html><body>'
            '<input type="text" data-field="procore_documents_folder_id" '
            'value="4592384">'
            '</body></html>'
        )
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(html)
        parsed = parse_mod.parse_project_context_html(self.path)
        self.assertEqual(parsed['procore_documents_folder_id'], '4592384')

    def test_field_defaults_empty_on_missing(self):
        # Round-trip a context that omits the field. Parser must
        # tolerate older HTML files written before the field existed.
        ctx = dict(FULL_CTX)
        ctx.pop('procore_documents_folder_id', None)
        gen.generate_project_context_html(self.path, ctx,
                                          today_iso='2026-05-18')
        parsed = parse_mod.parse_project_context_html(self.path)
        self.assertEqual(parsed['procore_documents_folder_id'], '')

    def test_user_blanks_field_to_re_trigger_discovery(self):
        # The Procore phase blanks this field when the user wants to
        # switch folders. Round-trip an empty value via static HTML.
        html = (
            '<!DOCTYPE html><html><body>'
            '<input type="text" data-field="procore_documents_folder_id" '
            'value="">'
            '</body></html>'
        )
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(html)
        parsed = parse_mod.parse_project_context_html(self.path)
        self.assertEqual(parsed['procore_documents_folder_id'], '')


if __name__ == '__main__':
    unittest.main()
