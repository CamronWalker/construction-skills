---
name: schedule-create-proposal-schedule
description: >
  Create a construction proposal schedule plan by analyzing bid documents and sample XER files,
  then generate the XER file. Use this skill whenever the user wants to "plan a proposal schedule",
  "create a schedule plan", "build a bid schedule", "proposal schedule", "I have some similar
  schedules and a bid package", "help me plan out this schedule", "schedule plan from bid docs",
  or wants to create a new schedule from bid documents and sample schedules. This skill reads the
  documents first, makes smart recommendations using Westland standards, and only asks about things
  the documents don't answer. Output feeds into the schedule-xer skill for XER generation.
---

# Proposal Schedule Planning

This skill creates a proposal schedule by analyzing bid documents and sample XER files. It reads the documents, proposes a schedule structure using Westland standards, asks only what the documents don't answer, then generates the plan document and XER file.

## Workflow

1. **Gather Inputs** — Collect project folder with bid docs and sample XERs
2. **Auto-Parse & Analyze** — Parse XERs and read bid docs to extract all knowable information
3. **Present Recommendations** — Propose complete schedule structure based on findings
4. **Ask 2-3 Targeted Questions** — Only what the documents don't answer
5. **Generate Plan Document** — Save to project folder
6. **Generate XER** — Via `schedule-xer` skill
7. **Score & Iterate** — Via `schedule-standards` skill until A grade achieved

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
For each XER, parse using the `schedule-xer` skill and extract a profile. Read `references/xer-analysis-code.md` for the extraction functions. Extract: WBS structure, activity counts, duration stats, relationship types, milestones, naming patterns, calendars.

### Read Bid Documents
Extract into structured categories:
- Project name, location, type
- Contract duration / substantial completion date
- Required milestones and interim deadlines
- Phasing requirements
- Liquidated damages amounts and triggers
- Schedule specification requirements (update frequency, format, detail level)
- Scope summary by major division or area
- Special conditions (occupied building, phased turnover, seasonal restrictions)

### Present Analysis Summary
Show the user: sample schedule profiles side by side + bid document findings.

## Phase 3: Smart Recommendations

Based on the analysis, propose a **complete schedule structure** using Westland standards as the default for all style/format decisions. The skill determines from the documents:

- **WBS structure** — Westland standard from `schedule-standards`, adapted to project scope (e.g., add Demo phase above Construction if demolition is required before construction starts)
- **Activity list and durations** — From sample XER analysis, scaled to project scope
- **Milestone strategy** — Contract milestones + Westland 30-day rule
- **Construction sequence/flow** — From sample schedule patterns and bid doc scope
- **Procurement items** — From specs + sample schedule procurement activities
- **Calendar** — From contract requirements (5-day/6-day/7-day)
- **Logic network** — Based on sample schedule patterns

**Do NOT ask about:** WBS format, naming conventions, milestone frequency, formatting, branding, responsibility codes, relationship type targets, SmartPM integration. These are all answered by Westland standards.

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
1. Use the `schedule-xer` skill to generate the XER file from the plan
2. Pass the plan document as scope input + sample XERs as reference schedules
3. Apply all Westland standards during generation (from `schedule-standards`)
4. Convert all durations from working days (plan) to hours (days x 8 for XER)
5. Save to `<project-folder>/Proposal Schedule/[Project Name].xer`

## Phase 7: Score & Iterate

Score the generated XER using the `schedule-standards` skill. Target: **A grade (90+)**.

If below A:
1. Identify failing metrics from the `details` dict (contains every flagged activity with `task_code`)
2. Apply automatic fixes where possible (add missing logic, convert relationship types, tighten network)
3. Ask user follow-up only for fixes that require judgment (e.g., "Is this high float intentional buffer?")
4. Regenerate and re-score. Maximum 3 iterations.
5. Never sacrifice schedule accuracy for score — document accepted deviations.

Present the final quality report and XER file location when complete.

---

## Reference Files

| File | When to Load |
|------|-------------|
| `references/generate_proposal_schedule_pdf.py` | Westland-branded PDF generator — load when generating the plan document |
| `references/sample_data.json` | Schema template showing all required JSON keys for the PDF generator |
| `references/xer-analysis-code.md` | Python functions for extracting schedule profiles from sample XERs |
| `references/plan-document-template.md` | Full 14-section plan document template — content reference for what goes in the PDF |

