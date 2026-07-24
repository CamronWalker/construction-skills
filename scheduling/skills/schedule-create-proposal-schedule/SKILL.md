---
name: schedule-create-proposal-schedule
description: >
  Create a construction proposal schedule plan by analyzing bid documents and sample XER files,
  then generate the XER file. Use this skill whenever the user wants to "plan a proposal schedule",
  "create a schedule plan", "build a bid schedule", "proposal schedule", "I have some similar
  schedules and a bid package", "help me plan out this schedule", "schedule plan from bid docs",
  or wants to create a new schedule from bid documents and sample schedules. This skill reads the
  documents first, makes smart recommendations using Westland standards, and only asks about things
  the documents don't answer. Output feeds into the schedule-toolbox skill for XER generation.
---

# Proposal Schedule Planning

This skill creates a proposal schedule by analyzing bid documents and sample XER files. It reads the documents, proposes a schedule structure using Westland standards, asks only what the documents don't answer, then generates the plan document and XER file.

A proposal schedule is a **sales document built to win the job** -- a clean, credible, defensible path to completion that a reviewer will compare against competitors. Scope every decision to that purpose. Construction-phase tracking elements (Progress Impact buckets, SmartPM, TIA, weekly updates) belong to post-award work and do not go in a proposal.

This skill operationalizes the Westland Scheduling Department Procedural Outline for the proposal-schedule phase specifically. The full text is bundled as `references/westland-procedures.md` with site logistics workflow examples in `references/site-logistics-examples/`.

## Workflow

1. **Gather Inputs** -- Collect project folder with bid docs and sample XERs
2. **Auto-Parse & Analyze** -- Parse XERs and read bid docs to extract all knowable information
3. **Present Recommendations** -- Propose complete schedule structure based on findings
4. **Ask 2-3 Targeted Questions** -- Only what the documents don't answer
5. **Generate XER (v1)** -- Via `create_xer_from_template` + `apply_xer_changes`
6. **Iterate via the online review link** -- Claude publishes the review link; Camron (or a reviewer) leaves comments there; agent pulls + reconciles them and runs `proposal_iterate.py`; loop until approved
7. **Score & Iterate** -- Quality (DCMA / Westland rubric) iteration via the toolbox until target letter grade is reached
8. **On Final Approval** -- Write the AI postmortem, generate the Westland-branded Plan PDF, then run the final XER-validation gate (the PDF reflects the *final* schedule, not the v1 draft)

The Plan PDF is the last step, not Phase 5. Generating it before iteration produces a document that contradicts the XER it ships with.

## Progressive disclosure -- which phase file to load

This SKILL.md is a dispatcher. Load the relevant phase file for what you're actually doing -- you do NOT need to load all of them.

| Situation | Load |
|-----------|------|
| Starting a new proposal from bid docs and sample XERs (workflow steps 1-6) | `phases/01-draft.md` |
| Camron left comments on the online review link (workflow step 7, the high-frequency loop) | `phases/02-iterate.md` -- and ONLY this file |
| Scoring schedule quality / fixing dangling, missing logic, soft constraints (workflow step 8) | `phases/03-score.md` |
| Bootstrapping anchors on a project with legacy hard-constraints | `phases/02-iterate.md` -- see the `anchors_from_constraints.py` section |

The iteration loop (`02-iterate.md`) is the most common case. Resist the urge to load `01-draft.md` once a draft exists; it adds tokens with no payoff because every section is about content the agent has already produced.

## Iteration tools (Phase 6+)

All operations route through one CLI: **`python scheduling/tools/propsched.py <verb>`**. The full reference for every verb (inputs, outputs, exit codes, examples) lives in `scheduling/tools/REFERENCE.md` -- load that file when you need the menu; do not read the individual `tools/*.py` scripts.

