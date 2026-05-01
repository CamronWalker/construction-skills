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

A proposal schedule is a **sales document built to win the job** — a clean, credible, defensible path to completion that a reviewer will compare against competitors. Scope every decision to that purpose. Construction-phase tracking elements (Progress Impact buckets, SmartPM, TIA, weekly updates) belong to post-award work and do not go in a proposal.

This skill operationalizes the Westland Scheduling Department Procedural Outline for the proposal-schedule phase specifically. The full text is bundled as `references/westland-procedures.md` with site logistics workflow examples in `references/site-logistics-examples/`. Load `references/westland-procedures-summary.md` in Phase 2 for the distilled proposal-stage version; load `westland-procedures.md` only when the summary doesn't answer the question.

## Workflow

1. **Gather Inputs** — Collect project folder with bid docs and sample XERs
2. **Auto-Parse & Analyze** — Parse XERs and read bid docs to extract all knowable information
3. **Present Recommendations** — Propose complete schedule structure based on findings
4. **Ask 2-3 Targeted Questions** — Only what the documents don't answer
5. **Generate Plan Document** — Save to project folder
6. **Generate XER** — Via `schedule-toolbox` skill
7. **Render Gantt Review HTML** — Self-contained `schedule-review.html` next to the XER. Camron opens it locally (file://, no server) and eyeballs the schedule shape before scoring kicks in.
8. **Score & Iterate** — Via `schedule-toolbox` skill until A grade achieved. Each iteration is one `proposal_iterate.py` call: paste-back -> what-if CPM -> anchor check -> write XER + JSON + HTML, Camron refreshes.

---

## Phase 1: Gather Inputs

Ask the user for the project folder path. Expected structure:

```
<project-folder>/
  Bid Documents/              <- bid proposal, specs, plans, contract docs
  Proposal Schedule/
    Sample Schedules/         <- 1-5 XER files from similar completed projects
    [outputs go here]
```

List all files found and confirm before proceeding.

## Phase 2: Auto-Parse & Analyze

### Parse Sample XER Files
For each XER, parse using the `schedule-toolbox` skill and extract a profile. Read `references/xer-analysis-code.md` for the extraction functions. Extract: WBS structure, activity counts, duration stats, relationship types, milestones, naming patterns, calendars.

### Read Bid Documents
Extract into structured categories:
- Project name, location, type
- **Delivery method** (Design-Bid-Build / CM/GC / Design-Build / IPD) — determines whether design-phase activities belong in the schedule
- Contract duration / substantial completion date
- Required milestones and interim deadlines
- Phasing requirements
- Liquidated damages amounts and triggers
- Schedule specification requirements (update frequency, format, detail level)
- Scope summary by major division or area
- Special conditions (occupied building, phased turnover, seasonal restrictions)

### Extract Phasing & Occupancy Profile (mandatory)
From the RFP and bid docs, determine and display back to the user:
- **Occupancy state during construction** (site empty / partial occupancy / full occupancy)
- **Demolition timing** (before construction / during construction / after SC / no demo)
- **Post-demo site use** (nothing / parking / fields / additional structure)
- **Turnover phases and dates**, if any

Call this block "Phasing & Occupancy Profile". It is the single most important input to the WBS pattern choice (Phase 3). If any of these four items cannot be answered from the documents, that is a Phase 4 question — not an assumption.

### Load the Westland Procedures Summary
Read `references/westland-procedures-summary.md` before generating recommendations. The proposal-stage checklist in that file is the authoritative list of what Phase 3 must cover (design schedule, preconstruction deliverables, procurement fab+ship pairs, site logistics plan, responsibility codes). Load the full `Westland Scheduling Procedures Outline - 2026-03-09.pdf` only if the summary doesn't answer a specific question.

### Present Analysis Summary
Show the user: sample schedule profiles side by side + bid document findings + Phasing & Occupancy Profile.

## Phase 3: Smart Recommendations

Based on the analysis, propose a **complete schedule structure** using Westland standards as the default for all style/format decisions. The skill determines from the documents:

- **WBS pattern** — Select A, B, or C from `references/wbs-patterns.md` using the Phasing & Occupancy Profile from Phase 2. Present the pattern choice explicitly to the user **before** listing activities:

  > *"Based on occupied-rebuild phasing (full occupancy through SC, demo after SC, old footprint becomes fields), I'm using **Pattern B**: DEMOLITION top-level after CONSTRUCTION, with FINAL SITEWORK nested under DEMOLITION. Confirm before I lay out activities?"*

  Do not generate activities until the pattern is confirmed. The pattern choice is structural and a wrong pick propagates everywhere.

- **Activity list and durations** — From sample XER analysis, scaled to project scope
- **Milestone strategy** — Contract milestones + Westland 30-day rule (one milestone every 30 days on critical path or significant events)
- **Construction sequence/flow** — From sample schedule patterns and bid doc scope
- **Design schedule** (CM/GC or Design-Build only) — Include Schematic Design, Design Development, 70% CDs, 100% CDs, Permit/Consent Process as activities in PRE-CONSTRUCTION/DESIGN, with the design team's durations if available or placeholders flagged "needs design team input" otherwise
- **Preconstruction deliverables** — Coordinate with estimating: prequalification, buy out / proposal & award, constructability reports, BIM modeling if applicable. These belong in PRE-CONSTRUCTION.
- **Procurement pairs** — Every long-lead procurement item gets BOTH a fabrication activity AND a shipping activity. Duration sources: specs, sample schedules, historical data. Flag items whose vendor input is missing.
- **Calendar** — From contract requirements (5-day/6-day/7-day)
- **Logic network** — Based on sample schedule patterns
- **Responsibility codes** — Assign a Westland standard responsibility code to every activity. No unassigned activities in the final XER.
- **Site Logistics & Workflow Plan** — The procedures doc requires a graphic zone-and-arrow plan view *prior to* the detailed schedule. Reference `references/site-logistics-examples/` for what a good one looks like (Lubumbashi structural/interior/site workflows, Querétaro floor-level zoning). If one has not been developed, flag it as a Phase 4 question to the PMT rather than inferring zones from the sample schedule. Note the status in the plan document.

**Task code prefix** — Ask once whether to rename task codes from the sample prefix to the project prefix, or keep sample codes for traceability. Default: keep sample codes. Do not bulk-rename without user confirmation.

### Naming and consistency rules (do not violate)

These are deterministic rules, not style preferences. A reviewer notices violations immediately.

- **WBS titles ALL CAPS.** Every WBS band — summary, pre-construction, procurement, construction, commissioning, and all sub-bands — is uppercase. This is the Westland house look across projects.
- **Activity names do not duplicate the WBS name.** If the activity lives under `CONSTRUCTION / INTERIOR / KITCHEN`, the activity is *"Drywall Hang"*, not *"Drywall Hang - Kitchen"* or *"Drywall Hang - Kitchen/Mechanical"*. The WBS tells the reader where it lives; the name says what the work is. Duplicating creates clutter and reads as auto-generated.
- **Zone the schedule consistently.** If the interior is broken into zones/areas/levels, the structure must also be zoned the same way. Mixing a zoned interior with a monolithic structure throws the whole sequencing off and signals the scheduler didn't think about trade flow. Procedures doc: *"identifying general areas, zoning, phasing, and flow for all site development and structures included in the project."*
- **Procurement layout matches other Westland projects.** Use the same division-based structure (CONCRETE, MASONRY, METALS, WOODS-PLASTICS-COMPOSITES, OPENINGS, FINISH SYSTEMS, EQUIPMENT, ELEVATOR, PLUMBING, HVAC, ELECTRICAL) rather than inventing a new organization. Consistency across projects matters more than local optimization.
- **Same WBS structure across Westland projects.** Customize area/zone/phase *titles* to the project. Do not restructure the overall tree. The pattern choice (A/B/C from `wbs-patterns.md`) is the only structural variation.

**Do NOT ask about:** WBS format itself (the pattern question covers structural choice), naming conventions, milestone frequency, formatting, branding, relationship type targets, SmartPM integration. These are all answered by Westland standards.

Present the proposed structure to the user as a concise summary before asking questions.

## Phase 4: Targeted Questions (2-3 max)

Ask ONLY about things genuinely unclear from the bid documents and sample schedules. Use AskUserQuestion format with a recommended answer at the top of each.

### Question 1: Construction Sequence Confirmation
Present the proposed construction sequence derived from sample schedules and bid docs. Ask:
> "Here's the proposed construction sequence based on the bid docs and sample schedules. Does this match your planned approach, or do you want to change the flow?"

Recommended answer: Accept the proposed sequence. Provide the proposed sequence as the first option.

### Question 2: Known Risks & Special Conditions
> "Are there risks, site conditions, or constraints not captured in the bid docs that should affect the schedule?"

This catches team knowledge that doesn't appear in written documents — site access issues, known trade availability problems, weather concerns specific to timing, etc.

### Question 3 (optional — only if docs are unclear)
> "The bid docs leave these items unclear: [list]. What are your assumptions for [specific items]?"

Only ask if there are genuine unknowns about crew sizing, work hours, owner-furnished items, or phasing that can't be inferred from the sample schedules.

### Free-Write (1-2 prompts at end)
> "Is there anything else from the project team discussions or your experience that should be captured in this schedule plan?"

Optional second prompt if the project has unusual site conditions or logistics.

## Phase 5: Generate Plan Document (PDF)

Generate the plan document as a **Westland-branded PDF** using the `references/generate_proposal_schedule_pdf.py` script:

1. Build a JSON data dict with all plan data — use `references/sample_data.json` as the schema template for all required keys and structure
2. Include all analysis results, user responses (as `question_responses`), bid documents list, assumptions, WBS tree, phase timeline, logic, procurement with TIA qualifications, risks, milestones, and decision log
3. Set `logo_path` to the Westland primary logo: `brand-assets/Westland Logos/Westland Primary Logo 2022_1200x321.png` (NEVER use Light variants — they are invisible on white backgrounds)
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

## Phase 6: Generate XER

After the user reviews the plan document:
1. Use the `schedule-toolbox` skill to generate the XER file from the plan
2. Pass the plan document as scope input + sample XERs as reference schedules
3. Apply all Westland standards during generation (from `schedule-toolbox`)
4. Convert all durations from working days (plan) to hours (days x 8 for XER)
5. Save to `<project-folder>/Proposal Schedule/[Project Name].xer`

## Phase 6.5: Gantt Review HTML

After the XER is generated, emit `schedule-activities.json` and render `schedule-review.html` next to it. This is the comprehension layer for both Camron and Claude -- not a deliverable, a working document overwritten each iteration.

> **Don't read source files. Call them.**
> The proposal-iteration loop runs through four CLI tools in `scheduling/tools/`. These are the canonical entry points -- do not Read `cpm_engine.py`, `gantt-review.html`, `frappe-gantt.umd.js`, the full `schedule-activities.json`, or any `.xer` file during iteration.
> - DO NOT write your own pipeline. Use `tools/proposal_iterate.py`.
> - DO NOT load the full activities JSON for context. Use `tools/show_paths.py` and `tools/show_anchors.py`.
> - DO NOT read `cpm_engine.py` to understand helpers -- the CLIs already call them.
> - If a CLI lacks a flag you need, ask before refactoring. Worked Python is in `examples/iterate.py` for advanced custom flows; copy-and-adapt only when the CLI cannot do the job.

The first proposal-iteration call generates the JSON and HTML automatically (see § "Iteration loop" below). On a brand-new project, you can render the HTML directly from the existing activities JSON via `python scheduling/tools/build_gantt_html.py <project>/Proposal Schedule/schedule-activities.json`.

Output: `<project-folder>/Proposal Schedule/schedule-review.html` (self-contained, no CDN). Camron opens it in Chrome. The HTML shows top-level WBS bars by default with carets to expand into trade-level activities. Critical path is red, near-critical amber, summary navy. The right-side panel lists the critical path, every driving path (to SC, to project end, to each FNLT-constrained task), near-critical chains, and parallel branches.

### Read the paths section first (mandatory before any edit)

`schedule-activities.json` includes a `paths` block with the critical, near-critical, driving, and parallel-branch chains. **Before proposing any duration, sequence, or constraint change, open that block and state which path you're modifying and the second-order effect on the critical and near-critical paths.** The flat activity list is not enough -- without the path chains, edits land blind. Without this read, any edit is forbidden.

Example (good): *"This shortens A220 by 3 days. A220 is on the critical path → SC milestone (chain: A100 → A220 → A350 → SC), so the SC date moves earlier by 3 days. Near-critical chain B (B100 → B250) had 3-day float — it now becomes co-critical at 0d float."*

Example (bad): *"Reducing A220 from 10d to 7d."* (No path awareness, no second-order analysis.)

### Iteration loop

The HTML is the input surface. Camron edits durations inline, leaves notes on activity-ID chips, and clicks **Copy for Claude** -- that copies a structured JSON payload to his clipboard. He pastes it into the agent terminal. Claude consumes the payload, regenerates the XER + JSON + HTML, Camron refreshes.

**Paste-back payload schema** (what Camron pastes into chat):

```json
{
  "project": "Murray City Apex Center",
  "data_date": "2026-04-29",
  "generated_at": "2026-04-30T17:24:00Z",
  "change_count": 2,
  "comment_count": 3,
  "activities": [
    {
      "id": "12345",                            // XER task_id
      "task_code": "APEX0040",                  // human-readable code
      "name": "50% CD Estimate Update Complete",
      "duration_change": {"from_days": 5, "to_days": 7},   // optional
      "comment": "Add LLI lead time"                       // optional
    }
  ],
  "default_view": {                             // optional, present when "Default view" checkbox was on
    "px_per_day": 4,
    "display_unit": "Quarter",
    "scroll_left": 1240,
    "scroll_top": 0,
    "expanded_ids": ["WBS01", "WBS02"],
    "table_width_px": 540
  }
}
```

**Claude's iteration steps:**

1. **Orient with `show_paths.py`.** Before touching anything, run `python scheduling/tools/show_paths.py "<project>"` to see which activities the proposed `activities[*].id` lie on (critical path, driving path to SC, near-critical, parallel branches). State the second-order effect of every change before applying.
2. **Save Camron's paste-back to `paste.json`** in the project folder (or wherever you like; the path is just a CLI argument).
3. **Apply each `comment`** that needs a sequence change, constraint addition, parent move, or new activity. Comments are free-form; for simple ones edit directly via the XER write-back pattern, for ambiguous ones reply with a clarifying question before editing.
4. **Run the iterate CLI:**
    ```bash
    python scheduling/tools/proposal_iterate.py --project "<project>" --paste paste.json
    ```
   Behavior:
   - Loads the latest `-v{N}.xer`, applies in-memory `duration_change` from `paste.json`, runs what-if CPM.
   - Calls `check_anchor_dates`. If any anchor (NTP, 100% CDs, SC, GMP, etc.) slips later than its bid-given date, prints the slips + top-5 cut candidates per slip and exits with code 2. **Nothing is written.**
   - If anchors hold, writes `-v{N+1}.xer`, regenerates `schedule-activities.json` (preserving `default_view` from the paste-back so zoom/scroll/expand state survive), regenerates `schedule-review.html`, archives the paste-back to `iterations/paste-{N+1}.json`, and prints a 5-line summary.
5. **If the CLI reported slips**, formulate an absorption plan WITH Camron (cut candidates from the CLI output + any logic changes), save the plan as `absorption.json` (same schema as paste -- list of `activities` with `duration_change`), then re-run:
    ```bash
    python scheduling/tools/proposal_iterate.py --project "<project>" --paste paste.json --apply absorption.json
    ```
6. **Camron refreshes** the HTML and verifies. Loop.
7. **On approval ("this is good, generate the XER")**, write the AI self-postmortem BEFORE producing the final XER. See § "Postmortem on final approval" below.
8. **The latest `-v{N}.xer` is the final.** The HTML and `schedule-activities.json` are transient working documents -- overwritten each iteration, never versioned. The per-iteration paste-backs in `iterations/paste-*.json` are durable; the postmortem reads them.

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

To re-check anchor status without running a full iteration, use `python scheduling/tools/show_anchors.py "<project>"` (reads `proposal-anchors.json` + `schedule-activities.json`, no XER parse, no CPM run).

Reply pattern:

> "Adding 20 days to A220 would push SC from 2027-07-14 to 2027-08-03 -- but the bid pins SC at 2027-07-14. Here's how I'm planning to absorb it through logic and durations (no constraints):
> - Split A350 into A350a (5d) // A350b (5d), run in parallel -- saves 5d
> - Change B200 -> B250 from FS 0d to SS 0d -- saves 8d
> - Cut A410 from 12d to 5d (post-FF, low-risk) -- saves 7d
>
> Total absorbed: 20d. After re-CPM, SC lands on 2027-07-14 because of the logic, not because anything is constrained. Want me to do it a different way?"

Wait for Camron's reply. Apply what he confirms (his version may differ) by writing `absorption.json` with the agreed `duration_change` items, then re-run `proposal_iterate.py --paste paste.json --apply absorption.json`. The CLI re-checks anchors and only writes the new XER + JSON + HTML when they hold.

**If a previous version of the XER carries hard constraints on anchor tasks**, that's a Phase 1 hygiene issue: run `python scheduling/tools/anchors_from_constraints.py "<project>"` once to lift CS_MSO / CS_FNLT / CS_MANDSTART / CS_MANDFIN / CS_MEOB / CS_MFO into `proposal-anchors.json` and emit a sibling `-v{N+1}.xer` with the constraint fields cleared. Westland's anchor-via-logic rule -- the new XER carries no anchor constraints; the bid dates live in `proposal-anchors.json` and are enforced by `proposal_iterate.py` on every iteration. Note the cleanup in the iteration log.

### Postmortem on final approval

When Camron approves the schedule ("this is good, generate the XER"), Claude writes a self-reflection artifact **before** producing the final XER. This is one postmortem per proposal cycle (proposals ship once at GMP), date-stamped so a future aggregator can weight newer postmortems more heavily.

**Path:** `<project-folder>/Proposal Schedule/feedback/postmortem-{YYYY-MM-DD}-{project-slug}.md`

- Date prefix -> sortable chronologically across projects.
- Project slug in filename -> vault-wide grep finds all postmortems on the same project type.
- `feedback/` subfolder -> separates postmortems from the iteration artifacts.

**Source data:**
- `iterations/paste-*.json` (the per-iteration paste-back archive that `proposal_iterate.py` writes on every successful apply -- this is the durable record of every change Camron asked for, in order).
- The v1 XER (Westland's immutability rule preserves it).
- The final v{N} XER.
- Session memory if the agent is the same one that drafted v1; otherwise reconstruct from the paste archive.

**Sections (write all six):**

```markdown
---
project: "Murray City Apex Center"
project_type: "office-tenant-improvement"   # informal taxonomy, freeform
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

## Themes within this project
Patterns that recurred across multiple corrections in this single cycle. Caveat: still hypotheses, not rules.

## Hypotheses for next time
Numbered, first-person AI voice, scoped to project type. Format that future-me can load as prompt context. Explicitly NOT rules -- rules emerge from aggregation across many postmortems.
```

**Constraints:**

1. **No rules from a single postmortem.** Each is observation + hypothesis. Promotion to rules happens later, at aggregation time across N postmortems.
2. **One postmortem per proposal cycle.** Generally one per project. Don't overwrite an existing postmortem; if one exists for the same project + date, append a `-2` suffix.
3. **Write the postmortem BEFORE producing the final XER.** Iteration history is freshest in memory at approval time.

**Out of scope here** (Camron will revise the SKILL when these become real): reader / aggregator that pulls past postmortems into Phase-1 of the next proposal draft, decay function for temporal weighting, project-type filter / scoping logic, synthesized ruleset format for prompt injection, cross-project pattern miner. Until those exist, postmortems sit on disk waiting for the corpus to grow.

## Phase 7: Score & Iterate

**Letter grade targets are ranges, not floors.** If the user asks for "at least an A", treat the lower bound of that letter (A- = 90) as the stopping point. Confirm at that threshold and only push higher if the user explicitly accepts the trade-off:

> *"I can get you to 93 but only by adding 100+ soft constraints; the A- at 90.5 is cleaner. Which do you want?"*

A 90.5 (A-) with honest logic beats a 95.0 (A) propped up by bulk soft constraints. The Westland procedures doc is explicit: "teams must resist the temptation to then assume the schedule is accurate. It may be a great outline, but without real input from trade partners, suppliers, design teams, owners, etc. the schedule will not be a true reflection of how the work will progress." A reviewer who opens a proposal with 140 CS_FNLT constraints reads it as dishonest — which is how Westland loses a job, not wins one.

### How to iterate — targeted, not full-rescore

**Run the full score ONCE** (`score_schedule.py <xer>`) to identify which metrics are failing. After that, query individual checks via the toolbox's `quality_checks.py <check_name> <xer>` CLI to get the specific failing activities as JSON — no rescoring the whole schedule per fix. Each check returns `task_code`, `task_name`, and `issues[]` for every offender. Examples:

```
python quality_checks.py dangling <xer>
python quality_checks.py missing_logic <xer>
python quality_checks.py high_float <xer>
python quality_checks.py soft_constraints <xer>
python quality_checks.py out_of_sequence <xer>
```

Fix what that check surfaces, then query the next failing check. Rescore with `score_schedule.py` at most once per major iteration to confirm progress — not after every edit.

### The two buckets — never mix in one iteration

Classify each failing metric into ONE bucket and fix each in a separate iteration:

**Bucket 1 — Real-logic fixes (always allowed)**
- Add genuinely missing logic ties (from `missing_logic` and `dangling` check results)
- Tighten FS→SS/FF where parallel work is real and documented in the sample
- Remove redundant ties (`duplicate_rels` check)
- Fix wrong predecessors (`out_of_sequence`)
- Correct calendar assignments

**Bucket 2 — Rubric-adjusting moves (STOP and ask before applying)**
- Bulk CS_FNLT / CS_FNET to pin late dates against the float deduction
- Bulk CS_MEOA / CS_MEOB on milestones with no contract or physical basis
- Adding milestones solely to shorten the longest path
- Closing open-ends with nonsense terminal ties

Hard cap: no more than 5 soft constraints added in a single iteration without user consent. Any bulk pass must be a separate, user-approved iteration, not mixed in with real-logic fixes.

### Before closing dangling activities — classify first

Dangling activities are not all the same bug, and the wrong close is worse than leaving it open. Build the classification from `quality_checks.py dangling <xer>` and choose the close per-category:

- **Procurement chain (fabricate → deliver)** → tie the delivery activity to its **installation activity** (the trade activity that consumes the material). Procurement should not dangle, but it also should not be artificially tied to Construction Clean or any unrelated milestone. The correct successor is whichever activity physically uses the material.

  **Guard rail:** before accepting a procurement → installation tie as final, check whether that procurement chain is the sole driver of the first phase of the schedule. A 12-month lead time must not be the first 12 months of an 18-month project — that would mean no parallel work is happening during procurement, which is never true. If procurement is solo-driving: look for the parallel work that should be running alongside (preconstruction activities, early trade prequal, site prep, design milestones for CM/GC, mobilization, early-release site packages) and wire those in. Procurement is one stream of many, not the spine.

  In the sample schedule, long-leads may intentionally dangle to save modeling time for a proposal package; do not copy that pattern into the output without giving each procurement chain its real installation successor.

- **Intermediate activity missing a successor** → real logic bug. Close with the correct downstream activity (not a sweeping FS+0 to a terminal milestone).
- **Terminal-looking activity** (final inspections, survey, closeout) → confirm it genuinely ends the project before tying to a milestone.

Ask for user confirmation on the classification table before mass-closing.

### Stopping rule

After TWO iterations of real-logic fixes, if still below the lower-bound target:
1. Stop iterating.
2. Produce a narrative note documenting remaining deductions as structural to the schedule approach (e.g., *"SS% is 19% because this is a compressed fast-track; defensible in narrative"*).
3. Deliver the current schedule + the note for the proposal package.

Letter grade is a floor, not a target to maximize. Present the final quality report, the narrative note (if any), and XER file location when complete.

---

## After the Project: Lessons Learned Loop

When this skill is used on a real proposal and the human-submitted version diverges meaningfully from Claude's output, write a `Lessons Learned - <Project>.md` next to the Claude output in the `Proposal Schedule/` folder. Order divergences by severity; each section captures *what the scheduler did*, *what Claude did*, *why it matters*, and *proposed skill gap and fix*. Feed that doc back into a skill-improvement session to produce the next version. See the repo-root `CLAUDE.md` ("Continuous Improvement Loop") for the standing process, and `~Proposal Schedules/Spanish Fork Jr High/Proposal Schedule/Lessons Learned - SFJHS Proposal Schedule.md` as the template. This skill exists today because that loop ran once — keep running it.

---

## Reference Files

| File | When to Load |
|------|-------------|
| `references/wbs-patterns.md` | WBS pattern selection (A/B/C) — load in Phase 2/3 when deciding top-level structure |
| `references/westland-procedures-summary.md` | Distilled Westland procedure for proposal schedules — load in Phase 2 before recommendations |
| `references/westland-procedures.md` | Full Westland procedures text — load only when the summary doesn't answer the question |
| `references/site-logistics-examples/` | Lubumbashi & Querétaro site logistics workflow PNGs — reference for what a good plan looks like |
| `references/generate_proposal_schedule_pdf.py` | Westland-branded PDF generator — load when generating the plan document |
| `references/sample_data.json` | Schema template showing all required JSON keys for the PDF generator |
| `references/xer-analysis-code.md` | Python functions for extracting schedule profiles from sample XERs |
| `references/plan-document-template.md` | Full 14-section plan document template — content reference for what goes in the PDF |
| `examples/iterate.py` | Worked Python for the iteration loop -- copy and adapt only when `proposal_iterate.py` cannot do the job |

## Iteration tools (Phase 6+)

| Tool | When to use |
|------|-------------|
| `tools/proposal_iterate.py` | Every paste-back. Applies `duration_change` items, runs CPM, checks anchors, writes -v{N+1}.xer + JSON + HTML, archives the paste-back. Exit 0 on success, 2 on anchor slip. |
| `tools/show_paths.py` | Re-orient before proposing a change. Reads `schedule-activities.json` only -- no XER parse, no CPM. |
| `tools/show_anchors.py` | Re-check anchor status without running an iteration. Reads `proposal-anchors.json` + `schedule-activities.json`. |
| `tools/anchors_from_constraints.py` | One-shot bootstrap on a project that still carries CS_MSO / CS_FNLT / CS_MANDSTART / CS_MANDFIN / CS_MEOB / CS_MFO on anchor tasks. Lifts those into `proposal-anchors.json` and emits a sibling -v{N+1}.xer with the constraint fields cleared. |

