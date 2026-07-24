# Phase 6.5+: Iteration Loop

Load this file when iterating on a draft proposal -- after v1 has been
generated and published to the online review link, and Camron (or a
reviewer) is leaving comments there for Claude to pull. This is the
high-frequency loop; it should be the only phase file an agent loads
during iteration.

For drafting from bid docs, see `phases/01-draft.md`.
For score & quality iteration, see `phases/03-score.md`.

---

## Phase 6.5: Publish the Online Review Link

There is no local review file anymore. After the XER is generated (v1, and
again after each iteration), Claude publishes the current
`schedule-activities.json` to a hosted review link -- that link is the
review surface for both solo iteration and a distributed review round,
and it's the only comprehension layer between Camron and Claude for this
phase.

> **Don't read source files. Call them.**
> The proposal-iteration loop runs through the CLI tools in `scheduling/tools/`. These are the canonical entry points -- do not Read `cpm_engine.py`, the full `schedule-activities.json`, or any `.xer` file during iteration.
> - DO NOT write your own pipeline. Use `tools/proposal_iterate.py`.
> - DO NOT load the full activities JSON for context. Use `tools/show_paths.py` and `tools/show_anchors.py`.
> - DO NOT read `cpm_engine.py` to understand helpers -- the CLIs already call them.
> - If a CLI lacks a flag you need, ask before refactoring. Worked Python is in `examples/iterate.py` for advanced custom flows; copy-and-adapt only when the CLI cannot do the job.

### Publish

Read the project's `schedule-activities.json` and call:

```
generate_proposal_review_link({
  job_number:      "<job number -- from the project's Supabase record via get_project>",
  project_name:    "<Project Name>",
  activities_json: <contents of schedule-activities.json>,
  new_version:     false   # omit/false during solo iteration; true to open a fresh review round
})
```

Returns `{ review_url, expires_at, version_label, mode }`. Hand `review_url`
to Camron -- that is the entire hand-off, there is no file to send or open.

- **Solo iteration (no `new_version`, or `new_version: false`):** re-publishing
  updates the *current* version in place and preserves existing comments.
  Camron refreshes the same link after every regeneration.
- **After a review round (`new_version: true`):** cuts a fresh version with a
  clean comment slate, so resolved or stale comments from the prior round
  don't clutter the next one. Publish with `new_version: true` right after
  you've pulled and applied a round of comments (see below).
- Optionally log the publish: `append_project_log(category="schedule_published")`.

### Read the paths section first (mandatory before any edit)

`schedule-activities.json` includes a `paths` block with the critical, near-critical, driving, and parallel-branch chains. **Before proposing any duration, sequence, or constraint change, open that block via `show_paths.py` and state which path you're modifying and the second-order effect on the critical and near-critical paths.** The flat activity list is not enough -- without the path chains, edits land blind. Without this read, any edit is forbidden.

Example (good): *"This shortens A220 by 3 days. A220 is on the critical path -> SC milestone (chain: A100 -> A220 -> A350 -> SC), so the SC date moves earlier by 3 days. Near-critical chain B (B100 -> B250) had 3-day float -- it now becomes co-critical at 0d float."*

Example (bad): *"Reducing A220 from 10d to 7d."* (No path awareness, no second-order analysis.)

### Pull & reconcile comments

Comments accumulate on the hosted link -- there is no clipboard payload to
paste anymore. Pull them down when Camron says he's left comments, or on
your own cadence during a review round:

1. Call `get_proposal_review_comments({ job_number })`.
2. Write the result to `<project>/Old Iterations/online-comments-<date>.json`.
3. Reconcile against the current schedule:
   ```bash
   python scheduling/tools/propsched.py feedback pull "<project>" --file "<project>/Old Iterations/online-comments-<date>.json"
   ```
   This maps the online comments onto the same `westland-reviewer-feedback`
   shape `feedback ingest` uses (grouped by reviewer + version reviewed),
   runs the same drift detection, and parks each mapped payload under
   `Old Iterations/reviewer-feedback/`. Resolved comments are excluded by
   default -- pass `--include-resolved` to pull them anyway.
4. Read the parked feedback (`propsched feedback show "<project>" <reviewer>`)
   and decide what to apply. Anything the drift report flags -- a task
   renamed, moved, or changed duration since the comment was left -- needs a
   judgment call; ask Camron rather than silently applying or dropping it.

**The `get_proposal_review_comments` result shape** (what gets written to
`online-comments-<date>.json`):

```json
{
  "job_number": "W1234",
  "current_version": "v3",
  "versions": ["v1", "v2", "v3"],
  "comments": [
    {
      "id": "c1",
      "version_label": "v2",
      "task_code": "APEX0040",
      "task_name_snapshot": "50% CD Estimate Update Complete",
      "orig_duration_snapshot": 5,
      "reviewer_id": "r1",
      "reviewer_name": "Steve Westover",
      "body": "Add LLI lead time",
      "suggested_duration_days": 7,
      "resolved": false,
      "created_at": "2026-04-29T17:24:00Z"
    }
  ]
}
```

