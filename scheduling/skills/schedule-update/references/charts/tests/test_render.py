import json
import tempfile
import unittest
from pathlib import Path

from charts import render


class TestRenderPayload(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.payload_dir = Path(self._tmp.name) / 'payload'
        self.output_dir = Path(self._tmp.name) / 'out'
        self.payload_dir.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_empty_payload_dir_returns_empty_results(self):
        r = render.render_payload(self.payload_dir, self.output_dir)
        self.assertEqual(r, {'rendered': [], 'failed': []})

    def test_unknown_slug_reports_failure(self):
        (self.payload_dir / 'totally-not-a-real-chart.json').write_text('{}')
        r = render.render_payload(self.payload_dir, self.output_dir)
        self.assertEqual(r['rendered'], [])
        self.assertEqual(len(r['failed']), 1)
        self.assertEqual(r['failed'][0]['slug'], 'totally-not-a-real-chart')
        self.assertIn('no renderer in registry', r['failed'][0]['reason'])


if __name__ == '__main__':
    unittest.main()
