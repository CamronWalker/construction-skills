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
        self.assertEqual(draft['project'], 'G2203')
        self.assertEqual(draft['report_date'], '2026-05-21')
        self.assertEqual(draft['meta']['schema_version'], 1)

    def test_load_draft_raises_on_missing_top_level_keys(self):
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump({'project': 'X'}, f)
            path = f.name
        try:
            with self.assertRaises(email_draft_io.DraftError):
                email_draft_io.load_draft(path)
        finally:
            os.unlink(path)

    def test_load_draft_raises_on_unsupported_schema(self):
        bad = json.loads(SAMPLE_DRAFT_PATH.read_text())
        bad['meta']['schema_version'] = 999
        with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
            json.dump(bad, f)
            path = f.name
        try:
            with self.assertRaises(email_draft_io.DraftError) as ctx:
                email_draft_io.load_draft(path)
            self.assertIn('schema_version', str(ctx.exception))
        finally:
            os.unlink(path)


class BuildStackedChartPageTests(unittest.TestCase):
    def setUp(self):
        self.draft = email_draft_io.load_draft(str(SAMPLE_DRAFT_PATH))
        self.graph_html = self.draft['graph_html']
        self.order = self.draft['editorial']['graph_order']

    def test_emits_html5_document(self):
        page = email_draft_io.build_stacked_chart_page(self.graph_html, self.order)
        self.assertTrue(page.startswith('<!DOCTYPE html>'))
        self.assertIn('<html', page)
        self.assertIn('</html>', page)

    def test_contains_every_slug_in_canonical_order(self):
        page = email_draft_io.build_stacked_chart_page(self.graph_html, self.order)
        positions = [page.find(slug) for slug in self.order]
        # All present
        self.assertTrue(all(p >= 0 for p in positions), f'positions: {positions}')
        # Ascending — appears in canonical order
        self.assertEqual(positions, sorted(positions))

    def test_viewport_width_is_1200(self):
        page = email_draft_io.build_stacked_chart_page(self.graph_html, self.order)
        # Either via meta viewport or explicit body width — either signal is fine
        self.assertTrue(
            'width=1200' in page or 'width:1200px' in page or 'max-width:1200px' in page,
            'expected a 1200px width signal in stacked page'
        )

    def test_skips_slugs_missing_from_graph_html(self):
        page = email_draft_io.build_stacked_chart_page(
            self.graph_html,
            self.order + ['nonexistent-slug-xyz']
        )
        # Doesn't crash; doesn't include the missing slug verbatim
        self.assertNotIn('nonexistent-slug-xyz', page)

    def test_skips_slugs_with_blank_html(self):
        graph_html = dict(self.graph_html)
        graph_html['02-schedule-quality-grade-over-time'] = {
            'status': 'ready',
            'html': '',
            'svgInner': ''
        }
        page = email_draft_io.build_stacked_chart_page(graph_html, self.order)
        # Other slugs still present
        self.assertIn('01-planned-vs-actual-percent-complete', page)


if __name__ == '__main__':
    unittest.main()
