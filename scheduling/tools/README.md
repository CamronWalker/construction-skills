# scheduling/tools/

Standalone CLI tools for the proposal-schedule iteration loop. Each is a
thin wrapper over `cpm_engine.py` (in `skills/schedule-toolbox/references/`)
designed so a Claude Code agent can iterate on a proposal schedule by
calling these CLIs and reading short stdout summaries -- never reading
`cpm_engine.py`, raw `.xer` files, or the full `schedule-activities.json`.

## proposal_iterate.py

Single entry point for the paste-back -> what-if -> anchor-check -> write
cycle. The agent calls this on every paste-back from Camron's Gantt HTML.

```bash
# 1. Camron pastes the Copy-for-Claude payload; agent saves to paste.json.
python scheduling/tools/proposal_iterate.py --project "<project>" --paste paste.json

# 2. If the script reports anchor slips, agent forms an absorption plan
# WITH Camron, saves to absorption.json, then re-runs:
python scheduling/tools/proposal_iterate.py --project "<project>" \
    --paste paste.json --apply absorption.json
```

**Behavior**
1. Locates the latest `-v{N}.xer` in `<project>/Proposal Schedule/`.
2. Applies `duration_change` items from `--paste` (and optional `--apply`)
   to the matching TASK rows in memory. `target_drtn_hr_cnt = to_days * 8`.
3. Runs what-if CPM via `schedule_forward_backward`.
4. Loads `<project>/Proposal Schedule/proposal-anchors.json` and calls
   `check_anchor_dates`.
5. **If any anchor slips later than its bid-given date:** prints the slips
   plus the top-5 cut candidates per slip from `suggest_anchor_absorption`,
   exits with code 2. **Nothing is written.**
6. **If anchors hold:** writes `-v{N+1}.xer` with the duration changes and
   CPM-computed dates / float baked in, regenerates `schedule-activities.json`
   (preserves `default_view` from the paste-back so zoom/scroll/expand state
   persist), regenerates `schedule-review.html`, archives the paste-back to
   `<project>/Proposal Schedule/iterations/paste-{N+1}.json`, and prints a
   5-line success summary. Exit code 0.

**Flags**
- `--project` (required): the proposal-schedule project folder.
- `--paste` (required): path to the Copy-for-Claude paste-back JSON.
- `--apply` (optional): path to an absorption plan (same schema as paste).
- `--data-date YYYY-MM-DD` (optional): override the CPM data date.
- `--dry-run` (optional): run the full pipeline but write no files.
- `--verbose` (optional): write debug detail to
  `<project>/Proposal Schedule/.iterate-debug.log` on error or slip.

**Stdout target** -- agents read this directly as part of their iteration
context.

- ≤30 lines on slip (slip summary + top-5 cuts per slip)
- ≤8 lines on success (paths written + SC date + anchor count)

## show_paths.py

Compact read of the project's current paths. Reads
`<project>/Proposal Schedule/schedule-activities.json` only -- no XER parse,
no CPM. Used by the agent to orient before proposing a change.

```bash
python scheduling/tools/show_paths.py "<project>"
```

Output: critical path (with task code, name, dates), each driving path
(head + tail to keep token cost low), near-critical chains (length + min
float), parallel branches (diverge -> converge nodes). Target ≤50 lines.

## show_anchors.py

Compact read of anchor status. Reads `proposal-anchors.json` plus
`schedule-activities.json`, calls `check_anchor_dates`, prints one line
per anchor with `anchor / computed / drift`. No CPM run.

```bash
python scheduling/tools/show_anchors.py "<project>"
```

Exit code 2 if any anchor slips past tolerance (late). Useful as a
between-iterations sanity check.

## anchors_from_constraints.py

One-shot bootstrap for projects whose XER still carries hard constraints
on anchor tasks (CS_MSO, CS_FNLT, CS_MANDSTART, CS_MANDFIN, CS_MEOB,
CS_MFO). Westland's anchor-via-logic rule says these dates should live in
`proposal-anchors.json` and be enforced by `proposal_iterate.py` on every
iteration -- not as constraints in the XER itself.

```bash
# Dry-run shows what would be lifted
python scheduling/tools/anchors_from_constraints.py "<project>" --dry-run

# Apply: writes proposal-anchors.json + sibling -v{N+1}.xer
python scheduling/tools/anchors_from_constraints.py "<project>"
```

Seasonal constraints (e.g. CS_MSOA on a curb-and-gutter task that can't
start before spring) are NOT lifted -- they're real construction logic,
not anchors.

## build_gantt_html.py

Renders the self-contained Gantt review HTML from
`schedule-activities.json`. Inlines the vendored frappe-gantt bundle, the
Westland logo, and the activity JSON into a single ~100 KB file that
opens locally from disk. `proposal_iterate.py` calls this automatically on
every successful apply; you only invoke it directly when starting from an
existing JSON without running an iteration.

```bash
# default: writes <input-folder>/schedule-review.html
python scheduling/tools/build_gantt_html.py path/to/schedule-activities.json

# explicit output path + project-name override
python scheduling/tools/build_gantt_html.py schedule-activities.json \
    -o my-review.html --project "Murray Apex"
```

## End-to-end flow

```
[Bid docs + sample XERs]
  -> Phase 1-5 of schedule-create-proposal-schedule (initial XER + JSON + HTML)
  -> anchors_from_constraints.py (one-shot, lifts constraints into anchors)
  -> Camron opens schedule-review.html in Chrome
  -> [iterate]
       Camron edits durations, leaves comments, clicks Copy for Claude
       -> agent runs show_paths.py to orient
       -> agent saves paste.json
       -> proposal_iterate.py --paste paste.json
            -> if slips: agent + Camron form absorption.json
                          -> proposal_iterate.py --paste paste.json --apply absorption.json
            -> if anchors hold: writes -v{N+1}.xer + JSON + HTML + iterations/paste-{N+1}.json
       -> Camron refreshes, loops
  -> [final approval]
       Camron says "this is good, generate the XER"
       -> agent writes feedback/postmortem-{date}-{project-slug}.md (see SKILL.md)
       -> latest -v{N}.xer is the deliverable
```

For the paste-back schema, anchor JSON schema, and postmortem section
template, see `skills/schedule-create-proposal-schedule/SKILL.md`. For
advanced custom flows that the CLI cannot express, see
`skills/schedule-create-proposal-schedule/examples/iterate.py`.

## Repository layout

```
scheduling/
  assets/westland-logo.png        # embedded as data URI in the HTML
  lib/frappe-gantt/               # vendored frappe-gantt UMD + CSS
  templates/gantt-review.html     # HTML template with <<<TOKEN>>> placeholders
  skills/
    schedule-toolbox/references/cpm_engine.py     # the engine (don't read in iteration)
    schedule-create-proposal-schedule/SKILL.md    # the proposal-schedule playbook
    schedule-create-proposal-schedule/examples/iterate.py
  tools/
    proposal_iterate.py           # iteration entry point
    show_paths.py
    show_anchors.py
    anchors_from_constraints.py
    build_gantt_html.py
    _xer_io.py                    # shared parse/write helpers
    _cpm_loader.py                # locates cpm_engine for the CLIs
    README.md                     # you are here
```
