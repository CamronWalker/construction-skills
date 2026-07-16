---
name: construction-project-pulse
description: >
  A 30-second Procore health snapshot for a project — open and overdue RFIs, submittal aging,
  and RFI/submittal turnaround against target — pulled from Procore's executive widgets and
  synthesized into a short read. Use when someone asks "how's [project] doing", "project pulse",
  "project health", "give me a status snapshot", "are RFIs/submittals piling up", "are we slow
  on responses", "who's sitting on responses", "turnaround", or wants a quick executive read on
  a project's open-items health. For chasing specific overdue items or drafting nudges, this hands
  off to construction-rfi-followup / construction-submittal-followup.
---

# Construction Project Pulse

A fast, executive read on a project's open-items health, built from Procore's purpose-made widgets. Renders the widgets inline and adds a tight narrative on top — the kind of read a PM or director wants in half a minute.

> Reads through the Procore MCP. See `construction-procore-toolbox` for project resolution and the tool surface.

## When to use

- "How's the project tracking?" / "project pulse" / "status snapshot"
- "Are RFIs or submittals backing up?" / "who's sitting on responses?"
- "Is our turnaround slipping?"

When the user wants to *act* on the overdue items (chase them, draft nudges), hand off to `construction-rfi-followup` (RFIs) or `construction-submittal-followup` (submittals).

## Workflow

1. **Resolve the project** — `find_project` → confirm the match → `projectId`.
2. **Pull the widgets.** Call, in one batch:
   - `project_rfi_snapshot(projectId)` — open RFIs, past-due count, aging breakdown, ball-in-court.
   - `project_submittal_snapshot(projectId)` — same shape for submittals.
   - `project_response_times(projectId)` — RFI and submittal turnaround gauges vs. target (last 90 days).
   - Offer `project_daily_log_quality(projectId)` too if they want field-documentation health in the same read (or point them to `construction-daily-log-review` for the deep version).
   Each renders its own inline widget and returns a text summary — the widgets are the visual, the summaries feed your narrative.
3. **Synthesize a short read.** Three to five sentences over the widgets: the headline (healthy / watch / problem), the one or two numbers that matter most (e.g. "9 open RFIs, 3 past due, oldest 21 days on the architect"), and the single biggest lever. Concrete numbers only — no filler.
4. **Offer the next step.** If anything is overdue, offer the matching follow-up skill: "3 RFIs are past due on the architect — want me to draft nudges? (construction-rfi-followup)".

## Quick reference

| Want | Tool |
|------|------|
| Open/overdue RFIs + ball-in-court | `project_rfi_snapshot` |
| Open/overdue submittals + aging | `project_submittal_snapshot` |
| RFI/submittal turnaround vs. target | `project_response_times` |
| Daily-log documentation health | `project_daily_log_quality` (or `construction-daily-log-review`) |

The snapshot tools cache ~1 hour; pass `fresh: true` on `project_response_times` only when you specifically need a recompute.

## Common mistakes

- **Dumping the widgets with no narrative.** The value is the 30-second read on top — always synthesize.
- **Guessing the project.** `find_project` and confirm first.
- **Over-reaching into action.** Pulse is read-only; route chasing/drafting to the follow-up skills rather than drafting emails here.

**Voice:** see `westland-house-style` — lead with the headline, state numbers plainly, no hedging.
