# propsched -- API reference

Single-page reference for the proposal-schedule toolchain. All operations
run through one dispatcher: `python propsched.py <verb> [args]`.

If you're an agent iterating on a proposal schedule, this is the only
file you need to load to know how to act. Each verb is documented below
with its inputs, outputs, exit codes, and a one-line example. The
underlying scripts live in `scheduling/tools/`; you should not need to
read them directly.

## Folder layout (v5.0.0+)

```
<project>/
  Bid Documents/                        <- bid PDFs
  Sample Schedules/                     <- reference XERs
  <Project>.xer                         <- current/working XER (no -vN suffix)
  schedule-activities.json              <- current
  schedule-review.html                  <- current (now version-aware in topbar)
  Schedule Plan.pdf                     <- final plan (post-approval)
  proposal-anchors.json                 <- anchor metadata
  project-metadata.json                 <- v5: project context (type, sf, region, systems, ...)
  Old Iterations/
    <Project> -v1.xer ... -v{N-1}.xer  <- prior versions
    paste-*.json                        <- per-iteration paste-back archive
    durations.json                      <- v5: per-activity duration knowledge (project-context-bound)
    reviewer-feedback/                  <- v5: parked external-reviewer JSONs
      {reviewer-slug}-{date}-v{N}.json
    postmortems/                        <- v5: folder-style postmortems
      {YYYY-MM-DD}-{project-slug}/
        postmortem.md
        project-metadata.json           <- snapshot at completion
        durations-captured.json         <- entries added this cycle
        reviewer-feedback/              <- copies of parked feedback
    postmortem-*.md                     <- legacy v4.x single-file postmortem (still readable)
    scores/v{N}.json                    <- per-version score sidecars
    .cpm-cache/<sha256>.json            <- CPM result cache
    .iterate-debug.log                  <- when iterate is run with --verbose
```

Legacy projects (v3.x and v4.x) are auto-detected and continue to work;
new projects use the layout above. The folder-style postmortem is
self-contained and copyable to a master library.

## Quick reference

