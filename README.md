# Construction Skills

Claude Code skills for construction workflows.

## Installation

Browse available plugins and install the ones you need:

```
/plugin marketplace add CamronWalker/construction-skills
/plugin install scheduling@construction-skills
/plugin install preconstruction@construction-skills
/plugin install construction@construction-skills
/plugin install safety@construction-skills
```

## Skills

### Schedule

- **schedule-project-init** — Initialize a project's Schedules folder with persistent project configuration (SmartPM URLs, recipients, signer, attachments, graph selection). Creates `project-context.md` at the Schedules root. Re-run to update any field.
- **schedule-toolbox** — P6 XER operations: parse, analyze, score quality (31 checks), update review, trade activities, SC coverage, path analysis, schedule comparison, and XER generation. Also covers Westland standards, DCMA best practices, and CPM recalculation. Core tool for all schedule analytics.
- **schedule-create-proposal-schedule** — Create a construction proposal schedule plan through a structured Q&A session using sample schedules and bid documents. Generates plan PDF and XER.
- **schedule-update** — Full weekly schedule update pipeline: folder setup, SmartPM screenshot capture, email draft generation, and Outlook draft creation.
- **schedule-update-report** (TODO) — Generate schedule narrative reports from XER data — weekly update narratives, critical path discussion, and milestone summaries.
- **schedule-delay-analysis** (TODO) — Analyze schedule versions to identify and document delays, compare baselines, and draft time impact analyses.

### Preconstruction

Business development, estimating, and proposals — the teams that share Buildr.

- **buildr-toolbox** — Companion skill for the remote Buildr MCP connector. Routes Buildr's read/write tools and ships four report recipes: win/loss reporting, workforce availability, pipeline/pursuit snapshot, and account 360. Read-and-report first; writes are fenced and confirm-gated.
- **estimating-bid-docs-review** (TODO) — Review bid documents for completeness — flag missing drawings, specs, addenda, or conflicting information before bid day.
- **estimating-scope-gap-review** (TODO) — Analyze scopes across trades to identify gaps, overlaps, and ambiguous responsibility areas between subcontractor proposals.
- **estimating-bid-leveling** (TODO) — Level and compare subcontractor bids side-by-side — normalize inclusions/exclusions, flag qualifications, and highlight pricing outliers.
- **estimating-spec-assignments** (TODO) — Read the project specs and generate a summary of which spec sections each subcontractor is carrying.

### Construction

Construction-phase skills — Procore-native workflows plus a Procore MCP toolkit. Merges the former **project-management** and **site-operations** plugins. Every Procore write is two-stage (dry-run preview → confirm).

- **construction-procore-toolbox** — The Procore MCP toolkit and dispatcher: how to read/write Procore, project resolution, pagination, the two-stage write contract, the raw endpoint escape hatch, and which skill owns which workflow. The anchor for everything below.
- **construction-daily-log-review** — Review and grade a project's daily logs over a window: the Procore quality chart, a thoroughness scorecard, and an Executive Insights narrative of the month plus growth areas.
- **construction-project-pulse** — 30-second project-health snapshot from Procore's executive widgets — open/overdue RFIs, submittal aging, and turnaround vs. target.
- **construction-rfi-followup** — Drill overdue RFIs by ball-in-court and draft chase nudges (or suggest what to draft).
- **construction-submittal-followup** — Drill overdue/pending submittals by ball-in-court — sorted by need-by/lead-time risk — and draft chase nudges.
- **construction-daily-log-entry** — Draft and post manpower / call / photo daily-log entries; optional scheduled-vs-actual read.
- **construction-email-to-log** — Turn important recent emails into Procore call-log entries on the right day (call-log capture; no inbox forwarding).
- **construction-observations-import** — Batch-import observations from an architect/engineer/commissioning report — reasoned type and location per item, deduped against existing.
- **construction-submittal-review** — Review submittals against spec requirements — compliance table plus draft review comments.
- **construction-rfi-writing** — Guide RFI writing through an interactive Q&A process — searches project documents first (no RFI is the best RFI), then builds a clear, actionable RFI. Optional direct create in Procore.
- **construction-change-event** — Analyze incoming change events (PRs, CCDs, ASIs, bulletins) and distribute scope to affected subcontractors. Optional direct create in Procore.
- **construction-closeout-status-dashboard** — Build and update interactive HTML closeout status dashboards from Excel trackers or Procore submittal-log exports.
- **construction-submittal-requirements** (TODO) — Read the specs and generate a trade-specific submittal requirements list with section references for subs to check off.
- **construction-subcontractor-spec-reader** (TODO) — Parse contract specs for a specific subcontractor and produce their custom checklist — obligations, hold points, testing requirements, closeout docs.
- **construction-change-order-docs** (TODO) — Help document and justify change orders — draft cover letters, organize backup, reference contract provisions.

### Safety

- **safety-toolbox-talk** (TODO) — Generate toolbox talk documents tailored to the current work activities — topic overview, key hazards, required PPE, and discussion points.
- **safety-jsa-jha** (TODO) — Create Job Safety Analysis / Job Hazard Analysis documents — break tasks into steps, identify hazards, and define controls for each step.
- **safety-orientation-checklist** (TODO) — Generate site-specific safety orientation checklists for new workers — covering site rules, emergency procedures, hazard areas, and required training.
- **safety-incident-report** (TODO) — Assist with incident report writing — structured narrative, root cause analysis prompts, corrective actions, and follow-up tracking.
