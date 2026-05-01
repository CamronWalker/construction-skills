# propsched -- API reference

Single-page reference for the proposal-schedule toolchain. All operations
run through one dispatcher: `python propsched.py <verb> [args]`.

If you're an agent iterating on a proposal schedule, this is the only
file you need to load to know how to act. Each verb is documented below
with its inputs, outputs, exit codes, and a one-line example. The
underlying scripts live in `scheduling/tools/`; you should not need to
read them directly.

## Folder layout (v4.0.0+)

```
<project>/
  Bid Documents/                        <- bid PDFs
  Sample Schedules/                     <- reference XERs
  <Project>.xer                         <- current/working XER (no -vN suffix)
  schedule-activities.json              <- current
  schedule-review.html                  <- current
  Schedule Plan.pdf                     <- final plan (post-approval)
  proposal-anchors.json                 <- anchor metadata
  Old Iterations/
    <Project> -v1.xer ... -v{N-1}.xer  <- prior versions
    paste-*.json                        <- per-iteration paste-back archive
    postmortem-*.md                     <- per-cycle AI postmortems
    scores/v{N}.json                    <- per-version score sidecars
    .cpm-cache/<sha256>.json            <- CPM result cache
    .iterate-debug.log                  <- when iterate is run with --verbose
```

Legacy projects (v3.x and earlier, "Proposal Schedule/" subfolder) are
auto-detected and continue to work; new projects use the layout above.

## Quick reference

```bash
# Set up a new project
propsched init "<path>"

# After v1 is generated (via the schedule-create-proposal-schedule skill)
propsched bootstrap-anchors "<project>"      # if v1 still has CS_MSO/CS_FNLT
propsched anchors "<project>"                 # confirm anchor status
propsched paths "<project>"                   # see critical / driving paths

# Camron paste-back arrives
propsched iterate --project "<project>" --paste paste.json
# If it reports anchor slips, form absorption.json, then:
propsched iterate --project "<project>" --paste paste.json --apply absorption.json

# Inspect history
propsched diff "<project>" v3 v4              # pairwise compare
propsched walk "<project>"                    # walk v1 -> current
propsched score "<project>" --version 11      # score sidecar

# Phase 1 of next proposal: ingest prior lessons
propsched aggregate-postmortems --project-type lab-research
```

## Verbs

### `propsched init`

Create a new project folder with the v4.0.0 layout.

```bash
propsched init "C:/path/to/Spanish Fork High"
propsched init "Spanish Fork High" --root "/path/to/~Proposal Schedules"
propsched init "<path>" --anchors-stub        # also drop a placeholder anchors JSON
```

Creates: `Bid Documents/`, `Sample Schedules/`, `Old Iterations/`, `Old Iterations/scores/`.
Does NOT create the XER -- that comes from the proposal-schedule skill.

Exit codes: 0 (created), 1 (path exists as a file).

---

### `propsched iterate`

Apply a Copy-for-Claude paste-back. Single entry point for the iteration
loop.

```bash
propsched iterate --project "<project>" --paste paste.json
propsched iterate --project "<project>" --paste paste.json --apply absorption.json
propsched iterate --project "<project>" --paste paste.json --dry-run
propsched iterate --project "<project>" --paste paste.json --no-cache
```

Behavior:
1. Locates the current XER (project root in new layout, latest `-v{N}.xer` in legacy).
2. Applies `duration_change` from `--paste` (and optional `--apply`) in memory.
3. Runs what-if CPM (cached by content hash; `--no-cache` to bypass).
4. Calls `check_anchor_dates`. If any anchor slips later than its bid-given date, prints slips + top-5 cut candidates per slip and exits with code 2. **Nothing is written.**
5. If anchors hold:
   - New layout: archives the existing root XER to `Old Iterations/<Project> -v{N}.xer`, writes new XER content to root.
   - Legacy: writes `-v{N+1}.xer` in place.
   - Regenerates `schedule-activities.json` (preserves `default_view` from paste).
   - Regenerates `schedule-review.html`.
   - Archives the paste-back to `Old Iterations/paste-{N+1}.json`.
   - Prints a 5-line summary.

Exit codes: 0 (success), 1 (error), 2 (anchor slip).

---

### `propsched paths`

Print critical / driving / near-critical / parallel-branch paths from
`schedule-activities.json`. No CPM run, no XER parse.

```bash
propsched paths "<project>"
```

Output: ≤50 lines, formatted for token-efficient agent context. The
critical path (every activity), the driving path to SC (head + tail of
the chain), each near-critical chain (length + min float), parallel
branches.

Exit codes: 0 (printed), 1 (missing JSON).

---

### `propsched anchors`

Print anchor status (anchor / computed / drift) for every anchor in
`proposal-anchors.json`. Reads activities JSON only -- no CPM run.

```bash
propsched anchors "<project>"
```

Output: one line per anchor.

