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

### Capture project metadata up front

Before any analysis runs, record what kind of project this is so future
postmortems and duration-knowledge entries inherit the context:

```bash
python scheduling/tools/propsched.py metadata set "<project>" \
    --project-type k-12 \
    --region "Utah Valley" \
    --square-footage 65000 \
    --building-systems structural-masonry,steel-joist \
    --difficulty medium
```

If you only know some fields, set what you know -- you can revise later
via `propsched metadata set` (it merges).

### Pull past-project hypotheses (if any)

Run the postmortem aggregator filtered by THIS project's metadata so the
hypotheses surfaced come from comparable past cycles -- a K-12 in Utah
Valley with structural masonry should learn from prior K-12s, not from
a tilt-up warehouse:

```bash
python scheduling/tools/propsched.py aggregate-postmortems \
    --project-type "<type>" --region "<region>" --system "<building-system>" \
    --show-durations
```

With zero postmortems available it returns a friendly skip message;
with a corpus, it ranks recency-weighted hypotheses by project metadata
match so they inform Phase 3 recommendations. `--show-durations` also
surfaces per-activity duration knowledge captured in past cycles.

Read the output before generating recommendations; cite a hypothesis
explicitly if you act on it ("postmortem 2026-04 from Spanish Fork
flagged Pour -> Place; using Place here").

### Query duration knowledge for headline activities

For the activities you know will dominate the critical path (foundations,
structure, weather-dependent work), query the duration DB before picking
durations:

```bash
python scheduling/tools/propsched.py durations query \
    --root "<proposals-root>" --task "Pour Footings" \
    --type "<project-type>" --region "<region>"
```

Output groups observations by task with min/max/avg + project context.
Use it as a Westland-internal benchmark, not as a rule.

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

After the recommendations and answers are locked in, generate the v1 XER using the two-tool compositional flow:

### Step 1 — Instantiate the skeleton

Call `create_xer_from_template("westland-skeleton-v1", metadata)` where `metadata` is:

```json
{
  "project_name":        "<Project Name>",
  "project_id":          "<Job Number>",
  "planned_start":       "YYYY-MM-DD",
  "planned_data_date":   "YYYY-MM-DD",
  "task_code_prefix":    "A"
}
```

`task_code_prefix` is optional (defaults to `"A"`). Use the prefix confirmed with the user in Phase 3. The call writes an intermediate skeleton XER and returns:

- `output_path` — the skeleton file to pass to the next step
- `ntp_milestone` — task_id of the MILESTONE-NTP activity
- `sc_milestone` — task_id of the MILESTONE-SC activity
- `validation` — a brief structural check; review before continuing

Capture `ntp_milestone` and `sc_milestone`. You will wire logic to both when you build the change set.

### Step 2 — Build the change-record list

Construct the full list of changes that turns the skeleton into the project-specific schedule. The complete change-type catalog is in `schedule-toolbox/references/xer-modify.md`; refer to it for field shapes. Apply changes in this order within the list — `apply_xer_changes` resolves references in-pass, so order matters:

**2a. `add_wbs` records for the selected WBS pattern**

The skeleton already contains the standard top-level tree (SUMMARY & MILESTONES, PRE-CONSTRUCTION with DESIGN subtree, PROCUREMENT, CONSTRUCTION with SITEWORK/STRUCTURE/ENCLOSURE/INTERIOR subtree, COMMISSIONING & CLOSE-OUT). The pattern adds only what the skeleton does not have — DEMOLITION, FINAL SITEWORK, and phase branches as applicable. See `references/wbs-patterns.md` § "MCP change records for this pattern" for the exact `add_wbs` record sets per pattern.

Use a dry run to capture new `wbs_id` values before building the full call (see the wbs-patterns reference for the recommended approach). All `add_wbs` records must appear before any `add_activity` records that reference the new WBS nodes.

**2b. `add_activity` records for every activity**

One record per activity with the full spec:

```json
{
  "type": "add_activity",
  "spec": {
    "code":          "A1010",
    "name":          "Mobilization",
    "duration_days": 5,
    "calendar_id":   "CAL-5DAY",
    "wbs_id":        "<wbs_id from skeleton or add_wbs result>",
    "activity_type": "TT_Task"
  }
}
```

Duration unit: convert all working days to hours in the XER (days x 8). Supply `duration_days` to the tool — the tool handles the conversion internally.

Milestones already exist in the skeleton (NTP, SC). Wire them via `add_logic` in step 2c rather than creating new milestone activities.

**2c. `add_logic` records for the logic network**

One record per relationship edge (FS/SS/FF/SF with lags in days). Include:
- Logic from the first activity into `ntp_milestone`
- Logic from the last critical activity into `sc_milestone`
- All internal logic derived from the construction sequence

### Step 3 — Apply all changes in one bulk call

```python
apply_xer_changes(
    xer_path    = skeleton_output_path,   # from Step 1
    changes     = [...],                  # full ordered list from Step 2
    output_path = "<Project Name>.xer",
    dry_run     = False,
    strict      = True
)
```

One call. The tool writes a new file — it never overwrites the skeleton. `strict=True` causes the call to fail on any unresolvable reference rather than silently skipping changes; leave it on so problems surface immediately.

### Step 4 — Validate before showing the user

Call `validate_xer_structure(output_path)` and confirm `import_ready: true`. If validation fails, review the per-change feedback from `apply_xer_changes` (each change record returns a `result` block) to locate the first unresolved reference or rejected field, fix the change list, and re-run from Step 3.

### Step 5 — Save location

- **v4.0.0+ layout:** `<project>/<Project Name>.xer` at the project root.
- **Legacy layout** (project has a `Proposal Schedule/` subfolder): `<project>/Proposal Schedule/<Project Name> -v1.xer`.

The plan PDF is **NOT** generated yet. The PDF gets built at the end (after iteration + scoring + approval) so it reflects the final schedule, not the v1 draft. See `phases/02-iterate.md` § "Generate the Plan PDF (post-approval)" for the trigger.

After v1 is written, render the Gantt review HTML and start iterating -- load `phases/02-iterate.md` from that point on.
