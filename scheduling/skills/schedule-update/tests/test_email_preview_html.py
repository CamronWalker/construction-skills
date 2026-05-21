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
import re
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


class ProcoreFieldsParseTests(unittest.TestCase):
    """Parser surface for the Procore upload workflow (added 2026-05)."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name,
                                 '2026-05-07-email-preview.html')

    def test_share_to_procore_true_parsed_from_data_attribute(self):
        html = (
            '<!DOCTYPE html><html><body>'
            '<div class="attachments-section" data-field="attachments">'
            '<ul class="attachment-list">'
            '<li class="attachment-item" data-checked="true" '
            '    data-status="active" data-share-procore="true">'
            '<input type="checkbox" data-item-checked checked>'
            '<input type="checkbox" data-procore-checked checked>'
            '<span class="attachment-name" data-field="attachment_name">'
            'View 01.pdf</span></li>'
            '</ul></div></body></html>'
        )
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(html)
        parsed = parse_mod.parse_preview_html(self.path)
        atts = parsed['attachments']
        self.assertEqual(len(atts), 1)
        self.assertTrue(atts[0]['share_to_procore'])

    def test_share_to_procore_false_when_attribute_missing_or_false(self):
        html = (
            '<!DOCTYPE html><html><body>'
            '<div class="attachments-section" data-field="attachments">'
            '<ul class="attachment-list">'
            '<li class="attachment-item" data-checked="true" '
            '    data-status="active" data-share-procore="false">'
            '<input type="checkbox" data-item-checked checked>'
            '<span class="attachment-name" data-field="attachment_name">'
            'SmartPM Summary.pdf</span></li>'
            '<li class="attachment-item" data-checked="true" '
            '    data-status="active">'  # no data-share-procore
            '<input type="checkbox" data-item-checked checked>'
            '<span class="attachment-name" data-field="attachment_name">'
            'Internal Notes.pdf</span></li>'
            '</ul></div></body></html>'
        )
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(html)
        parsed = parse_mod.parse_preview_html(self.path)
        atts = parsed['attachments']
        self.assertEqual(len(atts), 2)
        self.assertFalse(atts[0]['share_to_procore'])
        self.assertFalse(atts[1]['share_to_procore'])

    def test_skip_procore_true(self):
        html = (
            '<!DOCTYPE html><html><body>'
            '<div class="attachments-section" data-field="attachments">'
            '<input type="checkbox" data-field="skip_procore" checked>'
            '<ul class="attachment-list"></ul></div></body></html>'
        )
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(html)
        parsed = parse_mod.parse_preview_html(self.path)
        self.assertTrue(parsed['skip_procore'])

    def test_skip_procore_false_default(self):
        html = (
            '<!DOCTYPE html><html><body>'
            '<div class="attachments-section" data-field="attachments">'
            '<ul class="attachment-list"></ul></div></body></html>'
        )
        with open(self.path, 'w', encoding='utf-8') as f:
            f.write(html)
        parsed = parse_mod.parse_preview_html(self.path)
        self.assertFalse(parsed['skip_procore'])


class ProcoreFieldsGenerateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name,
                                 '2026-05-07-email-preview.html')

    def _gen(self, **overrides):
        kw = dict(FULL_KWARGS)
        kw.update(overrides)
        gen.generate_preview_html(self.path, **kw)
        with open(self.path, 'r', encoding='utf-8') as f:
            return f.read()

    def test_share_to_procore_true_renders_data_attr_and_checked(self):
        html = self._gen(attachments=[
            {'filename': 'View 01.pdf', 'checked': True, 'status': 'active',
             'share_to_procore': True},
        ])
        self.assertIn('data-share-procore="true"', html)
        # The Procore checkbox should be checked
        self.assertRegex(html, r'data-procore-checked[^>]*checked')

    def test_share_to_procore_false_renders_data_attr_and_unchecked(self):
        html = self._gen(attachments=[
            {'filename': 'Notes.pdf', 'checked': True, 'status': 'active',
             'share_to_procore': False},
        ])
        self.assertIn('data-share-procore="false"', html)
        # Procore checkbox present but NOT checked
        self.assertIn('data-procore-checked', html)
        # Use regex to ensure the procore checkbox specifically lacks `checked`
        m = re.search(
            r'<input[^>]*data-procore-checked[^>]*>', html, re.IGNORECASE,
        )
        self.assertIsNotNone(m)
        self.assertNotIn(' checked', m.group(0))

    def test_share_to_procore_defaults_false_when_omitted(self):
        html = self._gen(attachments=[
            {'filename': 'Notes.pdf', 'checked': True, 'status': 'active'},
        ])
        self.assertIn('data-share-procore="false"', html)

    def test_skip_procore_kwarg_renders_checked_master_toggle(self):
        html = self._gen(skip_procore=True)
        # Master toggle present and checked
        m = re.search(
            r'<input[^>]*data-field="skip_procore"[^>]*>', html, re.IGNORECASE,
        )
        self.assertIsNotNone(m)
        self.assertIn('checked', m.group(0))

    def test_skip_procore_default_renders_unchecked_master_toggle(self):
        html = self._gen()  # no skip_procore kwarg
        m = re.search(
            r'<input[^>]*data-field="skip_procore"[^>]*>', html, re.IGNORECASE,
        )
        self.assertIsNotNone(m)
        self.assertNotIn(' checked', m.group(0))

    def test_round_trip_preserves_procore_fields(self):
        gen.generate_preview_html(
            self.path,
            **dict(FULL_KWARGS,
                   skip_procore=True,
                   attachments=[
                       {'filename': 'View 01.pdf', 'checked': True,
                        'status': 'active', 'share_to_procore': True},
                       {'filename': 'Summary.pdf', 'checked': True,
                        'status': 'active', 'share_to_procore': False},
                   ]),
        )
        parsed = parse_mod.parse_preview_html(self.path)
        self.assertTrue(parsed['skip_procore'])
        self.assertEqual(len(parsed['attachments']), 2)
        self.assertTrue(parsed['attachments'][0]['share_to_procore'])
        self.assertFalse(parsed['attachments'][1]['share_to_procore'])

    def test_attachment_template_js_includes_procore_checkbox(self):
        # The JS template used by + Browse files / + Add by name spawns new
        # rows. New rows must default share_to_procore=false (off) and include
        # the procore checkbox so users can opt in.
        html = self._gen()
        # Find the ATTACHMENT_TEMPLATE block in the generated JS
        m = re.search(
            r'const ATTACHMENT_TEMPLATE\s*=\s*`([^`]*)`', html, re.DOTALL,
        )
        self.assertIsNotNone(m, 'ATTACHMENT_TEMPLATE literal not found in JS')
        tmpl = m.group(1)
        self.assertIn('data-share-procore="false"', tmpl)
        self.assertIn('data-procore-checked', tmpl)

    def test_copy_for_claude_js_emits_procore_fields(self):
        """`Copy for Claude` builds JSON via collectFields(). The shape must
        match parse_email_html.parse_preview_html so Claude can apply the
        JSON in one pass without re-reading the HTML — specifically
        share_to_procore per attachment and top-level skip_procore."""
        html = self._gen()
        # Locate the collectFields function body with a brace-matching walk
        start = html.find('function collectFields()')
        self.assertGreaterEqual(start, 0, 'collectFields() not found in JS')
        depth = 0
        body_end = -1
        for i, ch in enumerate(html[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    body_end = i + 1
                    break
        self.assertGreater(body_end, start, 'collectFields() body unbalanced')
        body = html[start:body_end]
        # share_to_procore must be emitted on each attachment row
        self.assertIn('share_to_procore', body,
                      'collectFields() must include share_to_procore on each '
                      'attachment so Copy-for-Claude matches the parser shape')
        # Top-level skip_procore must be emitted
        self.assertIn('skip_procore', body,
                      'collectFields() must emit top-level skip_procore so '
                      'Copy-for-Claude matches the parser shape')

    def test_procore_checkbox_change_listener_present(self):
        """As the user toggles a Procore P checkbox, the LI's
        data-share-procore must update live so the CSS border highlight
        tracks the checkbox and the saved-snapshot HTML stays accurate."""
        html = self._gen()
        # The change listener must reference data-procore-checked
        self.assertRegex(
            html,
            r"matches\(\s*['\"]input\[data-procore-checked\]['\"]\s*\)",
            'No change listener wires data-procore-checked → '
            'data-share-procore on the attachment row',
        )


if __name__ == '__main__':
    unittest.main()