`feedback pull` groups comments by `(reviewer_name, version_label)` into one
`westland-reviewer-feedback` payload per group -- the same shape `feedback
ingest` and the postmortem's drift-detection code already expect.

**Claude's iteration steps:**

1. **Orient with `show_paths.py`.** Before touching anything, run `python scheduling/tools/propsched.py paths "<project>"` to see which activities the reconciled comments' `task_code`/`id` lie on (critical path, driving path to SC, near-critical, parallel branches). State the second-order effect of every change before applying.
2. **Build `paste.json`** from the comments you're accepting this round -- same schema `propsched iterate` has always taken: a `project`/`data_date` header plus an `activities` list keyed by `id`/`task_code`, each with an optional `duration_change` and/or `comment`. Source the list from the parked reviewer-feedback JSON (or directly from `online-comments-<date>.json` when you're applying comments without a formal review round).
3. **Apply each `comment`** that needs a sequence change, constraint addition, parent move, or new activity. Comments are free-form; for simple ones edit directly via the XER write-back pattern, for ambiguous ones reply with a clarifying question before editing.
4. **Run the iterate CLI:**
    ```bash
    python scheduling/tools/propsched.py iterate --project "<project>" --paste paste.json
    ```
   Behavior:
   - Loads the latest `-v{N}.xer`, applies in-memory `duration_change` from `paste.json`, runs what-if CPM (cached by hash of the modified task graph; `--no-cache` to force).
   - Calls `check_anchor_dates`. If any anchor (NTP, 100% CDs, SC, GMP, etc.) slips later than its bid-given date, prints the slips + top-5 cut candidates per slip and exits with code 2. **Nothing is written.**
   - If anchors hold, writes `-v{N+1}.xer`, regenerates `schedule-activities.json` (preserving `default_view` from the paste-back so zoom/scroll/expand state survive), archives the paste-back to `iterations/paste-{N+1}.json`, and prints a 5-line summary.
5. **If the CLI reported slips**, formulate an absorption plan WITH Camron (cut candidates from the CLI output + any logic changes), save the plan as `absorption.json` (same schema as paste -- list of `activities` with `duration_change`), then re-run:
    ```bash
    python scheduling/tools/propsched.py iterate --project "<project>" --paste paste.json --apply absorption.json
    ```
6. **Re-publish the review link** (`generate_proposal_review_link`, see § "Publish" above) so Camron can see the update -- omit `new_version` if you're still mid-round on the same batch of comments, or pass `new_version: true` if this iteration closed out a review round. Camron refreshes the online link and verifies. Loop.
7. **On approval ("this is good, generate the XER")**, write the AI self-postmortem BEFORE producing the final XER. See § "Postmortem on final approval" below.
8. **The latest `-v{N}.xer` is the final.** `schedule-activities.json` and the hosted review link are transient working state -- overwritten or updated each iteration, never versioned. The per-iteration paste-backs in `iterations/paste-*.json` are durable; the postmortem reads them.

### Anchor milestones -- confirm before regenerating

Some proposal dates are *given* and don't move:

- NTP (Notice to Proceed)
- Drawings / permits issued
- Substantial Completion (SC)
- Final GMP
- Any other dates the bid documents pin

> **Best practice: do NOT encode anchors as XER hard constraints.** Constraints (CS_FNLT, CS_MANDSTART, etc.) hide broken logic and make a schedule brittle -- a reviewer who opens a proposal full of constraints reads it as dishonest. Westland's rule: anchor dates stay pinned via **logic and durations**, not constraints. Claude's job is to keep the dates landing where the bid says they should land *because the work flows that way*, not because the schedule has been forced.

Capture anchors during Phase 1 as project metadata, written to `<project>/Proposal Schedule/proposal-anchors.json` (next to the XER). Schema:

```json
{
  "project_name": "Murray City Apex Center",
  "anchors": [
    {
      "kind_label": "NTP",
      "task_code": "APEX0090",
      "task_name": "Construction Award and NTP",
      "anchor_kind": "finish",
      "anchor_date": "2026-09-01",
      "source": "Bid documents §3.2"
    },
    {
      "kind_label": "100% CDs Issued",
      "task_code": "APEX0050",
      "task_name": "100% CDs Complete",
      "anchor_kind": "finish",
      "anchor_date": "2026-07-30",
      "source": "Bid documents §2.1"
    },
    {
      "kind_label": "Substantial Completion",
      "task_code": "APEX0140",
      "task_name": "Substantial Completion and Punch",
      "anchor_kind": "finish",
      "anchor_date": "2027-07-14",
      "source": "Bid documents §1.4"
    }
  ]
}
```

