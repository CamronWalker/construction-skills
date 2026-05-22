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


if __name__ == '__main__':
    unittest.main()
