# Westland Construction Skills

Claude Code skills for Westland Construction workflows.

## Installation

```
/plugin marketplace add CamronWalker/westland-skills
/plugin install westland@westland-skills
```

## Skills

- **schedule-best-practices** — Guide for building and maintaining construction schedules that score well on DCMA, GAO, and AACE best practice metrics.
- **schedule-create-proposal-schedule** — Create a construction proposal schedule plan through a structured Q&A session using sample schedules and bid documents.
- **schedule-quality-score** — Score a Primavera P6 schedule against industry best practice metrics and output a quality report with a letter grade, scored metrics, and key findings.
- **schedule-xer-generate** — Generate new Primavera P6 XER schedule files from scratch using similar project schedules and a proposal/scope document.
- **schedule-xer-read-modify** — Read, parse, analyze, and modify existing Primavera P6 XER schedule files.

### Schedule

- **schedule-update** (TODO) — Import actual start/finish dates and revised durations into an XER file. Feed it a spreadsheet or list of updates and get back the updated schedule.
- **schedule-narrative** (TODO) — Generate schedule narrative reports from XER data — monthly update narratives, critical path discussion, and milestone summaries.
- **schedule-delay-analysis** (TODO) — Analyze schedule versions to identify and document delays, compare baselines, and draft time impact analyses.

### Estimating

- **estimating-bid-docs-review** (TODO) — Review bid documents for completeness — flag missing drawings, specs, addenda, or conflicting information before bid day.
- **estimating-scope-gap-review** (TODO) — Analyze scopes across trades to identify gaps, overlaps, and ambiguous responsibility areas between subcontractor proposals.
- **estimating-bid-leveling** (TODO) — Level and compare subcontractor bids side-by-side — normalize inclusions/exclusions, flag qualifications, and highlight pricing outliers.

### Project Management

- **pm-submittal-review** (TODO) — Review product data submittals against spec requirements — check compliance, flag deviations, and draft review comments.
- **pm-submittal-requirements** (TODO) — Read the specs and generate a trade-specific submittal requirements list with section references for subs to check off.
- **pm-subcontractor-spec-reader** (TODO) — Parse contract specs for a specific subcontractor and produce their custom checklist — obligations, hold points, testing requirements, closeout docs.
- **pm-subcontractor-spec-assignments** (TODO) — Read the project specs and generate a summary of which spec sections each subcontractor is carrying.
- **pm-meeting-minutes** (TODO) — Generate structured OAC meeting minutes from rough notes — action items, decisions, open issues, attendees.
- **pm-change-order-docs** (TODO) — Help document and justify change orders — draft cover letters, organize backup, reference contract provisions.

### Site / Field

- **site-rfi-writing** (TODO) — Guide RFI writing with proper formatting, spec references, and suggested resolution language. Helps craft clear, actionable RFIs.
- **site-daily-log** (TODO) — Assist with daily log entries — manpower, equipment, work performed, delays, and a scheduled-vs-actual work analysis. Optional Procore MCP integration for direct posting.