`anchor_kind` is `"finish"` (compare to `early_end_date`) or `"start"` (compare to `early_start_date`). The XER itself stays clean: no CS_FNLT / CS_MANDSTART / CS_MSO on these tasks.

**Iteration check.** `proposal_iterate.py` runs the what-if CPM and calls `check_anchor_dates` automatically before writing the new XER. If any anchor slips, the CLI exits with code 2 and prints (a) the slipped anchor(s) and (b) for each slip, the top-5 cut candidates from `suggest_anchor_absorption` ranked by leverage (longest critical-path tasks first; tasks with float are filtered because cutting them just adds slack to parallel branches without moving the anchor).

You then formulate an absorption plan with the scheduler -- pick a subset whose cuts add up to (or exceed) the slip, mix in any logic changes (FS -> SS, parallelize) that make sense -- save the plan as `absorption.json`, and re-run `proposal_iterate.py` with `--apply absorption.json`.

To re-check anchor status without running a full iteration, use `python scheduling/tools/propsched.py anchors "<project>"` (reads `proposal-anchors.json` + `schedule-activities.json`, no XER parse, no CPM run).

Reply pattern:

> "Adding 20 days to A220 would push SC from 2027-07-14 to 2027-08-03 -- but the bid pins SC at 2027-07-14. Here's how I'm planning to absorb it through logic and durations (no constraints):
> - Split A350 into A350a (5d) // A350b (5d), run in parallel -- saves 5d
> - Change B200 -> B250 from FS 0d to SS 0d -- saves 8d
> - Cut A410 from 12d to 5d (post-FF, low-risk) -- saves 7d
>
> Total absorbed: 20d. After re-CPM, SC lands on 2027-07-14 because of the logic, not because anything is constrained. Want me to do it a different way?"

Wait for Camron's reply. Apply what he confirms (his version may differ) by writing `absorption.json` with the agreed `duration_change` items, then re-run `proposal_iterate.py --paste paste.json --apply absorption.json`. The CLI re-checks anchors and only writes the new XER + JSON + HTML when they hold.

**If a previous version of the XER carries hard constraints on anchor tasks**, that's a Phase 1 hygiene issue: run `python scheduling/tools/propsched.py bootstrap-anchors "<project>"` once to lift CS_MSO / CS_FNLT / CS_MANDSTART / CS_MANDFIN / CS_MEOB / CS_MFO into `proposal-anchors.json` and emit a sibling `-v{N+1}.xer` with the constraint fields cleared. Westland's anchor-via-logic rule -- the new XER carries no anchor constraints; the bid dates live in `proposal-anchors.json` and are enforced by `proposal_iterate.py` on every iteration. Note the cleanup in the iteration log.

### Postmortem on final approval (Tier 7+ folder schema)

When Camron approves the schedule ("this is good, generate the XER"),
Claude writes a self-reflection artifact **before** producing the final
XER. The artifact is now a self-contained folder, not a single file --
copyable to a master postmortems library without losing context.

**Path:** `<project>/Old Iterations/postmortems/{YYYY-MM-DD}-{project-slug}/`

```
{date}-{slug}/
  postmortem.md             <- the narrative (you write this)
  project-metadata.json     <- snapshot of project-metadata.json at completion
  durations-captured.json   <- duration entries added this cycle (if any)
  reviewer-feedback/        <- copies of every parked reviewer JSON
    *.json
```

