import json
import shutil
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
        # Use slug 02 (still a stub) — slug 01 is implemented now via the
        # HTML+SVG path. Replace with another remaining stub if 02 also
        # gets implemented later.
        payload_dir = Path(self._tmp.name) / 'payload'
        payload_dir.mkdir()
        (payload_dir / '02-schedule-quality-grade-over-time.json').write_text('{}')
        results = render.render_payload(payload_dir, self.output_dir)
        self.assertEqual(results['rendered'], [])
        self.assertEqual(len(results['failed']), 1)
        self.assertIn('NotImplementedError', results['failed'][0]['reason'])
        self.assertIn('--legacy', results['failed'][0]['reason'])


@unittest.skipIf(shutil.which('node') is None,
                 'node executable not on PATH — HTML→PNG rasterisation needs it')
class TestPlannedVsActualPercentComplete(unittest.TestCase):
    """Chart 01 — HTML+SVG renderer + Chromium rasterisation. Verifies both
    the HTML artifact (so QA can open it in a browser) and the PNG attachment
    (what the email pipeline ships) are produced with the SmartPM-cloned
    series colors and dash patterns intact."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.output = Path(self._tmp.name) / '01-planned-vs-actual-percent-complete.png'
        self.html   = self.output.with_suffix('.html')
        self.data = json.loads(
            (FIXTURE_DIR / '01-planned-vs-actual-percent-complete.json').read_text()
        )

    def tearDown(self):
        self._tmp.cleanup()

    def test_renders_html_sibling_with_smartpm_palette_and_dasharray(self):
        # The .png needs Chromium (~30s on a cold start); the .html artifact
        # alone is enough to assert the visual contract — palette + dashes.
        # Call the building blocks directly so this test stays fast and
        # doesn't depend on Chromium being installed.
        charts.render_planned_vs_actual_percent_complete.__wrapped__ if False else None
        # Build only the HTML by going through the public function but
        # short-circuiting the rasterisation step.
        original = charts._html_to_png
        try:
            charts._html_to_png = lambda *a, **kw: None  # no-op
            charts.render_planned_vs_actual_percent_complete(self.data, str(self.output))
        finally:
            charts._html_to_png = original

        self.assertTrue(self.html.exists(), 'sibling HTML artifact missing')
        body = self.html.read_text(encoding='utf-8')

        # All six SmartPM series colors must be present.
        for color in ('#808080', '#b00020', '#2caffe', '#1476b7', '#388543', '#cccccc'):
            self.assertIn(color, body, f'palette color {color} missing from HTML')

        # Scheduled Completion must carry the dashed pattern (this is the
        # specific bug the rebuild fixes — the dashed line going missing on
        # the legacy Playwright capture).
        self.assertIn('stroke-dasharray="8,6"', body,
                      '8,6 dash pattern (Scheduled Completion + data-date line) missing')

        # Title and the legend labels show up verbatim.
        self.assertIn('Planned VS Actual Percent Complete', body)
        self.assertIn('Progress Target', body)
        self.assertIn('Scheduled Completion', body)
        self.assertIn('Late Date Planned', body)
        self.assertIn('Early Date Planned', body)

    def test_full_pipeline_writes_png_via_chromium(self):
        # The full end-to-end: HTML written, then rasterised by html_to_png.js.
        # Skipped if node isn't installed (class-level decorator above);
        # individually skip when Playwright/Chromium isn't installed yet,
        # since we don't want to auto-install in a test.
        try:
            charts.render_planned_vs_actual_percent_complete(self.data, str(self.output))
        except RuntimeError as e:
            msg = str(e)
            if 'Playwright is not installed' in msg or 'Executable doesn' in msg:
                self.skipTest(f'Playwright/Chromium not installed: {msg.splitlines()[0]}')
            raise

        self.assertTrue(self.output.exists(), 'PNG was not created')
        img = Image.open(self.output)
        self.assertEqual(img.format, 'PNG')
        width, height = img.size
        # Wide-and-short, like the matplotlib charts (≥ 1.8 aspect ratio).
        self.assertGreater(width, height * 1.8,
                           f'expected wide PNG, got {width}x{height}')
        # 1728x432 nominal at 2× = 3456x864. Allow some slack for either DPR.
        self.assertGreaterEqual(width, 1700)
        img.close()


class TestSummaryReportComposite(unittest.TestCase):
    """All three summary parts (cards, milestones, curve) render → render.py
    composites them into a single smartpm-summary-report.png so the email
    pipeline's single-summary-image kwarg keeps working unchanged."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.payload_dir = Path(self._tmp.name) / 'payload'
        self.payload_dir.mkdir()
        self.output_dir = Path(self._tmp.name) / 'out'

    def tearDown(self):
        self._tmp.cleanup()

    def _seed_summary_parts(self):
        for slug in (
            'smartpm-summary-cards',
            'smartpm-summary-curve',
            'smartpm-summary-milestones',
        ):
            (self.payload_dir / f'{slug}.json').write_text(
                (FIXTURE_DIR / f'{slug}.json').read_text()
            )

    def test_composite_produced_when_all_three_parts_render(self):
        self._seed_summary_parts()
        r = render.render_payload(self.payload_dir, self.output_dir)

        slugs = [item['slug'] for item in r['rendered']]
        self.assertIn('smartpm-summary-report', slugs,
                      'composite was not produced even though all 3 parts rendered')

        composite_path = self.output_dir / 'smartpm-summary-report.png'
        self.assertTrue(composite_path.exists())
        img = Image.open(composite_path)
        self.assertEqual(img.format, 'PNG')

        # The composite stacks all three parts vertically with no padding,
        # so total height == sum of part heights and width == max part width.
        part_heights = []
        part_widths  = []
        for slug in (
            'smartpm-summary-cards',
            'smartpm-summary-curve',
            'smartpm-summary-milestones',
        ):
            part = Image.open(self.output_dir / f'{slug}.png')
            part_heights.append(part.height)
            part_widths.append(part.width)
            part.close()
        self.assertEqual(img.height, sum(part_heights))
        self.assertEqual(img.width, max(part_widths))
        img.close()

    def test_no_composite_when_a_part_is_missing(self):
        # Render only two of the three parts — composite should NOT fire.
        for slug in ('smartpm-summary-cards', 'smartpm-summary-curve'):
            (self.payload_dir / f'{slug}.json').write_text(
                (FIXTURE_DIR / f'{slug}.json').read_text()
            )
        r = render.render_payload(self.payload_dir, self.output_dir)
        slugs = [item['slug'] for item in r['rendered']]
        self.assertNotIn('smartpm-summary-report', slugs)
        self.assertFalse((self.output_dir / 'smartpm-summary-report.png').exists())


if __name__ == '__main__':
    unittest.main()
