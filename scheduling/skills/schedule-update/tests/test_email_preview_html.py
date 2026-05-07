"""
Unit tests for the email-preview generate/parse pair.

Mirrors the schedule-project-init contract: HTML CRUD on
{YYYY-MM-DD}-email-preview.html happens through these two scripts only.
Reads use parse_email_html.parse_preview_html; writes use
generate_email_preview_html.generate_preview_html. Tests pin the
roundtrip plus the post-mortem-driven fixes (UNC URL builders, the
previous_days_behind / previous_gain_loss kwargs, cache-control meta).

Run:
    python scheduling/skills/schedule-update/tests/test_email_preview_html.py
"""

import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

_HERE = pathlib.Path(__file__).resolve().parent
_REFS = _HERE.parent / 'references'
sys.path.insert(0, str(_REFS))

import generate_email_preview_html as gen  # noqa: E402
import parse_email_html as parse_mod  # noqa: E402
# Import the changes-report module too so the file-URI helper is tested
# in its real call site, not just in isolation.
import generate_changes_report_html as ch_mod  # noqa: E402


FULL_KWARGS = {
    'date_label': '2026-05-07',
    'project_info': {
        'project_name': 'Test Roundtrip Temple',
        'job_number': 'W9990',
        'contractual_completion': 'June 1, 2027',
        'projected_completion': 'July 15, 2027',
    },
    'days_behind': 7,
    'gain_loss': -3,
    'previous_days_behind': 12,
    'previous_gain_loss': -2,
    'gain_loss_narrative': 'Lost 3 days due to weather.',
    'eot_recovery': 'EOT request pending owner review.',
    'logic_changes': 'Reordered MEP rough-in sequence.',
    'smartpm_changelog_url': 'https://live.smartpmtech.com/proj/changelog',
    'successes': [
        {'text': 'Foundation poured.', 'status': 'active', 'checked': True},
        {'text': '**New milestone hit.**', 'status': 'new', 'checked': True},
    ],
    'red_flags': [
        {'text': '**Steel delivery slipped.**', 'status': 'active', 'checked': True},
    ],
    'stalled_tasks': [],
    'key_items': [
        {'text': 'Coordinate elevator delivery.', 'status': 'active', 'checked': True},
    ],
    'custom_paragraphs': [
        {'label': 'Compliance', 'checked': True, 'text': 'Compliance text.'},
    ],
    'attachments': [
        {'filename': 'Report 01.pdf', 'checked': True, 'status': 'active'},
        {'filename': 'Procurement.xlsm', 'checked': True, 'status': 'new'},
    ],
    'signer_name': 'CAMRON WALKER',
    'signer_title': 'SCHEDULER',
}


class RoundtripTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, '2026-05-07-email-preview.html')

    def _gen(self, **overrides):
        kw = dict(FULL_KWARGS)
        kw.update(overrides)
        gen.generate_preview_html(self.path, **kw)
        self.assertTrue(os.path.isfile(self.path))
        return parse_mod.parse_preview_html(self.path)

    def test_full_roundtrip(self):
        out = self._gen()
        self.assertEqual(out['days_behind'], FULL_KWARGS['days_behind'])
        self.assertEqual(out['gain_loss'], FULL_KWARGS['gain_loss'])
        self.assertEqual(out['signer_name'], FULL_KWARGS['signer_name'])
        self.assertEqual(out['signer_title'], FULL_KWARGS['signer_title'])
        self.assertEqual(
            out['project_info']['project_name'],
            FULL_KWARGS['project_info']['project_name'],
        )
        # The roundtrip preserves *checked* item text.
        success_texts = [s for s in out['successes']]
        self.assertIn('Foundation poured.', success_texts)
        red_flag_texts = [s for s in out['red_flags']]
        self.assertTrue(any('Steel delivery' in t for t in red_flag_texts))
        # Attachments survive: filename + checked-only filtering.
        self.assertEqual(out['attachment_names'], ['Report 01.pdf', 'Procurement.xlsm'])

    def test_no_prev_metric_span_when_unchanged(self):
        """If previous_* equals current, suppress the prefix — there's
        nothing to show. Otherwise the strikethrough adds noise."""
        gen.generate_preview_html(self.path,
            **{**FULL_KWARGS, 'previous_days_behind': 7,
               'previous_gain_loss': -3})
        html = pathlib.Path(self.path).read_text(encoding='utf-8')
        self.assertNotIn('previous_days_behind', html)
        self.assertNotIn('previous_gain_loss', html)

    def test_prev_metric_span_rendered_when_changed(self):
        """Week-over-week movement: 12 → 7 days behind. The prefix should
        render with strikethrough so reviewers see the prior value."""
        gen.generate_preview_html(self.path, **FULL_KWARGS)
        html = pathlib.Path(self.path).read_text(encoding='utf-8')
        self.assertIn('data-field="previous_days_behind"', html)
        self.assertIn('data-value="12"', html)
        self.assertIn('text-decoration:line-through', html)
        self.assertIn('data-field="previous_gain_loss"', html)
        self.assertIn('data-value="-2"', html)

    def test_prev_metric_does_not_pollute_parser(self):
        """The new prev-metric span is non-contenteditable and has no
        data-metric, so the parser must still extract days_behind=7
        from the parent <p data-metric="days_behind" data-value="7">."""
        out = self._gen()
        self.assertEqual(out['days_behind'], 7)   # current, not 12
        self.assertEqual(out['gain_loss'], -3)    # current, not -2

    def test_cache_control_meta_present(self):
        """No-store keeps Chrome from serving the stale preview after
        regenerate. Post-mortem #8 — the user kept seeing 'same as before'
        because Chrome was caching."""
        gen.generate_preview_html(self.path, **FULL_KWARGS)
        html = pathlib.Path(self.path).read_text(encoding='utf-8')
        self.assertIn('http-equiv="cache-control"', html)
        self.assertIn('no-store', html)


@unittest.skipUnless(os.name == 'nt', 'Windows-only path semantics')
class FileUriTests(unittest.TestCase):
    """`_file_uri` (which wraps `Path.as_uri()`) emits proper RFC 8089
    file URLs. Replaces the broken `'file:///' + p.replace('\\','/').
    lstrip('/')` pattern that mangled UNC roots into file:///orem-fs/...
    (drive form) and 404'd in Chromium. Post-mortem #1+#2.

    Skipped off-Windows because the production code only runs on the
    Westland Windows shop, and Path('C:\\foo') resolves differently on
    POSIX (where backslash is a literal filename character)."""

    def test_drive_path_round_trips(self):
        uri = ch_mod._file_uri(r'C:\Westland\W9990\screenshot.png')
        self.assertEqual(uri, 'file:///C:/Westland/W9990/screenshot.png')

    def test_unc_path_emits_authority_form(self):
        # The whole point: UNC path must keep the server name as the
        # authority, not collapse it to a drive-root path. The old
        # manual builder produced file:///orem-fs/Common/... and
        # Chromium 404'd (no host = looks for "orem-fs" as a drive root).
        uri = ch_mod._file_uri(r'\\orem-fs\Common\file.png')
        # Path.as_uri emits file:////orem-fs/Common/file.png (RFC 8089
        # four-slash form). Chromium accepts both two-slash and four-slash
        # UNC forms — what matters is the host isn't lost.
        self.assertIn('orem-fs', uri)
        self.assertIn('Common', uri)
        # Anti-regression: must NOT collapse to drive-root form.
        self.assertFalse(
            uri.startswith('file:///orem-fs/'),
            f'UNC path collapsed to drive-root form: {uri!r}',
        )


if __name__ == '__main__':
    unittest.main()