(Legacy single-file postmortems at `Old Iterations/postmortem-*.md` and
`Proposal Schedule/feedback/postmortem-*.md` continue to be readable
by the aggregator -- old projects don't need migration.)

**Step-by-step:**

1. **Auto-extract duration knowledge from this cycle's reviewer feedback** so the durations DB carries forward:
   ```bash
   python scheduling/tools/propsched.py durations extract "<project>"
   ```
2. **Assemble the postmortem folder** (creates the folder + writes a stub postmortem.md + snapshots metadata + copies reviewer feedback):
   ```bash
   python scheduling/tools/propsched.py postmortem "<project>" --slug "<project-slug>"
   ```
3. **Open `postmortem.md` and fill in the stub sections** (schema below).
4. **Optionally add manual duration entries** that came up during the cycle but were not captured in formal feedback:
   ```bash
   python scheduling/tools/propsched.py durations add "<project>" \
       --task-code APEX0040 --duration 5 --source "super:Mike" \
       --rationale "Soil conditions in Utah Valley typically drive 5-7d"
   ```

**Source data while writing the narrative:**
- `Old Iterations/paste-*.json` -- every paste-back the scheduler sent, in order
- The v1 XER (Westland's immutability rule preserves it)
- The final v{N} XER and `schedule-activities.json`
- The folder's own `reviewer-feedback/` -- external reviewer comments to summarize
- Session memory if the agent is the same one that drafted v1

**postmortem.md sections (the stub writes the headers; fill them in):**

```markdown
---
project: "Murray City Apex Center"
project_type: "office-tenant-improvement"   # mirrored from project-metadata.json
proposal_data_date: "2026-04-29"
draft_version: 1
final_version: 7
iteration_count: 6
scheduler: "camron"
postmortem_date: "2026-04-30"
---

## What I drafted (v1)
High-level summary of v1: activity count, total duration, anchor dates I picked, top-level WBS structure.

## What shipped (v{N})
Deltas vs v1: total duration change, anchor movements (if any), new/removed activities, structural shifts.

## What I missed
Per substantive correction, write three lines:
- **Change** -- what the scheduler edited (concrete: from X to Y)
- **Signal I should have caught** -- bid doc page reference, similar-project XER, Westland convention, or other concrete signal that should have produced a better v1
- **Hypothesis I am extracting** -- first-person, scoped to this project type, NOT crowned a rule

## Reviewer feedback received
Summarize external-reviewer JSONs in this folder's reviewer-feedback/. Feedback
now arrives via `propsched feedback pull` (attributed comments pulled off the
published online review link) or, for out-of-band JSON, `propsched feedback
ingest`. For each material insight kept, cite reviewer + date and note whether
the feedback was on the version that shipped or an earlier one (the drift
report from whichever verb parked it already showed you).

## Themes within this project
Patterns that recurred across multiple corrections in this single cycle. Caveat: still hypotheses, not rules.

## Hypotheses for next time
Numbered, first-person AI voice, scoped to project type. Format that future-me can load as prompt context. Explicitly NOT rules -- rules emerge from aggregation across many postmortems.
```

**Constraints:**

1. **No rules from a single postmortem.** Each is observation + hypothesis. Promotion to rules happens later, at aggregation time across N postmortems.
2. **One postmortem per proposal cycle.** Generally one per project. Don't overwrite an existing folder; pass `--force` only if you intend to.
3. **Write the postmortem BEFORE producing the final XER.** Iteration history is freshest in memory at approval time.

After writing the postmortem, the next proposal draft (a different project) can pull a recency-weighted ruleset from the accumulated corpus filtered to comparable projects:

```bash
python scheduling/tools/propsched.py aggregate-postmortems \
    --project-type "<type>" --region "<region>" --system "<building-system>" \
    --show-durations
```

That closes the lessons-learned loop -- the postmortem you write today
informs the next draft tomorrow, with full project-metadata context.

### Generate the Plan PDF (post-approval)

The Westland-branded plan PDF is generated **after** the schedule is finalized (after iteration + scoring + Camron's approval). This ordering matters: the PDF includes the WBS tree, phase timeline summary table, logic network, milestone list, and procurement qualification language -- all of which reflect the *final* schedule, not the v1 draft. Generating the PDF before iteration produces a document that contradicts the XER it ships with.

Sequence at final approval:

1. Camron says "this is good, generate the XER".
2. Write the AI self-postmortem (above).
3. Generate the plan PDF.
4. Confirm the latest `-v{N}.xer` is the deliverable.

Use `references/generate_proposal_schedule_pdf.py`:

1. Build a JSON data dict with all plan data -- use `references/sample_data.json` as the schema template for all required keys and structure. Pull the WBS, activity list, milestones, and phase timeline from the final `schedule-activities.json`, not from the original v1 plan.
2. Include all analysis results, user responses (as `question_responses`), bid documents list, assumptions, WBS tree, phase timeline, logic, procurement with TIA qualifications, risks, milestones, and decision log.
3. Set `logo_path` to the Westland primary logo: `brand-assets/Westland Logos/Westland Primary Logo 2022_1200x321.png` (NEVER use Light variants -- they are invisible on white backgrounds).
4. Write the JSON to a temp file, then run:
   ```python
   from generate_proposal_schedule_pdf import generate_proposal_schedule_pdf
   generate_proposal_schedule_pdf(data, output_path, logo_path=logo)
   ```
   Or via CLI: `python generate_proposal_schedule_pdf.py data.json output.pdf logo.png`
5. Save to `<project-folder>/Proposal Schedule/Schedule Plan - [Project Name].pdf`

The PDF includes: cover page with logo + project overview, schedule basis with reference schedules and bid documents, planning interview responses (question/answer pairs), bid-time assumptions & qualifications, WBS in monospace grey box, phase timeline summary table, logic network, construction sequence, milestones, procurement with TIA/change order qualification language, risk register, calendar, and decision log.

**Key sections for procurement:** The PDF auto-generates procurement qualification language stating that lead time estimates are professional assessments, and that any exceedance constitutes a justified basis for a TIA and potential change order. Procurement status is tracked monthly.

See `references/plan-document-template.md` for the original markdown template structure (still valid as a content reference).
