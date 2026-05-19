import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from charts import render, charts


FIXTURE_DIR = Path(__file__).resolve().parent / 'fixtures'


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


class TestEndDateVariance(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / '06-end-date-variance.png'

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_valid_png_at_wide_aspect(self):
        data = json.loads((FIXTURE_DIR / '06-end-date-variance.json').read_text())
        charts.render_end_date_variance(data, str(self.output))

        self.assertTrue(self.output.exists(), 'PNG was not created')
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')
        width, height = img.size
        self.assertGreater(width, height * 1.8,
                           f'Image should be wide-and-short for email column, got {width}x{height}')

    def test_renders_via_orchestrator(self):
        payload_dir = Path(self._tmp.name) / 'payload'
        payload_dir.mkdir()
        (payload_dir / '06-end-date-variance.json').write_text(
            (FIXTURE_DIR / '06-end-date-variance.json').read_text()
        )
        output_dir = Path(self._tmp.name) / 'out'
        results = render.render_payload(payload_dir, output_dir)
        self.assertEqual(len(results['rendered']), 1)
        self.assertEqual(len(results['failed']), 0)
        self.assertTrue((output_dir / '06-end-date-variance.png').exists())


if __name__ == '__main__':
    unittest.main()