```bash
# Set up a new project
propsched init "<path>"
propsched metadata set "<project>" --project-type k-12 --region "Utah Valley" \
    --building-systems structural-masonry,steel-joist --square-footage 65000

# After v1 is generated (via the schedule-create-proposal-schedule skill)
propsched bootstrap-anchors "<project>"      # if v1 still has CS_MSO/CS_FNLT
propsched anchors "<project>"                 # confirm anchor status
propsched paths "<project>"                   # see critical / driving paths

# Camron paste-back arrives
propsched iterate --project "<project>" --paste paste.json
# If it reports anchor slips, form absorption.json, then:
propsched iterate --project "<project>" --paste paste.json --apply absorption.json

# External reviewer (boss / consultant) emails their feedback JSON back
propsched feedback ingest "<project>" --file steve-feedback.json
propsched feedback list "<project>"            # see all parked feedback + staleness

# Inspect history
propsched diff "<project>" v3 v4              # pairwise compare
propsched walk "<project>"                    # walk v1 -> current
propsched score "<project>" --version 11      # score sidecar

# Pull duration knowledge for the next draft
propsched durations query --root "<proposals-root>" --task "Pour Footings" \
    --type k-12 --region "Utah Valley"

# Phase 1 of next proposal: ingest prior lessons
propsched aggregate-postmortems --project-type lab-research --show-durations

# Final approval -- assemble the postmortem folder, then write postmortem.md
propsched postmortem "<project>" --slug murray-apex-center
propsched durations extract "<project>"        # auto-pull duration insights from feedback
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
2. Snapshots prior task dates for the impact diff.
3. Applies `duration_change` from `--paste` (and optional `--apply`) in memory.
4. Runs what-if CPM (cached by content hash; `--no-cache` to bypass).
5. Calls `check_anchor_dates`. If any anchor slips later than its bid-given date, prints slips + top-5 cut candidates per slip and exits with code 2. **Nothing is written.**
6. If anchors hold:
   - New layout: archives the existing root XER to `Old Iterations/<Project> -v{N}.xer`, writes new XER content to root.
   - Legacy: writes `-v{N+1}.xer` in place.
   - Regenerates `schedule-activities.json` (preserves `default_view` from paste).
   - **Parallel:** renders `schedule-review.html` (subprocess) while scoring the new state.
   - Archives the paste-back to `Old Iterations/paste-{N+1}.json`.
   - Writes a score sidecar to `Old Iterations/scores/v{N+1}.json`.
   - Prints the file-write confirmation, then an **Impact** block (only sections with non-zero changes) + **Score** block.

**Impact block fields** (each shown only if it changed):
- SC delta (anchor or absolute)
- Critical-path end task and length (with "(was X)" if the end shifted)
- Per-anchor drift change (old drift -> new drift, with "pulled in / pushed out" annotation)
- Top 5 task EF shifts by absolute delta
- Near-critical chain count delta

**Score block fields**:
- `Grade Score -> Grade Score (+/-delta)` if a prior sidecar exists; else just the new grade
- Top 3 deductions by points lost
- Drill-down hint to `propsched score` for full activity lists

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

Phase 1 of the next proposal: walk past postmortems across every project
(folder-style and legacy single-file), parse the Hypotheses section,
recency-weight, print a markdown ruleset block ready to inject into
recommendations. Filterable by project metadata (type / region /
building system) so the next K-12 in Utah Valley pulls hypotheses from
the same context.

```bash
propsched aggregate-postmortems
propsched aggregate-postmortems --project-type "lab-research"
propsched aggregate-postmortems --region "Utah Valley" --system structural-masonry
propsched aggregate-postmortems --show-durations         # also surface duration knowledge
propsched aggregate-postmortems --top 5 --half-life 180
propsched aggregate-postmortems --json
```

With zero postmortems: friendly skip message, draft proceeds with
default Westland standards. With a corpus: every hypothesis is cited
back to its source project + date for auditability.

Exit codes: 0 (printed), 1 (no root found).

---

### `propsched feedback`

Park reviewer-feedback JSONs (downloaded from `schedule-review.html` by
external reviewers) and report drift vs the current XER. Feedback can
arrive days or weeks after the reviewer looked at the schedule -- this
verb does NOT auto-apply changes; it parks the JSON for the scheduler
to read with full context (version reviewed, tasks renamed since,
durations changed since, tasks dropped).

```bash
propsched feedback ingest "<project>" --file steve-feedback.json
propsched feedback ingest "<project>" --file steve-feedback.json --force
propsched feedback list "<project>"
propsched feedback show "<project>" steve                 # prefix match
```

Storage: `Old Iterations/reviewer-feedback/{reviewer-slug}-{date}-v{N}.json`.

Drift report flags:
- `[error]` reviewer claims a future version (file probably wrong project)
- `[warn]`  reviewer is N versions behind / task no longer exists / duration changed
- `[info]`  task renamed since review / no version_reviewed in JSON

Exit codes: 0 (no drift), 1 (error), 2 (drift warnings present).

---

### `propsched metadata`

Read or set per-project metadata (project_type, square_footage, region,
delivery_method, building_systems, ...). Stored as `project-metadata.json`
at the project root. Every duration entry inherits this snapshot --
context-free durations don't mean anything.

```bash
propsched metadata init "<project>"           # create empty stub
propsched metadata set "<project>" \
    --project-type k-12 --region "Utah Valley" \
    --square-footage 65000 --difficulty medium \
    --building-systems structural-masonry,steel-joist
propsched metadata show "<project>"
propsched metadata get "<project>" --field region    # one field, plain
propsched metadata get "<project>"                    # full JSON
```

Exit codes: 0, 1.

---

### `propsched durations`

Per-activity duration knowledge keyed by project metadata. The DB lives
at `Old Iterations/durations.json`. Every entry carries a snapshot of
`project-metadata.json` so future drafts can ask "what have we seen
for pour-footings on K-12 jobs in Utah Valley with structural masonry?"

```bash
# Manual entry
propsched durations add "<project>" \
    --task-code APEX0040 --duration 5 \
    --source "super:Mike" \
    --rationale "Soil conditions in Utah Valley typically drive 5-7d for this size"

# Auto-extract from parked reviewer feedback (each duration_change becomes an entry)
propsched durations extract "<project>"

# Query within one project
propsched durations query --project "<project>" --task "Pour Footings"

