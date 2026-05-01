# Phase 1-6: Drafting a Proposal Schedule

Load this file when starting a new proposal from bid documents and sample
XERs. Covers gather inputs, parse + analyze, recommend structure, ask
targeted questions, generate the plan PDF, and generate the v1 XER.

For iteration on a draft (paste-back from the Gantt review HTML), load
`phases/02-iterate.md` instead -- not this file.

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

### Pull past-project hypotheses (if any)

Run the postmortem aggregator to surface lessons from prior proposal
cycles. With zero postmortems available it returns a friendly skip
message; with a corpus, it ranks recency-weighted hypotheses by project
type so they inform Phase 3 recommendations.

```bash
python scheduling/tools/postmortem_aggregate.py [--project-type "<type>"]
```

Read the output before generating recommendations; cite a hypothesis
explicitly if you act on it ("postmortem 2026-04 from Spanish Fork
flagged Pour -> Place; using Place here").

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

## Phase 5: Generate XER (v1)

After the recommendations and answers are locked in, generate the v1 XER directly from the plan structure:

1. Use the `schedule-toolbox` skill to generate the XER file
2. Pass the plan structure (WBS, activities, durations, logic) as scope + sample XERs as reference schedules
3. Apply all Westland standards during generation (from `schedule-toolbox`)
4. Convert all durations from working days to hours (days x 8 for XER)
5. Save to `<project-folder>/Proposal Schedule/[Project Name] -v1.xer`

The plan PDF is **NOT** generated yet. The PDF gets built at the end (after iteration + scoring + approval) so it reflects the final schedule, not the v1 draft. See `phases/02-iterate.md` § "Generate the Plan PDF (post-approval)" for the trigger.

After v1 is written, render the Gantt review HTML and start iterating -- load `phases/02-iterate.md` from that point on.
