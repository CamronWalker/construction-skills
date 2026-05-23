"""Tests for email_draft_io — load, stack, generate-from-draft."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

# Make references/ importable for the tests
REFERENCES_DIR = Path(__file__).resolve().parent.parent / 'references'
sys.path.insert(0, str(REFERENCES_DIR))

import email_draft_io  # noqa: E402

FIXTURES_DIR = Path(__file__).resolve().parent / 'fixtures'
SAMPLE_DRAFT_PATH = FIXTURES_DIR / 'email-draft-sample.json'


class LoadDraftTests(unittest.TestCase):
    def test_load_draft_returns_parsed_dict(self):
        draft = email_draft_io.load_draft(str(SAMPLE_DRAFT_PATH))
        self.assertEqual(draft['version'], 1)
        self.assertEqual(draft['report_date'], '2026-05-21')
        self.assertEqual(draft['project_info']['job_number'], 'G2203')

    def test_load_draft_raises_on_missing_top_level_keys(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump({'version': 1}, f)
            path = f.name
        try:
            with self.assertRaises(email_draft_io.DraftError):
                email_draft_io.load_draft(path)
        finally:
            os.unlink(path)

    def test_load_draft_raises_on_unsupported_version(self):
        bad = json.loads(SAMPLE_DRAFT_PATH.read_text())
        bad['version'] = 999
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump(bad, f)
            path = f.name
        try:
            with self.assertRaises(email_draft_io.DraftError) as ctx:
                email_draft_io.load_draft(path)
            self.assertIn('version', str(ctx.exception))
        finally:
            os.unlink(path)

    def test_load_draft_allows_null_last_week(self):
        """Week-1 projects ship with last_week=null and must still load."""
        d = json.loads(SAMPLE_DRAFT_PATH.read_text())
        d['last_week'] = None
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump(d, f)
            path = f.name
        try:
            draft = email_draft_io.load_draft(path)
            self.assertIsNone(draft['last_week'])
        finally:
            os.unlink(path)


class BuildStackedChartPageTests(unittest.TestCase):
    def setUp(self):
        self.draft = email_draft_io.load_draft(str(SAMPLE_DRAFT_PATH))
        self.graphs = self.draft['graphs']
        self.order = self.draft['this_week']['graph_order']

    def test_emits_html5_document(self):
        page = email_draft_io.build_stacked_chart_page(self.graphs, self.order)
        self.assertTrue(page.startswith('<!DOCTYPE html>'))
        self.assertIn('<html', page)
        self.assertIn('</html>', page)

    def test_contains_every_slug_in_canonical_order(self):
        page = email_draft_io.build_stacked_chart_page(self.graphs, self.order)
        positions = [page.find(slug) for slug in self.order]
        # All present
        self.assertTrue(all(p >= 0 for p in positions), f'positions: {positions}')
        # Ascending — appears in canonical order
        self.assertEqual(positions, sorted(positions))

    def test_viewport_width_is_1200(self):
        page = email_draft_io.build_stacked_chart_page(self.graphs, self.order)
        # Either via meta viewport or explicit body width — either signal is fine
        self.assertTrue(
            'width=1200' in page or 'width:1200px' in page or 'max-width:1200px' in page,
            'expected a 1200px width signal in stacked page'
        )

    def test_skips_slugs_missing_from_graphs(self):
        page = email_draft_io.build_stacked_chart_page(
            self.graphs,
            self.order + ['nonexistent-slug-xyz']
        )
        # Doesn't crash; doesn't include the missing slug verbatim
        self.assertNotIn('nonexistent-slug-xyz', page)

    def test_skips_slugs_with_blank_html(self):
        graphs = dict(self.graphs)
        graphs['02-schedule-quality-grade-over-time'] = {
            'html': '',
            'data': {}
        }
        page = email_draft_io.build_stacked_chart_page(graphs, self.order)
        # Other slugs still present
        self.assertIn('01-planned-vs-actual-percent-complete', page)


class RenderStackedPngTests(unittest.TestCase):
    def setUp(self):
        self.draft = email_draft_io.load_draft(str(SAMPLE_DRAFT_PATH))

    def test_returns_path_to_existing_png(self):
        # Real integration: this requires html_to_png.cjs to exist + Node + Playwright
        # Use a fake renderer to keep the unit test hermetic.
        import unittest.mock as mock

        def fake_render(html_path, png_path, *args, **kwargs):
            Path(png_path).write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 16)
            return png_path

        with mock.patch.object(email_draft_io, '_run_html_to_png', side_effect=fake_render):
            with tempfile.TemporaryDirectory() as tmpdir:
                out = email_draft_io.render_stacked_png(
                    self.draft, output_dir=tmpdir
                )
                self.assertTrue(os.path.isfile(out))
                self.assertTrue(out.endswith('.png'))
                self.assertGreater(os.path.getsize(out), 0)

    def test_raises_if_html_to_png_fails(self):
        import unittest.mock as mock

        def failing_render(*args, **kwargs):
            raise email_draft_io.DraftError('html_to_png.cjs failed')

        with mock.patch.object(email_draft_io, '_run_html_to_png', side_effect=failing_render):
            with tempfile.TemporaryDirectory() as tmpdir:
                with self.assertRaises(email_draft_io.DraftError):
                    email_draft_io.render_stacked_png(self.draft, output_dir=tmpdir)


class EditorialToKwargsTests(unittest.TestCase):
    def setUp(self):
        self.draft = email_draft_io.load_draft(str(SAMPLE_DRAFT_PATH))
        self.kwargs = email_draft_io.editorial_to_kwargs(
            self.draft['this_week'],
            project_info=self.draft['project_info'],
            last_week=self.draft.get('last_week'),
        )

    def test_passes_through_project_info_and_metrics(self):
        self.assertEqual(self.kwargs['project_info']['project_name'], 'Lubumbashi MTC')
        self.assertEqual(self.kwargs['project_info']['job_number'], 'G2203')
        self.assertEqual(self.kwargs['days_behind'], 14)
        self.assertEqual(self.kwargs['gain_loss'], -3)

    def test_passes_through_subject_and_recipients(self):
        self.assertIn('Lubumbashi', self.kwargs['subject'])
        self.assertEqual(self.kwargs['to_recipients'], 'owner@example.com; pm@example.com')
        self.assertEqual(self.kwargs['cc_recipients'], 'sub1@example.com; sub2@example.com')
        self.assertIn('camron@westlandconstruction.com', self.kwargs['from_address'])

    def test_passes_through_narrative_blocks(self):
        self.assertIn('weather delays', self.kwargs['gain_loss_narrative'])
        self.assertIn('EOT request 0017', self.kwargs['eot_recovery'])
        self.assertIn('Reordered MEP', self.kwargs['logic_changes'])
        self.assertEqual(self.kwargs['smartpm_changelog_url'],
                         'https://app.smartpm.com/projects/12345/changelog')

    def test_filters_item_lists_to_checked_and_not_archived(self):
        # Sample has 3 successes: 2 active/new + checked, 1 archived.
        # The .eml builder receives only the 2 visible items as HTML strings.
        successes = self.kwargs['successes']
        self.assertEqual(len(successes), 2)
        self.assertIn('Foundation pour', successes[0])
        self.assertIn('Steel delivery confirmed', successes[1])
        # Archived item is excluded.
        self.assertFalse(any('Old success' in s for s in successes))

    def test_filters_attachments_to_checked_and_not_archived(self):
        att = self.kwargs['attachment_paths']
        self.assertEqual(len(att), 2)
        # Names, not paths — the orchestrator resolves to absolute paths.
        self.assertTrue(att[0].endswith('Weekly Report 2026-05-21.pdf'))
        self.assertTrue(att[1].endswith('EOT Request 0017.pdf'))

    def test_passes_signer_block(self):
        self.assertEqual(self.kwargs['signer_name'], 'Camron Walker')
        self.assertEqual(self.kwargs['signer_title'], 'Scheduler')
        self.assertEqual(self.kwargs['signer_mobile'], '555-0100')

    def test_passes_custom_paragraphs_filtered_to_checked(self):
        custom = self.kwargs['custom_paragraphs']
        self.assertEqual(len(custom), 1)
        self.assertEqual(custom[0]['label'], 'Owner directive 2026-05-19')

    def test_drops_skip_procore_and_share_to_procore_fields(self):
        # Those fields drive the procore phase, not the .eml body.
        self.assertNotIn('skip_procore', self.kwargs)
        self.assertNotIn('share_to_procore', self.kwargs)

    def test_passes_closing_line_and_salutation(self):
        self.assertEqual(
            self.kwargs['closing_line'],
            'Please let me know if you have any questions.',
        )
        self.assertEqual(self.kwargs['salutation'], 'Thanks,')

    def test_passes_prev_metrics_from_last_week(self):
        # Fixture last_week.days_behind=11, gain_loss=2.
        self.assertEqual(self.kwargs['prev_days_behind'], 11)
        self.assertEqual(self.kwargs['prev_gain_loss'], 2)

    def test_prev_metrics_none_when_last_week_missing(self):
        kwargs = email_draft_io.editorial_to_kwargs(
            self.draft['this_week'],
            project_info=self.draft['project_info'],
            last_week=None,
        )
        self.assertIsNone(kwargs['prev_days_behind'])
        self.assertIsNone(kwargs['prev_gain_loss'])


class GenerateEmailFromDraftTests(unittest.TestCase):
    def setUp(self):
        self.draft = email_draft_io.load_draft(str(SAMPLE_DRAFT_PATH))

    def test_full_orchestration_writes_eml_and_invokes_builder(self):
        import unittest.mock as mock
        captured = {}

        def fake_render_stacked_png(draft, output_dir):
            os.makedirs(output_dir, exist_ok=True)
            path = os.path.join(output_dir, 'fake-stacked.png')
            Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 16)
            return path

        def fake_generate_eml(output_path, **kwargs):
            captured['kwargs'] = kwargs
            captured['output_path'] = output_path
            Path(output_path).write_text('fake eml')
            return os.path.abspath(output_path)

        with mock.patch.object(email_draft_io, 'render_stacked_png',
                               side_effect=fake_render_stacked_png), \
             mock.patch.object(email_draft_io, '_call_generate_update_email_eml',
                               side_effect=fake_generate_eml):
            with tempfile.TemporaryDirectory() as tmpdir:
                # Pretend the .pdf attachments are present in the dated folder
                for att in self.draft['this_week']['attachments']:
                    Path(tmpdir, att['filename']).write_bytes(b'%PDF stub')
                Path(tmpdir, self.draft['this_week']['changes_report']['filename']).write_bytes(b'%PDF stub')

                eml_path = email_draft_io.generate_email_from_draft(
                    draft_path=str(SAMPLE_DRAFT_PATH),
                    output_eml_path=os.path.join(tmpdir, 'out.eml'),
                    dated_folder=tmpdir,
                )

                self.assertTrue(os.path.isfile(eml_path))
                # Builder received the stacked PNG via summary_screenshot_path
                self.assertIn('summary_screenshot_path', captured['kwargs'])
                self.assertTrue(captured['kwargs']['summary_screenshot_path'].endswith('.png'))
                # No per-graph paths — stacked PNG replaces them
                self.assertEqual(captured['kwargs'].get('graph_screenshot_paths', []), [])
                # Attachment paths are absolute and exist
                for att_path in captured['kwargs']['attachment_paths']:
                    self.assertTrue(os.path.isabs(att_path))
                    self.assertTrue(os.path.isfile(att_path))

    def test_skips_attachments_that_dont_exist_on_disk(self):
        import unittest.mock as mock

        def fake_render_stacked_png(draft, output_dir):
            os.makedirs(output_dir, exist_ok=True)
            path = os.path.join(output_dir, 'fake-stacked.png')
            Path(path).write_bytes(b'\x89PNG\r\n\x1a\n' + b'\x00' * 16)
            return path

        captured = {}

        def fake_generate_eml(output_path, **kwargs):
            captured['kwargs'] = kwargs
            Path(output_path).write_text('fake eml')
            return os.path.abspath(output_path)

        with mock.patch.object(email_draft_io, 'render_stacked_png',
                               side_effect=fake_render_stacked_png), \
             mock.patch.object(email_draft_io, '_call_generate_update_email_eml',
                               side_effect=fake_generate_eml):
            with tempfile.TemporaryDirectory() as tmpdir:
                # NO attachment files placed in tmpdir
                email_draft_io.generate_email_from_draft(
                    draft_path=str(SAMPLE_DRAFT_PATH),
                    output_eml_path=os.path.join(tmpdir, 'out.eml'),
                    dated_folder=tmpdir,
                )
                # Builder receives empty attachment list (missing files skipped)
                self.assertEqual(captured['kwargs']['attachment_paths'], [])


if __name__ == '__main__':
    unittest.main()