# Query across every project under a root
propsched durations query --root "<proposals-root>" \
    --task "Pour Footings" --type k-12 --region "Utah Valley"

propsched durations list "<project>"          # local enumeration
propsched durations query ... --json          # machine-readable
```

Output groups entries by task and shows min/max/avg duration with
project-context tags inline (so the user can spot "5d on K-12 + tilt-up
vs 8d on K-12 + structural-masonry" at a glance).

Exit codes: 0, 1.

---

### `propsched postmortem`

Assemble the post-approval postmortem folder (Tier 7+ schema). The
agent writes the narrative; this script does the boring assembly:
creates the folder, snapshots `project-metadata.json`, copies parked
reviewer-feedback into the folder, and (optionally) snapshots the
durations entries added during this cycle.

```bash
propsched postmortem "<project>" --slug murray-apex-center
propsched postmortem "<project>" --slug ... --date 2026-04-30
propsched postmortem "<project>" --slug ... --cycle-start 2026-04-01
propsched postmortem "<project>" --slug ... --print-stub > postmortem.md
propsched postmortem "<project>" --slug ... --skip-durations --skip-reviewer-feedback
```

Output folder:

```
Old Iterations/postmortems/{date}-{slug}/
  postmortem.md                <- stub; agent fills it in
  project-metadata.json        <- snapshot at completion
  durations-captured.json      <- entries added this cycle (if any)
  reviewer-feedback/           <- copies of every parked reviewer JSON
    *.json
```

The folder is self-contained -- copy it to a master library at any time
without losing context.

Exit codes: 0, 1.

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

1. Auto-extract any duration knowledge captured this cycle from parked
   reviewer feedback:
   ```bash
   propsched durations extract "<project>"
   ```
2. Assemble the postmortem folder (creates the folder + stub +
   snapshots metadata + copies reviewer feedback):
   ```bash
   propsched postmortem "<project>" --slug "<project-slug>"
   ```
3. Open `Old Iterations/postmortems/{date}-{slug}/postmortem.md` and fill
   in the stub sections. See `phases/02-iterate.md` for the section schema.
4. Generate the Westland-branded plan PDF (post-approval; the PDF reflects
   the final schedule).
5. Final XER is the `<Project>.xer` at the project root.

### "An external reviewer emailed back their feedback JSON"

```bash
propsched feedback ingest "<project>" --file path/to/steve-feedback.json
# Drift report tells you whether they reviewed the current version
# or one that has since changed.

propsched feedback list "<project>"     # what's parked
propsched feedback show "<project>" steve   # one reviewer in detail
```

The verb only PARKS the JSON. To act on a reviewer's duration suggestions
or comments: read `feedback show`, decide which to keep, then either feed
specific items back through the regular `iterate` paste-back flow or
just adjust the XER directly via the existing iteration loop.

### "Starting a new proposal -- what should I learn from prior cycles?"

```bash
# Hypotheses, recency-weighted, filtered by project context
propsched aggregate-postmortems --project-type "<type>" \
    --region "<region>" --system structural-masonry --show-durations
```

Cite hypotheses you act on by source project + date. Duration knowledge
also surfaces with --show-durations -- "we have N observations of Pour
Footings = 5-7d on K-12 + structural-masonry; using 6d as the seed".

### "What changed across all iterations of this project?"

```bash
propsched walk "<project>"
```

For a single transition with full detail:

```bash
propsched diff "<project>" v6 v7
```

### "Querying duration knowledge for a specific task"

```bash
# Across all projects under a root
propsched durations query --root "<proposals-root>" \
    --task "Pour Footings" --type k-12 --region "Utah Valley"

# Within just one project
propsched durations query --project "<project>" --task-code APEX0040
```

---

## Internal modules (don't read directly)

These live in `scheduling/tools/` and back the CLIs above. You should not
need to import or read them; the CLIs already cover their surface.

- `_xer_io.py` -- XER parse + write helpers
- `_cpm_loader.py` -- locates `cpm_engine.py` (in `schedule-toolbox/lib/`)
- `_cpm_cache.py` -- CPM result cache keyed by content hash
- `_layout.py` -- detects new vs legacy folder layout, resolves paths
