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
5. **Generate XER (v1)** -- Via `schedule-toolbox` skill
6. **Iterate via Gantt Review HTML** -- Camron pastes back changes; agent runs `proposal_iterate.py`; loop until approved
7. **Score & Iterate** -- Quality (DCMA / Westland rubric) iteration via the toolbox until target letter grade is reached
8. **On Final Approval** -- Write the AI postmortem, then generate the Westland-branded Plan PDF (the PDF reflects the *final* schedule, not the v1 draft)

The Plan PDF is the last step, not Phase 5. Generating it before iteration produces a document that contradicts the XER it ships with.

## Progressive disclosure -- which phase file to load

This SKILL.md is a dispatcher. Load the relevant phase file for what you're actually doing -- you do NOT need to load all of them.

| Situation | Load |
|-----------|------|
| Starting a new proposal from bid docs and sample XERs (workflow steps 1-6) | `phases/01-draft.md` |
| Camron pasted a Copy-for-Claude payload from `schedule-review.html` (workflow step 7, the high-frequency loop) | `phases/02-iterate.md` -- and ONLY this file |
| Scoring schedule quality / fixing dangling, missing logic, soft constraints (workflow step 8) | `phases/03-score.md` |
| Bootstrapping anchors on a project with legacy hard-constraints | `phases/02-iterate.md` -- see the `anchors_from_constraints.py` section |

The iteration loop (`02-iterate.md`) is the most common case. Resist the urge to load `01-draft.md` once a draft exists; it adds tokens with no payoff because every section is about content the agent has already produced.

## Iteration tools (Phase 6+)

| Tool | When to use |
|------|-------------|
| `tools/proposal_iterate.py` | Every paste-back. Applies `duration_change` items, runs CPM (cached by content hash), checks anchors, writes -v{N+1}.xer + JSON + HTML, archives the paste-back. Exit 0 on success, 2 on anchor slip. |
| `tools/show_paths.py` | Re-orient before proposing a change. Reads `schedule-activities.json` only -- no XER parse, no CPM. |
| `tools/show_anchors.py` | Re-check anchor status without running an iteration. Reads `proposal-anchors.json` + `schedule-activities.json`. |
| `tools/anchors_from_constraints.py` | One-shot bootstrap on a project that still carries CS_MSO / CS_FNLT / CS_MANDSTART / CS_MANDFIN / CS_MEOB / CS_MFO on anchor tasks. Lifts those into `proposal-anchors.json` and emits a sibling -v{N+1}.xer with the constraint fields cleared. |
| `tools/postmortem_aggregate.py` | Phase 1 of the next proposal. Scans existing `*/Proposal Schedule/feedback/postmortem-*.md`, recency-weights hypotheses, optionally filters by project type, prints a ruleset block to inject into recommendations. |

## After the Project: Lessons Learned Loop

When this skill is used on a real proposal and the human-submitted version diverges meaningfully from Claude's output, write a `Lessons Learned - <Project>.md` next to the Claude output in the `Proposal Schedule/` folder. Order divergences by severity; each section captures *what the scheduler did*, *what Claude did*, *why it matters*, and *proposed skill gap and fix*. Feed that doc back into a skill-improvement session to produce the next version. See the repo-root `CLAUDE.md` ("Continuous Improvement Loop") for the standing process, and `~Proposal Schedules/Spanish Fork Jr High/Proposal Schedule/Lessons Learned - SFJHS Proposal Schedule.md` as the template. This skill exists today because that loop ran once -- keep running it.

The complementary mechanism is the per-project AI postmortem written at final approval (see `phases/02-iterate.md` § "Postmortem on final approval"). Postmortems accumulate in `<project>/Proposal Schedule/feedback/`; `postmortem_aggregate.py` synthesizes them into hypotheses for the next draft.

## Reference Files

| File | When to Load |
|------|-------------|
| `phases/01-draft.md` | Drafting from bid docs (Phase 1-6) |
| `phases/02-iterate.md` | Paste-back iteration (Phase 6.5+) -- the high-frequency loop |
| `phases/03-score.md` | Schedule quality scoring (Phase 7) |
| `references/wbs-patterns.md` | WBS pattern selection (A/B/C) -- load in Phase 2/3 when deciding top-level structure |
| `references/westland-procedures-summary.md` | Distilled Westland procedure for proposal schedules -- load in Phase 2 before recommendations |
| `references/westland-procedures.md` | Full Westland procedures text -- load only when the summary doesn't answer the question |
| `references/site-logistics-examples/` | Lubumbashi & Querétaro site logistics workflow PNGs -- reference for what a good plan looks like |
| `references/generate_proposal_schedule_pdf.py` | Westland-branded PDF generator -- load when generating the plan document |
| `references/sample_data.json` | Schema template showing all required JSON keys for the PDF generator |
| `references/xer-analysis-code.md` | Python functions for extracting schedule profiles from sample XERs |
| `references/plan-document-template.md` | Full 14-section plan document template -- content reference for what goes in the PDF |
| `examples/iterate.py` | Worked Python for the iteration loop -- copy and adapt only when `proposal_iterate.py` cannot do the job |
