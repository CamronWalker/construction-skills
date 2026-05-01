"""propsched.py -- single-entry dispatcher for the proposal-schedule
toolchain.

Every operation runs through one CLI: `python propsched.py <verb> [args]`.
The dispatcher is a thin shell over the per-verb scripts; each script
keeps its argparse interface and `--help` flows through.

Verbs:
    iterate              Apply a paste-back, run CPM, write next XER
    paths                Read the project's critical / driving / near-critical paths
    anchors              Read anchor status (anchor / computed / drift)
    bootstrap-anchors    One-shot: lift anchor-class XER constraints into
                         proposal-anchors.json (legacy hygiene)
    aggregate-postmortems
                         Walk past postmortems, print recency-weighted hypotheses
    diff                 Pairwise XER diff with classification + reassignment flag
    walk                 Walk v1 -> current with per-iteration narrative
    score                Score an XER and write a sidecar to Old Iterations/scores/
    init                 Create a new project folder with the v4.0.0 layout

Run `propsched <verb> --help` for any verb's flags.
"""

import os
import sys
from pathlib import Path


_THIS_DIR = Path(__file__).resolve().parent

# Verb -> (script filename, one-line description)
COMMANDS = {
    'iterate': (
        'proposal_iterate.py',
        'Apply a paste-back; run CPM; write next XER + JSON + HTML',
    ),
    'paths': (
        'show_paths.py',
        'Print critical / driving / near-critical paths',
    ),
    'anchors': (
        'show_anchors.py',
        'Print anchor status (anchor / computed / drift)',
    ),
    'bootstrap-anchors': (
        'anchors_from_constraints.py',
        'Lift CS_MSO/CS_FNLT/etc into proposal-anchors.json + clear them on the XER',
    ),
    'aggregate-postmortems': (
        'postmortem_aggregate.py',
        'Recency-weight past postmortems into a Phase 1 ruleset',
    ),
    'diff': (
        'show_diff.py',
        'Pairwise XER diff with classification + reassignment flag',
    ),
    'walk': (
        'walk_history.py',
        'Walk v1 -> current and narrate every transition',
    ),
    'score': (
        'score_with_sidecar.py',
        'Score an XER (DCMA / Westland) and write sidecar JSON',
    ),
    'init': (
        'init_project.py',
        'Create a new project folder with the v4.0.0 layout',
    ),
}

# Aliases to be forgiving
ALIASES = {
    'init-project': 'init',
    'bootstrap': 'bootstrap-anchors',
    'aggregate': 'aggregate-postmortems',
    'postmortems': 'aggregate-postmortems',
    'history': 'walk',
}


def _print_help():
    print('usage: propsched <verb> [args]')
    print()
    print('Verbs:')
    width = max(len(v) for v in COMMANDS)
    for verb, (_script, desc) in COMMANDS.items():
        print(f'  {verb:<{width}}  {desc}')
    print()
    print('Run `propsched <verb> --help` for any verb-specific flags.')
    print('See REFERENCE.md in this folder for detailed usage of every verb.')


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv or argv[0] in ('-h', '--help', 'help'):
        _print_help()
        return 0
    verb = argv[0]
    verb = ALIASES.get(verb, verb)
    if verb not in COMMANDS:
        print(f'ERROR: unknown verb: {verb}', file=sys.stderr)
        print(file=sys.stderr)
        _print_help()
        return 1
    script_name, _desc = COMMANDS[verb]
    script_path = _THIS_DIR / script_name
    if not script_path.exists():
        print(f'ERROR: missing script: {script_path}', file=sys.stderr)
        return 1

    # Replace sys.argv so the inner script's argparse sees the right name
    # in usage messages (`propsched <verb>` instead of e.g. `proposal_iterate.py`).
    new_argv = [f'propsched {verb}'] + argv[1:]
    saved_argv = sys.argv
    sys.argv = new_argv
    try:
        # Load the target script as a module under its own name and run main()
        import importlib.util
        spec = importlib.util.spec_from_file_location(verb.replace('-', '_'),
                                                      script_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        if hasattr(mod, 'main'):
            return mod.main() or 0
        # Fallback: the script ran top-level on import; if it set sys.exit
        # the SystemExit propagates.
        return 0
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else (1 if e.code else 0)
    finally:
        sys.argv = saved_argv


if __name__ == '__main__':
    sys.exit(main())
