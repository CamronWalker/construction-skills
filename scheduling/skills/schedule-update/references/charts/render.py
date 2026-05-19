"""CLI entry point: read {slug}.json files from a payload dir, dispatch each
to its render function from the REGISTRY, write {slug}.png to the output dir.

Partial success: one chart failing does not abort the others. Failures are
reported in the JSON output.
"""

import json
import sys
from pathlib import Path

from . import charts  # noqa: F401 — chart functions registered below as they're added

REGISTRY = {
    '06-end-date-variance': charts.render_end_date_variance,
    '07-schedule-compression-index-over-time': charts.render_schedule_compression_index,
    '08-velocity': charts.render_velocity,
}


def render_payload(payload_dir, output_dir):
    """Render every {slug}.json in payload_dir to {slug}.png in output_dir.

    Returns a dict {'rendered': [...], 'failed': [...]}. Also prints the JSON
    to stdout so the calling phase file can parse it.
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

    print(json.dumps(results, indent=2))
    return results


if __name__ == '__main__':
    if len(sys.argv) != 3:
        print('Usage: python -m references.charts.render <payload_dir> <output_dir>',
              file=sys.stderr)
        sys.exit(2)
    r = render_payload(sys.argv[1], sys.argv[2])
    sys.exit(0 if not r['failed'] else 1)
