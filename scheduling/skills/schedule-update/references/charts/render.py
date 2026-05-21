"""CLI entry point: read {slug}.json files from a payload dir, dispatch each
to its render function from the REGISTRY, write {slug}.png to the output dir.

Partial success: one chart failing does not abort the others. Failures are
reported in the JSON output.

Summary Report composite: after the main loop, if all three summary parts
(smartpm-summary-cards, smartpm-summary-milestones, smartpm-summary-curve)
rendered successfully, they are stacked vertically into a single
`smartpm-summary-report.png` so the email pipeline (which embeds one
`summary_screenshot_path` inline image) can use the matplotlib output
unchanged. See `_composite_summary_report`.
"""

import json
import sys
from pathlib import Path

from PIL import Image

from . import charts  # noqa: F401 — chart functions registered below as they're added


# The three summary-report parts that get composited, in the order they
# stack top-to-bottom in the final PNG. Cards first (KPI headline), then
# the plan-vs-actual curve (project trajectory), then the milestones table
# with its header + change-summary bullets last (the dated detail).
_SUMMARY_COMPOSITE_ORDER = (
    'smartpm-summary-cards',
    'smartpm-summary-curve',
    'smartpm-summary-milestones',
)
_SUMMARY_COMPOSITE_OUTPUT_SLUG = 'smartpm-summary-report'

REGISTRY = {
    '06-end-date-variance': charts.render_end_date_variance,
    '07-schedule-compression-index-over-time': charts.render_schedule_compression_index,
    '08-velocity': charts.render_velocity,
    '09-spi-over-time': charts.render_spi_over_time,
    '10-activity-hit-rate': charts.render_activity_hit_rate,
    '11-window-start-accuracy': charts.render_window_start_accuracy,
    '12-window-finish-accuracy': charts.render_window_finish_accuracy,
    'smartpm-summary-curve': charts.render_summary_plan_vs_actual,
    'smartpm-summary-cards': charts.render_summary_cards,
    'smartpm-summary-milestones': charts.render_summary_milestones,

    # Stubs for non-default trend graphs — raise NotImplementedError with a
    # `--legacy` hint. Replace with real render functions as implemented.
    '01-planned-vs-actual-percent-complete': charts.render_planned_vs_actual_percent_complete,
    '02-schedule-quality-grade-over-time': charts.render_schedule_quality_grade_over_time,
    '03-project-health-index-over-time': charts.render_project_health_index_over_time,
    '04-schedule-changes-over-time': charts.render_schedule_changes_over_time,
    '05-schedule-delay-over-time': charts.render_schedule_delay_over_time,
    '13-missing-logic': charts.render_missing_logic,
    '14-average-total-float': charts.render_average_total_float,
    '15-high-total-float': charts.render_high_total_float,
    '16-critical-path-percentage': charts.render_critical_path_percentage,
}


def _composite_summary_report(output_dir, rendered_slugs):
    """If all three summary parts rendered, stack them into one PNG.

    The email pipeline's `summary_screenshot_path` kwarg embeds a single
    inline image with the file name `smartpm-summary-report.png` — the same
    filename the legacy Playwright path produced. This function preserves
    that contract by compositing the matplotlib parts after the main loop.

    Returns a `{slug, path}` dict if the composite was written, or None if
    any part is missing.
    """
    if not all(slug in rendered_slugs for slug in _SUMMARY_COMPOSITE_ORDER):
        return None

    output_dir = Path(output_dir)
    parts = []
    for slug in _SUMMARY_COMPOSITE_ORDER:
        path = output_dir / f'{slug}.png'
        if not path.is_file():
            return None
        parts.append(Image.open(path).convert('RGB'))

    # All summary parts are designed at the same 12-inch figure width, so
    # their pixel widths line up. If they ever drift (one chart at a
    # different DPI, say), use the widest and center-pad narrower ones
    # with white so nothing gets cropped or distorted.
    target_w = max(p.width for p in parts)
    total_h  = sum(p.height for p in parts)

    composite = Image.new('RGB', (target_w, total_h), color=(255, 255, 255))
    y = 0
    for p in parts:
        x = (target_w - p.width) // 2
        composite.paste(p, (x, y))
        y += p.height
        p.close()

    out_path = output_dir / f'{_SUMMARY_COMPOSITE_OUTPUT_SLUG}.png'
    composite.save(out_path, format='PNG')
    composite.close()

    return {'slug': _SUMMARY_COMPOSITE_OUTPUT_SLUG, 'path': str(out_path)}


def render_payload(payload_dir, output_dir):
    """Render every {slug}.json in payload_dir to {slug}.png in output_dir.

    Returns a dict {'rendered': [...], 'failed': [...]}. Also prints the JSON
    to stdout so the calling phase file can parse it.

    After the main loop, if all three summary parts rendered, they're
    composited into a single `smartpm-summary-report.png` so the email
    pipeline can embed it unchanged (matches the legacy Playwright filename).
    """
    payload_dir = Path(payload_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    results = {'rendered': [], 'failed': []}
    for json_file in sorted(payload_dir.glob('*.json')):
        slug = json_file.stem
        func = REGISTRY.get(slug)
        if func is None:
            results['failed'].append({
                'slug': slug,
                'reason': 'no renderer in registry',
            })
            continue
        try:
            data = json.loads(json_file.read_text(encoding='utf-8'))
            out = output_dir / f'{slug}.png'
            func(data, str(out))
            results['rendered'].append({
                'slug': slug,
                'path': str(out),
            })
        except Exception as e:
            results['failed'].append({
                'slug': slug,
                'reason': f'{type(e).__name__}: {e}',
            })

    # Stitch the summary parts (cards + milestones + curve) into a single
    # smartpm-summary-report.png so the email pipeline can embed it via
    # its existing single-image `summary_screenshot_path` kwarg.
    rendered_slugs = {r['slug'] for r in results['rendered']}
    composite = _composite_summary_report(output_dir, rendered_slugs)
    if composite is not None:
        results['rendered'].append(composite)

    print(json.dumps(results, indent=2))
    return results


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: python -m references.charts.render <payload_dir> <output_dir>',
              file=sys.stderr)
        sys.exit(2)
    r = render_payload(sys.argv[1], sys.argv[2])
    sys.exit(0 if not r['failed'] else 1)