Exit codes: 0 (all anchors hold), 1 (missing JSON), 2 (at least one anchor slipping late).

---

### `propsched bootstrap-anchors`

One-shot hygiene pass: lift CS_MSO / CS_FNLT / CS_MANDSTART / CS_MANDFIN /
CS_MEOB / CS_MFO from the current XER into `proposal-anchors.json`, then
clear the constraint fields on those tasks. Westland's anchor-via-logic
rule. Seasonal constraints (CS_MSOA on a curb-and-gutter task that must
wait for spring) are correctly preserved.

```bash
propsched bootstrap-anchors "<project>"
propsched bootstrap-anchors "<project>" --dry-run
propsched bootstrap-anchors "<project>" --include-types CS_MSO,CS_FNLT
```

In the new layout, the original XER is archived to `Old Iterations/<Project> -v{N}.xer` and the cleaned content is rewritten in place at the root. In the legacy layout, a sibling `-v{N+1}.xer` is written.

Exit codes: 0 (success), 1 (error).

---

### `propsched diff`

Pairwise XER diff between two versions of the same project. Wraps
`xer_compare` and adds two heuristics:

- **Code-reassignment flag**: when a `task_code`'s name has materially
  changed AND the duration delta is large, flags as `[likely-reassignment]`
  rather than reporting a misleading duration change.
- **Classification**: one-word label of the iteration's character --
  `write-back | anchor-cleanup | paste-back | sample-normalize | restructure | mixed`.

```bash
propsched diff "<project>" v3 v4
propsched diff "<project>" v12 current
propsched diff "<project>" v3 v4 --json
propsched diff "<project>" v3 v4 --top 10
```

Output: classification + headline numbers (SC slip, adds/removes,
duration count, constraint count) + top-N changes with reassignment flag.

Exit codes: 0 (printed), 1 (version not found).

---

### `propsched walk`

Walk a project's full chain (v1 -> current) and print one section per
transition. Same classification + reassignment flag as `diff`.

```bash
propsched walk "<project>"
propsched walk "<project>" --top 3
propsched walk "<project>" --json
```

Output: per-transition narrative with classification, headline numbers,
top-N duration changes.

Exit codes: 0.

---

### `propsched score`

Score an XER (DCMA / Westland rubric) and write a small JSON sidecar to
`Old Iterations/scores/v{N}.json` so `diff` and `walk` can show score
deltas across iterations.

```bash
propsched score "<project>"                         # score current
propsched score "<project>" --version 11
propsched score "<project>" --no-sidecar            # print only
propsched score "<project>" --json
```

Sidecar contents: `{version, xer, data_date, score, grade, sc_milestone_date, task_count_in_scope}`.

Exit codes: 0 (scored), 1 (error).

---

### `propsched aggregate-postmortems`

Phase 1 of the next proposal: walk past `Old Iterations/postmortem-*.md`
files across all projects, parse the Hypotheses section, recency-weight,
print a markdown ruleset block ready to inject into recommendations.

```bash
propsched aggregate-postmortems
propsched aggregate-postmortems --project-type "lab-research"
propsched aggregate-postmortems --top 5 --half-life 180
propsched aggregate-postmortems --json
```

With zero postmortems: friendly skip message, draft proceeds with
default Westland standards. With a corpus: every hypothesis is cited
back to its source project + date for auditability.

Exit codes: 0 (printed), 1 (no root found).

---

## Common patterns

### "Camron just sent me a paste-back"

```bash
# 1. Save the paste content to a JSON file
# 2. Optionally orient first
propsched paths "<project>"
# 3. Apply
propsched iterate --project "<project>" --paste paste.json
# If it exits 2: form absorption.json with cuts, then re-run with --apply
```

### "He approved -- generate the deliverable"

1. Write the AI postmortem to `Old Iterations/postmortem-{date}-{project-slug}.md`.
   See `phases/02-iterate.md` for the section schema.
2. Generate the Westland-branded plan PDF (post-approval; the PDF reflects the
   final schedule).
3. Final XER is the `<Project>.xer` at the project root.

### "What changed across all iterations of this project?"

```bash
propsched walk "<project>"
```

For a single transition with full detail:

```bash
propsched diff "<project>" v6 v7
```

### "Starting a new proposal -- what should I learn from prior cycles?"

```bash
propsched aggregate-postmortems --project-type "<type>"
```

Cite hypotheses you act on by source project + date.

---

## Internal modules (don't read directly)

These live in `scheduling/tools/` and back the CLIs above. You should not
need to import or read them; the CLIs already cover their surface.

- `_xer_io.py` -- XER parse + write helpers
- `_cpm_loader.py` -- locates `cpm_engine.py` (in `schedule-toolbox/references/`)
- `_cpm_cache.py` -- CPM result cache keyed by content hash
- `_layout.py` -- detects new vs legacy folder layout, resolves paths
