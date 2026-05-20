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


class TestScheduleCompressionIndex(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / '07-schedule-compression-index-over-time.png'

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_valid_png(self):
        data = json.loads((FIXTURE_DIR / '07-schedule-compression-index-over-time.json').read_text())
        charts.render_schedule_compression_index(data, str(self.output))
        self.assertTrue(self.output.exists())
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')
        width, height = img.size
        self.assertGreater(width, height * 1.8)


class TestVelocity(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / '08-velocity.png'

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_valid_png(self):
        data = json.loads((FIXTURE_DIR / '08-velocity.json').read_text())
        charts.render_velocity(data, str(self.output))
        self.assertTrue(self.output.exists())
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')
        width, height = img.size
        self.assertGreater(width, height * 1.8)


class TestSpiOverTime(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / '09-spi-over-time.png'

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_valid_png(self):
        data = json.loads((FIXTURE_DIR / '09-spi-over-time.json').read_text())
        charts.render_spi_over_time(data, str(self.output))
        self.assertTrue(self.output.exists())
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')
        width, height = img.size
        self.assertGreater(width, height * 1.8)


class TestActivityHitRate(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / '10-activity-hit-rate.png'

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_valid_png(self):
        data = json.loads((FIXTURE_DIR / '10-activity-hit-rate.json').read_text())
        charts.render_activity_hit_rate(data, str(self.output))
        self.assertTrue(self.output.exists())
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')
        width, height = img.size
        self.assertGreater(width, height * 1.8)


class TestWindowStartAccuracy(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / '11-window-start-accuracy.png'

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_valid_png(self):
        data = json.loads((FIXTURE_DIR / '11-window-start-accuracy.json').read_text())
        charts.render_window_start_accuracy(data, str(self.output))
        self.assertTrue(self.output.exists())
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')


class TestWindowFinishAccuracy(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / '12-window-finish-accuracy.png'

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_valid_png(self):
        data = json.loads((FIXTURE_DIR / '12-window-finish-accuracy.json').read_text())
        charts.render_window_finish_accuracy(data, str(self.output))
        self.assertTrue(self.output.exists())
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')


class TestNonDefaultStubs(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output_dir = Path(self._tmp.name) / 'out'

    def tearDown(self):
        self._tmp.cleanup()

    def test_unimplemented_chart_is_reported_as_failed(self):
        payload_dir = Path(self._tmp.name) / 'payload'
        payload_dir.mkdir()
        (payload_dir / '01-planned-vs-actual-percent-complete.json').write_text('{}')
        results = render.render_payload(payload_dir, self.output_dir)
        self.assertEqual(results['rendered'], [])
        self.assertEqual(len(results['failed']), 1)
        self.assertIn('NotImplementedError', results['failed'][0]['reason'])
        self.assertIn('--legacy', results['failed'][0]['reason'])


if __name__ == '__main__':
    unittest.main()
