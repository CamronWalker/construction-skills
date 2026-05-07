# scheduling/tools/

Single-entry CLI for the proposal-schedule toolchain:

```bash
python scheduling/tools/propsched.py <verb> [args]
```

Run `propsched --help` for the verb menu, or load **`REFERENCE.md`** in
this folder for the full API reference (inputs, outputs, exit codes,
examples for every verb).

## Folder layout (v4.0.0+)

```
<project>/
  Bid Documents/
  Sample Schedules/
  <Project>.xer                         <- current/working XER (no -vN suffix)
  schedule-activities.json
  schedule-review.html
  Schedule Plan.pdf                     <- final plan (post-approval)
  proposal-anchors.json
  Old Iterations/
    <Project> -v1.xer ... -v{N-1}.xer  <- prior versions
    paste-*.json                        <- per-iteration paste-back archive
    postmortem-*.md                     <- per-cycle AI postmortems
    scores/v{N}.json                    <- per-version score sidecars
    .cpm-cache/<sha256>.json            <- CPM result cache
    .iterate-debug.log                  <- when iterate is run with --verbose
```

Legacy projects (Proposal Schedule/ subfolder) auto-detected and supported.

## Files

```
tools/
  propsched.py                  # the dispatcher -- single CLI entry
  REFERENCE.md                  # API reference for every verb

  proposal_iterate.py           # iterate verb
  show_paths.py                 # paths verb
  show_anchors.py               # anchors verb
  anchors_from_constraints.py   # bootstrap-anchors verb
  show_diff.py                  # diff verb (with reassignment heuristic)
  walk_history.py               # walk verb
  score_with_sidecar.py         # score verb
  postmortem_aggregate.py       # aggregate-postmortems verb
  init_project.py               # init verb

  build_gantt_html.py           # called internally by iterate

  _xer_io.py                    # shared XER parse/write helpers
  _cpm_loader.py                # locates cpm_engine.py
  _cpm_cache.py                 # CPM result cache
  _layout.py                    # layout detection + path resolution
```

Agents iterating on a proposal should load `REFERENCE.md` (single page)
and call `propsched <verb>`. Do not read individual scripts -- the
reference covers every operation, and the dispatcher exposes
`propsched <verb> --help` for per-verb flags.