| Verb | Use |
|------|-----|
| `propsched init "<path>"` | Create a new project folder with the v4.0.0 layout |
| `propsched iterate --project "<p>" --paste paste.json` | Apply a paste-back: CPM, anchor check, write next XER + JSON, archive paste-back. Exit 2 on anchor slip with cut suggestions |
| `propsched feedback pull "<p>" --file online-comments.json` | Reconcile comments pulled from the online review link (`get_proposal_review_comments`) onto the current schedule, drift-aware |
| `propsched paths "<p>"` | Print critical / driving / near-critical paths (no CPM, no XER parse) |
| `propsched anchors "<p>"` | Print anchor status / drift |
| `propsched bootstrap-anchors "<p>"` | One-shot: lift hard-constraint anchors into `proposal-anchors.json` |
| `propsched diff "<p>" vA vB` | Pairwise XER diff with classification + reassignment flag |
| `propsched walk "<p>"` | Walk v1 -> current with per-iteration narrative |
| `propsched score "<p>" --version N` | DCMA / Westland score; writes sidecar JSON |
| `propsched aggregate-postmortems` | Phase 1 of next proposal: recency-weighted hypotheses from past postmortems |

## Folder layout (v4.0.0+)

```
<project>/
  Bid Documents/
  Sample Schedules/
  <Project>.xer                         <- current/working XER
  schedule-activities.json
  Schedule Plan.pdf                     <- final plan (post-approval)
  proposal-anchors.json
  Old Iterations/
    <Project> -v1.xer ... -v{N-1}.xer
    paste-*.json
    postmortem-*.md
    scores/v{N}.json
    .cpm-cache/
```

Legacy projects (Proposal Schedule/ subfolder) auto-detected and supported.
The review surface itself is hosted, not a local artifact -- `generate_proposal_review_link` serves it from the westland-mcps cloud MCP, so there is no `schedule-review.html` (or any other review file) in this tree to generate, version, or clean up.

## After the Project: Lessons Learned Loop

When this skill is used on a real proposal and the human-submitted version diverges meaningfully from Claude's output, write a `Lessons Learned - <Project>.md` next to the Claude output in the `Proposal Schedule/` folder. Order divergences by severity; each section captures *what the scheduler did*, *what Claude did*, *why it matters*, and *proposed skill gap and fix*. Feed that doc back into a skill-improvement session to produce the next version. See the repo-root `CLAUDE.md` ("Continuous Improvement Loop") for the standing process, and `~Proposal Schedules/Spanish Fork Jr High/Proposal Schedule/Lessons Learned - SFJHS Proposal Schedule.md` as the template. This skill exists today because that loop ran once -- keep running it.

The complementary mechanism is the per-project AI postmortem written at final approval (see `phases/02-iterate.md` § "Postmortem on final approval"). Postmortems accumulate in `<project>/Proposal Schedule/feedback/`; `postmortem_aggregate.py` synthesizes them into hypotheses for the next draft.

## Reference Files

| File | When to Load |
|------|-------------|
| `phases/01-draft.md` | Drafting from bid docs (Phase 1-5) |
| `phases/02-iterate.md` | Paste-back iteration (Phase 6+) -- the high-frequency loop |
| `phases/03-score.md` | Schedule quality scoring (Phase 7) |
| `tools/REFERENCE.md` | Single-page API reference for `propsched` -- load when you need the CLI menu |
| `references/wbs-patterns.md` | WBS pattern selection (A/B/C) -- load in Phase 2/3 when deciding top-level structure |
| `references/westland-procedures-summary.md` | Distilled Westland procedure for proposal schedules -- load in Phase 2 before recommendations |
| `references/westland-procedures.md` | Full Westland procedures text -- load only when the summary doesn't answer the question |
| `references/site-logistics-examples/` | Lubumbashi & Querétaro site logistics workflow PNGs -- reference for what a good plan looks like |
| `references/generate_proposal_schedule_pdf.py` | Westland-branded PDF generator -- load when generating the plan document |
| `references/sample_data.json` | Schema template showing all required JSON keys for the PDF generator |
| `references/xer-analysis-code.md` | Python functions for extracting schedule profiles from sample XERs |
| `references/plan-document-template.md` | Full 14-section plan document template -- content reference for what goes in the PDF |
| `examples/iterate.py` | Worked Python for the iteration loop -- copy and adapt only when `proposal_iterate.py` cannot do the job |
