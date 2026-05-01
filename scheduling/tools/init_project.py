"""init_project.py -- create the v4.0.0 folder layout for a new proposal
project.

Creates:
    <project>/
        Bid Documents/
        Sample Schedules/
        Old Iterations/
            scores/
        proposal-anchors.json   (stub, optional)

Does NOT create the XER -- that's the agent's job after the plan is locked.

Usage:
    python init_project.py "<path-to-project-folder>"
    python init_project.py "<name>" --root "<parent-folder>"
"""

import argparse
import json
import sys
from pathlib import Path

import _layout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project',
                    help='Either an absolute path to the project folder, or a '
                         'name (used with --root)')
    ap.add_argument('--root', default=None,
                    help='Parent folder; project is created under <root>/<name>')
    ap.add_argument('--anchors-stub', action='store_true',
                    help='Drop a placeholder proposal-anchors.json')
    args = ap.parse_args()

    if args.root:
        project = Path(args.root) / args.project
    else:
        project = Path(args.project)

    if project.exists() and not project.is_dir():
        print(f'ERROR: exists and is not a directory: {project}', file=sys.stderr)
        return 1
    project.mkdir(parents=True, exist_ok=True)

    bid = project / 'Bid Documents'
    samples = project / 'Sample Schedules'
    iters = project / _layout.NEW_ITERATIONS_DIR
    scores = iters / 'scores'

    bid.mkdir(exist_ok=True)
    samples.mkdir(exist_ok=True)
    iters.mkdir(exist_ok=True)
    scores.mkdir(exist_ok=True)

    if args.anchors_stub:
        stub_path = project / 'proposal-anchors.json'
        if not stub_path.exists():
            stub_path.write_text(
                json.dumps({
                    'project_name': project.name,
                    'anchors': []
                }, ensure_ascii=False, indent=2),
                encoding='utf-8',
            )

    print(f'Initialized:    {project}')
    print(f'  Bid Documents/      (drop bid PDFs here)')
    print(f'  Sample Schedules/   (drop reference XERs here)')
    print(f'  Old Iterations/     (will hold paste archives, prior XERs, scores)')
    print(f'    scores/')
    if args.anchors_stub:
        print(f'  proposal-anchors.json (stub)')
    print()
    print('Next: drop bid docs and sample XERs, run the proposal-schedule')
    print('skill to generate the v1 XER at the project root, then iterate.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
